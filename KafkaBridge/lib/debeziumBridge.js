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
const utils = require('./utils.js');
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
    const collectNonDefaultAttributes = function (refObj) {
      const nonDefaultAttributes = {};
      Object.keys(refObj).forEach(subkey => {
        if (subkey !== '@type' && subkey !== '@id' && (!subkey.startsWith('https://uri.etsi.org/ngsi-ld/') || subkey.startsWith('https://uri.etsi.org/ngsi-ld/default-context'))) {
          nonDefaultAttributes[subkey] = refObj[subkey];
        }
      });
      return nonDefaultAttributes;
    };
    let baEntity = {};
    const baAttrs = {};
    if (ba === null || ba === undefined) {
      return { entity: {}, attributes: {} };
    }

    try {
      baEntity = JSON.parse(ba.entity);
      // Delete all non-properties as defined by ETSI SPEC
      delete baEntity['@id'];
      delete baEntity['@type'];
      delete baEntity['https://uri.etsi.org/ngsi-ld/createdAt'];
      delete baEntity['https://uri.etsi.org/ngsi-ld/modifiedAt'];
      delete baEntity['https://uri.etsi.org/ngsi-ld/observedAt'];
      baEntity.id = ba.id;
      baEntity.type = ba.e_types[0];
    } catch (e) {
      logger.error(`Cannot parse debezium before field ${e}`);
      return;
    }

    const parseAttributes = (obj, parentId = null) => {
      const parsedAttributes = [];
      Object.keys(obj).forEach((key) => {
        if (key === 'type' || key === 'id') return;

        let refId = (parentId || baEntity.id);
        refId += '\\' + key;

        let refObjArray = obj[key];
        if (!Array.isArray(refObjArray)) {
          refObjArray = [refObjArray];
        }

        refObjArray.forEach((refObj) => {
          const attribute = {};
          attribute.entityId = baEntity.id;
          attribute.name = key;
          if (parentId !== null) {
            attribute.parentId = parentId;
          }

          if ('https://uri.etsi.org/ngsi-ld/datasetId' in refObj) {
            attribute.datasetId = refObj['https://uri.etsi.org/ngsi-ld/datasetId'][0]['@id'];
          } else {
            attribute.datasetId = '@none';
          }
          if ('https://uri.etsi.org/ngsi-ld/unitCode' in refObj) {
            attribute.unitCode = refObj['https://uri.etsi.org/ngsi-ld/unitCode'][0]['@value'];
          }

          if ('https://uri.etsi.org/ngsi-ld/observedAt' in refObj) {
            attribute['https://uri.etsi.org/ngsi-ld/observedAt'] = refObj['https://uri.etsi.org/ngsi-ld/observedAt'];
          } else if ('https://uri.etsi.org/ngsi-ld/modifiedAt' in refObj) {
            attribute['https://uri.etsi.org/ngsi-ld/observedAt'] = refObj['https://uri.etsi.org/ngsi-ld/modifiedAt'];
          }
          if (!Array.isArray(refObj['@type'])) {
            refObj['@type'] = [refObj['@type']];
          }
          if (refObj['@type'].includes('https://uri.etsi.org/ngsi-ld/Property')) {
            if ('@type' in refObj) {
              attribute.type = refObj['@type'][0]; // Can be Property and GeoProperty
            } else {
              attribute.type = 'https://uri.etsi.org/ngsi-ld/Property';
            }
            if ('https://uri.etsi.org/ngsi-ld/hasValue' in refObj && refObj['https://uri.etsi.org/ngsi-ld/hasValue'].length > 0) {
              if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value'] !== undefined) {
                attribute.attributeValue = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value'];
                attribute.nodeType = '@value';
              } else if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@id'] !== undefined) {
                attribute.attributeValue = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@id'];
                attribute.nodeType = '@id';
              }

              if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'] !== undefined) {
                if (Array.isArray(refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'])) {
                  attribute.valueType = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'][0];
                } else {
                  attribute.valueType = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'];
                }
              }
            }
          } else if (refObj['@type'].includes('https://uri.etsi.org/ngsi-ld/GeoProperty')) {
            if ('https://uri.etsi.org/ngsi-ld/hasValue' in refObj && refObj['https://uri.etsi.org/ngsi-ld/hasValue'].length > 0) {
              const obj = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0];
              if (typeof (obj) !== 'object') {
                logger.warn(`Dropping GeoProperty attribute ${attribute.id}. It is not an object.`);
                return;
              }
              if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'] !== undefined) {
                if (Array.isArray(refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'])) {
                  attribute.valueType = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'][0];
                } else {
                  attribute.valueType = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'];
                }
              }
              attribute.attributeValue = JSON.stringify(obj);
              attribute.type = 'https://uri.etsi.org/ngsi-ld/GeoProperty';
              attribute.nodeType = '@json';
            }
          } else if (refObj['@type'].includes('https://uri.etsi.org/ngsi-ld/JsonProperty')) {
            if ('https://uri.etsi.org/ngsi-ld/hasJSON' in refObj && refObj['https://uri.etsi.org/ngsi-ld/hasJSON'].length > 0) {
              const obj = refObj['https://uri.etsi.org/ngsi-ld/hasJSON'][0]['@value'];
              if (typeof (obj) !== 'object') {
                logger.warn(`Dropping JSON attribute ${attribute.id}. It is not an object.`);
                return;
              }
              attribute.attributeValue = JSON.stringify(obj);
              attribute.type = 'https://uri.etsi.org/ngsi-ld/JsonProperty';
              attribute.nodeType = '@json';
            }
          } else if (refObj['@type'].includes('https://uri.etsi.org/ngsi-ld/ListProperty')) {
            if ('https://uri.etsi.org/ngsi-ld/hasValueList' in refObj && refObj['https://uri.etsi.org/ngsi-ld/hasValueList'].length > 0) {
              let lst = refObj['https://uri.etsi.org/ngsi-ld/hasValueList'][0]['@list'];
              if (!Array.isArray(lst)) {
                logger.warn(`Dropping list attribute ${attribute.id}. It is not a list.`);
                return;
              }
              lst = lst.map(item => item['@value']); // remove '@values' from expanded list
              attribute.attributeValue = JSON.stringify(lst);
              attribute.type = 'https://uri.etsi.org/ngsi-ld/JsonProperty';
              attribute.nodeType = '@list';
            }
          } else if (refObj['@type'].includes('https://uri.etsi.org/ngsi-ld/Relationship')) {
            if ('https://uri.etsi.org/ngsi-ld/hasObject' in refObj && refObj['https://uri.etsi.org/ngsi-ld/hasObject'].length > 0) {
              attribute.type = 'https://uri.etsi.org/ngsi-ld/Relationship';
              attribute.attributeValue = refObj['https://uri.etsi.org/ngsi-ld/hasObject'][0]['@id'];
              attribute.nodeType = '@id';
            }
          } else {
            return;
          }
          // Remove all default subproperties of refObj and continue only with non standard attributes
          const subProperties = collectNonDefaultAttributes(refObj);
          const refIdLocal = refId + '\\' + attribute.datasetId;
          attribute.id = refIdLocal;
          if (typeof subProperties === 'object' && Object.keys(subProperties).length > 0) {
            parsedAttributes.push(...parseAttributes(subProperties, refIdLocal));
          }
          if (attribute.attributeValue !== undefined) {
            // Only push attribute if it has a value
            parsedAttributes.push(attribute);
          }
        });
      });
      return parsedAttributes;
    };

    const attributesArray = parseAttributes(baEntity);
    attributesArray.forEach((attr) => {
      if (!baAttrs[attr.name]) {
        baAttrs[attr.name] = [];
      }
      baAttrs[attr.name].push(attr);
    });

    // Sort attributes by datasetId
    Object.keys(baAttrs).forEach((key) => {
      // Create a map to track the latest element by `id` and `datasetId`
      const uniqueMap = new Map();

      // Hash the longer components
      for (let i = baAttrs[key].length - 1; i >= 0; i--) {
        const item = baAttrs[key][i];

        // Hash transformation for id and parentId
        ['id', 'parentId'].forEach((prop) => {
          if (item[prop]) {
            const parts = item[prop].split('\\');
            if (parts.length > 2) {
              // Hash all parts except the first one (preserve the urn prefix)
              const prefix = parts[0];
              const toHash = `${parts.slice(1).join('\\')}`;
              const hashed = utils.hashString(toHash, config.bridgeCommon.hashLength); // num of characters for the hash
              item[prop] = `${prefix}\\${hashed}`;
            }
          }
        });
        // Traverse the array from the end to preserve the latest element
        const uniqueKey = `${item.id}-${item.datasetId}`;
        if (!uniqueMap.has(uniqueKey)) {
          uniqueMap.set(uniqueKey, item);
        }
      }
      baAttrs[key] = Array.from(uniqueMap.values());
    });

    return { entity: { id: baEntity.id, type: baEntity.type }, attributes: baAttrs };
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
        const id = attrObj.id;
        const key = id;
        if (!beforeMap.has(key)) {
          beforeMap.set(key, { attrName, attrObj: setDatasetId(attrObj) });
        }
      }
    });

    const afterMap = new Map();
    Object.entries(afterAttrs).forEach(([attrName, attrArray]) => {
      for (let i = attrArray.length - 1; i >= 0; i--) {
        const attrObj = attrArray[i];
        const id = attrObj.id;
        const key = id;
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
        'parentId',
        'name',
        'entityId',
        'type',
        'datasetId',
        'nodeType'
      ];
      const deletedAttrObj = pickFields(attrObj, fields);
      deletedAttrs[attrName].push(deletedAttrObj);
    });

    return { insertedAttrs, updatedAttrs, deletedAttrs };
  };
};
