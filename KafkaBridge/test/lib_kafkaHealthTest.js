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
/* global describe it */
'use strict';

const chai = require('chai');
const assert = chai.assert;
const path = require('path');
const fs = require('fs');
const os = require('os');

const KafkaHealth = require('../lib/kafkaHealth.js');

const EVENTS = {
  HEARTBEAT: 'consumer.heartbeat',
  FETCH: 'consumer.fetch',
  END_BATCH_PROCESS: 'consumer.end_batch_process',
  COMMIT_OFFSETS: 'consumer.commit_offsets',
  GROUP_JOIN: 'consumer.group_join',
  CRASH: 'consumer.crash',
  STOP: 'consumer.stop',
  DISCONNECT: 'consumer.disconnect'
};

// Minimal stand-in for a kafkajs consumer: just the event surface KafkaHealth
// subscribes to, plus a way for the test to fire those events.
const fakeConsumer = function () {
  const handlers = {};
  return {
    events: EVENTS,
    on: function (event, handler) {
      if (handlers[event] === undefined) {
        handlers[event] = [];
      }
      handlers[event].push(handler);
    },
    emit: function (event, payload) {
      (handlers[event] || []).forEach(h => h({ payload }));
    }
  };
};

const fakeLogger = function () {
  const errors = [];
  return {
    errors,
    error: function (msg) { errors.push(msg); },
    info: function () {},
    debug: function () {},
    warn: function () {}
  };
};

const tmpFiles = function (name) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `kafkahealth-${name}-`));
  return {
    readyFile: path.join(dir, 'ready'),
    healthyFile: path.join(dir, 'healthy')
  };
};

describe('Test KafkaHealth', function () {
  it('Should write ready and healthy files on start', function () {
    const files = tmpFiles('start');
    const health = new KafkaHealth(fakeConsumer(), fakeLogger(), files);
    health.start();
    assert.equal(fs.readFileSync(files.readyFile, 'utf8'), 'ready');
    assert.equal(fs.readFileSync(files.healthyFile, 'utf8'), 'healthy');
    health.shutdown();
  });

  it('Should exit non-zero and remove the healthy file when the consumer crashes for good', function () {
    const files = tmpFiles('crash');
    const consumer = fakeConsumer();
    const logger = fakeLogger();
    const exits = [];
    const health = new KafkaHealth(consumer, logger,
      Object.assign({ exit: code => exits.push(code) }, files));
    health.start();

    consumer.emit(EVENTS.CRASH, { error: 'boom', restart: false });

    assert.deepEqual(exits, [1]);
    assert.isFalse(fs.existsSync(files.healthyFile), 'healthy file should be gone');
    assert.equal(logger.errors.length, 1);
    assert.include(logger.errors[0], 'boom');
  });

  it('Should stay alive when kafkajs says it will restart the consumer', function () {
    const files = tmpFiles('restart');
    const consumer = fakeConsumer();
    const logger = fakeLogger();
    const exits = [];
    const health = new KafkaHealth(consumer, logger,
      Object.assign({ exit: code => exits.push(code) }, files));
    health.start();

    consumer.emit(EVENTS.CRASH, { error: 'transient', restart: true });

    assert.deepEqual(exits, [], 'a self-healing crash must not kill the process');
    assert.isTrue(fs.existsSync(files.healthyFile));
    assert.include(logger.errors[0], 'transient');
    health.shutdown();
  });

  it('Should exit when the consumer stops or disconnects unexpectedly', function () {
    [EVENTS.STOP, EVENTS.DISCONNECT].forEach(function (event) {
      const files = tmpFiles('stop');
      const consumer = fakeConsumer();
      const exits = [];
      const health = new KafkaHealth(consumer, fakeLogger(),
        Object.assign({ exit: code => exits.push(code) }, files));
      health.start();
      consumer.emit(event);
      assert.deepEqual(exits, [1], `${event} should force a restart`);
      assert.isFalse(fs.existsSync(files.healthyFile));
    });
  });

  it('Should not report a failure when the stop is a graceful shutdown', function () {
    const files = tmpFiles('graceful');
    const consumer = fakeConsumer();
    const exits = [];
    const health = new KafkaHealth(consumer, fakeLogger(),
      Object.assign({ exit: code => exits.push(code) }, files));
    health.start();

    health.shutdown();
    consumer.emit(EVENTS.STOP);
    consumer.emit(EVENTS.DISCONNECT);

    assert.deepEqual(exits, [], 'SIGTERM must not look like a crash');
    assert.isTrue(fs.existsSync(files.healthyFile));
  });

  it('Should exit when the consumer loop goes quiet, and not before', function (done) {
    const files = tmpFiles('watchdog');
    const consumer = fakeConsumer();
    const exits = [];
    const health = new KafkaHealth(consumer, fakeLogger(),
      Object.assign({ staleAfterMs: 40, checkIntervalMs: 10, exit: code => exits.push(code) }, files));
    health.start();

    // Keep the loop ticking across more than one staleness window: a bridge on
    // an idle topic still emits FETCH, and must not be restarted for it.
    const keepAlive = setInterval(() => consumer.emit(EVENTS.FETCH), 10);
    setTimeout(function () {
      assert.deepEqual(exits, [], 'an idle but live consumer must not be restarted');
      clearInterval(keepAlive);
      // Now let it go silent.
      setTimeout(function () {
        assert.deepEqual(exits, [1]);
        assert.isFalse(fs.existsSync(files.healthyFile));
        done();
      }, 90);
    }, 100);
  });

  it('Should report a stopped consumer only once', function () {
    const files = tmpFiles('once');
    const consumer = fakeConsumer();
    const exits = [];
    const health = new KafkaHealth(consumer, fakeLogger(),
      Object.assign({ exit: code => exits.push(code) }, files));
    health.start();
    consumer.emit(EVENTS.STOP);
    consumer.emit(EVENTS.DISCONNECT);
    assert.deepEqual(exits, [1], 'the cascade of stop/disconnect is one failure');
  });
  it('Should survive a crash event that carries no payload', function () {
    const files = tmpFiles('nopayload');
    const consumer = fakeConsumer();
    const logger = fakeLogger();
    const exits = [];
    const health = new KafkaHealth(consumer, logger,
      Object.assign({ exit: code => exits.push(code) }, files));
    health.start();
    // kafkajs normally supplies one, but a malformed event must not turn into a
    // TypeError inside the very handler that is supposed to report failures.
    consumer.emit(consumer.events.CRASH, undefined);
    assert.deepEqual(exits, [1]);
  });

  it('Should work without any options, which is how the bridges construct it', function () {
    const consumer = fakeConsumer();
    // No options at all: the real bridges pass only consumer and logger, so the
    // default file names and windows have to hold up.
    const health = new KafkaHealth(consumer, fakeLogger());
    assert.isFunction(health.start);
    assert.isFunction(health.shutdown);
    health.shutdown();
  });
});
