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
const { Kafka } = require('kafkajs');
const config = require('../config/config.json');
const DebeziumBridge = require('../lib/debeziumBridge.js');
const Logger = require('../lib/logger.js');
const KafkaHealth = require('../lib/kafkaHealth.js');
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
  const health = new KafkaHealth(consumer, logger);
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

// observedAt is DATA; the Kafka record timestamp is TRANSPORT metadata. They
// used to be the same field, which meant retention.ms -- a storage policy
// measured against the record timestamp -- was being applied to an event time.
// The kms model observes at 2024-02-28, so every attribute record was born two
// and a half years older than any sane retention and Kafka deleted it on
// contact. Measured: three snapshot bursts of 249 records each, and
// iff.ngsild.attributes read back with logStart == logEnd every time. The
// pipeline still looked healthy because the job consumes records in flight --
// but there was no replay, no restart recovery and no way to observe anything.
//
// So observedAt now travels IN the payload and the record keeps its write-time
// stamp. Event-time semantics are unchanged: attributes_view still orders by
// observedAt, so which value wins is still decided by when it was observed and
// never by when it arrived.
//
// The wire format is a SQL timestamp -- 'YYYY-MM-DD HH:MM:SS.mmm' in UTC --
// because that is what Flink's json format parses by default, and what SQLite
// compares lexicographically in the oracle. An ISO string with 'T' and 'Z'
// would fail Flink's parse and, with json.ignore-parse-errors, become NULL
// without a word. Epoch millis would parse, but the SPARQL rules compare
// observedAt against xsd:dateTime literals, so it has to be a timestamp.
// A seam for the fallback below, so tests can pin it rather than mock the
// global clock -- the same rewire pattern the tests already use for config and
// producer.
const nowMillis = function () { return Date.now(); };

const asSqlTimestamp = function (millis) {
  return new Date(millis).toISOString().replace('T', ' ').replace('Z', '');
};

const carryObservedAt = function (val) {
  let observedAt = null;
  try {
    observedAt = new Date(val['https://uri.etsi.org/ngsi-ld/observedAt'][0]['@value']).getTime();
    delete (val['https://uri.etsi.org/ngsi-ld/observedAt']);
  } catch (err) {}
  // An attribute carrying no observedAt is observed when it is received. That
  // is what Kafka's own stamp meant before, so the ordering is unchanged.
  // Leaving it null instead would make such an attribute lose every comparison
  // in the dedup and disappear.
  val.observedAt = asSqlTimestamp(
    (observedAt !== null && !isNaN(observedAt)) ? observedAt : nowMillis());
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
    //
    // A delete carries the timestamp of the value it deletes, exactly as an
    // update does -- the LAST KNOWN timestamp of that attribute.
    //
    // It used to carry none, so Kafka stamped it with wall-clock while value
    // records are stamped from their observedAt. attributes_view deduplicates
    // ORDER BY ts DESC, so a delete written today outranked every later
    // republication of a value observed in the past and the attribute stayed
    // invisible for good. Measured: a delete at offset 581438 carrying
    // 2026-08-16 beat the values at 581453, 581705 and 581955, all carrying
    // 2024-02-28, and urn:filter:1 was reported as having no hasStrength
    // although it has one.
    //
    // Giving the delete the same timestamp as the value makes the two tie, and
    // a tie is broken by arrival order -- so the delete still wins while it is
    // the last word, and a re-creation afterwards wins again. Deliberately the
    // SAME timestamp and not one millisecond later: later would make the
    // delete unbeatable by a re-creation observed at the same instant, which
    // is the case this has to get right.
    const deleteMessages = Object.entries(deletedAttrs).flatMap(([key, value]) =>
      value.map(val => {
        val.deleted = true;
        val.synced = true;
        // Also strips observedAt from the payload, so the message on the wire
        // is unchanged from before.
        carryObservedAt(val);
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
        val.synced = true;
        carryObservedAt(val);
        return { key: genKey, value: JSON.stringify(val) };
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
        val.synced = true;
        carryObservedAt(val);
        return { key: genKey, value: JSON.stringify(val) };
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
