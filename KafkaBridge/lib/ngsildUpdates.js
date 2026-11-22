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

/**
 * True for a value Scorpio cannot merge: an IRI ({"@id": ...}) or a value
 * object with a keyword besides @value, like a declared double
 * {"@value": 80, "@type": "xsd:double"} (contracts/typed-literals, #961) or a
 * language-tagged string. Scorpio's merge recurses into every key of a value
 * and fails on these with 22023, see #967. A bare {"@value": ...} merges.
 */
const isUnmergeableValue = function (value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  if (value['@id'] !== undefined || value.id !== undefined) {
    return true;
  }
  return '@value' in value && Object.keys(value).length > 1;
};

/**
 * True when any attribute of the entity carries a value which Scorpio's merge
 * rejects (see isUnmergeableValue): batchMerge answers 400/22023 and merge
 * entity 500/22023, while the per-entity attrs endpoint accepts them and
 * keeps the declared @type, so these entities must take the other route.
 */
const needsAttrsRoute = function (entity) {
  return Object.keys(entity).some(function (key) {
    if (key === 'id' || key === 'type') {
      return false;
    }
    const attrs = Array.isArray(entity[key]) ? entity[key] : [entity[key]];
    return attrs.some(attr => attr !== null && typeof attr === 'object' &&
      [].concat(attr.value, attr.valueList).some(isUnmergeableValue));
  });
};

/**
 * The entities a batch operation refused, from the body of its answer, as
 * [{ entityId, error }], or null when the body holds no list of errors.
 * NGSI-LD reports them in a BatchOperationResult (CIM 009 clauses 5.2.16,
 * 5.2.17) as {"errors": [{"entityId": id, "error": ProblemDetails}]}. An
 * entry without these members is kept as it is, so that its log names what
 * the broker said.
 */
const batchErrors = function (body) {
  if (body === null || typeof body !== 'object' || !Array.isArray(body.errors)) {
    return null;
  }
  return body.errors.map(function (entry) {
    if (entry === null || typeof entry !== 'object') {
      return { entityId: undefined, error: entry };
    }
    if (entry.entityId === undefined || entry.error === undefined) {
      return entry;
    }
    return { entityId: entry.entityId, error: entry.error };
  });
};

/**
 * The ids of the entities sent in a batch operation that its answer names
 * neither under success nor under errors (CIM 009 clause 5.2.16), or none
 * when the answer has no list of successes.
 */
const unreported = function (entities, body, refused) {
  if (!Array.isArray(body.success)) {
    return [];
  }
  const reported = new Set(body.success.concat(refused.map(entry => entry.entityId)));
  return entities.filter(entity => !reported.has(entity.id)).map(entity => entity.id);
};

const ALREADY_EXISTS = 'https://uri.etsi.org/ngsi-ld/errors/AlreadyExists';

/**
 * True for a refusal of a batch create because the entity exists already
 * (CIM 009 clause 5.6.1, error type AlreadyExists).
 */
