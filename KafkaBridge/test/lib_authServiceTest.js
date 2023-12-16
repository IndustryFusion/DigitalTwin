/* eslint-disable no-useless-constructor */
/**
* Copyright (c) 2021, 2023 Intel Corporation
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

const assert = require('chai').assert;
const rewire = require('rewire');
const chai = require('chai');
global.should = chai.should();

let fileToTest = '../lib/authService/authenticate.js';

const PUBLISH = '2';

describe(fileToTest, function () {
  const ToTest = rewire(fileToTest);
  class Logger {
    info () {}
    debug () {}
    warn () {}
  };
  class Cache {
    init () {}
  };
  ToTest.__set__('Logger', Logger);
  ToTest.__set__('Cache', Cache);
  it('Shall verify and decode token successfully', function (done) {
    const decodedToken = { sub: '1234' };
    const config = {};
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => {
          return Promise.resolve({
            access_token: {
              content: decodedToken
            }
          });
        }
      }
    };
    auth.verifyAndDecodeToken('ex1123').then(result => {
      assert.equal(decodedToken, result, 'Wrong decoded Token');
      done();
    }).catch(err => {
      done(err);
    });
  });
  it('Shall test initialize', function (done) {
    const config = {
      keycloak: {
        mqttAuthService: {}
      },
      mqtt: {
        clientSecretVariable: 'CLIENTSECRETVARIABLE'
      }
    };
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    class Keycloak {
    }
    const process = {
      env: {
        CLIENTSECRETVARIABLE: 'CLIENTSECRETVARIABLE'
      }
    };
    ToTest.__set__('Keycloak', Keycloak);
    ToTest.__set__('process', process);
    auth.initialize().then(() => {
      done();
    }).catch(err => {
      done(err);
    });
  });
  it('Shall verify and decode token unsuccessfully', function (done) {
    const message = 'No valid token';
    const config = {};
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => {
          return Promise.reject(message);
        }
      }
    };
    auth.verifyAndDecodeToken('ex1123').then(result => {
      assert.equal(result, null, 'Wrong verfication result');
      done();
    }).catch(err => {
      done(err);
    });
  });
  it('Shall authenticate super user', function (done) {
    const Authenticate = ToTest.__get__('Authenticate');
    const config = {
      mqtt: {
        adminUsername: 'username',
        adminPassword: 'password'
      },
      cache: {
        port: 1432,
        host: 'cacheHost'
      }
    };
    const auth = new Authenticate(config);

    const req = {
      query: {
        username: 'username',
        password: 'password'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'allow', is_superuser: 'false' });
        done();
      }
    };
    auth.authenticate(req, res);
  });
  it('Authentication shall successfully validate a token', function (done) {
    const decodedToken = {
      sub: 'deviceId',
      iss: 'http://keycloak-url/auth/realms/realmId',
      type: 'device',
      device_id: 'deviceId'
    };
    const config = {
      mqtt: {
        adminUsername: 'username',
        adminPassword: 'password'
      }
    };
    const req = {
      query: {
        username: 'deviceId',
        password: 'token'
      }
    };
    const res = {
      sendStatus: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        done();
      }
    };
    class Cache {
      setValue (key, valueKey, value) {
        key.should.equal('realmId/deviceId');
        valueKey.should.equal('acl');
        value.should.equal('true');
      }
    }
    ToTest.__set__('Cache', Cache);
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => {
          return Promise.resolve({
            access_token: {
              content: decodedToken
            }
          });
        }
      }
    };

    auth.verifyAndDecodeToken = function () {
      return decodedToken;
    };
    auth.authenticate(req, res);
    done();
  });
  it('Shall authenticate super user', function (done) {
    const Authenticate = ToTest.__get__('Authenticate');
    const config = {
      mqtt: {
        adminUsername: 'username',
        adminPassword: 'password'
      },
      cache: {
        port: 1432,
        host: 'cacheHost'
      }
    };
    const auth = new Authenticate(config);

    const req = {
      query: {
        username: 'username',
        password: 'password'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'allow', is_superuser: 'false' });
        done();
      }
    };
    auth.authenticate(req, res);
  });
  it('Reject token with admin name as deviceId', function (done) {
    const decodedToken = {
      deviceId: 'username',
      iss: 'http://keycloak-url/auth/realms/realmId',
      type: 'device'
    };
    const config = {
      mqtt: {
        adminUsername: 'username',
        adminPassword: 'password'
      }
    };
    const req = {
      query: {
        username: 'username',
        password: 'token'
      }
    };
    const res = {
      sendStatus: function (status) {
        assert.equal(status, 400, 'Received wrong status');
        done();
      }
    };
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => {
          return Promise.resolve({
            access_token: {
              content: decodedToken
            }
          });
        }
      }
    };
    auth.verifyAndDecodeToken = function () {
      return decodedToken;
    };
    auth.authenticate(req, res);
  });

  it('Authentication shall detect wrong deviceId in username', function (done) {
    const decodedToken = {
      sub: 'deviceId',
      deviceId: 'deviceId',
      iss: 'http://keycloak-url/auth/realms/realmId',
      type: 'device'
    };

    const config = {
      mqtt: {
        adminUsername: 'username',
        adminPassword: 'password'
      }
    };
    const req = {
      query: {
        username: 'wrongDeviceId',
        password: 'password'
      }
    };
    const res = {
      sendStatus: function (status) {
        assert.equal(status, 400, 'Received wrong status');
        done();
      }
    };
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => {
          return Promise.resolve({
            access_token: {
              content: decodedToken
            }
          });
        }
      }
    };

    auth.authenticate(req, res);
  });
  it('Test verifyAndDecodeToken', function (done) {
    const token = 'token';
    const decodedToken = {
      sub: 'deviceId',
      deviceId: 'deviceId',
      iss: 'http://keycloak-url/auth/realms/realmId',
      type: 'device'
    };

    const config = {
      mqtt: {
        adminUsername: 'username',
        adminPassword: 'password'
      }
    };
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => {
          return Promise.resolve({
            access_token: {
              content: decodedToken
            }
          });
        }
      }
    };
    auth.verifyAndDecodeToken(token).then(result => result.should.deep.equal(decodedToken));
    done();
  });
});

fileToTest = '../lib/authService/acl.js';

describe(fileToTest, function () {
  const ToTest = rewire(fileToTest);
  class Logger {
    info () {}
    debug () {}
    warn () {}
  };
  class Cache {};
  ToTest.__set__('Logger', Logger);
  ToTest.__set__('Cache', Cache);
  it('Shall give access control to superuser', function (done) {
    const config = {
      mqtt: {
        adminUsername: 'superuser',
        adminPassword: 'password'
      }
    };

    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'superuser',
        topic: 'topic'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'allow' });
        done();
      }
    };
    acl.acl(req, res);
  });

  it('Shall give access control to SparkPlugB device', function (done) {
    const Cache = class Acl {
      constructor () {}
      getValue (subtopic, key) {
        assert.equal(aidSlashDid, subtopic, 'Wrong accountId/did subtopic');
        assert.equal(key, 'acl', 'Wrong key value');
        return 'true';
      }
    };
    ToTest.__set__('Cache', Cache);
    const aidSlashDid = 'accountId/deviceId';

    const config = {
      mqtt: {
        adminUsername: 'username',
        adminPassword: 'password'
      }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'deviceId',
        topic: 'spBv1.0/accountId/DBIRTH/eonID/deviceId'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'allow' });
        done();
      }
    };
    acl.acl(req, res);
  });

  it('Shall deny access control to device with wrong access', function (done) {
    const Cache = class Acl {
      constructor () {}
      getValue (subtopic, key) {
        assert.equal(aidSlashDid, subtopic, 'Wrong accountId/did subtopic');
        assert.equal(key, 'acl', 'Wrong key value');
        return true;
      }
    };
    ToTest.__set__('Cache', Cache);
    const aidSlashDid = 'accountId/deviceId';

    const config = {
      mqtt: {
        adminUsername: 'username',
        adminPassword: 'password'
      }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'deviceId',
        topic: 'server/accountId/DCMD/gatewayId/deviceId',
        access: PUBLISH
      }
    };
    const res = {
      sendStatus: function (status) {
        assert.equal(status, 400, 'Received wrong status');
        done();
      }
    };
    acl.acl(req, res);
  });
  it('Shall deny access control to device with wrong username', function (done) {
    const Cache = class Acl {
      constructor () {}

      getValue (subtopic, key) {
        assert.equal(key, 'acl', 'Wrong key value');
        return false;
      }
    };

    ToTest.__set__('Cache', Cache);
    const config = {
      mqtt: {
        adminUsername: 'superuser',
        adminPassword: 'password'
      }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'username',
        topic: 'spBv1.0/accountId/DBIRTH/eonID/deviceId'
      }
    };
    const res = {
      sendStatus: function (status) {
        assert.equal(status, 400, 'Received wrong status');
        done();
      }
    };
    acl.acl(req, res);
  });
});
