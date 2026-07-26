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
      body: {
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
      body: {
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
      body: {
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
      body: {
        username: 'username',
        password: 'token'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
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
      body: {
        username: 'wrongDeviceId',
        password: 'password'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
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

  it('Factory user with Factory-Admin role shall be authenticated', function (done) {
    const decodedToken = {
      iss: 'http://keycloak-url/auth/realms/iff',
      resource_access: {
        scorpio: {
          roles: ['Factory-Admin']
        }
      }
    };
    const config = {
      mqtt: {
        adminUsername: 'admin',
        adminPassword: 'password'
      }
    };
    const cacheEntries = {};
    const Cache = class {
      init () {}
      async deleteKeysWithValue () {}
      async setValue (key, valueKey, value) {
        if (!cacheEntries[key]) cacheEntries[key] = {};
        cacheEntries[key][valueKey] = value;
      }
    };
    ToTest.__set__('Cache', Cache);
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => Promise.resolve({ access_token: { content: decodedToken } })
      }
    };
    const req = {
      body: { username: 'realm_user', password: 'token', clientid: 'clientid-factory' }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'allow', is_superuser: 'false' });
        assert.equal(cacheEntries['_factory_reader/clientid-factory'].acl, 'clientid-factory');
        assert.equal(cacheEntries['_factory_reader/clientid-factory'].realm, 'iff');
        done();
      }
    };
    auth.authenticate(req, res);
  });

  it('Factory user with Factory-Reader role shall be authenticated', function (done) {
    const decodedToken = {
      iss: 'http://keycloak-url/auth/realms/iff',
      resource_access: {
        scorpio: {
          roles: ['Factory-Reader']
        }
      }
    };
    const config = {
      mqtt: {
        adminUsername: 'admin',
        adminPassword: 'password'
      }
    };
    const Cache = class {
      init () {}
      async deleteKeysWithValue () {}
      async setValue () {}
    };
    ToTest.__set__('Cache', Cache);
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => Promise.resolve({ access_token: { content: decodedToken } })
      }
    };
    const req = {
      body: { username: 'realm_user', password: 'token', clientid: 'clientid-factory' }
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

  it('User without factory roles shall be rejected by device validation', function (done) {
    const decodedToken = {
      iss: 'http://keycloak-url/auth/realms/iff',
      resource_access: {
        scorpio: {
          roles: ['some-other-role']
        }
      }
    };
    const config = {
      mqtt: {
        adminUsername: 'admin',
        adminPassword: 'password'
      }
    };
    const Cache = class {
      init () {}
      async deleteKeysWithValue () {}
      async setValue () {}
    };
    ToTest.__set__('Cache', Cache);
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => Promise.resolve({ access_token: { content: decodedToken } })
      }
    };
    const req = {
      body: { username: 'realm_user', password: 'token', clientid: 'clientid-1' }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
        done();
      }
    };
    auth.authenticate(req, res);
  });

  it('Null/invalid token shall be rejected with deny', function (done) {
    const config = {
      mqtt: { adminUsername: 'admin', adminPassword: 'password' }
    };
    const Cache = class {
      init () {}
    };
    ToTest.__set__('Cache', Cache);
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => Promise.reject(new Error('invalid token'))
      }
    };
    const req = {
      body: { username: 'deviceId', password: 'bad-token', clientid: 'clientid-1' }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
        done();
      }
    };
    auth.authenticate(req, res);
  });

  it('Factory user with empty iss shall be denied (no realm derivable)', function (done) {
    const decodedToken = {
      iss: '',
      resource_access: { scorpio: { roles: ['Factory-Admin'] } }
    };
    const config = {
      mqtt: { adminUsername: 'admin', adminPassword: 'password' }
    };
    const Cache = class {
      init () {}
      async deleteKeysWithValue () {}
      async setValue () {}
    };
    ToTest.__set__('Cache', Cache);
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => Promise.resolve({ access_token: { content: decodedToken } })
      }
    };
    const req = {
      body: { username: 'realm_user', password: 'token', clientid: 'clientid-1' }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
        done();
      }
    };
    auth.authenticate(req, res);
  });

  it('Device with tainted device_id shall be denied', function (done) {
    const decodedToken = {
      iss: 'http://keycloak-url/auth/realms/iff',
      device_id: 'tainted-device',
      gateway: 'someGateway'
    };
    const config = {
      mqtt: {
        adminUsername: 'admin',
        adminPassword: 'password',
        tainted: 'tainted-device'
      }
    };
    const Cache = class {
      init () {}
      async deleteKeysWithValue () {}
      async setValue () {}
    };
    ToTest.__set__('Cache', Cache);
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => Promise.resolve({ access_token: { content: decodedToken } })
      }
    };
    const req = {
      body: { username: 'tainted-device', password: 'token', clientid: 'clientid-1' }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
        done();
      }
    };
    auth.authenticate(req, res);
  });

  it('Valid device with subdevice_ids shall be authenticated and subdevices cached', function (done) {
    const decodedToken = {
      iss: 'http://keycloak-url/auth/realms/iff',
      device_id: 'deviceId',
      gateway: 'gatewayId',
      subdevice_ids: JSON.stringify(['subdevice1', 'subdevice2'])
    };
    const config = {
      mqtt: {
        adminUsername: 'admin',
        adminPassword: 'password',
        tainted: 'tainted-device'
      }
    };
    const cachedKeys = {};
    const Cache = class {
      init () {}
      async deleteKeysWithValue () {}
      async setValue (key, valueKey, value) {
        cachedKeys[key] = { valueKey, value };
      }
    };
    ToTest.__set__('Cache', Cache);
    const Authenticate = ToTest.__get__('Authenticate');
    const auth = new Authenticate(config);
    auth.keycloakAdapter = {
      grantManager: {
        createGrant: () => Promise.resolve({ access_token: { content: decodedToken } })
      }
    };
    const req = {
      body: { username: 'deviceId', password: 'token', clientid: 'clientid-1' }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'allow', is_superuser: 'false' });
        assert.ok(cachedKeys['iff/subdevice1'], 'subdevice1 should be in cache');
        assert.ok(cachedKeys['iff/subdevice2'], 'subdevice2 should be in cache');
        assert.ok(cachedKeys['iff/deviceId'], 'main device should be in cache');
        done();
      }
    };
    auth.authenticate(req, res);
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
        return 'clientid';
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
        clientid: 'clientid',
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
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
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
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
        done();
      }
    };
    acl.acl(req, res);
  });

  it('Factory user shall be allowed to subscribe to arbitrary SparkplugB topic', function (done) {
    const Cache = class {
      constructor () {}
      async getValue (key, valueKey) {
        if (key === '_factory_reader/clientid' && valueKey === 'realm') return 'iff';
        return undefined;
      }
    };
    ToTest.__set__('Cache', Cache);
    const config = {
      mqtt: { adminUsername: 'superuser', adminPassword: 'password' }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'realm_user',
        clientid: 'clientid',
        topic: 'spBv1.0/iff/DDATA/anygateway/anydevice',
        action: 'subscribe'
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

  it('Factory user shall be denied to publish to SparkplugB topic', function (done) {
    const Cache = class {
      constructor () {}
      async getValue (key, valueKey) {
        if (key === '_factory_reader/clientid' && valueKey === 'realm') return 'iff';
        return undefined;
      }
    };
    ToTest.__set__('Cache', Cache);
    const config = {
      mqtt: { adminUsername: 'superuser', adminPassword: 'password' }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'realm_user',
        clientid: 'clientid',
        topic: 'spBv1.0/iff/DDATA/anygateway/anydevice',
        action: 'publish'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
        done();
      }
    };
    acl.acl(req, res);
  });

  it('Factory user shall be denied access to topic in a different realm', function (done) {
    const Cache = class {
      constructor () {}
      async getValue (key, valueKey) {
        if (key === '_factory_reader/clientid' && valueKey === 'realm') return 'iff';
        return undefined;
      }
    };
    ToTest.__set__('Cache', Cache);
    const config = {
      mqtt: { adminUsername: 'superuser', adminPassword: 'password' }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'realm_user',
        clientid: 'clientid',
        topic: 'spBv1.0/other-realm/DDATA/anygateway/anydevice',
        action: 'subscribe'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
        done();
      }
    };
    acl.acl(req, res);
  });

  it('Factory user shall be denied when action is not provided', function (done) {
    const Cache = class {
      constructor () {}
      async getValue (key, valueKey) {
        if (key === '_factory_reader/clientid' && valueKey === 'realm') return 'iff';
        return undefined;
      }
    };
    ToTest.__set__('Cache', Cache);
    const config = {
      mqtt: { adminUsername: 'superuser', adminPassword: 'password' }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'realm_user',
        clientid: 'clientid',
        topic: 'spBv1.0/iff/DDATA/anygateway/anydevice'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
        done();
      }
    };
    acl.acl(req, res);
  });

  it('Factory user shall be allowed to subscribe to non-SparkplugB topic', function (done) {
    const Cache = class {
      constructor () {}
      async getValue (key, valueKey) {
        if (key === '_factory_reader/clientid' && valueKey === 'realm') return 'iff';
        return undefined;
      }
    };
    ToTest.__set__('Cache', Cache);
    const config = {
      mqtt: { adminUsername: 'superuser', adminPassword: 'password' }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'realm_user',
        clientid: 'clientid',
        action: 'subscribe',
        topic: 'scorpio-test'
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

  it('Factory user shall be allowed to publish to non-SparkplugB topic', function (done) {
    const Cache = class {
      constructor () {}
      async getValue (key, valueKey) {
        if (key === '_factory_reader/clientid' && valueKey === 'realm') return 'iff';
        return undefined;
      }
    };
    ToTest.__set__('Cache', Cache);
    const config = {
      mqtt: { adminUsername: 'superuser', adminPassword: 'password' }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'realm_user',
        clientid: 'clientid',
        action: 'publish',
        topic: 'scorpio-test'
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

  it('Non-factory user shall be denied on non-SparkplugB topic', function (done) {
    const Cache = class {
      constructor () {}
      async getValue () { return undefined; }
    };
    ToTest.__set__('Cache', Cache);
    const config = {
      mqtt: { adminUsername: 'superuser', adminPassword: 'password' }
    };
    const Acl = ToTest.__get__('Acl');
    const acl = new Acl(config);
    const req = {
      query: {
        username: 'realm_user',
        clientid: 'clientid',
        action: 'subscribe',
        topic: 'scorpio-test'
      }
    };
    const res = {
      status: function (status) {
        assert.equal(status, 200, 'Received wrong status');
        return this;
      },
      json: function (resultObj) {
        resultObj.should.deep.equal({ result: 'deny' });
        done();
      }
    };
    acl.acl(req, res);
  });
});
