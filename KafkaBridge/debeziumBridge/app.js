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

const GROUPID = 'debeziumBridgeGroup';
const CLIENTID = 'ngsildkafkaclient';
const fs = require('fs');
const { Kafka } = require('kafkajs');
const config = require('../config/config.json');
const DebeziumBridge = require('../lib/debeziumBridge.js');
const Logger = require('../lib/logger.js');
const runningAsMain = require.main === module;

const debeziumBridge = new DebeziumBridge(config);
const logger = new Logger(config);

const kafka = new Kafka({
  clientId: CLIENTID,
  brokers: config.kafka.brokers
});

const consumer = kafka.consumer({ groupId: GROUPID, allowAutoTopicCreation: false });
const producer = kafka.producer();

const startListener = async function () {
  await consumer.connect();
  await consumer.subscribe({ topic: config.debeziumBridge.topic, fromBeginning: false });
  await producer.connect();

  await consumer.run({
    eachMessage: async ({ topic, partition, message }) => {
      try {
        const body = JSON.parse(message.value);
        const result = await debeziumBridge.parse(body);
        if (result !== null) {
          await sendUpdates({
            entity: result.entity,
            deletedEntity: result.deletedEntity,
            updatedAttrs: result.updatedAttrs,
            deletedAttrs: result.deletedAttrs,
            insertedAttrs: result.insertedAttrs
          });
        }
      } catch (e) {
        logger.error('could not process message: ' + e.stack);
      }
    }
  }).catch(e => logger.error(`[StateUpdater/consumer] ${e.message}`, e));

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

const checkTimestamp = function (val) {
  let isotimestamp = null;
  let timestamp = null;
  try {
    isotimestamp = val['https://uri.etsi.org/ngsi-ld/observedAt'][0]['@value'];
    timestamp = new Date(isotimestamp).getTime();
    delete (val['https://uri.etsi.org/ngsi-ld/observedAt']);
  } catch (err) {}
  return timestamp;
};

/**
 * send batch of ngsild updates from debezium to respective kafka/sql topic
 * @param entity {object}- the entity object
 * @param updateAttrs {object} - contains the list of attributes of the entity which are changed
 * @param deleteAttrs {object} - contains the list of attributes of the entity which have to be deleted
 * @returns
 */
const sendUpdates = async function ({ entity, deletedEntity, updatedAttrs, deletedAttrs, insertedAttrs }) {
  let removeType = false;
  let updateOnly = false;

  // Remember deletion after subclasses have been determined.
  // Then remove type later
  if (deletedEntity !== undefined && deletedEntity !== null) {
    entity = deletedEntity;
    removeType = true;
  }
  // if attributes are updated ONLY - no entity refresh/update is needed
  if (updatedAttrs !== undefined && updatedAttrs !== null && Object.keys(updatedAttrs).length > 0 &&
      (insertedAttrs === undefined || insertedAttrs === null || Object.keys(insertedAttrs).length === 0) &&
      (deletedAttrs === undefined || deletedAttrs === null || Object.keys(deletedAttrs).length === 0)) {
    updateOnly = true;
  }

  if (entity === null || entity.id === undefined || entity.id === null || entity.type === undefined || entity.type === null) {
    logger.warn('No entity definition given. Will not forward updates.');
    return;
  }

  const genKey = entity.id;

  const topicMessages = [];
  // if only updates are detected, no update of entity is needed
  if (!updateOnly) {
    // let subClasses = await getSubClasses(entity.type);
    // if (subClasses.length === 0) {
    //   subClasses = [entity.type];
    // }
    // Now remove type. This has been determined earlier.
    if (removeType) {
      // delete of entities is done by set everything to NULL
      entity.deleted = true;
    }

    const obj = {};
    const entityTopic = config.debeziumBridge.entityTopicPrefix;
    obj.topic = entityTopic;
    obj.messages = [{
      key: genKey,
      value: JSON.stringify(entity)
    }];
    topicMessages.push(obj);
  }

  if (deletedAttrs !== null && deletedAttrs !== undefined && Object.keys(deletedAttrs).length > 0) {
    // Flatmap the array, i.e. {key: k, value: [m1, m2]} => [{key: k, value: m1}, {key: k, value: m2}]
    const deleteMessages = Object.entries(deletedAttrs).flatMap(([key, value]) =>
      value.map(val => {
        val.deleted = true;
        val.synched = true;
        return { key: genKey, value: JSON.stringify(val) };
      })
    );
    topicMessages.push({
      topic: config.debeziumBridge.attributesTopic,
      messages: deleteMessages
    });
  }
  if (updatedAttrs !== null && updatedAttrs !== undefined && Object.keys(updatedAttrs).length > 0) {
    // Flatmap the array, i.e. {key: k, value: [m1, m2]} => [{key: k, value: m1}, {key: k, value: m2}]
    const updateMessages = Object.entries(updatedAttrs).flatMap(([key, value]) => {
      return value.map(val => {
        val.synched = true;
        const timestamp = checkTimestamp(val);
        const result = { key: genKey, value: JSON.stringify(val) };
        if (timestamp !== null) {
          result.timestamp = timestamp;
        }
        return result;
      });
    });
    topicMessages.push({
      topic: config.debeziumBridge.attributesTopic,
      messages: updateMessages
    });
  }
  if (insertedAttrs !== null && insertedAttrs !== undefined && Object.keys(insertedAttrs).length > 0) {
    // Flatmap the array, i.e. {key: k, value: [m1, m2]} => [{key: k, value: m1}, {key: k, value: m2}]
    const insertMessages = Object.entries(insertedAttrs).flatMap(([key, value]) => {
      return value.map(val => {
        val.synched = true;
        const timestamp = checkTimestamp(val);
        const result = { key: genKey, value: JSON.stringify(val) };
        if (timestamp !== null) {
          result.timestamp = timestamp;
        }
        return result;
      });
    });
    topicMessages.push({
      topic: config.debeziumBridge.attributesTopic,
      messages: insertMessages
    });
  }
  await producer.sendBatch({ topicMessages });
};
if (runningAsMain) {
  logger.info('Now starting Kafka listener');
  startListener();
}
