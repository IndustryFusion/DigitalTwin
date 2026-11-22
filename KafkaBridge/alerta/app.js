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
const config = require('../config/config.json');
const Alerta = require('../lib/alerta.js');
const Logger = require('../lib/logger.js');
const KafkaHealth = require('../lib/kafkaHealth.js');
const runningAsMain = require.main === module;

const alerta = new Alerta(config);
const logger = new Logger(config);

const kafka = new Kafka({
  clientId: CLIENTID,
  brokers: config.kafka.brokers
});

const consumer = kafka.consumer({ groupId: GROUPID, allowAutoTopicCreation: false });
const producer = kafka.producer();

const errorIsUnrecoverable = function (body) {
  // The error code is not very expressive in Alerta. try to detect patterns in error message to filter out
  // non recoverable errors
  // Use body.statusCode if it exists, otherwise try body.status or body.code
  const statusCode = body.code;
  if ((body.message.includes('Severity') && body.message.includes('is not one of') && body.status === 'error') ||
  (statusCode === 400) || (statusCode === 415)) {
    logger.info(`Dropping record due to unrecoverable error: ${body.message}`);
    return true;
  }
  return false;
};

// Commit a record once it is done with: posted to Alerta, or dropped for good.
// Kafka keeps the offset of the next record to read, so that is offset + 1; a
// restart then resumes after the last record posted instead of posting it, and
// every record before it that was not yet committed, a second time -- which
// reopens an alert that was closed in between.
// A failed commit is only logged: throwing would make kafkajs hand the record
// over again and post it twice. The next record's commit covers this one.
const commitPast = async function (consumer, topic, partition, offset) {
  const next = (BigInt(offset) + BigInt(1)).toString();
  try {
    await consumer.commitOffsets([{ topic, partition, offset: next }]);
  } catch (err) {
    logger.error(`Could not commit offset ${next} of ${topic}/${partition}: ${err}`);
  }
};

const pauseresume = function (consumer, topic) {
  consumer.pause([{ topic }]);
  setTimeout(() => consumer.resume([{ topic }]), config.alerta.kafkaResumeTimeout);
  logger.debug('Set timeout. Waiting to resume');
};

const startListener = async function () {
  const health = new KafkaHealth(consumer, logger);
  await consumer.connect();
  await consumer.subscribe({ topic: config.alerta.topic, fromBeginning: false });

  // Strictly in order, one record at a time: a record that cannot be posted
  // pauses the topic and is handed back to kafkajs, so neither it nor any
  // record after it is committed before it has been posted.
  await consumer.run({
    autoCommit: false,
    eachMessage: async ({ topic, partition, message }) => {
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
            pauseresume(consumer, topic);
            throw new Error('Could not send Alert ' + err);
          });
        logger.debug(`Alerta Result ${result.statusCode}`);
        if (result.statusCode !== 201) {
          logger.error(`submission to Alerta failed with statuscode ${result.statusCode} and ${JSON.stringify(result.body)}`);
          // Filter out non recoverable errors
          if (!errorIsUnrecoverable(result.body)) {
            pauseresume(consumer, topic);
            throw new Error('Retry submission of Alert.');
          }
        }
      } else {
        logger.debug('Ignoring ' + JSON.stringify(body));
      }
      await commitPast(consumer, topic, partition, message.offset);
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
if (runningAsMain) {
  console.log(JSON.stringify(config));
  logger.info('Now starting Kafka listener');
  startListener();
  logger.info('Now starting Kafka periodic producer');
  startPeriodicProducer();
}
