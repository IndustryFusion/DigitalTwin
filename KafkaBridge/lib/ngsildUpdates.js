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
const NgsiLd = require('./ngsild.js');
const Keycloak = require('keycloak-connect');

const getFlag = function (value) {
  if (value === 'true' || value === true) {
    return true;
  }
  return false;
};

/**
 * Adds to every NGSILD entity the kafkaSyncOn attribute
 * entities: NGSILD entities to update
 */
const addSyncOnAttribute = function (entities, syncOnAttribute, timestamp) {
  entities.forEach(entity => {
    const val = String(timestamp) + '.' + Math.random().toString(36).slice(2, 7);
    entity[syncOnAttribute] = {
      type: 'Property',
      value: val
    };
  });
};

/**
 * Remove "@none" dataset ids
 *
 * entities: NGSILD entities
*/
const removeDefaultDatasetID = function (entities) {
  entities.forEach(entity => {
    Object.keys(entity).forEach(key => {
      let attributes = entity[key];
      if (!Array.isArray(attributes)) {
        attributes = [attributes];
      }
      attributes.forEach(attribute => {
        if (typeof attribute === 'object') {
          if ('datasetId' in attribute && attribute.datasetId === '@none') {
            delete attribute.datasetId;
          }
        }
      });
    });
  });
};

module.exports = function NgsildUpdates (conf) {
  const config = conf;
  const ngsild = new NgsiLd(config);
  const logger = new Logger(config);
  const authService = config.keycloak.ngsildUpdatesAuthService;
  authService.secret = process.env[config.ngsildUpdates.clientSecretVariable];
  const keycloakAdapter = new Keycloak({}, authService);
  let token;
  let headers = {};
  const refreshIntervalInMs = config.ngsildUpdates.refreshIntervalInSeconds * 1000;
  const syncOnAttribute = config.bridgeCommon.kafkaSyncOnAttribute;

  this.updateToken = async function () {
    token = await keycloakAdapter.grantManager
      .obtainFromClientCredentials();
    logger.debug('Service token refreshed!');
    // return token;
  };
  if (refreshIntervalInMs !== undefined && refreshIntervalInMs !== null) {
    setInterval(this.updateToken, refreshIntervalInMs);
  }
  this.updateToken();

  /**
   *
   * @param {object} body - object from ngsildUpdate channel
   *
   * body should contain:
   *  op, entities, overwriteOrReplace
   */
  this.ngsildUpdates = async function (body, timestamp) {
    if (token === undefined) {
      await this.updateToken();
    }
    headers = {};
    headers.Authorization = 'Bearer ' + token.access_token.token;

    if (body.op === undefined || body.entities === undefined || body.overwriteOrReplace === undefined) {
      logger.error('Format of message ' + JSON.stringify(body) + ' is invalid! Ignoring!');
      return;
    }

    const op = body.op;
    let entities;
    if (typeof body.entities === 'string') {
      try {
        entities = JSON.parse(body.entities);
      } catch (e) {
        logger.error('Could not parse entities field. Ignoring record.' + body.entities);
      }
    } else {
      entities = body.entities;
    }
    removeDefaultDatasetID(entities);

    const overwriteOrReplace = getFlag(body.overwriteOrReplace);
    const noForward = getFlag(body.noForward);
    let result;
    if (noForward) {
      addSyncOnAttribute(entities, syncOnAttribute, timestamp);
    }

    try {
      // update the entity - do not create it
      if (op === 'update') {
        // Only batch merge is run
        if (entities === undefined || entities == null) {
          logger.error('Unhealthy entities - ignoring it:' + JSON.stringify(entities));
        } else {
          logger.debug('Updating: ' + JSON.stringify(entities));
          result = await ngsild.batchMerge(entities, { headers });
          if (result.statusCode !== 204 && result.statusCode !== 207) {
            logger.error('Entity cannot run merge:' + JSON.stringify(result.body) + ' and status code ' + result.statusCode); // throw no error, log it and ignore it, repeating would probably not solve it
          }
        }
      } else if (op === 'upsert') {
        // in this case, entity will be created if not existing
        logger.debug('Upserting: ' + JSON.stringify(entities));
        result = await ngsild.replaceEntities(entities, overwriteOrReplace, { headers });
        if (result.statusCode !== 204 && result.statusCode !== 201) {
          logger.error('Cannot upsert entity:' + JSON.stringify(result.body) + ' and status code ' + result.statusCode); // throw no error, log it and igonore it, repeating would probalby not solve it
        }
      }
    } catch (e) {
      throw new Error('Error in REST call: ' + e.stack);
    }
  };
};
