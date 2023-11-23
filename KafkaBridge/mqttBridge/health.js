/**
* Copyright (c) 2017 Intel Corporation
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
const http = require('http');
const url = require('url');
const config = require('../config/config.json');
const pkg = require('../package');

function appPoolHealth (status) {
  const env = config.ENV || 'PRD';
  return {
    kind: 'healthcheck',
    isHealthy: status,
    currentSetting: env.toUpperCase(),
    name: pkg.name,
    build: pkg.version,
    date: pkg.date,
    items: []
  };
}

const getHealth = function (broker) {
  const healthy = appPoolHealth(broker.connected());
  healthy.items.push({
    broker: {
      connected: broker.connected()
    }
  });
  return healthy;
};
module.exports.status = getHealth;
/**
 * @description Implement a health api with a http server native,
 * allowing to ping the Gateway to know is functional or not
 * @param broker
 */
module.exports.init = function (broker) {
  const br = broker;
  http.Server(function (req, res) {
    const urlParts = url.parse(req.url, true);
    if (urlParts.path.indexOf('v1/api/health') !== -1) {
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
      res.write(JSON.stringify(getHealth(br), null, 4));
      res.end();
    }
  }).listen(config.health.port);
};
