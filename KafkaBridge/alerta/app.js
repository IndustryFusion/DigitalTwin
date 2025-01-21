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

const GROUPID = 'alertakafkabridge';
const CLIENTID = 'alertakafkaclient';
const { Kafka } = require('kafkajs');
const fs = require('fs');
const config = require('../config/config.json');
const Alerta = require('../lib/alerta.js');
const Logger = require('../lib/logger.js');

const alerta = new Alerta(config);
const logger = new Logger(config);

const kafka = new Kafka({
  clientId: CLIENTID,
  brokers: config.kafka.brokers
});

const consumer = kafka.consumer({ groupId: GROUPID, allowAutoTopicCreation: false });
const producer = kafka.producer();
console.log(JSON.stringify(config));

const errorIsUnrecoverable = function (body) {
  // The error code is not very expressive in Alerta. try to detect patterns in error message to filter out
  // non recoverable errors
  if (body.message.includes('Severity') && body.message.includes('is not one of') && body.status === 'error') {
    logger.info(`Dropping record due to unrecoverable error: ${body.message}`);
    return true;
  }
  return false;
};

const commitAppliedMessages = function (consumer, commitArray) {
  logger.debug(`Commit ${commitArray.length} messages `);
  consumer.commitOffsets(commitArray);
  return [];
};

const pauseresume = function (consumer, topic) {
  consumer.pause([{ topic }]);
  setTimeout(() => consumer.resume([{ topic }]), config.alerta.kafkaResumeTimeout);
  logger.debug('Set timeout. Waiting to resume');
};

const startListener = async function () {
  await consumer.connect();
  await consumer.subscribe({ topic: config.alerta.topic, fromBeginning: false });

  let committedOffsets = [];
  await consumer.run({
    autoCommit: false,
    eachMessage: async ({ topic, partition, message, pause }) => {
      let body = null;
      try {
        body = JSON.parse(message.value);
      } catch (e) {
        logger.error(`Could not deserialize message ${message.value}`);
      }
      if (body !== null && body.resource !== null && body.resource !== '' && body.event !== null && body.event !== '') {
        const result = await alerta.sendAlert(body, config.alerta.requestTimeout)
          .catch((err) => {
            logger.error('Could not send Alert: ' + err);
            committedOffsets = commitAppliedMessages(consumer, committedOffsets);
            pauseresume(consumer, topic);
            throw new Error('Could not send Alert ' + err);
          });
        logger.debug(`Alerta Result ${result.statusCode}}`);
        if (result.statusCode !== 201) {
          logger.error(`submission to Alerta failed with statuscode ${result.statusCode} and ${JSON.stringify(result.body)}`);
          committedOffsets = commitAppliedMessages(consumer, committedOffsets);
          // Filter out non recoverable errors
          if (errorIsUnrecoverable(result.body)) {
            committedOffsets.push({ topic, partition, offset: message.offset });
          } else {
            pauseresume(consumer, topic);
            throw new Error('Retry submission of Alert.');
          }
        } else {
          committedOffsets.push({ topic, partition, offset: message.offset });
        }
      } else {
        logger.debug('Ignoring ' + JSON.stringify(body));
        committedOffsets.push({ topic, partition, offset: message.offset });
      }
      if (committedOffsets.length > config.alerta.kafkaCommitThreshold) {
        committedOffsets = commitAppliedMessages(consumer, committedOffsets);
      }
    }
  }).catch(
    e => {
      console.error(`[example/consumer] ${e.message}`, e);
      throw e;
    }
  );

  const errorTypes = ['unhandledRejection', 'uncaughtException'];
  const signalTraps = ['SIGTERM', 'SIGINT', 'SIGUSR2'];

  errorTypes.map(type =>
    process.on(type, async e => {
      try {
        console.log(`process.on ${type}`);
        console.error(e);
        await consumer.disconnect();
        process.exit(0);
      } catch (_) {
        process.exit(1);
      }
    }));

  signalTraps.map(type =>
    process.once(type, async () => {
      try {
        await consumer.disconnect();
      } finally {
        process.kill(process.pid, type);
      }
    }));
  try {
    fs.writeFileSync('/tmp/ready', 'ready');
    fs.writeFileSync('/tmp/healthy', 'healthy');
  } catch (err) {
    logger.error(err);
  }
};

const startPeriodicProducer = async function () {
  if (config.alerta.heartbeatInterval === 0 || config.alerta.heartbeatInterval === undefined) {
    return;
  }
  logger.info(`Starting heartbeat to topic ${config.alerta.heartbeatTopic} with interval ${config.alerta.heartbeatInterval} and delay ${config.alerta.heartbeatDelay}`);
  await producer.connect();
  const heartbeat = {
    key: '{"resource":"heartbeat-owner","event":"heartbeat"}',
    value: null,
    topic: config.alerta.heartbeatTopic
  };

  setInterval(async () => {
    try {
      const timestamp = Date.now() - config.alerta.heartbeatDelay; // Current Kafka timestamp - 5 seconds
      await producer.send({
        topic: heartbeat.topic,
        messages: [
          {
            key: heartbeat.key,
            value: heartbeat.value,
            timestamp: timestamp.toString()
          }
        ]
      });
      logger.info('Alert heartbeat sent successfully');
    } catch (err) {
      logger.error('Could not send heartbeat: ' + err);
    }
  }, config.alerta.heartbeatInterval); // Send every second
};
logger.info('Now staring Kafka listener');
startListener();
logger.info('Now starting Kafka periodic producer');
startPeriodicProducer();
