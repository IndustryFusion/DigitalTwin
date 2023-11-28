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
const Broker = require('../lib/mqtt_connector');
const SparkplugApiData = require('./sparkplug_data_ingestion');
const config = require('../config/config.json');
const authService = require('../lib/authService');
const Logger = require('../lib/logger');
const fs = require('fs');

process.env.APP_ROOT = __dirname;
const logger = Logger(config);
const brokerConnector = Broker.singleton(config.mqtt, logger);

const startListener = async function () {
  const errorTypes = ['unhandledRejection', 'uncaughtException'];
  const signalTraps = ['SIGTERM', 'SIGINT', 'SIGUSR2'];

  logger.info('Now starting MQTT auth service.');
  await authService.init(config);

  logger.info('Now starting MQTT-Kafka bridge forwarding.');
  // SparkplugB connector
  const sparkplugapiDataConnector = new SparkplugApiData(config);
  sparkplugapiDataConnector.init();
  sparkplugapiDataConnector.bind(brokerConnector, sparkplugapiDataConnector);
  errorTypes.map(type =>
    process.on(type, async e => {
      try {
        console.log(`process.on ${type}`);
        console.error(e);
        process.exit(0);
      } catch (_) {
        process.exit(1);
      }
    }));

  signalTraps.map(type =>
    process.once(type, async () => {
      process.kill(process.pid, type);
    }));
  try {
    fs.writeFileSync('/tmp/ready', 'ready');
    fs.writeFileSync('/tmp/healthy', 'healthy');
  } catch (err) {
    logger.error(err);
  }
};

startListener();
