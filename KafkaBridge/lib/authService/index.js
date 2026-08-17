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

const express = require('express');
const rateLimit = require('express-rate-limit');
const Authenticate = require('./authenticate');
const Acl = require('./acl');
const app = express();
const Logger = require('../logger.js');

const init = async function (conf) {
  const log = Logger(conf);
  const auth = new Authenticate(conf, log);
  await auth.initialize();
  const acl = new Acl(conf, log);
  await acl.init();
  const config = conf;
  app.use(express.json());
  app.use(express.urlencoded({ extended: false }));

  const authLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 100 // limit each IP to 100 requests per windowMs
  });

  app.post('/auth', authLimiter, (req, res) => {
    auth.authenticate(req, res);
  });

  app.get('/acl', (req, res) => {
    acl.acl(req, res);
  });
  app.get('/v1/api/health', (req, res) => {
    res.sendStatus(200);
  });

  // Resolve on 'listening', not on the call: the caller declares readiness off
  // the back of this promise, and a pod that is Ready before its socket accepts
  // sends EMQX's auth callbacks to a closed port. A failed bind (port taken)
  // rejects here instead of surfacing as an unhandled 'error' event.
  return new Promise((resolve, reject) => {
    const server = app.listen(config.mqtt.authServicePort, () => {
      console.log(`Auth/ACL Service started and listening on port ${config.mqtt.authServicePort}`);
      resolve(server);
    });
    server.once('error', reject);
  });
};
module.exports.init = init;
