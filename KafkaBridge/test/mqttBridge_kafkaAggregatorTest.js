/**
* Copyright (c) 2026 Intel Corporation
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
/* global describe it beforeEach */
'use strict';

const chai = require('chai');
const assert = chai.assert;
const rewire = require('rewire');

const ToTest = rewire('../mqttBridge/sparkplug_data_ingestion.js');

const SPB_TOPIC = 'sparkplugB';
const NGSILD_TOPIC = 'iff.ngsild.attributes';

const config = {
  kafka: { brokers: ['broker:9092'] },
  mqtt: {
    kafka: { requestTimeout: 100, maxRetryTime: 100, retries: 1, linger: 5 },
    sparkplug: { spBkafKaTopic: SPB_TOPIC, ngsildKafkaTopic: NGSILD_TOPIC }
  },
  logger: { loglevel: 'error' }
};

// A producer whose sends can be made to fail on demand, so the tests can ask
// what happened to the messages rather than what was logged.
const fakeProducer = function () {
  return {
    sent: [],
    failing: false,
    events: { CONNECT: 'producer.connect', DISCONNECT: 'producer.disconnect' },
    on: function () {},
    connect: function () { return Promise.resolve(); },
    send: function (payload) {
      if (this.failing) {
        return Promise.reject(new Error('Broker not connected'));
      }
      this.sent.push(payload);
      return Promise.resolve();
    }
  };
};

const buildAggregator = function (producer, onFatal, overrides) {
  const KafkaAggregator = ToTest.__get__('KafkaAggregator');
  const cfg = JSON.parse(JSON.stringify(config));
  Object.assign(cfg.mqtt.kafka, overrides || {});
  const aggregator = new KafkaAggregator(cfg, onFatal);
  aggregator.kafkaProducer = producer;
  aggregator.logger = { info: () => {}, debug: () => {}, warn: () => {}, error: () => {} };
  return aggregator;
};

