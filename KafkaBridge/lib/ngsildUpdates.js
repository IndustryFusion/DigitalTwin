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

  this.updateToken = async function () {
    token = await keycloakAdapter.grantManager
      .obtainFromClientCredentials();
    logger.debug('Service token refreshed!');
    return token;
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
   *  parentId: NGSI-LD id of parent of object - must be defined and !== null
   *  parentRel: parent relationship name which relates to childId (in NGIS-LD terminology)
   *  childObj: NGSI-LD object - either childObj or childId must be defined and !== null.
   */
  this.ngsildUpdates = async function (body) {
    if (token === undefined) {
      token = await this.updateToken();
    }

    headers = {};
    headers.Authorization = 'Bearer ' + token.access_token.token;

    if (body.op === undefined || body.entities === undefined || body.overwriteOrReplace === undefined) {
      logger.error('Format of message ' + JSON.stringify(body) + ' is invalid! Ignoring!');
      return;
    }

    const op = body.op;
    const entities = body.entities;
    const overwriteOrReplace = getFlag(body.overwriteOrReplace);
    let result;

    try {
      // update the entity - do not create it
      if (op === 'update') {
        // NOTE: The batch update API of Scorpio does not yet support noOverwrite options. For the time being
        // the batch processing will be done sequentially - until this is fixed in Scorpio
        const promises = [];
        entities.forEach(entity => {
          promises.push(ngsild.updateProperties({ id: entity.id, body: entity, isOverwrite: overwriteOrReplace }, { headers })
            .then(result => {
              if (result.statusCode !== 204 && result.statusCode !== 207) {
                throw new Error('Entity cannot update entity:' + JSON.stringify(result.body));
              }
            })
          );
        });
        promises.reduce((p, fn) => p.then(fn), Promise.resolve()).catch((e) => logger.error('Could not updateProperties: ' + e));
      } else if (op === 'upsert') {
        // in this case, entity will be created if not existing
        result = await ngsild.replaceEntities(entities, overwriteOrReplace, { headers });
        if (result.statusCode !== 204) {
          throw new Error('Cannot upsert entity:' + JSON.stringify(result.body));
        }
      }
    } catch (e) {
      throw new Error('Error in REST call: ' + e.stack);
    }
  };
};
