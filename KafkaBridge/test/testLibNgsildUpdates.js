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

const { assert } = require('chai');
const chai = require('chai');
global.should = chai.should();

const rewire = require('rewire');
const ToTest = rewire('../lib/ngsildUpdates.js');

const logger = {
  debug: function () {},
  error: function () {}
};

const addSyncOnAttribute = function () {};

describe('Test libNgsildUpdates', function () {
  it('Should post entities with correct path and token for nonOverwrite update using batchMerge', async function () {
    let batchMergeCalled = false;
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {
        }
      },
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const process = {
      env: {
        CLIENT_SECRET: 'client_secret'
      }
    };
    const body = {
      op: 'update',
      entities: [{
        id: 'id',
        type: 'type'
      }],
      overwriteOrReplace: false
    };
    const expHeaders = {
      Authorization: 'Bearer token'
    };
    const Ngsild = function () {
      return {
        batchMerge: function (entities, { headers }) {
          batchMergeCalled = true;
          assert.deepEqual(entities, body.entities);
          assert.deepEqual(headers, expHeaders);
          return new Promise(function (resolve) {
            resolve({
              statusCode: 204
            });
          });
        },
        // Stub updateProperties if needed
        updateProperties: function () {},
        replaceEntities: function () {

        }
      };
    };
    const setInterval = function (fun, interv) {
    };

    const Keycloak = function () {
      return {
        grantManager: {
          obtainFromClientCredentials: async function () {
            return new Promise(function (resolve, reject) {
              resolve({
                access_token: {
                  token: 'token'
                }
              });
            });
          }
        }
      };
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('process', process);
    ToTest.__set__('NgsiLd', Ngsild);
    ToTest.__set__('setInterval', setInterval);
    ToTest.__set__('Keycloak', Keycloak);
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates(body);
    batchMergeCalled.should.equal(true);
    revert();
  });
  it('Should post entities and filter out datasetId === "@none"', async function () {
    let batchMergeCalled = false;
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {
        }
      },
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const process = {
      env: {
        CLIENT_SECRET: 'client_secret'
      }
    };
    const body = {
      op: 'update',
      entities: [{
        id: 'id',
        type: 'type',
        attribute: {
          datasetId: '@none',
          value: 'value'
        }
      }],
      overwriteOrReplace: false
    };
    const expHeaders = {
      Authorization: 'Bearer token'
    };
    const Ngsild = function () {
      return {
        batchMerge: function (entities, { headers }) {
          batchMergeCalled = true;
          entities.forEach(entity => {
            // Check top-level properties
            assert.equal(entity.id, 'id');
            assert.equal(entity.type, 'type');

            // Check attribute properties
            assert.isUndefined(entity.attribute.datasetId, 'datasetId should be filtered out');
            assert.property(entity.attribute, 'value');
            assert.equal(entity.attribute.value, 'value');
          });
          assert.deepEqual(headers, expHeaders);
          return new Promise(function (resolve) {
            resolve({
              statusCode: 204
            });
          });
        }
      };
    };
    const setInterval = function (fun, interv) {
    };
    const Keycloak = function () {
      return {
        grantManager: {
          obtainFromClientCredentials: async function () {
            return new Promise(function (resolve, reject) {
              resolve({
                access_token: {
                  token: 'token'
                }
              });
            });
          }
        }
      };
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('process', process);
    ToTest.__set__('NgsiLd', Ngsild);
    ToTest.__set__('setInterval', setInterval);
    ToTest.__set__('Keycloak', Keycloak);
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates(body);
    batchMergeCalled.should.equal(true);
    revert();
  });
  it('Should post body and filter out datasetId === "@none" from attribute array', async function () {
    let batchMergeCalled = false;
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {
        }
      },
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const process = {
      env: {
        CLIENT_SECRET: 'client_secret'
      }
    };
    const body = {
      op: 'update',
      entities: [{
        id: 'id',
        type: 'type',
        attribute: [
          {
            datasetId: '@none',
            value: 'value'
          },
          {
            datasetId: 'http://example.com#source10',
            value: 'value2'
          }
        ]
      }],
      overwriteOrReplace: false
    };
    const expHeaders = {
      Authorization: 'Bearer token'
    };
    const Ngsild = function () {
      return {
        batchMerge: function (entities, { headers }) {
          batchMergeCalled = true;
          entities.forEach(entity => {
            assert.deepEqual(entity.id, 'id');
            assert.deepEqual(entity, { id: 'id', type: 'type', attribute: [{ value: 'value' }, { value: 'value2', datasetId: 'http://example.com#source10' }] });
          });
          assert.deepEqual(headers, expHeaders);
          return new Promise(function (resolve) {
            resolve({
              statusCode: 204
            });
          });
        },
        replaceEntities: function () {
        }
      };
    };
    const setInterval = function (fun, interv) {
    };
    const Keycloak = function () {
      return {
        grantManager: {
          obtainFromClientCredentials: async function () {
            return new Promise(function (resolve, reject) {
              resolve({
                access_token: {
                  token: 'token'
                }
              });
            });
          }
        }
      };
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('process', process);
    ToTest.__set__('NgsiLd', Ngsild);
    ToTest.__set__('setInterval', setInterval);
    ToTest.__set__('Keycloak', Keycloak);
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates(body);
    batchMergeCalled.should.equal(true);
    revert();
  });
  it('Should post entities and not filter out datasetId !== "@none"', async function () {
    let batchMergeCalled = false;
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {
        }
      },
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const process = {
      env: {
        CLIENT_SECRET: 'client_secret'
      }
    };
    const body = {
      op: 'update',
      entities: [{
        id: 'id',
        type: 'type',
        attribute: {
          datasetId: 'https://example.com/source1',
          value: 'value'
        }
      }],
      overwriteOrReplace: false
    };
    const expHeaders = {
      Authorization: 'Bearer token'
    };
    const Ngsild = function () {
      return {
        batchMerge: function (entities, { headers }) {
          batchMergeCalled = true;
          assert.deepEqual(entities, body.entities);
          assert.deepEqual(headers, expHeaders);
          return new Promise(function (resolve) {
            resolve({
              statusCode: 204
            });
          });
        },
        replaceEntities: function () {
        }
      };
    };
    const setInterval = function (fun, interv) {
    };
    const Keycloak = function () {
      return {
        grantManager: {
          obtainFromClientCredentials: async function () {
            return new Promise(function (resolve, reject) {
              resolve({
                access_token: {
                  token: 'token'
                }
              });
            });
          }
        }
      };
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('process', process);
    ToTest.__set__('NgsiLd', Ngsild);
    ToTest.__set__('setInterval', setInterval);
    ToTest.__set__('Keycloak', Keycloak);
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates(body);
    batchMergeCalled.should.equal(true);
    revert();
  });
  it('Should post body with correct path and token for nonOverwrite upsert', async function () {
    let replaceEntitiyCalled = false;
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {
        }
      },
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const process = {
      env: {
        CLIENT_SECRET: 'client_secret'
      }
    };
    const body = {
      op: 'upsert',
      entities: [{
        id: 'id',
        type: 'type'
      }],
      overwriteOrReplace: false
    };
    const expHeaders = {
      Authorization: 'Bearer token'
    };
    const Ngsild = function () {
      return {
        replaceEntities: function ([entity], isReplace, { headers }) {
          replaceEntitiyCalled = true;
          assert.deepEqual(entity, { id: 'id', type: 'type' });
          isReplace.should.equal(false);
          assert.deepEqual(headers, expHeaders);
          return {
            statusCode: 204
          };
        }
      };
    };
    const setInterval = function (fun, interv) {
    };
    const Keycloak = function () {
      return {
        grantManager: {
          obtainFromClientCredentials: async function () {
            return new Promise(function (resolve, reject) {
              resolve({
                access_token: {
                  token: 'token'
                }
              });
            });
          }
        }
      };
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('process', process);
    ToTest.__set__('NgsiLd', Ngsild);
    ToTest.__set__('setInterval', setInterval);
    ToTest.__set__('Keycloak', Keycloak);
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);

    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates(body);
    replaceEntitiyCalled.should.equal(true);
    revert();
  });
  it('Should post body with string entity', async function () {
    let batchMergeCalled = false;
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {
        }
      },
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const process = {
      env: {
        CLIENT_SECRET: 'client_secret'
      }
    };
    const body = {
      op: 'update',
      entities: [{
        id: 'id',
        type: 'type'
      }],
      overwriteOrReplace: false
    };
    const expHeaders = {
      Authorization: 'Bearer token'
    };
    const Ngsild = function () {
      return {
        batchMerge: function (entities, { headers }) {
          batchMergeCalled = true;
          entities.forEach(entity => {
            assert.deepEqual(entity.id, 'id');
            assert.deepEqual(entity, { id: 'id', type: 'type' });
          });
          assert.deepEqual(headers, expHeaders);
          return new Promise(function (resolve) {
            resolve({
              statusCode: 204
            });
          });
        },
        replaceEntities: function () {
        }
      };
    };
    const setInterval = function (fun, interv) {
    };

    const Keycloak = function () {
      return {
        grantManager: {
          obtainFromClientCredentials: async function () {
            return new Promise(function (resolve, reject) {
              resolve({
                access_token: {
                  token: 'token'
                }
              });
            });
          }
        }
      };
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('process', process);
    ToTest.__set__('NgsiLd', Ngsild);
    ToTest.__set__('setInterval', setInterval);
    ToTest.__set__('Keycloak', Keycloak);
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);
    const ngsildUpdates = new ToTest(config);
    body.entities = JSON.stringify(body.entities);
    await ngsildUpdates.ngsildUpdates(body);
    batchMergeCalled.should.equal(true);
    revert();
  });

  it('Should ignore an unparseable entities string without throwing', async function () {
    let batchMergeCalled = false;
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {
        }
      },
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const process = {
      env: {
        CLIENT_SECRET: 'client_secret'
      }
    };
    // an unquoted ISO timestamp made a rule-written record unparseable, and
    // the bridge then crashed its whole batch instead of skipping the record
    const body = {
      op: 'update',
      entities: '[{"id":"id","value":2026-08-24T19:19:43.588Z}]',
      overwriteOrReplace: false
    };
    const Ngsild = function () {
      return {
        batchMerge: function (entities, { headers }) {
          batchMergeCalled = true;
          return new Promise(function (resolve) {
            resolve({ statusCode: 204 });
          });
        },
        replaceEntities: function () {
        }
      };
    };
    const setInterval = function (fun, interv) {
    };
    const Keycloak = function () {
      return {
        grantManager: {
          obtainFromClientCredentials: async function () {
            return new Promise(function (resolve, reject) {
              resolve({
                access_token: {
                  token: 'token'
                }
              });
            });
          }
        }
      };
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('process', process);
    ToTest.__set__('NgsiLd', Ngsild);
    ToTest.__set__('setInterval', setInterval);
    ToTest.__set__('Keycloak', Keycloak);
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates(body);
    batchMergeCalled.should.equal(false);
    revert();
  });

  it('Should route IRI-valued properties to updateProperties, not batchMerge', async function () {
    let batchMergeCalled = false;
    let updatePropertiesId = null;
    let updatePropertiesBody = null;
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {
        }
      },
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const process = {
      env: {
        CLIENT_SECRET: 'client_secret'
      }
    };
    const wasteclass = {
      type: 'Property',
      value: { '@id': 'https://example.com/WC2' }
    };
    const body = {
      op: 'update',
      entities: [{
        id: 'urn:cartridge',
        'https://example.com/hasWasteclass': [wasteclass]
      }],
      overwriteOrReplace: false
    };
    const Ngsild = function () {
      return {
        batchMerge: function (entities, { headers }) {
          batchMergeCalled = true;
          return new Promise(function (resolve) {
            resolve({ statusCode: 204 });
          });
        },
        updateProperties: function ({ id, body, isOverwrite }, { headers }) {
          updatePropertiesId = id;
          updatePropertiesBody = body;
          return new Promise(function (resolve) {
            resolve({ statusCode: 204 });
          });
        },
        replaceEntities: function () {
        }
      };
    };
    const setInterval = function (fun, interv) {
    };
    const Keycloak = function () {
      return {
        grantManager: {
          obtainFromClientCredentials: async function () {
            return new Promise(function (resolve, reject) {
              resolve({
                access_token: {
                  token: 'token'
                }
              });
            });
          }
        }
      };
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('process', process);
    ToTest.__set__('NgsiLd', Ngsild);
    ToTest.__set__('setInterval', setInterval);
    ToTest.__set__('Keycloak', Keycloak);
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates(body);
    batchMergeCalled.should.equal(false);
    updatePropertiesId.should.equal('urn:cartridge');
    updatePropertiesBody['https://example.com/hasWasteclass'][0]
      .value['@id'].should.equal('https://example.com/WC2');
    revert();
  });
});
describe('Test libNgsildUpdates routing of JSON-LD values', function () {
  // Scorpio's merge (merge entity and batch merge) fails with 22023 on a value
  // which carries a JSON-LD keyword besides @value, like a declared double
  // (#961, #967). Such entities go through the attrs endpoint, like IRI values.
  const DOUBLE = 'http://www.w3.org/2001/XMLSchema#double';
  const run = async function (entities) {
    const calls = { batchMerge: [], updateProperties: [] };
    const ToTest = rewire('../lib/ngsildUpdates.js');
    ToTest.__set__('Logger', function () { return logger; });
    ToTest.__set__('process', { env: { CLIENT_SECRET: 'client_secret' } });
    ToTest.__set__('setInterval', function () {});
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);
    ToTest.__set__('Keycloak', function () {
      return { grantManager: { obtainFromClientCredentials: async () => ({ access_token: { token: 'token' } }) } };
    });
    ToTest.__set__('NgsiLd', function () {
      return {
        batchMerge: async function (entities) {
          calls.batchMerge.push(entities);
          return { statusCode: 204 };
        },
        updateProperties: async function ({ id, body, isOverwrite }) {
          calls.updateProperties.push({ id, body, isOverwrite });
          return { statusCode: 204 };
        }
      };
    });
    const config = {
      ngsildUpdates: { clientSecretVariable: 'CLIENT_SECRET', refreshIntervalInSeconds: 200 },
      keycloak: { ngsildUpdatesAuthService: {} },
      bridgeCommon: { kafkaSyncOnAttribute: 'kafkaSyncOn' }
    };
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates({ op: 'update', entities, overwriteOrReplace: false });
    return calls;
  };
  const entity = (id, attribute) => ({ id, 'https://example.com/hasTemperature': [attribute] });

  it('Should route a declared double to updateProperties, not batchMerge', async function () {
    const declared = { type: 'Property', value: { '@value': 80, '@type': 'xsd:double' } };
    const calls = await run([entity('urn:pump', declared)]);
    calls.batchMerge.length.should.equal(0);
    calls.updateProperties.length.should.equal(1);
    calls.updateProperties[0].id.should.equal('urn:pump');
    calls.updateProperties[0].isOverwrite.should.equal(true);
    assert.deepEqual(calls.updateProperties[0].body['https://example.com/hasTemperature'], [declared]);
  });

  it('Should route a declared double given as an attribute object, not an array', async function () {
    const calls = await run([{ id: 'urn:pump', 'https://example.com/hasTemperature': { type: 'Property', value: { '@value': 80, '@type': DOUBLE } } }]);
    calls.batchMerge.length.should.equal(0);
    calls.updateProperties.length.should.equal(1);
  });

  it('Should route a value object with the type alias of the core context', async function () {
    const calls = await run([entity('urn:pump', { type: 'Property', value: { '@value': 80, type: DOUBLE } })]);
    calls.batchMerge.length.should.equal(0);
    calls.updateProperties.length.should.equal(1);
  });

  it('Should route a language-tagged value object', async function () {
    const calls = await run([entity('urn:pump', { type: 'Property', value: { '@value': 'Pumpe', '@language': 'de' } })]);
    calls.batchMerge.length.should.equal(0);
    calls.updateProperties.length.should.equal(1);
  });

  it('Should route a declared value among several values of a Property', async function () {
    const calls = await run([entity('urn:pump', { type: 'Property', value: [1, { '@value': 80, '@type': DOUBLE }] })]);
    calls.batchMerge.length.should.equal(0);
    calls.updateProperties.length.should.equal(1);
  });

  it('Should route a declared value in the valueList of a ListProperty', async function () {
    const calls = await run([entity('urn:pump', { type: 'ListProperty', valueList: [1, { '@value': 80, '@type': DOUBLE }] })]);
    calls.batchMerge.length.should.equal(0);
    calls.updateProperties.length.should.equal(1);
  });

  it('Should keep plain values and a bare @value on batchMerge', async function () {
    const calls = await run([
      entity('urn:a', { type: 'Property', value: 80 }),
      entity('urn:b', { type: 'Property', value: { '@value': 80 } }),
      entity('urn:c', { type: 'Property', value: [1, 2] }),
      entity('urn:d', { type: 'Property', value: null }),
      entity('urn:e', { type: 'JsonProperty', json: { '@value': 1, '@type': DOUBLE, '@id': 'urn:x' } }),
      entity('urn:f', { type: 'Relationship', object: 'urn:x' })
    ]);
    calls.updateProperties.length.should.equal(0);
    calls.batchMerge.length.should.equal(1);
    calls.batchMerge[0].map(e => e.id).should.deep.equal(['urn:a', 'urn:b', 'urn:c', 'urn:d', 'urn:e', 'urn:f']);
  });

  it('Should split a batch into merged plain entities and declared ones through attrs', async function () {
    const calls = await run([
      entity('urn:plain', { type: 'Property', value: 42.5 }),
      entity('urn:declared', { type: 'Property', value: { '@value': 80, '@type': DOUBLE } }),
      entity('urn:iri', { type: 'Property', value: { '@id': 'urn:x' } })
    ]);
    calls.batchMerge.length.should.equal(1);
    calls.batchMerge[0].map(e => e.id).should.deep.equal(['urn:plain']);
    calls.updateProperties.map(c => c.id).should.deep.equal(['urn:declared', 'urn:iri']);
    assert.notProperty(calls.updateProperties[0].body, 'id');
  });
});
describe('Test getFlag', function () {
  it('Should get true', async function () {
    const getFlag = ToTest.__get__('getFlag');
    let flag = getFlag('true');
    flag.should.equal(true);
    flag = getFlag(true);
    flag.should.equal(true);
  });
  it('Should get false', async function () {
    const getFlag = ToTest.__get__('getFlag');
    let flag = getFlag('false');
    flag.should.equal(false);
    flag = getFlag(false);
    flag.should.equal(false);
    flag = getFlag(undefined);
    flag.should.equal(false);
    flag = getFlag(null);
    flag.should.equal(false);
  });
});
describe('Test addSyncOnAttribute', function () {
  const ToTest = rewire('../lib/ngsildUpdates.js');
  it('Should get true', function () {
    const addSyncOnAttribute = ToTest.__get__('addSyncOnAttribute');
    const entities = [
      {
        id: 'id',
        type: 'type'
      },
      {
        id: 'id2',
        type: 'type'
      }
    ];
    const expectedResult = [
      {
        id: 'id',
        type: 'type',
        synchOnAttribute: {
          type: 'Property',
          value: '1.4fzzz'
        }
      },
      {
        id: 'id2',
        type: 'type',
        synchOnAttribute: {
          type: 'Property',
          value: '1.4fzzz'
        }
      }
    ];

    const Math = {
      random: function () {
        return 0.123456789;
      }
    };
    const revert = ToTest.__set__('Math', Math);
    addSyncOnAttribute(entities, 'synchOnAttribute', 1);
    assert.deepEqual(entities, expectedResult);
    revert();
  });
});
describe('Test libNgsildUpdates refusals inside a 207 of a batch merge', function () {
  // NGSI-LD reports the entities a batch merge refused inside a 207 as a
  // BatchOperationResult (CIM 009 6.31.3.1, 5.2.16, 5.2.17). Each of them must
  // be logged as refused, as a 400 is, so the OPC UA chain test sees it.
  const SB001 = { type: 'https://uri.etsi.org/ngsi-ld/errors/InvalidRequest', title: 'Invalid request.', detail: 'SB001', status: 400 };
  const run = async function (answer) {
    const errors = [];
    const ToTest = rewire('../lib/ngsildUpdates.js');
    ToTest.__set__('Logger', function () {
      return { debug: function () {}, error: function (message) { errors.push(message); } };
    });
    ToTest.__set__('process', { env: { CLIENT_SECRET: 'client_secret' } });
    ToTest.__set__('setInterval', function () {});
    ToTest.__set__('addSyncOnAttribute', addSyncOnAttribute);
    ToTest.__set__('Keycloak', function () {
      return { grantManager: { obtainFromClientCredentials: async () => ({ access_token: { token: 'token' } }) } };
    });
    ToTest.__set__('NgsiLd', function () {
      return { batchMerge: async () => answer };
    });
    const config = {
      ngsildUpdates: { clientSecretVariable: 'CLIENT_SECRET', refreshIntervalInSeconds: 200 },
      keycloak: { ngsildUpdatesAuthService: {} },
      bridgeCommon: { kafkaSyncOnAttribute: 'kafkaSyncOn' }
    };
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates({
      op: 'update',
      overwriteOrReplace: true,
      entities: [{ id: 'urn:a', 'https://example.com/p': { type: 'Property', value: 1 } },
        { id: 'urn:b', 'https://example.com/p': { type: 'Property', value: 2 } }]
    });
    return errors;
  };

  it('Should log an entity refused in a 207 with entityId and error, the standard form', async function () {
    const errors = await run({ statusCode: 207, body: { success: ['urn:b'], errors: [{ entityId: 'urn:a', error: SB001 }] } });
    errors.length.should.equal(1);
    errors[0].should.include('urn:a');
    errors[0].should.include('SB001');
    errors[0].should.not.include('urn:b');
    errors[0].should.include('status code 207');
  });

  it('Should log an entity refused in a 207 with id and ProblemDetails, the fork form', async function () {
    const errors = await run({ statusCode: 207, body: { success: ['urn:b'], errors: [{ id: 'urn:a', ProblemDetails: SB001, type: 'Merge' }] } });
    errors.length.should.equal(1);
    const logged = JSON.parse(errors[0].replace('Entity cannot run merge:', '').replace(' and status code 207', ''));
    assert.deepEqual(logged, { entityId: 'urn:a', error: SB001 });
  });

  it('Should log every refused entity of a 207 on its own', async function () {
    const errors = await run({
      statusCode: 207,
      body: { success: [], errors: [{ entityId: 'urn:a', error: SB001 }, { entityId: 'urn:b', error: SB001 }] }
    });
    errors.length.should.equal(2);
    errors[0].should.include('urn:a');
    errors[1].should.include('urn:b');
  });

  it('Should count a 207 which reports every entity as merged as success', async function () {
    (await run({ statusCode: 207, body: { success: ['urn:a', 'urn:b'], errors: [] } })).length.should.equal(0);
  });

  it('Should log a 207 without a list of errors', async function () {
    // errors is mandatory in a BatchOperationResult (CIM 009 5.2.16)
    for (const body of [{ success: ['urn:a', 'urn:b'] }, null, { errors: 'x' }]) {
      const errors = await run({ statusCode: 207, body });
      errors.length.should.equal(1);
      errors[0].should.equal('Entity cannot run merge: a 207 without a list of errors:' + JSON.stringify(body) + ' and status code 207');
    }
  });

  it('Should log an entity a 207 reports neither merged nor refused', async function () {
    const errors = await run({ statusCode: 207, body: { success: ['urn:b'], errors: [] } });
    errors.length.should.equal(1);
    errors[0].should.equal('Entity cannot run merge: urn:a is not reported as merged and status code 207');
  });

  it('Should log a 400 and a 204 as before', async function () {
    const body = { errors: [{ id: 'urn:a', ProblemDetails: SB001, type: 'Merge' }] };
    const errors = await run({ statusCode: 400, body });
    errors.length.should.equal(1);
    errors[0].should.equal('Entity cannot run merge:' + JSON.stringify(body) + ' and status code 400');
    (await run({ statusCode: 204, body: null })).length.should.equal(0);
  });
});
describe('Test batchErrors', function () {
  const batchErrors = ToTest.__get__('batchErrors');
  it('Should read both member forms', function () {
    assert.deepEqual(batchErrors({ errors: [{ entityId: 'urn:a', error: { status: 400 } }, { id: 'urn:b', ProblemDetails: { status: 409 }, type: 'Create' }] }),
      [{ entityId: 'urn:a', error: { status: 400 } }, { entityId: 'urn:b', error: { status: 409 } }]);
  });
  it('Should return null without a list of errors', function () {
    (batchErrors(null) === null).should.equal(true);
    (batchErrors('text') === null).should.equal(true);
    (batchErrors({ success: ['urn:a'] }) === null).should.equal(true);
    (batchErrors({ errors: 'x' }) === null).should.equal(true);
  });
  it('Should keep an entry which is no object as the error', function () {
    assert.deepEqual(batchErrors({ errors: ['oops'] }), [{ entityId: undefined, error: 'oops' }]);
  });
});