const isAlreadyExists = function (refused) {
  return refused.error !== null && typeof refused.error === 'object' && refused.error.type === ALREADY_EXISTS;
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
   * Creates the entities which don't exist and appends to the existing ones
   * only the attributes they don't have, leaving every existing attribute
   * untouched. An upsert with options=update would overwrite them (CIM 009
   * clauses 5.6.8 and 5.6.2), so the standard operations meaning "keep" are
   * used: a batch create (clause 5.6.7), which refuses the existing entities
   * with AlreadyExists, and for those a batch update with noOverwrite
   * (clauses 5.6.9, 6.16.3.1), which appends what is new (clause 5.6.3).
   * AlreadyExists is the expected answer for an existing entity and is not
   * logged; every other refusal is logged, like any refused request, and so
   * is every entity an answer names neither as done nor as refused.
   */
  const upsertWithoutOverwrite = async function (entities) {
    let result = await ngsild.createEntities(entities, { headers });
    if (result.statusCode === 201) {
      return;
    }
    let refused = batchErrors(result.body);
    if (refused === null) {
      logger.error('Cannot upsert entity:' + JSON.stringify(result.body) + ' and status code ' + result.statusCode);
      return;
    }
    const existing = new Set();
    refused.forEach(function (entry) {
      if (isAlreadyExists(entry)) {
        existing.add(entry.entityId);
      } else {
        logger.error('Cannot upsert entity:' + JSON.stringify(entry) + ' and status code ' + result.statusCode);
      }
    });
    unreported(entities, result.body, refused).forEach(function (id) {
      logger.error('Cannot upsert entity: ' + id + ' is not reported as created and status code ' + result.statusCode);
    });
    const toUpdate = entities.filter(entity => existing.has(entity.id));
    if (toUpdate.length === 0) {
      return;
    }
    result = await ngsild.updateEntities(toUpdate, false, { headers });
    if (result.statusCode === 204) {
      return;
    }
    refused = batchErrors(result.body);
    if (refused === null) {
      logger.error('Cannot upsert entity:' + JSON.stringify(result.body) + ' and status code ' + result.statusCode);
      return;
    }
    refused.forEach(function (entry) {
      logger.error('Cannot upsert entity:' + JSON.stringify(entry) + ' and status code ' + result.statusCode);
    });
    unreported(toUpdate, result.body, refused).forEach(function (id) {
      logger.error('Cannot upsert entity: ' + id + ' is not reported as updated and status code ' + result.statusCode);
    });
  };

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
        // without this return the undefined entities crashed the caller's
        // batch loop, so one malformed record silenced every valid update
        // behind it
        return;
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
          // Scorpio's batchMerge cannot digest IRI values (value: {"@id": ...},
          // what a rule writing e.g. a waste class produces) nor declared
          // values (value: {"@value": 80, "@type": "xsd:double"}); both answer
          // 400/22023 (#967). Those entities go through the per-entity attrs
          // endpoint, which accepts them; the rest keeps the batch path.
          const mergeable = entities.filter(entity => !needsAttrsRoute(entity));
          const unmergeable = entities.filter(needsAttrsRoute);
          if (mergeable.length > 0) {
            result = await ngsild.batchMerge(mergeable, { headers });
            if (result.statusCode === 207) {
              // A 207 is a partial success: the BatchOperationResult lists
              // the refused entities under errors (CIM 009 6.31.3.1), each
              // logged like any other refused merge. The list is mandatory
              // (5.2.16), so a 207 without one is logged as a refusal too,
              // and so is every entity reported neither merged nor refused.
              const refusedList = batchErrors(result.body);
              if (refusedList === null) {
                logger.error('Entity cannot run merge: a 207 without a list of errors:' + JSON.stringify(result.body) + ' and status code ' + result.statusCode);
              } else {
                refusedList.forEach(function (refused) {
                  logger.error('Entity cannot run merge:' + JSON.stringify(refused) + ' and status code ' + result.statusCode);
                });
                unreported(mergeable, result.body, refusedList).forEach(function (id) {
                  logger.error('Entity cannot run merge: ' + id + ' is not reported as merged and status code ' + result.statusCode);
                });
              }
            } else if (result.statusCode !== 204) {
              logger.error('Entity cannot run merge:' + JSON.stringify(result.body) + ' and status code ' + result.statusCode); // throw no error, log it and ignore it, repeating would probably not solve it
            }
          }
          for (const entity of unmergeable) {
            const attrs = {};
            Object.keys(entity).forEach(function (key) {
              if (key !== 'id' && key !== 'type') {
                attrs[key] = entity[key];
              }
            });
            result = await ngsild.updateProperties(
              { id: entity.id, body: attrs, isOverwrite: true }, { headers });
            if (result.statusCode !== 204 && result.statusCode !== 207) {
              logger.error('Entity cannot update properties:' + JSON.stringify(result.body) + ' and status code ' + result.statusCode);
            }
          }
        }
      } else if (op === 'upsert') {
        // in this case, entity will be created if not existing
        logger.debug('Upserting: ' + JSON.stringify(entities));
        if (overwriteOrReplace) {
          result = await ngsild.replaceEntities(entities, overwriteOrReplace, { headers });
          if (result.statusCode !== 204 && result.statusCode !== 201) {
            logger.error('Cannot upsert entity:' + JSON.stringify(result.body) + ' and status code ' + result.statusCode); // throw no error, log it and igonore it, repeating would probalby not solve it
          }
        } else {
          await upsertWithoutOverwrite(entities);
        }
      }
    } catch (e) {
      throw new Error('Error in REST call: ' + e.stack);
    }
  };
};
