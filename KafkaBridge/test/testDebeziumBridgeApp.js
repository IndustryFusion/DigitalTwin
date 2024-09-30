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

describe('Test GetTopic', function () {
  it('Should return last part of url path', async function () {
    const getTopic = toTest.__get__('getTopic');
    const result = getTopic('http://example/Device');
    result.should.equal('device');
  });
  it('Should return last part in snake_case', async function () {
    const getTopic = toTest.__get__('getTopic');
    const result = getTopic('http://example/Device_Test_WithUnderscore');
    result.should.equal('device__test__with_underscore');
  });
  it('Should return reference part of url', async function () {
    const getTopic = toTest.__get__('getTopic');
    const result = getTopic('http://example/Device#realDevice');
    result.should.equal('real_device');
  });
  it('Should return snake_case', async function () {
    const getTopic = toTest.__get__('getTopic');
    const result = getTopic('http://example/Device#RealDevice');
    result.should.equal('real_device');
  });
});

describe('Test getSubclasses', function () {
  it('Should construct queryterm and use right rdfSource', async function () {
    const config = {
      debeziumBridge: {
        rdfSources: 'rdfSource'
      }
    };
    const klass = 'klass';
    const queryTermExpected = `
    PREFIX iff: <https://industry-fusion.com/types/v0.9/>
    SELECT ?o WHERE {
    <${klass}> rdfs:subClassOf* ?o.
    } LIMIT 100`;
    const res = {
      bindings: () => new Promise(function (resolve, reject) {
        resolve([
          {
            get: (arg) => { arg.should.equal('?o'); return { value: 'subklass' }; }
          }
        ]);
      })
    };
    const iffEngine = {
      query: function (queryTerm, { sources }) {
        return new Promise(function (resolve, reject) {
          sources.should.equal(config.debeziumBridge.rdfSources);
          queryTerm.should.equal(queryTermExpected);
          resolve(res);
        });
      }
    };
    const revert = toTest.__set__('iffEngine', iffEngine);
    toTest.__set__('config', config);
    const getSubClasses = toTest.__get__('getSubClasses');
    const result = await getSubClasses(klass);
    result[0].should.equal('subklass');
    revert();
  });
});
describe('Test sendUpdates', function () {
  it('Should update and delete attributes', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"deleteValueKey":"deleteValueValue"}' },
      { key: 'id', value: '{"updateValueKey":"updateValueValue"}' }
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
        topicMessages[0].topic.should.equal('topicPrefix.klass');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('topicPrefix.subklass');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
        topicMessages[2].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[2].messages[0], messages[2]);
        topicMessages[3].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[3].messages[0], messages[3]);
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
    const getSubClasses = function () {
      return ['klass', 'subklass'];
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    toTest.__set__('getSubClasses', getSubClasses);
    await sendUpdates({ entity, updatedAttrs, deletedAttrs });
    revert();
  });
  it('Should update and delete attributes with timestamp', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"deleteValueKey":"deleteValueValue"}' },
      { key: 'id', value: '{"updateValueKey":"updateValueValue"}', timestamp: 1672914001456 }
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
        topicMessages[0].topic.should.equal('topicPrefix.klass');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('topicPrefix.subklass');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
        topicMessages[2].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[2].messages[0], messages[2]);
        topicMessages[3].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[3].messages[0], messages[3]);
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
    const getSubClasses = function () {
      return ['klass', 'subklass'];
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    toTest.__set__('getSubClasses', getSubClasses);
    await sendUpdates({ entity, updatedAttrs, deletedAttrs });
    revert();
  });
  it('Should delete entity', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id"}' },
      { key: 'id', value: '{"id":"id"}' }
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
        topicMessages[0].topic.should.equal('topicPrefix.klass');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('topicPrefix.subklass');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
      }
    };

    const deletedEntity = {
      id: 'id',
      type: 'http://example/type'
    };
    const getSubClasses = function () {
      return ['klass', 'subklass'];
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    toTest.__set__('getSubClasses', getSubClasses);
    await sendUpdates({ deletedEntity });
    revert();
  });
  it('Should flatten input arrays of attributes', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      [{ key: 'id', value: '{"deleteValueKey":"deleteValueValue"}' }, { key: 'id', value: '{"deleteValueKey":"deleteValueValue2"}' }],
      [{ key: 'id', value: '{"updateValueKey":"updateValueValue"}' }, { key: 'id', value: '{"updateValueKey":"updateValueValue2"}' }]
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
        topicMessages[0].topic.should.equal('topicPrefix.klass');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('topicPrefix.subklass');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
        topicMessages[2].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[2].messages, messages[2]);
        topicMessages[3].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[3].messages, messages[3]);
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
    const getSubClasses = function () {
      return ['klass', 'subklass'];
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    toTest.__set__('getSubClasses', getSubClasses);
    await sendUpdates({ entity, updatedAttrs, deletedAttrs });
    revert();
  });
  it('Should work without subclasses ', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"deleteValueKey":"deleteValueValue"}' },
      { key: 'id', value: '{"updateValueKey":"updateValueValue"}' }
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
        topicMessages[0].topic.should.equal('topicPrefix.type');
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
    const getSubClasses = function () {
      return [];
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    toTest.__set__('getSubClasses', getSubClasses);
    await sendUpdates({ entity, updatedAttrs, deletedAttrs });
    revert();
  });
  it('Should insert attributes with timestamp', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"insertValueKey":"insertValueValue"}', timestamp: 1704460984123 }
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
        topicMessages[0].topic.should.equal('topicPrefix.klass');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('topicPrefix.subklass');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
        topicMessages[2].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[2].messages[0], messages[2]);
      }
    };
    const entity = {
      id: 'id',
      type: 'http://example/type'
    };
    const insertedAttrs = {
      insertKey: [{ insertValueKey: 'insertValueValue', 'https://uri.etsi.org/ngsi-ld/observedAt': [{ '@value': '2024-01-05T13:23:04.123Z' }] }]
    };

    const getSubClasses = function () {
      return ['klass', 'subklass'];
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    toTest.__set__('getSubClasses', getSubClasses);
    await sendUpdates({ entity, insertedAttrs });
    revert();
  });
  it('Should insert attributes', async function () {
    const messages = [
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"id":"id","type":"http://example/type"}' },
      { key: 'id', value: '{"insertValueKey":"insertValueValue"}' }
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
        topicMessages[0].topic.should.equal('topicPrefix.klass');
        assert.deepEqual(topicMessages[0].messages[0], messages[0]);
        topicMessages[1].topic.should.equal('topicPrefix.subklass');
        assert.deepEqual(topicMessages[1].messages[0], messages[1]);
        topicMessages[2].topic.should.equal('attributesTopic');
        assert.deepEqual(topicMessages[2].messages[0], messages[2]);
      }
    };
    const entity = {
      id: 'id',
      type: 'http://example/type'
    };
    const insertedAttrs = {
      insertKey: [{ insertValueKey: 'insertValueValue' }]
    };

    const getSubClasses = function () {
      return ['klass', 'subklass'];
    };
    const revert = toTest.__set__('producer', producer);
    toTest.__set__('config', config);
    toTest.__set__('getSubClasses', getSubClasses);
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
    const fs = {
      writeFileSync: function (file, message) {
        expect(file).to.satisfy(function (str) {
          if (str === '/tmp/ready' || str === '/tmp/healthy') {
            return true;
          }
        });
        expect(message).to.satisfy(function (str) {
          if (str === 'ready' || str === 'healthy') {
            return true;
          }
        });
      }
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
        await f('Test Error');
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
    toTest.__set__('fs', fs);
    toTest.__set__('config', config);
    toTest.__set__('process', process);
    const startListener = toTest.__get__('startListener');
    await startListener();
    consumerDisconnectSpy.callCount.should.equal(5);
    assert(consumerConnectSpy.calledOnce);
    assert(producerConnectSpy.calledOnce);
    processExitSpy.withArgs(0).callCount.should.equal(2);
    assert(processOnceSpy.calledThrice);
    revert();
  });
});
