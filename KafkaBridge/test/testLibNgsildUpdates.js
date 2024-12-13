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
