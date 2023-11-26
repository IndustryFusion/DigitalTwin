/**
* Copyright (c) 2021 Intel Corporation
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
'use esversion: 8';

const Cache = require('../cache');
const Keycloak = require('keycloak-connect');
//let me;

function verifyAndDecodeToken (token) {
  me.logger.debug('decode token: ' + token);
  return me.keycloakAdapter.grantManager
    .createGrant({ access_token: token })
    .then(grant => grant.access_token.content)
    .catch(err => {
      me.logger.debug('Token decoding error: ' + err);
      return null;
    });
}

function getRealm (token) {
  // issuer has to contain realm id, e.g.: http://<keycloak-url>/auth/realms/iff
  const parts = token.iss.split('/');
  return parts[parts.length - 1];
}

function validate (token, username) {
  const type = token.type;
  const did = token.device_id;
  if (!type || !did) {
    return false;
  }
  if (type !== 'device' || did !== username) {
    return false;
  }
  return true;
}

function legacyValidate (token, username) {
  const accounts = token.accounts;
  const type = token.type;
  const did = token.sub;
  if (!accounts || !type || !did) {
    return false;
  }
  if (accounts.length !== 1 || accounts[0].role !== 'device' || type !== 'device' || did !== username) {
    return false;
  }
  return true;
}

class Authenticate {
  constructor (config, logger) {
    this.config = config;
    this.logger = logger;
    this.cache = new Cache(this.config);
  }

  async initialize () {
    const authService = this.config.keycloak.mqttAuthService;
    authService.secret = process.env[this.config.mqtt.clientSecretVariable];
    this.keycloakAdapter = new Keycloak({}, authService);
    this.cache.init();
  }

  // expects "username" and "password" as url-query-parameters
  async authenticate (req, res) {
    this.logger.debug('Auth request ' + JSON.stringify(req.query));
    const username = req.query.username;
    const token = req.query.password;
    if (username === this.config.mqtt.adminUsername && token === this.config.mqtt.adminPassword) {
      // superuser
      this.logger.info('Superuser connected');
      res.status(200).json({ result: 'allow', is_superuser: 'true' });
      return;
    }
    const decoded_token = await verifyAndDecodeToken(token);
    this.logger.debug('token decoded: ' + JSON.stringify(decoded_token));
    if (decoded_token === null) {
      res.sendStatus(400);
      return;
    }
    if (!validate(decoded_token, username) && !legacyValidate(decoded_token, username)) {
      res.sendStatus(400);
      return;
    }
    // check whether accounts contains only one element and role is device
    const accounts = decoded_token.accounts;
    const did = decoded_token.device_id ? decoded_token.device_id : decoded_token.sub;
    const accountId = accounts && accounts.length > 0 ? accounts[0].id : null;
    const realm = getRealm(decoded_token);
    // put realm/device into the list of accepted topics
    await this.cache.setValue(realm + '/' + did, 'acl', true);
    // put account/device into the list of accepted topics (legacy)
    if (accountId) {
      const key = accountId + '/' + did;
      await this.cache.setValue(key, 'acl', true);
    }
    // For SparkplugB put (legacy) account/gateway(node) and realm/gateway(node) into the list of accepted topics to authenticate Node/gateway messages
    if (decoded_token.gateway !== undefined || decoded_token.gateway === null) {
      if (accountId) {
        const legacyGatewayKey = accountId + '/' + decoded_token.gateway;
        await this.cache.setValue(legacyGatewayKey, 'acl', true);
      }
      const gatewayKey = realm + '/' + decoded_token.gateway;
      await this.cache.setValue(gatewayKey, 'acl', true);
    }
    res.sendStatus(200);
  }
}
module.exports = Authenticate;
