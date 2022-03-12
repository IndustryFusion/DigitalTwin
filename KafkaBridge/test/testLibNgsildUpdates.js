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

describe('Test libNgsildUpdates', function () {
  it('Should post body with correct path and token for nonOverwrite update', async function () {
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {

        }
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
      entity: 'entity',
      id: 'id',
      overwrite: false
    };
    const expHeaders = {
      Authorization: 'Bearer token'
    };
    const Ngsild = function () {
      return {
        updateProperties: function (id, entity, noOverwrite, { headers }) {
          id.should.equal('id');
          entity.should.equal('entity');
          noOverwrite.should.equal(true);
          assert.deepEqual(headers, expHeaders);
          return {
            statusCode: 204
          };
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
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates(body);
    revert();
  });
  it('Should post body with correct path and token for nonOverwrite upsert', async function () {
    const config = {
      ngsildUpdates: {
        clientSecretVariable: 'CLIENT_SECRET',
        refreshIntervalInSeconds: 200
      },
      keycloak: {
        ngsildUpdatesAuthService: {

        }
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
      entity: 'entity',
      id: 'id',
      overwrite: false
    };
    const expHeaders = {
      Authorization: 'Bearer token'
    };
    const Ngsild = function () {
      return {
        replaceEntities: function ([entity], noOverwrite, { headers }) {
          entity.should.equal('entity');
          noOverwrite.should.equal(true);
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
    const ngsildUpdates = new ToTest(config);
    await ngsildUpdates.ngsildUpdates(body);
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
