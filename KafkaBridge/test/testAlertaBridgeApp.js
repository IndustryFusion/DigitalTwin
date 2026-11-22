/**
* Copyright (c) 2026 IndustryFusion Foundation
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
const sinon = require('sinon');
const rewire = require('rewire');

const TOPIC = 'iff.alerts';

const logger = {
  debug: function () {},
  info: function () {},
  error: function () {}
};

const config = {
  kafka: { brokers: [] },
  alerta: {
    topic: TOPIC,
    kafkaResumeTimeout: 0,
    requestTimeout: 100,
    heartbeatInterval: 0
  }
};

// The group's committed offsets, shared by every incarnation of the bridge, as
// Kafka keeps them across restarts. Per partition, the next offset to read.
const createGroup = function () {
  return { committed: {} };
};

// A kafkajs consumer double: run() hands back eachMessage, commitOffsets()
// records what the bridge commits into the group.
const createConsumer = function (group) {
  const consumer = {
    runOptions: null,
    commits: [],
    connect: async function () {},
    subscribe: async function () {},
    disconnect: async function () {},
    pause: sinon.spy(),
    resume: sinon.spy(),
    run: async function (options) {
      consumer.runOptions = options;
    },
    commitOffsets: async function (offsets) {
      offsets.forEach(({ topic, partition, offset }) => {
        consumer.commits.push({ topic, partition, offset });
        group.committed[partition] = offset;
      });
    }
  };
  sinon.spy(consumer, 'commitOffsets');
  return consumer;
};

const record = function (offset, body) {
  return {
    offset: String(offset),
    value: Buffer.from(typeof body === 'string' ? body : JSON.stringify(body))
  };
};

const alertBody = function (n) {
  return { resource: 'resource' + n, event: 'event' + n, severity: 'critical' };
};

// Start one incarnation of the bridge on the given consumer.
const startBridge = async function (consumer, sendAlert) {
  const toTest = rewire('../alerta/app.js');
  toTest.__set__('consumer', consumer);
  toTest.__set__('config', config);
  toTest.__set__('logger', logger);
  toTest.__set__('alerta', { sendAlert });
  toTest.__set__('KafkaHealth', function () {
    return { start: function () {}, shutdown: function () {} };
  });
  toTest.__set__('process', { on: function () {}, once: function () {}, exit: function () {} });
  await toTest.__get__('startListener')();
  return consumer.runOptions.eachMessage;
};

// What kafkajs does for one partition: read from the committed offset on,
// in order, and stop at the first record whose handler throws.
const consumeFrom = async function (eachMessage, group, partition, log) {
  const start = group.committed[partition] === undefined ? 0 : Number(group.committed[partition]);
  for (const message of log.filter(m => Number(m.offset) >= start)) {
    try {
      await eachMessage({ topic: TOPIC, partition, message });
    } catch (e) {
      return message.offset;
    }
  }
  return null;
};

const lastCommit = function (consumer, partition) {
  const commits = consumer.commits.filter(c => c.partition === partition);
  return commits.length === 0 ? undefined : commits[commits.length - 1];
};

describe('alerta bridge commits what it has posted', function () {
  it('commits the next offset after a successful post', async function () {
    const group = createGroup();
    const consumer = createConsumer(group);
    const sendAlert = sinon.stub().resolves({ statusCode: 201, body: {} });
    const eachMessage = await startBridge(consumer, sendAlert);

    await eachMessage({ topic: TOPIC, partition: 3, message: record(5, alertBody(5)) });

    assert(sendAlert.calledOnce);
    assert.deepEqual(lastCommit(consumer, 3), { topic: TOPIC, partition: 3, offset: '6' });
    consumer.runOptions.autoCommit.should.equal(false);
  });

  it('commits past a record that Alerta rejects for good (400, 415)', async function () {
    for (const code of [400, 415]) {
      const group = createGroup();
      const consumer = createConsumer(group);
      const sendAlert = sinon.stub().resolves({
        statusCode: code,
        body: { status: 'error', code, message: 'bad alert' }
      });
      const eachMessage = await startBridge(consumer, sendAlert);

      await eachMessage({ topic: TOPIC, partition: 0, message: record(7, alertBody(7)) });

      assert.deepEqual(lastCommit(consumer, 0), { topic: TOPIC, partition: 0, offset: '8' }, `status ${code}`);
    }
  });

  it('commits past a record with an unknown severity', async function () {
    const group = createGroup();
    const consumer = createConsumer(group);
    const sendAlert = sinon.stub().resolves({
      statusCode: 500,
      body: { status: 'error', code: 500, message: "Severity (bogus) is not one of 'critical', 'major'" }
    });
    const eachMessage = await startBridge(consumer, sendAlert);

    await eachMessage({ topic: TOPIC, partition: 0, message: record(2, alertBody(2)) });

    assert.deepEqual(lastCommit(consumer, 0), { topic: TOPIC, partition: 0, offset: '3' });
  });

  it('commits past a record without resource or event, or that is not JSON', async function () {
    const group = createGroup();
    const consumer = createConsumer(group);
    const sendAlert = sinon.stub().resolves({ statusCode: 201, body: {} });
    const eachMessage = await startBridge(consumer, sendAlert);

    await eachMessage({ topic: TOPIC, partition: 0, message: record(10, { resource: '', event: 'e' }) });
    assert.deepEqual(lastCommit(consumer, 0), { topic: TOPIC, partition: 0, offset: '11' });
    await eachMessage({ topic: TOPIC, partition: 0, message: record(11, { resource: 'r', event: '' }) });
    assert.deepEqual(lastCommit(consumer, 0), { topic: TOPIC, partition: 0, offset: '12' });
    await eachMessage({ topic: TOPIC, partition: 0, message: record(12, 'not json') });
    assert.deepEqual(lastCommit(consumer, 0), { topic: TOPIC, partition: 0, offset: '13' });
    sinon.assert.notCalled(sendAlert);
  });

  it('keeps a record that failed to post and is retried uncommitted (5xx)', async function () {
    const group = createGroup();
    const consumer = createConsumer(group);
    const sendAlert = sinon.stub();
    sendAlert.onFirstCall().resolves({ statusCode: 201, body: {} });
    sendAlert.onSecondCall().resolves({ statusCode: 503, body: { status: 'error', code: 503, message: 'unavailable' } });
    const eachMessage = await startBridge(consumer, sendAlert);

    await eachMessage({ topic: TOPIC, partition: 0, message: record(4, alertBody(4)) });
    let error = null;
    await eachMessage({ topic: TOPIC, partition: 0, message: record(5, alertBody(5)) })
      .catch(e => { error = e; });

    assert.isNotNull(error, 'the failed post is handed back to kafkajs to retry');
    sinon.assert.calledWith(consumer.pause, [{ topic: TOPIC }]);
    // The committed offset points to the failed record: it is read again, and
    // the record before it, which was posted, is not.
    group.committed[0].should.equal('5');
    consumer.commits.forEach(c => Number(c.offset).should.be.at.most(5));
  });

  it('keeps a record uncommitted when the post itself fails', async function () {
    const group = createGroup();
    const consumer = createConsumer(group);
    const sendAlert = sinon.stub();
    sendAlert.onFirstCall().resolves({ statusCode: 201, body: {} });
    sendAlert.onSecondCall().rejects(new Error('ECONNREFUSED'));
    const eachMessage = await startBridge(consumer, sendAlert);

    await eachMessage({ topic: TOPIC, partition: 0, message: record(0, alertBody(0)) });
    let error = null;
    await eachMessage({ topic: TOPIC, partition: 0, message: record(1, alertBody(1)) })
      .catch(e => { error = e; });

    assert.isNotNull(error);
    sinon.assert.calledWith(consumer.pause, [{ topic: TOPIC }]);
    group.committed[0].should.equal('1');
  });

  it('keeps going when a commit fails, without posting the record again', async function () {
    const group = createGroup();
    const consumer = createConsumer(group);
    consumer.commitOffsets = sinon.stub().rejects(new Error('rebalancing'));
    const sendAlert = sinon.stub().resolves({ statusCode: 201, body: {} });
    const eachMessage = await startBridge(consumer, sendAlert);

    // Throwing here would make kafkajs hand the record over again and post it twice.
    await eachMessage({ topic: TOPIC, partition: 0, message: record(0, alertBody(0)) });
    sinon.assert.calledOnce(sendAlert);
  });

  it('a restart after fewer records than a batch posts no record a second time', async function () {
    const group = createGroup();
    const log = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => record(n, alertBody(n)));
    const posted = [];
    const sendAlert = sinon.spy(async function (body) {
      posted.push(body.resource);
      return { statusCode: 201, body: {} };
    });

    // First run: the bridge posts the first five records, then is restarted.
    let eachMessage = await startBridge(createConsumer(group), sendAlert);
    await consumeFrom(eachMessage, group, 0, log.slice(0, 5));
    assert.equal(group.committed[0], '5', 'the five posted records are committed');

    // Second run: a new consumer of the same group resumes at the committed offset.
    eachMessage = await startBridge(createConsumer(group), sendAlert);
    await consumeFrom(eachMessage, group, 0, log);

    assert.deepEqual(posted, log.map((m, n) => 'resource' + n), 'every record posted exactly once');
    // Nothing left to read: the group's lag is 0.
    assert.equal(group.committed[0], String(log.length));
  });

  it('a restart after a retried failure posts the failed record, not the ones before it', async function () {
    const group = createGroup();
    const log = [0, 1, 2, 3].map(n => record(n, alertBody(n)));
    const posted = [];
    let fail = true;
    const sendAlert = sinon.spy(async function (body) {
      if (body.resource === 'resource2' && fail) {
        fail = false;
        return { statusCode: 502, body: { status: 'error', code: 502, message: 'bad gateway' } };
      }
      posted.push(body.resource);
      return { statusCode: 201, body: {} };
    });

    let eachMessage = await startBridge(createConsumer(group), sendAlert);
    const failedAt = await consumeFrom(eachMessage, group, 0, log);
    failedAt.should.equal('2');

    eachMessage = await startBridge(createConsumer(group), sendAlert);
    await consumeFrom(eachMessage, group, 0, log);

    assert.deepEqual(posted, ['resource0', 'resource1', 'resource2', 'resource3']);
    group.committed[0].should.equal('4');
  });
});

describe('alerta bridge lifecycle', function () {
  it('disconnects on an unhandled error and on a signal', async function () {
    const toTest = rewire('../alerta/app.js');
    const consumer = createConsumer(createGroup());
    sinon.spy(consumer, 'disconnect');
    const handlers = {};
    const process = {
      pid: 42,
      on: function (type, f) { handlers[type] = f; },
      once: function (type, f) { handlers[type] = f; },
      exit: sinon.spy(),
      kill: sinon.spy()
    };
    const health = { start: sinon.spy(), shutdown: sinon.spy() };
    toTest.__set__('consumer', consumer);
    toTest.__set__('config', config);
    toTest.__set__('logger', logger);
    toTest.__set__('KafkaHealth', function () { return health; });
    toTest.__set__('process', process);
    toTest.__set__('console', { log: function () {}, error: function () {} });
    await toTest.__get__('startListener')();
    sinon.assert.calledOnce(health.start);

    await handlers.unhandledRejection(new Error('boom'));
    await handlers.uncaughtException(new Error('boom'));
    sinon.assert.calledTwice(process.exit);
    sinon.assert.alwaysCalledWith(process.exit, 1);

    await handlers.SIGTERM();
    sinon.assert.calledWith(process.kill, 42, 'SIGTERM');
    sinon.assert.calledThrice(consumer.disconnect);
  });

  it('sends a heartbeat every interval and keeps going when a send fails', async function () {
    const clock = sinon.useFakeTimers({ now: 100000, toFake: ['setInterval', 'Date'] });
    try {
      const toTest = rewire('../alerta/app.js');
      const producer = { connect: sinon.stub().resolves(), send: sinon.stub() };
      producer.send.onFirstCall().resolves();
      producer.send.onSecondCall().rejects(new Error('no broker'));
      toTest.__set__('producer', producer);
      toTest.__set__('logger', logger);
      toTest.__set__('config', {
        alerta: { heartbeatInterval: 1000, heartbeatDelay: 2000, heartbeatTopic: 'iff.alerts.bulk' }
      });
      await toTest.__get__('startPeriodicProducer')();
      await clock.tickAsync(2000);
      sinon.assert.calledTwice(producer.send);
      const sent = producer.send.firstCall.args[0];
      sent.topic.should.equal('iff.alerts.bulk');
      sent.messages[0].timestamp.should.equal(String(101000 - 2000));
    } finally {
      clock.restore();
    }
  });

  it('sends no heartbeat when the interval is 0', async function () {
    const toTest = rewire('../alerta/app.js');
    const producer = { connect: sinon.spy() };
    toTest.__set__('producer', producer);
    toTest.__set__('config', { alerta: { heartbeatInterval: 0 } });
    await toTest.__get__('startPeriodicProducer')();
    sinon.assert.notCalled(producer.connect);
  });
});

describe('alerta bridge delivers every record at least once', function () {
  it('commits a record only after its post has returned', async function () {
    const group = createGroup();
    const consumer = createConsumer(group);
    let answer;
    const sendAlert = sinon.stub().returns(new Promise(resolve => { answer = resolve; }));
    const eachMessage = await startBridge(consumer, sendAlert);

    const handled = eachMessage({ topic: TOPIC, partition: 0, message: record(3, alertBody(3)) });
    await new Promise(resolve => setImmediate(resolve));
    sinon.assert.calledOnce(sendAlert);
    sinon.assert.notCalled(consumer.commitOffsets);
    assert.isUndefined(group.committed[0], 'nothing committed while the post is under way');

    answer({ statusCode: 201, body: {} });
    await handled;
    assert.equal(group.committed[0], '4');
  });

  it('posts a record again after a crash during its post, and nothing before it', async function () {
    const group = createGroup();
    const log = [0, 1, 2, 3].map(n => record(n, alertBody(n)));
    const posted = [];
    let crashed = false;
    const sendAlert = sinon.spy(async function (body) {
      if (body.resource === 'resource2' && !crashed) {
        crashed = true;
        throw new Error('process killed during the post');
      }
      posted.push(body.resource);
      return { statusCode: 201, body: {} };
    });

    let eachMessage = await startBridge(createConsumer(group), sendAlert);
    await consumeFrom(eachMessage, group, 0, log);
    assert.equal(group.committed[0], '2', 'the record whose post did not return stays uncommitted');

    eachMessage = await startBridge(createConsumer(group), sendAlert);
    await consumeFrom(eachMessage, group, 0, log);
    assert.deepEqual(posted, ['resource0', 'resource1', 'resource2', 'resource3'], 'no record lost');
  });

  it('posts only that one record again after a crash between its post and its commit', async function () {
    const group = createGroup();
    const log = [0, 1, 2, 3, 4].map(n => record(n, alertBody(n)));
    const posted = [];
    const sendAlert = sinon.spy(async function (body) {
      posted.push(body.resource);
      return { statusCode: 201, body: {} };
    });

    // First run: record 2 is posted, then the process dies before its commit
    // reaches Kafka. Records 3 and 4 are never handled.
    const consumer = createConsumer(group);
    const commit = consumer.commitOffsets;
    consumer.commitOffsets = async function (offsets) {
      if (offsets[0].offset === '3') {
        throw new Error('killed before the commit');
      }
      return commit(offsets);
    };
    let eachMessage = await startBridge(consumer, sendAlert);
    await consumeFrom(eachMessage, group, 0, log.slice(0, 3));
    assert.equal(group.committed[0], '2');

    eachMessage = await startBridge(createConsumer(group), sendAlert);
    await consumeFrom(eachMessage, group, 0, log);

    // At least once: record 2 is posted twice, every other record once.
    assert.deepEqual(posted, ['resource0', 'resource1', 'resource2', 'resource2', 'resource3', 'resource4']);
    assert.equal(group.committed[0], '5');
  });
});
