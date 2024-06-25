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

'use strict';
'use esversion: 8';

const Cache = require('../cache');
const Keycloak = require('keycloak-connect');
const Logger = require('../logger');

function getRealm (token) {
  // issuer has to contain realm id, e.g.: http://<keycloak-url>/auth/realms/iff
  const parts = token.iss.split('/');
  return parts[parts.length - 1];
}

function validate (token, username) {
  const did = token.device_id;
  const gateway = token.gateway;
  if (did === null || did === undefined || gateway === null || gateway === undefined) {
    return false;
  }
  if (did !== username) {
    return false;
  }
  return true;
}

class Authenticate {
  constructor (config) {
    this.config = config;
    this.logger = new Logger(config);
    this.cache = new Cache(this.config);
  }

  async initialize () {
    const authService = this.config.keycloak.mqttAuthService;
    authService.secret = process.env[this.config.mqtt.clientSecretVariable];
    this.keycloakAdapter = new Keycloak({}, authService);
    this.cache.init();
  }

  async addSubdeviceAcl (realm, clientid, decodedToken) {
    if ('subdevice_ids' in decodedToken) {
      const subdevices = decodedToken.subdevice_ids;
      const parsedSubdevices = JSON.parse(subdevices);
      for (const did of parsedSubdevices) {
        await this.cache.setValue(realm + '/' + did, 'acl', clientid);
      }
    }
  }

  // expects "username" and "password" as url-query-parameters
  async authenticate (req, res) {
    this.logger.debug('Auth request ' + JSON.stringify(req.query));
    const username = req.query.username;
    const token = req.query.password;
    const clientid = req.query.clientid;
    if (username === this.config.mqtt.adminUsername) {
      if (token === this.config.mqtt.adminPassword) {
        // superuser
        this.logger.info('Superuser connected');
        res.status(200).json({ result: 'allow', is_superuser: 'false' });
        return;
      } else {
        // will also kick out tokens who use the superuser name as deviceId
        this.logger.warn('Wrong Superuser password.');
        res.status(200).json({ result: 'deny' });
        return;
      }
    }
    const decodedToken = await this.verifyAndDecodeToken(token);
    this.logger.debug('token decoded: ' + JSON.stringify(decodedToken));
    if (decodedToken === null) {
      this.logger.info('Could not decode token.');
      res.status(200).json({ result: 'deny' });
      return;
    }
    if (!validate(decodedToken, username)) {
      this.logger.warn('Validation of token failed. Username: ' + username);
      res.status(200).json({ result: 'deny' });
      return;
    }
    // check whether accounts contains only one element and role is device
    const did = decodedToken.device_id;
    const gateway = decodedToken.gateway;
    const realm = getRealm(decodedToken);
    if (did === null || did === undefined || realm === null || realm === undefined) {
      this.logger.warn('Validation failed: Device id or realm not valid.');
      res.status(200).json({ result: 'deny' });
      return;
    }
    if (did === this.config.mqtt.tainted || gateway === this.config.mqtt.tainted) {
      this.logger.warn('This token is tained! Rejecting.');
      res.status(200).json({ result: 'deny' });
    }
    // put realm/device into the list of accepted topics
    await this.cache.deleteKeysWithValue('acl', clientid);
    await this.addSubdeviceAcl(realm, clientid, decodedToken);
    await this.cache.setValue(realm + '/' + did, 'acl', clientid);
    res.status(200).json({ result: 'allow', is_superuser: 'false' });
  }

  verifyAndDecodeToken (token) {
    this.logger.debug('decode token: ' + token);
    return this.keycloakAdapter.grantManager
      .createGrant({ access_token: token })
      .then(grant => grant.access_token.content)
      .catch(err => {
        this.logger.debug('Token decoding error: ' + err);
        return null;
      });
  }
}
module.exports = Authenticate;
