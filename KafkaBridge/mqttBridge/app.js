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
const MqttHealth = require('../lib/mqttHealth');

process.env.APP_ROOT = __dirname;
const logger = Logger(config);
const brokerConnector = Broker.singleton(config.mqtt, logger);
const runningAsMain = require.main === module;

const startListener = async function () {
  const errorTypes = ['unhandledRejection', 'uncaughtException'];
  const signalTraps = ['SIGTERM', 'SIGINT', 'SIGUSR2'];

  // Armed before anything can block, so a broker that never accepts the
  // connection ends as a restart instead of a bridge that waits forever.
  const health = new MqttHealth(brokerConnector, logger).start();

  logger.info('Now starting MQTT auth service.');
  await authService.init(config);
  // Ready as soon as the auth API is listening, because that API is the only
  // thing the mqtt-bridge Service carries and EMQX cannot authorise anyone --
  // this bridge included -- until the Service has an endpoint to send the
  // callbacks to. Whether the subscription then works is a liveness question.
  health.serving();

  logger.info('Now starting MQTT-Kafka bridge forwarding.');
  // SparkplugB connector
  // The aggregator buffers measurements when Kafka is unreachable; once that
  // buffer is full the next thing it would do is lose them, so it fails the pod
  // instead.
  const sparkplugapiDataConnector = new SparkplugApiData(config, reason => health.fatal(reason));
  sparkplugapiDataConnector.init();
  // bind() only starts connecting. Readiness has to wait for the SUBSCRIBE to
  // be granted -- declaring it here, as this used to, made the pod Ready within
  // milliseconds even when the broker was unreachable.
  sparkplugapiDataConnector.bind(brokerConnector, sparkplugapiDataConnector, err => {
    if (err) {
      health.fatal(`MQTT subscription failed: ${err}`);
      return;
    }
    health.ready();
  });

  errorTypes.map(type =>
    process.on(type, async e => {
      try {
        console.log(`process.on ${type}`);
        console.error(e);
        // Non-zero: exiting 0 on an unhandled error makes a crash-looping
        // bridge look like a clean stop.
        process.exit(1);
      } catch (_) {
        process.exit(1);
      }
    }));

  signalTraps.map(type =>
    process.once(type, async () => {
      health.shutdown();
      process.kill(process.pid, type);
    }));
};

// Guarded like the other bridges: without it, requiring this module for a test
// opens a real broker connection and arms the real startup deadline.
if (runningAsMain) {
  // Explicit: startup happens before the uncaughtException handler above is
  // registered, so without this a failing authService.init would rely on Node's
  // default unhandled-rejection behaviour to be noticed at all.
  startListener().catch(e => {
    logger.error('Could not start MQTT bridge: ' + e);
    process.exit(1);
  });
}
