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

const { assert } = require('chai');
const chai = require('chai');
global.should = chai.should();
const expect = chai.expect;
const sinon = require('sinon');
const rewire = require('rewire');
const toTest = rewire('../debeziumBridge/app.js');

describe('Test sendUpdates', function () {
  // carryObservedAt now puts observedAt IN the payload, falling back to the
  // time of receipt when the attribute carries none. Pin that fallback so it is
  // a fixed value rather than differing on every run.
  const FIXED_NOW = 1700000000000;
  beforeEach(function () {
    toTest.__set__('nowMillis', () => FIXED_NOW);
  });

  it('Should update and delete attributes', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"deleteValueKey":"deleteValueValue","deleted":true,"synced":true,"observedAt":"2023-11-14 22:13:20.000"}' },
      { key: 'id', value: '{"updateValueKey":"updateValueValue","synced":true,"observedAt":"2023-11-14 22:13:20.000"}' }
    ];
    const sendUpdates = toTest.__get__('sendUpdates');
    const config = {
      debeziumBridge: {
        attributesTopic: 'attributesTopic',
        entityTopicPrefix: 'topicPrefix'
      }
    };
    const producer = {
      sendBatch: function ({ topicMessages }) {
        topicMessages[0].topic.should.equal('topicPrefix');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
        topicMessages[2].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[2].messages[0], messages[2]);
      }
    };
    const entity = {
      id: 'id',
      type: 'http://example/type'
    };
    const updatedAttrs = {
      updateKey: [{ updateValueKey: 'updateValueValue' }]
    };
    const deletedAttrs = {
      deleteKey: [{ deleteValueKey: 'deleteValueValue' }]
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    await sendUpdates({ entity, updatedAttrs, deletedAttrs });
    revert();
  });
  it('Should update and delete attributes with timestamp', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"deleteValueKey":"deleteValueValue","deleted":true,"synced":true,"observedAt":"2023-11-14 22:13:20.000"}' },
      { key: 'id', value: '{"updateValueKey":"updateValueValue","synced":true,"observedAt":"2023-01-05 10:20:01.456"}' }
    ];
    const sendUpdates = toTest.__get__('sendUpdates');
    const config = {
      debeziumBridge: {
        attributesTopic: 'attributesTopic',
        entityTopicPrefix: 'topicPrefix'
      }
    };
    const producer = {
      sendBatch: function ({ topicMessages }) {
        topicMessages[0].topic.should.equal('topicPrefix');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
        topicMessages[2].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[2].messages[0], messages[2]);
      }
    };
    const entity = {
      id: 'id',
      type: 'http://example/type'
    };
    const updatedAttrs = {
      updateKey: [{ updateValueKey: 'updateValueValue', 'https://uri.etsi.org/ngsi-ld/observedAt': [{ '@value': '2023-01-05T10:20:01.456Z' }] }]
    };
    const deletedAttrs = {
      deleteKey: [{ deleteValueKey: 'deleteValueValue' }]
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    await sendUpdates({ entity, updatedAttrs, deletedAttrs });
    revert();
  });
  it('Should stamp a deleted attribute with the timestamp of the value it deletes', async function () {
    // A delete used to carry no timestamp, so Kafka stamped it with wall-clock
    // while value records are stamped from their observedAt. attributes_view
    // deduplicates ORDER BY ts DESC, so a delete written today outranked every
    // later republication of a value observed in the past, and the attribute
    // stayed invisible to validation for good.
    //
    // Carrying the value's own timestamp makes the two TIE, and a tie goes to
    // whichever arrived last -- so a delete still wins while it is the last
    // word, and a re-creation afterwards wins again.
    //
    // observedAt now stays IN the payload and the record keeps its write-time
    // stamp, so retention -- a wall-clock storage policy -- is no longer applied
    // to an event time. The delete still carries the value's OWN observedAt, so
    // the tie described above is unchanged.
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      {
        key: 'id',
        value: '{"deleteValueKey":"deleteValueValue","deleted":true,"synced":true,"observedAt":"2023-01-05 10:20:01.456"}'
      }
    ];
    const sendUpdates = toTest.__get__('sendUpdates');
    const config = {
      debeziumBridge: {
        attributesTopic: 'attributesTopic',
        entityTopicPrefix: 'topicPrefix'
      }
    };
    let seen = 0;
    const producer = {
      sendBatch: function ({ topicMessages }) {
        seen++;
        topicMessages[0].topic.should.equal('topicPrefix');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
      }
    };
    const entity = {
      id: 'id',
      type: 'http://example/type'
    };
    const deletedAttrs = {
      deleteKey: [{
        deleteValueKey: 'deleteValueValue',
        'https://uri.etsi.org/ngsi-ld/observedAt': [{ '@value': '2023-01-05T10:20:01.456Z' }]
      }]
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    await sendUpdates({ entity, deletedAttrs });
    seen.should.equal(1);
    revert();
  });
  it('Should delete entity', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type","deleted":true}' }
    ];
    const sendUpdates = toTest.__get__('sendUpdates');
    const config = {
      debeziumBridge: {
        attributesTopic: 'attributesTopic',
        entityTopicPrefix: 'topicPrefix'
      }
    };
    const producer = {
      sendBatch: function ({ topicMessages }) {
        topicMessages[0].topic.should.equal('topicPrefix');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
      }
    };

    const deletedEntity = {
      id: 'id',
      type: 'http://example/type'
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    await sendUpdates({ deletedEntity });
    revert();
  });
  it('Should flatten input arrays of attributes', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      [{ key: 'id', value: '{"deleteValueKey":"deleteValueValue","deleted":true,"synced":true,"observedAt":"2023-11-14 22:13:20.000"}' }, { key: 'id', value: '{"deleteValueKey":"deleteValueValue2","deleted":true,"synced":true,"observedAt":"2023-11-14 22:13:20.000"}' }],
      [{ key: 'id', value: '{"updateValueKey":"updateValueValue","synced":true,"observedAt":"2023-11-14 22:13:20.000"}' }, { key: 'id', value: '{"updateValueKey":"updateValueValue2","synced":true,"observedAt":"2023-11-14 22:13:20.000"}' }]
    ];
    const sendUpdates = toTest.__get__('sendUpdates');
    const config = {
      debeziumBridge: {
        attributesTopic: 'attributesTopic',
        entityTopicPrefix: 'topicPrefix'
      }
    };
    const producer = {
      sendBatch: function ({ topicMessages }) {
        topicMessages[0].topic.should.equal('topicPrefix');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[1].messages, messages[1]);
        topicMessages[2].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[2].messages, messages[2]);
      }
    };
    const entity = {
      id: 'id',
      type: 'http://example/type'
    };
    const updatedAttrs = {
      updateKey: [{ updateValueKey: 'updateValueValue' }, { updateValueKey: 'updateValueValue2' }]
    };
    const deletedAttrs = {
      deleteKey: [{ deleteValueKey: 'deleteValueValue' }, { deleteValueKey: 'deleteValueValue2' }]
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    await sendUpdates({ entity, updatedAttrs, deletedAttrs });
    revert();
  });
  it('Should work without subclasses ', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"deleteValueKey":"deleteValueValue","deleted":true,"synced":true,"observedAt":"2023-11-14 22:13:20.000"}' },
      { key: 'id', value: '{"updateValueKey":"updateValueValue","synced":true,"observedAt":"2023-11-14 22:13:20.000"}' }
    ];
    const sendUpdates = toTest.__get__('sendUpdates');
    const config = {
      debeziumBridge: {
        attributesTopic: 'attributesTopic',
        entityTopicPrefix: 'topicPrefix'
      }
    };
    const producer = {
      sendBatch: function ({ topicMessages }) {
        topicMessages[0].topic.should.equal('topicPrefix');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
        topicMessages[2].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[2].messages[0], messages[2]);
      }
    };
    const entity = {
      id: 'id',
      type: 'http://example/type'
    };
    const updatedAttrs = {
      updateKey: [{ updateValueKey: 'updateValueValue' }]
    };
    const deletedAttrs = {
      deleteKey: [{ deleteValueKey: 'deleteValueValue' }]
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    await sendUpdates({ entity, updatedAttrs, deletedAttrs });
    revert();
  });
  it('Should insert attributes with timestamp', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"insertValueKey":"insertValueValue","synced":true,"observedAt":"2024-01-05 13:23:04.123"}' }
    ];
    const sendUpdates = toTest.__get__('sendUpdates');
    const config = {
      debeziumBridge: {
        attributesTopic: 'attributesTopic',
        entityTopicPrefix: 'topicPrefix'
      }
    };
    const producer = {
      sendBatch: function ({ topicMessages }) {
        topicMessages[0].topic.should.equal('topicPrefix');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
      }
    };
    const entity = {
      id: 'id',
      type: 'http://example/type'
    };
    const insertedAttrs = {
      insertKey: [{ insertValueKey: 'insertValueValue', 'https://uri.etsi.org/ngsi-ld/observedAt': [{ '@value': '2024-01-05T13:23:04.123Z' }] }]
    };

    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    await sendUpdates({ entity, insertedAttrs });
    revert();
  });
  it('Should insert attributes', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"insertValueKey":"insertValueValue","synced":true,"observedAt":"2023-11-14 22:13:20.000"}' }
    ];
    const sendUpdates = toTest.__get__('sendUpdates');
    const config = {
      debeziumBridge: {
        attributesTopic: 'attributesTopic',
        entityTopicPrefix: 'topicPrefix'
      }
    };
    const producer = {
      sendBatch: function ({ topicMessages }) {
        topicMessages[0].topic.should.equal('topicPrefix');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
      }
    };
    const entity = {
      id: 'id',
      type: 'http://example/type'
    };
    const insertedAttrs = {
      insertKey: [{ insertValueKey: 'insertValueValue' }]
    };

    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    await sendUpdates({ entity, insertedAttrs });
    revert();
  });
});

