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
const Rest = require('./rest.js');

module.exports =
function fiwareApi (conf) {
  const config = conf;
  const rest = new Rest(config);
  const logger = new Logger(config);

  this.getNgsildEntity = function (id) {
    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/entities/' + id,
      method: 'GET',
      headers: {
        Accept: 'application/ld+json'
      }
    };
    return rest.getBody(options);
  };

  /**
   * Gets list of objects defined by urns
   * @param {Array[String]} ids - list of urns to retrieve
   * @param {String} idPattern - Ngsi Pattern
   * @param {Array[String]} attrs - list of attributes (must be defined if type is not defined)
   * @param {Array[String]} type - list of ngsi-ld types  (must be defined if attrs is not defined)
   * @param {Array[String]} queries - list of query parameters
   */
  this.getNgsildEntities = function (params) {
    const ids = params.ids;
    const idPattern = params.idPattern;
    const attrs = params.attrs;
    const type = params.type;
    const queries = params.queries;

    if ((attrs === undefined || attrs === null) && (type === undefined || type === null)) {
      throw new Error('Neither attrs nor type is defined. But either of one has to be provided.');
    }
    let listOfIds = null;
    if (ids !== null && ids !== undefined) {
      listOfIds = ids.reduce((list, id) => {
        list += id + ',';
        return list;
      }, '');
      listOfIds = listOfIds.slice(0, -1);
    }
    let listOfAttrs = null;
    if (attrs !== null && attrs !== undefined) {
      listOfAttrs = attrs.reduce((list, id) => {
        list += id + ',';
        return list;
      }, '');
      listOfAttrs = listOfAttrs.slice(0, -1);
    }
    let listOfTypes = null;
    if (type !== null && type !== undefined) {
      listOfTypes = type.reduce((list, id) => {
        list += id + ',';
        return list;
      }, '');
      listOfTypes = listOfTypes.slice(0, -1);
    }
    let listOfQueries = null;
    if (queries !== null && queries !== undefined) {
      listOfQueries = queries.reduce((list, id) => {
        list += id + '|';
        return list;
      }, '');
      listOfQueries = listOfQueries.slice(0, -1);
    }
    let queryString = '?';
    if (listOfIds !== null) {
      queryString += 'id=' + listOfIds;
    }
    if (idPattern !== undefined && idPattern !== null) {
      if (queryString.length > 1) {
        queryString += '&';
      }
      queryString += 'idPattern=' + idPattern;
    }
    if (listOfAttrs !== undefined && listOfAttrs !== null) {
      if (queryString.length > 1) {
        queryString += '&';
      }
      queryString += 'attrs=' + listOfAttrs;
    }
    if (listOfTypes !== undefined && listOfTypes !== null) {
      if (queryString.length > 1) {
        queryString += '&';
      }
      queryString += 'type=' + listOfTypes;
    }
    if (listOfQueries !== undefined && listOfQueries !== null) {
      if (queryString.length > 1) {
        queryString += '&';
      }
      queryString += 'q=' + listOfQueries;
    }

    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/entities' + queryString,
      method: 'GET',
      headers: {
        Accept: 'application/ld+json'
      }
    };
    return rest.getBody(options);
  };

  /**
   * Gets list of Context Source Registrations for a tenant
   * @param {Array[String]} ids - list of urns to retrieve
   * @param {String} idPattern - Ngsi Pattern
   * @param {Array[String]} attrs - ngsi-ld attributes of monitored(!) entities (NOT of csourceregistration)
   * @param {Array[String]} types - ngsi-ld types of monitored(!) entities
   */
  this.getNgsildCSourceRegistrations = function (params) {
    const ids = params.ids;
    const idPattern = params.idPattern;
    const attrs = params.attrs;
    const types = params.types;

    let listOfIds = null;
    if (ids !== null && ids !== undefined) {
      listOfIds = ids.reduce((list, id) => {
        list += id + ',';
        return list;
      }, '');
      listOfIds = listOfIds.slice(0, -1);
    }

    let listOfAttrs = null;
    if (attrs !== null && attrs !== undefined) {
      listOfAttrs = attrs.reduce((list, id) => {
        list += id + ',';
        return list;
      }, '');
      listOfAttrs = listOfAttrs.slice(0, -1);
    }

    let listOfTypes = null;
    if (types !== null && types !== undefined) {
      listOfTypes = types.reduce((list, id) => {
        list += id + ',';
        return list;
      }, '');
      listOfTypes = listOfTypes.slice(0, -1);
    }

    let queryString = '?';
    if (listOfIds !== null) {
      queryString += 'id=' + listOfIds;
    }
    if (idPattern !== undefined && idPattern !== null) {
      if (queryString.length > 1) {
        queryString += '&';
      }
      queryString += 'idPattern=' + idPattern;
    }
    if (listOfAttrs !== undefined && listOfAttrs !== null) {
      if (queryString.length > 1) {
        queryString += '&';
      }
      queryString += 'attrs=' + listOfAttrs;
    }
    if (listOfTypes !== undefined && listOfTypes !== null) {
      if (queryString.length > 1) {
        queryString += '&';
      }
      queryString += 'type=' + listOfTypes;
    }

    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/csourceRegistrations' + queryString,
      method: 'GET',
      headers: {
        'Content-type': 'application/ld+json',
        Accept: 'application/ld+json'
      }
    };
    return rest.getBody(options);
  };

  /**
   * Deletes a Context Source Registrations for a tenant
   */
  this.deleteNgsildCSourceRegistration = function (id) {
    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/csourceRegistrations/' + id,
      method: 'DELETE'

    };
    return rest.getBody(options);
  };

  /**
   * Updates a Context Source Registrations for a tenant
   * @param {Object} entity - ngsi-ld context registration entity
   * @param {Boolean} isJsonLd - true if entity contains @context
   */
  this.updateNgsildCSourceRegistration = function (entity, isJsonLd) {
    const id = entity.id;
    delete entity.id;
    delete entity.type;
    const data = entity;
    const headers = {};
    if (isJsonLd === true) {
      headers['Content-Type'] = 'application/ld+json';
    } else {
      headers['Content-Type'] = 'application/json';
    }
    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/csourceRegistrations/' + id,
      headers: headers,
      method: 'PATCH'
    };
    return rest.postBody({ options, body: data });
  };

  /**
   * Create CSourceRegistration defined by array
   * @param {Object} entity- CSourceRegistration to create
   * @param {Boolean} isJsonLd - true if it contains @context
   */
  this.createNgsildCSourceRegistration = function (entity, isJsonLd) {
    const data = entity;

    const headers = {};
    if (isJsonLd === true) {
      headers['Content-Type'] = 'application/ld+json';
    } else {
      headers['Content-Type'] = 'application/json';
    }
    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/csourceRegistrations',
      headers: headers,
      method: 'POST'
    };
    return rest.postBody({ options, body: data });
  };

  /**
   *
   * @param {*} type - NGSI-LD type e.g. https://myontolgy/type
   */
  this.getAllObjectsOfType = function (type) {
    logger.debug(`getAllObjectsOfType type: ${type}`);
    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/entities' + '?type=' + type,
      method: 'GET',
      headers: {
        Accept: 'application/ld+json'
      }
    };
    return rest.getBody(options);
  };

  /**
   * Deletes list of objects defined by urns
   * @param {Array[String]} ids - list of urns to delete
   */
  this.deleteEntities = function (ids) {
    const data = ids;

    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/entityOperations/delete',
      headers: {
        'Content-Type': 'application/json'
      },
      method: 'POST'
    };
    return rest.postBody({ options, body: data });
  };

  /**
   * Create Entities defined by array
   * @param {array[Object]} entities- Array of entities to create
   */
  this.createEntities = function (entities) {
    const data = entities;

    // return new Promise(function(resolve, reject) {
    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/entityOperations/create',
      headers: {
        'Content-Type': 'application/ld+json'
      },
      method: 'POST'
    };
    return rest.postBody({ options, body: data });
  };

  /**
   * Create Entity defined by array
   * @param {array[Object]} entitiy- Array of entities to create
   */
  this.createEntity = function (entity) {
    const data = entity;

    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/entities',
      headers: {
        'Content-Type': 'application/ld+json'
      },
      method: 'POST'
    };
    return rest.postBody({ options, body: data });
  };

  /**
   * Replace Entities defined by array
   * @param {array[Object]} entities - Array of entities to create or update
   * @param {boolean} isUpdate - if this is true, the objects are only updated, not replaced
   * @param {array[Object]} headers - additional headers
   */
  this.replaceEntities = function (entities, isReplace, { headers }) {
    let queryString = '?options=replace';
    if (!isReplace) {
      queryString = '?options=update';
    }
    headers = headers || {};
    headers['Content-Type'] = 'application/ld+json';
    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: `/ngsi-ld/v1/entityOperations/upsert${queryString}`,
      headers: headers,
      method: 'POST'
    };
    return rest.postBody({ options, body: entities });
  };

  /**
   * Update Entities defined by array - this is creating new attributes if needed
   * @param {array[Object]} entities - Array of entities to create or update
   * @param {boolean} isOverwrite - if this is false, the objects are NOT overwritten
   * @param {array[Object]} headers - additional headers
   */
  this.updateEntities = function (entities, isOverwrite, { headers }) {
    let queryString = '';
    if (!isOverwrite) {
      queryString = '?options=noOverwrite';
    }
    headers = headers || {};
    headers['Content-Type'] = 'application/ld+json';
    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: `/ngsi-ld/v1/entityOperations/update${queryString}`,
      headers: headers,
      method: 'POST'
    };
    return rest.postBody({ options, body: entities });
  };

  this.updateProperties = async function ({ id, body, isOverwrite, noStringify }, { headers }) {
    logger.debug(`updateProperties with id ${id}, body ${JSON.stringify(body)}, noUpdate ${isOverwrite}`);
    let path = `/ngsi-ld/v1/entities/${id}/attrs`;
    let contentType = 'application/json';

    if (noStringify === undefined) {
      noStringify = false;
    }
    if (!isOverwrite) {
      path += '?options=noOverwrite';
    }
    if (body['@context'] !== undefined) {
      contentType = 'application/ld+json';
    }

    headers = headers || {};
    headers['Content-Type'] = contentType;

    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: path,
      method: 'POST',
      headers: headers
    };
    return rest.postBody({ options, body, disableChunks: false, noStringify: noStringify });
  };

  this.updateProperty = function (id, propertyKey, propertyValue, isRelation, isOverwrite) {
    logger.debug(`updateProperty with id ${id}, propertyKey ${propertyKey}, propertyValue ${propertyValue}`);
    const data = {};
    if (isRelation) {
      data[propertyKey] = {
        type: 'Relationship',
        object: propertyValue
      };
    } else {
      data[propertyKey] = {
        type: 'Property',
        value: propertyValue
      };
    }

    return this.updateProperties(id, data, isOverwrite, {});
  };

  /**
   *
   * @param {String} id - id of subscription Config
   * @param {String} type - type to subscribe changes to
   * @param {Int} interval - regular interval of updates (or null)
   */
  this.subscribe = function (id, type, interval) {
    const typeUrl = new URL(type);
    const typeOnly = typeUrl.pathname.substring(1);
    typeUrl.pathname = '';
    const prefix = typeUrl.toString().slice(0, -1);
    const data = getSubscriptionConfig(typeOnly, prefix);
    logger.debug('subscriptionConfig: ' + JSON.stringify(data));
    data.id = id;
    if (interval !== undefined && interval !== null) {
      data.timeInterval = interval;
    }
    logger.debug(`subscribing id: ${id} type: ${type}`);
    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/subscriptions/',
      headers: { 'Content-Type': 'application/ld+json' },
      method: 'POST'
    };
    return rest.postBody({ options, body: data });
  };

  this.updateSubscription = function (id, type, interval) {
    const typeUrl = new URL(type);
    const typeOnly = typeUrl.pathname.substring(1);
    typeUrl.pathname = '';
    const prefix = typeUrl.toString().slice(0, -1);
    const data = getSubscriptionConfig(typeOnly, prefix);
    delete data.id;
    if (interval !== undefined && interval !== null) {
      data.timeInterval = interval;
    }

    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/subscriptions/' + id,
      headers: { 'Content-Type': 'application/ld+json' },
      method: 'PATCH'
    };
    return rest.postBody({ options, body: data });
  };

  /**
   * Run batch merge operation on the entities
   * @param {array[Object]} entities - Array of JSON patches to merge
   * @param {array[Object]} headers - additional headers
   */
  this.batchMerge = function (entities, { headers }) {
    headers = headers || {};
    headers['Content-Type'] = 'application/ld+json';

    const options = {
      hostname: config.ngsildServer.hostname,
      protocol: config.ngsildServer.protocol,
      port: config.ngsildServer.port,
      path: '/ngsi-ld/v1/entityOperations/merge',
      headers: headers,
      method: 'POST'
    };
    return rest.postBody({ options, body: entities });
  };

  /**
   * Helpers
   */
  const jsonldFilesForTypes = {
    'https://oisp.info': 'oisp.jsonld',
    'https://ibn40': 'ibn40.jsonld',
    'https://industry-fusion.com': 'ibn40.jsonld'
  };

  const getSubscriptionConfig = function (type, typePrefix) {
    return {
      description: 'Notify me if ' + type + ' are changed',
      id: 'urn:ngsi-ld:Subscription:fwbridge001',
      type: 'Subscription',
      entities: [{ type: `${typePrefix}/${type}` }],
      notification: {
        endpoint: {
          uri: config.bridgeConfig.host + ':' + config.bridgeConfig.port + '/subscription',
          accept: 'application/json'
        }
      },
      '@context': [
        'https://fiware.github.io/data-models/context.jsonld',
        'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.3.jsonld',
        config.bridgeConfig.host + ':' + config.bridgeConfig.port + '/jsonld/' + jsonldFilesForTypes[typePrefix]
      ]
    };
  };
};
