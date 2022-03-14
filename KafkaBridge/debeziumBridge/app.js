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
const newEngine = require('@comunica/actor-init-sparql-file').newEngine;
const iffEngine = newEngine();
const runningAsMain = require.main === module;

const debeziumBridge = new DebeziumBridge(config);
const logger = new Logger(config);

const kafka = new Kafka({
  clientId: CLIENTID,
  brokers: config.kafka.brokers
});

const consumer = kafka.consumer({ groupId: GROUPID });
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
        sendUpdates({ entity: result.entity, deletedEntity: result.deletedEntity, updatedAttrs: result.updatedAttrs, deletedAttrs: result.deletedAttrs });
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

/**
 *
 * @param klass {string} - a RDF klass
 * @returns {array<string>} RDF subclasses of klass, e.g.
 *                          'plasmacutter' => cutter, device
 */
const getSubClasses = async function (klass) {
  // TODO: needs caching
  const queryTerm = `
    PREFIX iff: <https://industry-fusion.com/types/v0.9/>
    SELECT ?o WHERE {
    <${klass}> rdfs:subClassOf* ?o.
    } LIMIT 100`;

  const result = await iffEngine.query(queryTerm, {
    sources: config.debeziumBridge.rdfSources
  });
  const bindings = await result.bindings();
  const subClasses = bindings.reduce((accum, element) => { accum.push(element.get('?o').value); return accum; }, []);
  return subClasses;
};

/**
 * returns type-part of uri, e.g. https://test/Device => Device
 * @param topic {string}
 * @returns
 */
const getTopic = function (topic) {
  return topic.match(/([^/]*)$/)[0];
};

/**
 * send batch of ngsild updates from debezium to respective kafka/sql topic
 * @param entity {object}- the entity object
 * @param updateAttrs {object} - contains the list of attributes of the entity which are changed
 * @param deleteAttrs {object} - contains the list of attributes of the entity which have to be deleted
 * @returns
 */
const sendUpdates = async function ({ entity, deletedEntity, updatedAttrs, deletedAttrs }) {
  let removeType = false;

  if (deletedEntity !== undefined && deletedEntity !== null) {
    entity = deletedEntity;
    removeType = true;
  }
  if (entity === null || entity.id === undefined || entity.id === null || entity.type === undefined || entity.type === null) {
    return;
  }
  const genKey = entity.id;
  let subClasses = await getSubClasses(entity.type);
  if (subClasses.length === 0) {
    subClasses = [entity.type];
  }
  const topicMessages = [];

  if (removeType) {
    // delete of entities is done by set everything to NULL
    delete entity.type;
  }

  subClasses.forEach((element) => {
    const obj = {};
    const entityTopic = config.debeziumBridge.entityTopicPrefix + '.' + getTopic(element);
    obj.topic = entityTopic;
    obj.messages = [{
      key: genKey,
      value: JSON.stringify(entity)
    }];
    topicMessages.push(obj);
  });

  if (deletedAttrs !== null && deletedAttrs !== undefined && Object.keys(deletedAttrs).length > 0) {
    // Flatmap the array, i.e. {key: k, value: [m1, m2]} => [{key: k, value: m1}, {key: k, value: m2}]
    const deleteMessages = Object.entries(deletedAttrs).flatMap(([key, value]) =>
      value.map(val => {
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
    const updateMessages = Object.entries(updatedAttrs).flatMap(([key, value]) =>
      value.map(val => {
        return { key: genKey, value: JSON.stringify(val) };
      })
    );
    topicMessages.push({
      topic: config.debeziumBridge.attributesTopic,
      messages: updateMessages
    });
  }

  await producer.sendBatch({ topicMessages });
};
if (runningAsMain) {
  logger.info('Now starting Kafka listener');
  startListener();
}
