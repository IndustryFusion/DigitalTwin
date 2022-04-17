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
    const overwriteOrReplace = getFlag(body.overwriteOrReplace);
    const noForward = getFlag(body.noForward);
    let result;
    if (noForward) {
      addSyncOnAttribute(entities, syncOnAttribute, timestamp);
    }

    try {
      // update the entity - do not create it
      if (op === 'update') {
        // NOTE: The batch update API of Scorpio does not yet support noOverwrite options. For the time being
        // the batch processing will be done sequentially - until this is fixed in Scorpio
        for (const entity of entities) { // olet i = 0; i < entities.length; i ++) {
          // basic health check of entity
          if (entity.id === undefined || entity.id == null) {
            logger.error('Unhealthy entity - ignoring it:' + JSON.stringify(entity));
          } else {
            result = await ngsild.updateProperties({ id: entity.id, body: entity, isOverwrite: overwriteOrReplace }, { headers });
            if (result.statusCode !== 204 && result.statusCode !== 207) {
              logger.error('Entity cannot update entity:' + JSON.stringify(result.body)); // throw no error, log it and ignore it, repeating would probably not solve it
            }
          }
        };
      } else if (op === 'upsert') {
        // in this case, entity will be created if not existing
        result = await ngsild.replaceEntities(entities, overwriteOrReplace, { headers });
        if (result.statusCode !== 204) {
          logger.error('Cannot upsert entity:' + JSON.stringify(result.body)); // throw no error, log it and igonore it, repeating would probalby not solve it
        }
      }
    } catch (e) {
      throw new Error('Error in REST call: ' + e.stack);
    }
  };
};
