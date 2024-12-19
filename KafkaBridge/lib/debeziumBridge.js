/**
* Copyright (c) 2022 Intel Corporation
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*    http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/
'use strict';
const Logger = require('./logger.js');
const _ = require('underscore');

module.exports = function DebeziumBridge (conf) {
  const config = conf;
  const logger = new Logger(config);
  const syncOnAttribute = config.bridgeCommon.kafkaSyncOnAttribute;

  /**
   *
   * @param {object} body - object from stateUpdate
   *
   * body should be in debezium format:
   *  before: entity before
   *  after: entity after
   */
  this.parse = function (body) {
    let result = null;
    if (body === null || body === undefined) {
      return result;
    }
    const before = this.parseBeforeAfterEntity(body.before);
    const beforeEntity = before.entity;
    const beforeAttrs = before.attributes;
    const after = this.parseBeforeAfterEntity(body.after);
    const afterEntity = after.entity;
    const afterAttrs = after.attributes;
    const isEntityUpdated = this.diffEntity(beforeEntity, afterEntity);
    const { insertedAttrs, updatedAttrs, deletedAttrs } = this.diffAttributes(beforeAttrs, afterAttrs);
    const isKafkaUpdate = (updatedAttrs[syncOnAttribute] !== undefined ||
      insertedAttrs[syncOnAttribute] !== undefined) && body.before != null; // There is one important exception:
    // When body.before is null, it means that the whole entity is created.
    // This is unlikely happening over default Kafka update. Even if it is a Kafka update
    // the next iteration will be an update with body.before != null so the loop will be detected.
    // when syncOnAttribute is used, it means that update
    // did not come through API but through Kafka channel
    // so do not forward to avoid 'infinity' loop

    delete deletedAttrs[syncOnAttribute]; // this attribute is only used to detect API vs Kafka inputs
    delete updatedAttrs[syncOnAttribute]; // remove it before detecting changes
    delete insertedAttrs[syncOnAttribute]; // remove it before detecting changes
    delete afterEntity[syncOnAttribute];
    // isAttributesChanged: When there are changes in any of the attrs (not coming over Kafka)
    const isAttributesChanged = !isKafkaUpdate && (Object.keys(updatedAttrs).length > 0 ||
      Object.keys(deletedAttrs).length > 0 || Object.keys(insertedAttrs).length > 0);
    // deletedEntity needs to remember type so that it can be deleted for
    // all subtypes. However, type must be removed lated since it is not part of
    // primary key. Deletion means to set type to null
    let deletedEntity = null;
    if (isEntityUpdated && Object.keys(afterEntity).length === 0) {
      deletedEntity = beforeEntity;
      // Type will be removed later to signal deletion
    }
    if (isEntityUpdated || isAttributesChanged) {
      result = {
        entity: isEntityUpdated || isAttributesChanged ? afterEntity : null,
        deletedEntity: deletedEntity,
        updatedAttrs: isAttributesChanged ? updatedAttrs : null,
        deletedAttrs: isAttributesChanged ? deletedAttrs : null,
        insertedAttrs: isAttributesChanged ? insertedAttrs : null
      };
    }
    return result;
  };

  /**
   * Provide entitiy and attributes separated, prepared for StreamingSQL
   * @param {object} ba - before/after object from Debezium
   *
   */
  this.parseBeforeAfterEntity = function (ba) {
    let baEntity = {};
    const baAttrs = {};
    if (ba === null || ba === undefined) {
      return { entity: {}, attributes: {} };
    }

    try {
      baEntity = JSON.parse(ba.entity);
      // Delete all non-properties as defined by ETSI SPEC (ETSI GS CIM 009 V1.5.1 (2021-11))
      delete baEntity['@id'];
      delete baEntity['@type'];
      delete baEntity['https://uri.etsi.org/ngsi-ld/createdAt'];
      delete baEntity['https://uri.etsi.org/ngsi-ld/modifiedAt'];
      delete baEntity['https://uri.etsi.org/ngsi-ld/obvervedAt'];
      baEntity.id = ba.id;
      baEntity.type = ba.e_types[0];
    } catch (e) { logger.error(`Cannot parse debezium before field ${e}`); return; } // not throwing an error due to the fact that it cannot be fixed in next try

    // create entity table
    let id = baEntity.id;
    const resEntity = {};
    // Object.keys(baEntity).filter(key => key !== 'type' && key !== 'id')
    //   .forEach(key => {
    //     resEntity[key] = id + '\\' + key;
    //   });
    resEntity.id = baEntity.id;
    resEntity.type = baEntity.type;
    delete resEntity[syncOnAttribute]; // this attribute should not change the diff calculation, but should be in attributes to detect changes from Kafka

    // create attribute table
    id = baEntity.id;
    Object.keys(baEntity).filter(key => key !== 'type' && key !== 'id').forEach(
      key => {
        const refId = id + '\\' + key;
        let refObjArray = baEntity[key];
        if (!Array.isArray(refObjArray)) {
          refObjArray = [refObjArray];
        }
        baAttrs[key] = [];
        refObjArray.forEach((refObj, index) => {
          const obj = {};
          obj.id = refId;
          obj.entityId = id;
          obj.name = key;
          if ('https://uri.etsi.org/ngsi-ld/datasetId' in refObj) {
            obj.datasetId = refObj['https://uri.etsi.org/ngsi-ld/datasetId'][0]['@id'];
          } else {
            obj.datasetId = '@none';
          }

          // extract timestamp
          // timestamp is normally observedAt but it is non-mandatory
          // If observedAt is missing (e.g. because it was entered over REST API)
          // the modifiedAt value is taken.
          if ('https://uri.etsi.org/ngsi-ld/observedAt' in refObj) {
            obj['https://uri.etsi.org/ngsi-ld/observedAt'] = refObj['https://uri.etsi.org/ngsi-ld/observedAt'];
          } else if ('https://uri.etsi.org/ngsi-ld/modifiedAt' in refObj) {
            obj['https://uri.etsi.org/ngsi-ld/observedAt'] = refObj['https://uri.etsi.org/ngsi-ld/modifiedAt'];
          }
          if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'] !== undefined) {
            obj.type = 'https://uri.etsi.org/ngsi-ld/Property';
            // every Property is array with one element, hence [0] is no restriction
            // Property can be Literal => @value,@json or IRI => @id
            if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value'] !== undefined) {
              obj.attributeValue = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value'];
              obj.nodeType = '@value';
            } else if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@id'] !== undefined) { // Property can be IRI => @id
              obj.attributeValue = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@id'];
              obj.nodeType = '@id';
            } else if (typeof refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0] === 'object') { // no @id, no @value, must be a @json type
              obj.attributeValue = JSON.stringify(refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]);
              obj.nodeType = '@json';
            }

            if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'] !== undefined) {
              // every Property is array with one element, hence [0] is no restriction
              obj.valueType = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'];
            }
          } else if (refObj['https://uri.etsi.org/ngsi-ld/hasObject'] !== undefined) {
            obj.type = 'https://uri.etsi.org/ngsi-ld/Relationship';
            // every Relationship is array with one element, hence [0] is no restriction
            obj.attributeValue = refObj['https://uri.etsi.org/ngsi-ld/hasObject'][0]['@id'];
            obj.nodeType = '@id';
          } else {
            return;
          }
          baAttrs[key].push(obj);
        });
        // Check if datasetId is doubled
        let counter = 0;
        const copyArr = [];
        baAttrs[key].forEach((obj, idx) => {
          let check = false;
          const curDatId = obj.datasetId;
          for (let i = idx + 1; i < baAttrs[key].length; i++) {
            if (curDatId === baAttrs[key][i].datasetId) {
              check = true;
              copyArr[counter] = baAttrs[key][i];
            }
          }
          if (check === false) {
            copyArr[counter] = baAttrs[key][idx];
            counter++;
          }
        });
        copyArr.sort((a, b) => {
          if (a.datasetId === '@none') return -1;
          if (b.datasetId === '@none') return 1;
          return a.datasetId.localeCompare(b.datasetId);
        });
        copyArr.forEach((obj, idx) => { // Index it according to their sorting
          obj.index = idx;
        });
        baAttrs[key] = copyArr;
      });
    return { entity: resEntity, attributes: baAttrs };
  };

  /**
   *
   * @param {object} before - before object
   * @param {object} after - after object
   * @returns true if Entities are different
   */
  this.diffEntity = function (before, after) {
    return !_.isEqual(before, after);
  };

  /**
   * @name diffAttributes
   * @param {object} beforeAttrs - object with atrributes
   * @param {object} afterAttrs - object with attributes
   * @returns inserted, updated and deleted atributes {insertedAttrs, updatedAttrs, deletedAttrs}
    The function gets two objects, beforeAttrs and afterAttrs. The objects keys are attribute names which index an array of attribute-objects.
    The elements are uniquely identified by attribute-name and  one of the fields in the object, called
    "https://uri.etsi.org/ngsi-ld/datasetId", for instance:
   * const beforeAttrs = {
      attr1: [{
        id: 'id',
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        value: 'value',
        index: 0
      }],
      attr2: [{
        id: 'id2',
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        value: 'value3',
        'https://uri.etsi.org/ngsi-ld/datasetId': 'http://example/datasetId',
        index: 0
      }]
    }; contains two  ids (attr1, "@none") and (attr1, "http://example/datasetId'") Like in this example,
    when the datasetId is not defined at all it is equivalent of it being equal to "@none".
    The function returns
    { insertedAttrs, updatedAttrs, deletedAttrs } objects again indexed by the attr keys and containing arrays.
    insertedAttrs contains the attributes which are in the afterAttrs
    but not in beforeAttrs, updatedAttrs contains the attributes which are in the before and in the afterAttrs
    (and the respective afterAttr object is provided" and deltedAttrs are in the beforeAttrs and not in the afterAttrs.
    Additional requiements:
    - When no datasetId is given, the respective result object contains the "@none" value.
    - Deleted attributes contain only the following fields id, name, entityId, type, datasetId, index, and of this selection only the existing fields
    - When there are two objects with same attr/datasetId, take the latest in list and ignore the earlier ones
    Example afterAttrs would be:
    const afterAttrs = {
      attr1: [{
        id: 'id',
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        value: 'value2',
        'https://uri.etsi.org/ngsi-ld/datasetId': '@none',
        index: 0
      },
      {
        id: 'id4',
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        value: 'value5',
        'https://uri.etsi.org/ngsi-ld/datasetId': 'http://example/datasetId2',
        index: 0
      }]
    };
    Example result would be:
    insertedAttrs = {
      attr1: [{
        id: 'id4',
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        value: 'value5',
        'https://uri.etsi.org/ngsi-ld/datasetId': 'http://example/datasetId2',
        index: 0
      }]
    }
    updatedAttrs = {
       attr1: [{
        id: 'id',
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        value: 'value2',
        'https://uri.etsi.org/ngsi-ld/datasetId': '@none',
        index: 0
      }]
    }, deletedAttrs = {
           attr2: [{
        id: 'id2',
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        'https://uri.etsi.org/ngsi-ld/datasetId': 'http://example/datasetId',
        index: 0
      }]
    }
    Must comply with ESLint standard rules
    API: this.diffAttributes = function(..)
    No comment header
    base indentation: 2
    identation space: 2
   */
  this.diffAttributes = function (beforeAttrs, afterAttrs) {
    const insertedAttrs = {};
    const updatedAttrs = {};
    const deletedAttrs = {};

    const getDatasetId = (attrObj) =>
      attrObj.datasetId || '@none';

    const setDatasetId = (attrObj) => {
      if (!attrObj.datasetId) {
        attrObj.datasetId = '@none';
      }
      return attrObj;
    };

    const pickFields = (attrObj, fields) => {
      const result = {};
      fields.forEach((field) => {
        if (attrObj[field] !== undefined) {
          result[field] = attrObj[field];
        }
      });
      return result;
    };

    const beforeMap = new Map();
    Object.entries(beforeAttrs).forEach(([attrName, attrArray]) => {
      for (let i = attrArray.length - 1; i >= 0; i--) {
        const attrObj = attrArray[i];
        const datasetId = getDatasetId(attrObj);
        const key = `${attrName}:${datasetId}`;
        if (!beforeMap.has(key)) {
          beforeMap.set(key, { attrName, attrObj: setDatasetId(attrObj) });
        }
      }
    });

    const afterMap = new Map();
    Object.entries(afterAttrs).forEach(([attrName, attrArray]) => {
      for (let i = attrArray.length - 1; i >= 0; i--) {
        const attrObj = attrArray[i];
        const datasetId = getDatasetId(attrObj);
        const key = `${attrName}:${datasetId}`;
        if (!afterMap.has(key)) {
          afterMap.set(key, { attrName, attrObj: setDatasetId(attrObj) });
        }
      }
    });

    afterMap.forEach(({ attrName, attrObj }, key) => {
      if (beforeMap.has(key)) {
        const { attrObj: beforeAttrObj } = beforeMap.get(key);
        if (JSON.stringify(beforeAttrObj) !== JSON.stringify(attrObj)) {
          if (!updatedAttrs[attrName]) {
            updatedAttrs[attrName] = [];
          }
          updatedAttrs[attrName].push(attrObj);
        }
        beforeMap.delete(key);
      } else {
        if (!insertedAttrs[attrName]) {
          insertedAttrs[attrName] = [];
        }
        insertedAttrs[attrName].push(attrObj);
      }
    });

    beforeMap.forEach(({ attrName, attrObj }) => {
      if (!deletedAttrs[attrName]) {
        deletedAttrs[attrName] = [];
      }
      const fields = [
        'id',
        'name',
        'entityId',
        'type',
        'datasetId',
        'nodeType',
        'index'
      ];
      const deletedAttrObj = pickFields(attrObj, fields);
      deletedAttrs[attrName].push(deletedAttrObj);
    });

    return { insertedAttrs, updatedAttrs, deletedAttrs };
  };
};