describe('Test KafkaAggregator delivery', function () {
  let producer;
  let capturedKafkaOptions;

  beforeEach(function () {
    producer = fakeProducer();
    capturedKafkaOptions = {};
    ToTest.__set__('Kafka', function () {
      return {
        producer: function (options) {
          capturedKafkaOptions = options;
          return producer;
        }
      };
    });
  });

  it('Should create an idempotent producer so retries cannot reorder the topic', function () {
    buildAggregator(producer, () => {});
    assert.isTrue(capturedKafkaOptions.idempotent,
      'without idempotence a retried batch can be appended after the batch behind it');
  });

  it('Should keep the messages when the send fails', async function () {
    const aggregator = buildAggregator(producer, () => {});
    aggregator.addMessage({ key: 'k', value: 'v' }, NGSILD_TOPIC);
    producer.failing = true;

    await aggregator.flush();

    assert.equal(producer.sent.length, 0);
    assert.equal(aggregator.ngsildMessageArray.length, 1,
      'a failed batch must survive for the next flush, not vanish with a log line');
  });

  it('Should deliver the kept messages once Kafka comes back', async function () {
    const aggregator = buildAggregator(producer, () => {});
    aggregator.addMessage({ key: 'a', value: '1' }, NGSILD_TOPIC);
    producer.failing = true;
    await aggregator.flush();

    producer.failing = false;
    aggregator.addMessage({ key: 'b', value: '2' }, NGSILD_TOPIC);
    await aggregator.flush();

    assert.equal(producer.sent.length, 1);
    assert.deepEqual(producer.sent[0].messages.map(m => m.key), ['a', 'b'],
      'the retried batch must go out ahead of what arrived while it was in flight');
    assert.equal(aggregator.ngsildMessageArray.length, 0);
  });

  it('Should clear the buffer on a successful send', async function () {
    const aggregator = buildAggregator(producer, () => {});
    aggregator.addMessage({ key: 'k', value: 'v' }, NGSILD_TOPIC);
    await aggregator.flush();
    assert.equal(producer.sent.length, 1);
    assert.equal(aggregator.ngsildMessageArray.length, 0);
  });

  it('Should route each buffer to its own topic', async function () {
    const aggregator = buildAggregator(producer, () => {});
    aggregator.addMessage({ key: 'spb', value: '1' }, SPB_TOPIC);
    aggregator.addMessage({ key: 'ngsild', value: '2' }, NGSILD_TOPIC);
    await aggregator.flush();
    assert.deepEqual(producer.sent.map(p => p.topic), [SPB_TOPIC, NGSILD_TOPIC]);
  });

  it('Should fail the bridge rather than buffer without bound', async function () {
    const fatals = [];
    const aggregator = buildAggregator(producer, r => fatals.push(r), { maxBufferedMessages: 3 });
    producer.failing = true;
    for (let i = 0; i < 3; i++) {
      aggregator.addMessage({ key: String(i), value: 'v' }, NGSILD_TOPIC);
    }
    await aggregator.flush();
    assert.deepEqual(fatals, [], 'at the limit is still fine');

    aggregator.addMessage({ key: 'overflow', value: 'v' }, NGSILD_TOPIC);
    assert.equal(fatals.length, 1, 'past the limit the bridge must say so');
    assert.include(fatals[0], NGSILD_TOPIC);
    assert.include(fatals[0], 'will be lost');
  });

  it('Should not start the next flush before the previous one settles', async function () {
    const aggregator = buildAggregator(producer, () => {});
    let inFlight = 0;
    let maxConcurrent = 0;
    producer.send = function (payload) {
      inFlight += 1;
      maxConcurrent = Math.max(maxConcurrent, inFlight);
      return new Promise(resolve => setTimeout(function () {
        inFlight -= 1;
        resolve();
      }, 30));
    };
    aggregator.start(1);
    const feeder = setInterval(() => aggregator.addMessage({ key: 'k', value: 'v' }, NGSILD_TOPIC), 1);

    await new Promise(resolve => setTimeout(resolve, 150));
    clearInterval(feeder);
    aggregator.stop();

    assert.equal(maxConcurrent, 1,
      'setInterval used to stack a new flush every linger ms regardless of the one in flight');
  });

  it('Should keep flushing after an unexpected error', async function () {
    const aggregator = buildAggregator(producer, () => {});
    let calls = 0;
    const realFlush = aggregator.flush.bind(aggregator);
    aggregator.flush = function () {
      calls += 1;
      if (calls === 1) {
        return Promise.reject(new Error('something unexpected'));
      }
      return realFlush();
    };
    aggregator.start(5);
    aggregator.addMessage({ key: 'k', value: 'v' }, NGSILD_TOPIC);

    await new Promise(resolve => setTimeout(resolve, 60));
    aggregator.stop();

    assert.isAbove(calls, 1, 'one bad flush must not end the flush loop');
    assert.equal(producer.sent.length, 1, 'and the buffered message still has to go out');
  });

  it('Should stop flushing after stop()', async function () {
    const aggregator = buildAggregator(producer, () => {});
    aggregator.start(1);
    aggregator.stop();
    aggregator.addMessage({ key: 'k', value: 'v' }, NGSILD_TOPIC);
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.equal(producer.sent.length, 0);
  });
  it('Should resolve a message only once Kafka has it', async function () {
    const aggregator = buildAggregator(producer, () => {});
    aggregator.start(5);
    let delivered = false;
    let releaseSend = null;
    producer.send = function (payload) {
      this.sent.push(payload);
      return new Promise(resolve => { releaseSend = resolve; });
    };

    const promise = aggregator.addMessage({ key: 'k', value: 'v' }, NGSILD_TOPIC)
      .then(() => { delivered = true; });

    await new Promise(resolve => setTimeout(resolve, 30));
    assert.isFalse(delivered, 'resolving before the broker acknowledged would let the MQTT side ack too early');
    releaseSend();
    await promise;
    assert.isTrue(delivered);
    aggregator.stop();
  });

  it('Should leave a message unresolved while the send keeps failing', async function () {
    const aggregator = buildAggregator(producer, () => {});
    aggregator.start(5);
    producer.failing = true;
    let delivered = false;
    aggregator.addMessage({ key: 'k', value: 'v' }, NGSILD_TOPIC).then(() => { delivered = true; });

    await new Promise(resolve => setTimeout(resolve, 40));
    assert.isFalse(delivered, 'an unresolved message is what keeps the broker holding it');

    producer.failing = false;
    await new Promise(resolve => setTimeout(resolve, 40));
    assert.isTrue(delivered, 'and it must resolve once the broker recovers');
    assert.equal(producer.sent.length, 1);
    aggregator.stop();
  });

  it('Should resolve immediately when awaitDelivery is off', async function () {
    const aggregator = buildAggregator(producer, () => {}, { awaitDelivery: false });
    let delivered = false;
    producer.send = function () { return new Promise(() => {}); };
    aggregator.addMessage({ key: 'k', value: 'v' }, NGSILD_TOPIC).then(() => { delivered = true; });
    await new Promise(resolve => setTimeout(resolve, 10));
    assert.isTrue(delivered, 'the opt-out has to stay non-blocking');
  });

  it('Should fail the bridge when delivery stays stuck', async function () {
    const fatals = [];
    const aggregator = buildAggregator(producer, r => fatals.push(r), { maxDeliveryStallMs: 30 });
    producer.failing = true;
    aggregator.addMessage({ key: 'k', value: 'v' }, NGSILD_TOPIC);
    aggregator.start(5);

    await new Promise(resolve => setTimeout(resolve, 20));
    assert.deepEqual(fatals, [], 'a short outage is not a reason to restart');

    await new Promise(resolve => setTimeout(resolve, 40));
    assert.isAbove(fatals.length, 0, 'a bridge that stopped acknowledging must not sit there looking healthy');
    assert.include(fatals[0], 'nothing delivered to Kafka');
    aggregator.stop();
  });

  it('Should clear the stall clock once delivery succeeds', async function () {
    const fatals = [];
    const aggregator = buildAggregator(producer, r => fatals.push(r), { maxDeliveryStallMs: 40 });
    aggregator.start(5);
    for (let i = 0; i < 6; i++) {
      aggregator.addMessage({ key: String(i), value: 'v' }, NGSILD_TOPIC);
      await new Promise(resolve => setTimeout(resolve, 15));
    }
    assert.deepEqual(fatals, [], 'a bridge that keeps delivering must never be called stalled');
    aggregator.stop();
  });
  it('Should exit by itself when no onFatal was supplied', function () {
    const aggregator = buildAggregator(producer, undefined, { maxBufferedMessages: 1 });
    const realExit = process.exit;
    const exits = [];
    process.exit = code => exits.push(code);
    try {
      aggregator.addMessage({ key: 'a', value: 'v' }, NGSILD_TOPIC);
      aggregator.addMessage({ key: 'b', value: 'v' }, NGSILD_TOPIC);
    } finally {
      process.exit = realExit;
    }
    assert.deepEqual(exits, [1],
      'the default has to be as loud as the wired-up one, or a caller that forgets it loses messages quietly');
  });
});
