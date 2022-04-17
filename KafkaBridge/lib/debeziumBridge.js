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
    const isKafkaUpdate = updatedAttrs[syncOnAttribute] !== undefined || insertedAttrs[syncOnAttribute] !== undefined;
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
    // primary key. Deletion means to set everythin, which is not primary key to null
    let deletedEntity = null;
    if (isEntityUpdated && Object.keys(afterEntity).length === 0) {
      deletedEntity = {
        id: beforeEntity.id,
        type: beforeEntity.type
      };
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
      baEntity = JSON.parse(ba.data);
      // Delete all non-properties as defined by ETSI SPEC (ETSI GS CIM 009 V1.5.1 (2021-11))
      delete baEntity['@id'];
      delete baEntity['@type'];
      delete baEntity['https://uri.etsi.org/ngsi-ld/createdAt'];
      delete baEntity['https://uri.etsi.org/ngsi-ld/modifiedAt'];
      delete baEntity['https://uri.etsi.org/ngsi-ld/obvervedAt'];
      baEntity.id = ba.id;
      baEntity.type = ba.type;
    } catch (e) { logger.error(`Cannot parse debezium before field ${e}`); return; } // not throwing an error due to the fact that it cannot be fixed in next try

    // create entity table
    let id = baEntity.id;
    const resEntity = {};
    Object.keys(baEntity).filter(key => key !== 'type' && key !== 'id')
      .forEach(key => {
        resEntity[key] = id + '\\' + key;
      });
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
          if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'] !== undefined) {
            obj.type = 'https://uri.etsi.org/ngsi-ld/Property';
            // every Property is array with one element, hence [0] is no restriction
            // Property can be Literal => @value,@json or IRI => @id
            if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value'] !== undefined) {
              obj['https://uri.etsi.org/ngsi-ld/hasValue'] = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value'];
              obj.nodeType = '@value';
            } else if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@id'] !== undefined) { // Property can be IRI => @id
              obj['https://uri.etsi.org/ngsi-ld/hasValue'] = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@id'];
              obj.nodeType = '@id';
            } else if (typeof refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0] === 'object') { // no @id, no @value, must be a @json type
              obj['https://uri.etsi.org/ngsi-ld/hasValue'] = JSON.stringify(refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]);
              obj.nodeType = '@json';
            }

            if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'] !== undefined) {
              // every Property is array with one element, hence [0] is no restriction
              obj.valueType = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'];
            }
          } else if (refObj['https://uri.etsi.org/ngsi-ld/hasObject'] !== undefined) {
            obj.type = 'https://uri.etsi.org/ngsi-ld/Relationship';
            // every Relationship is array with one element, hence [0] is no restriction
            obj['https://uri.etsi.org/ngsi-ld/hasObject'] = refObj['https://uri.etsi.org/ngsi-ld/hasObject'][0]['@id'];
            obj.nodeType = '@id';
          } else {
            return;
          }
          obj.index = index;
          baAttrs[key].push(obj);
        });
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
   *
   * @param {object} beforeAttrs - object with atrributes
   * @param {object} afterAttrs - object with attributes
   * @returns list with inserted, updated and deleted atributes {insertedAttrs, updatedAttrs, deletedAttrs}
   */
  this.diffAttributes = function (beforeAttrs, afterAttrs) {
    const insertedAttrs = {}; // contains all attributes which are found in afterAttrs but not in beforeAttrs
    const updatedAttrs = {}; // contains all attribures which are found in afterAttrs and in beforeAttrs
    const deletedAttrs = {}; // contains all attributes which are not found in afterAttrs but in beforeAttrs

    // Determine all attributes which are found in beforeAttrs but not in afterAttrs
    // These attributes are added to deleteAttrs
    Object.keys(beforeAttrs).forEach(key => {
      if (afterAttrs[key] === undefined || afterAttrs[key] === null || !Array.isArray(afterAttrs[key]) || afterAttrs[key].length === 0) {
        const obj = beforeAttrs[key].reduce((accum, element) => {
          const obj = {};
          obj.id = element.id;
          obj.index = element.index;
          accum.push(obj);
          return accum;
        }, []);
        deletedAttrs[key] = obj;
      }
    });

    // Determine all attributes which are found in afterAttrs but not in beforeAttrs
    // These attributes are added to insertedAttrs
    Object.keys(afterAttrs).forEach(key => {
      if (beforeAttrs[key] === undefined || beforeAttrs[key] === null || !Array.isArray(beforeAttrs[key]) || beforeAttrs[key].length === 0) {
        insertedAttrs[key] = afterAttrs[key];
      }
    });

    // Determine all attributes which are changed and add them to updatedAttrs
    // Detect wheter before had higher index and add these to deleteAttrs
    Object.keys(afterAttrs).forEach(key => {
      // if the attributes are not existing in
      // if the attributes are unequal
      // add every different attribute per index to the updatedAttrs
      // add every attribute which have indexes in before but not mentioned in after to deletedAttrs
      if (beforeAttrs[key] !== undefined && beforeAttrs[key] !== null &&
        !_.isEqual(afterAttrs[key], beforeAttrs[key])) {
        // delete all old elements with higher indexes
        // the attribute lists are sorted so length diff reveals what has to be deleted
        const delementArray = [];
        if (beforeAttrs[key] !== undefined && beforeAttrs[key].length > afterAttrs[key].length) {
          for (let i = afterAttrs[key].length; i < beforeAttrs[key].length; i++) {
            const delement = {};
            delement.id = beforeAttrs[key][i].id;
            delement.index = i;
            delementArray.push(delement);
          }
          deletedAttrs[key] = delementArray;
        }
        // and create new one
        updatedAttrs[key] = afterAttrs[key];
      }
    });
    return { insertedAttrs, updatedAttrs, deletedAttrs };
  };
};
