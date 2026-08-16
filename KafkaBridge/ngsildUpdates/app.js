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

const GROUPID = 'statekafkabridge';
const CLIENTID = 'statekafkaclient';
const { Kafka } = require('kafkajs');
const config = require('../config/config.json');
const State = require('../lib/ngsildUpdates.js');
const Logger = require('../lib/logger.js');
const KafkaHealth = require('../lib/kafkaHealth.js');

const state = new State(config);
const logger = new Logger(config);

const kafka = new Kafka({
  clientId: CLIENTID,
  brokers: config.kafka.brokers
});

const consumer = kafka.consumer({ groupId: GROUPID, allowAutoTopicCreation: false });

const startListener = async function () {
  const health = new KafkaHealth(consumer, logger);
  await consumer.connect();
  await consumer.subscribe({ topic: config.ngsildUpdates.topic, fromBeginning: false });

  await consumer.run({
    eachMessage: async ({ topic, partition, message }) => {
      try {
        const body = JSON.parse(message.value);
        await state.ngsildUpdates(body, message.timestamp);
      } catch (e) {
        logger.error('could not process message: ' + e);
      }
    }
  }).catch(e => {
    // Rethrow: a consumer.run() that rejects leaves the bridge with no message
    // loop at all, and swallowing it here let startup continue on to declare
    // the pod ready.
    logger.error(`[StateUpdater/consumer] ${e.message}`, e);
    throw e;
  });

  const errorTypes = ['unhandledRejection', 'uncaughtException'];
  const signalTraps = ['SIGTERM', 'SIGINT', 'SIGUSR2'];

  errorTypes.map(type =>
    process.on(type, async e => {
      try {
        console.log(`process.on ${type}`);
        console.error(e);
        health.shutdown();
        await consumer.disconnect();
        // Non-zero: this path is only reached on an unhandled error, and
        // exiting 0 made a crash-looping bridge indistinguishable from a clean
        // stop in kubectl and in any exit-code based alerting.
        process.exit(1);
      } catch (_) {
        process.exit(1);
      }
    }));

  signalTraps.map(type =>
    process.once(type, async () => {
      try {
        health.shutdown();
        await consumer.disconnect();
      } finally {
        process.kill(process.pid, type);
      }
    }));
  try {
    health.start();
  } catch (err) {
    logger.error(err);
  }
};

logger.info('Now starting Kafka listener');
startListener();