describe('Test startListener', function () {
  it('Setup Kafka listener, readiness and health status', async function () {
    const consumer = {
      run: function (run) {
        return new Promise(function (resolve, reject) {
          resolve();
        });
      },
      connect: function () {},
      subscribe: function (obj) {
        obj.topic.should.equal('topic');
        obj.fromBeginning.should.equal(false);
      },
      disconnect: function () {
      }
    };
    const producer = {
      connect: function () {}
    };
    // The bridges now hand their liveness files to KafkaHealth, which needs a
    // consumer that can report on its own state. Stub it out here so this test
    // keeps exercising the app wiring rather than the watchdog -- the watchdog has
    // its own test in lib_kafkaHealthTest.js.
    const KafkaHealth = function () {
      return { start: function () {}, shutdown: function () {} };
    };
    const config = {
      debeziumBridge: {
        topic: 'topic'
      }
    };
    const process = {
      on: async function (type, f) {
        expect(type).to.satisfy(function (type) {
          if (type === 'unhandledRejection' || type === 'uncaughtException') {
            return true;
          }
        });
        await f('Test Error output');
      },
      exit: function (value) {
      },
      once: async function (type, f) {
        await f('Test Error');
      }
    };
    const consumerDisconnectSpy = sinon.spy(consumer, 'disconnect');
    const consumerConnectSpy = sinon.spy(consumer, 'connect');
    const producerConnectSpy = sinon.spy(producer, 'connect');
    const processExitSpy = sinon.spy(process, 'exit');
    const processOnceSpy = sinon.spy(process, 'once');
    const revert = toTest.__set__('consumer', consumer);
    toTest.__set__('producer', producer);
    toTest.__set__('KafkaHealth', KafkaHealth);
    toTest.__set__('config', config);
    toTest.__set__('process', process);
    const startListener = toTest.__get__('startListener');
    await startListener();
    consumerDisconnectSpy.callCount.should.equal(5);
    assert(consumerConnectSpy.calledOnce);
    assert(producerConnectSpy.calledOnce);
    processExitSpy.withArgs(1).callCount.should.equal(2);
    assert(processOnceSpy.calledThrice);
    revert();
  });
});
