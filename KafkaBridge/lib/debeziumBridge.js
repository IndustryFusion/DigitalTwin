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
    let result = {
      entity: null,
      updatedAttrs: null,
      deletedAttrs: null
    };
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
    const { updatedAttrs, deletedAttrs } = this.diffAttributes(beforeAttrs, afterAttrs);
    const isKafkaUpdate = updatedAttrs[syncOnAttribute] !== undefined; // when syncOnAttribute is used, it means that update
    // did not come through API but through Kafka channel
    // so do not forward to avoid 'infinity' loop
    delete deletedAttrs[syncOnAttribute]; // this attribute is only used to detect API vs Kafka inputs
    delete updatedAttrs[syncOnAttribute]; // remove it before detecting changes
    delete afterEntity[syncOnAttribute];
    const isChanged = isEntityUpdated || Object.keys(updatedAttrs).length > 0 || Object.keys(deletedAttrs).length > 0;

    let deletedEntity;
    if (isChanged && Object.keys(afterEntity).length === 0) {
      deletedEntity = {
        id: beforeEntity.id,
        type: beforeEntity.type
      };
    }
    result = {
      entity: isChanged ? afterEntity : null,
      deletedEntity: deletedEntity,
      updatedAttrs: !isKafkaUpdate && isChanged ? updatedAttrs : null,
      deletedAttrs: !isKafkaUpdate && isChanged ? deletedAttrs : null
    };
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
          obj.synchronized = true;
          obj.name = key;
          if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'] !== undefined) {
            obj.type = 'https://uri.etsi.org/ngsi-ld/Property';
            // every Property is array with one element, hence [0] is no restriction
            // Property can be Literal => @value or IRI => @id
            if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value'] !== undefined) {
              obj['https://uri.etsi.org/ngsi-ld/hasValue'] = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value'];
            } else if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@id'] !== undefined) { // Property can be IRI => @id
              obj['https://uri.etsi.org/ngsi-ld/hasValue'] = '{"@id": "' + refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@id'] + '"}';
            }
            if (refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'] !== undefined) {
              // every Property is array with one element, hence [0] is no restriction
              obj.valuetype = refObj['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@type'];
            }
          } else if (refObj['https://uri.etsi.org/ngsi-ld/hasObject'] !== undefined) {
            obj.type = 'https://uri.etsi.org/ngsi-ld/Relationship';
            // every Relationship is array with one element, hence [0] is no restriction
            obj['https://uri.etsi.org/ngsi-ld/hasObject'] = refObj['https://uri.etsi.org/ngsi-ld/hasObject'][0]['@id'];
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
   * @returns list with updated and deleted atributes {updatedAttrs, deletedAttrs}
   */
  this.diffAttributes = function (beforeAttrs, afterAttrs) {
    const updatedAttrs = {};
    const deletedAttrs = {};

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

    // Determine all attributes which are changed and add them to updatedAttrs
    // Detect wheter before had higher index and add these to deleteAttrs
    Object.keys(afterAttrs).forEach(key => {
      // if the attributes are unequal
      // add every different attribute per index to the updatedAttrs
      // add every attribute which have indexes in before but not mentioned in after to deletedAttrs
      if (!_.isEqual(afterAttrs[key], beforeAttrs[key])) {
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
    return { updatedAttrs, deletedAttrs };
  };
};
