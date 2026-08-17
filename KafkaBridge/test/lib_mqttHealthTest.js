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

const MqttHealth = require('../lib/mqttHealth.js');

const fakeBroker = function (connected) {
  return {
    state: connected,
    connected: function () { return this.state; }
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
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `mqtthealth-${name}-`));
  return {
    readyFile: path.join(dir, 'ready'),
    healthyFile: path.join(dir, 'healthy')
  };
};

describe('Test MqttHealth', function () {
  it('Should claim neither probe merely because bind was called', function () {
    const files = tmpFiles('notready');
    const health = new MqttHealth(fakeBroker(false), fakeLogger(),
      Object.assign({ exit: () => {} }, files));
    health.start();
    assert.isFalse(fs.existsSync(files.healthyFile),
      'liveness must wait for the subscription, not for bind() to return');
    assert.isFalse(fs.existsSync(files.readyFile),
      'readiness follows the auth API listening, which start() says nothing about');
    health.shutdown();
  });

  // Readiness is what lets EMQX reach the auth API over the mqtt-bridge
  // Service, and the subscription cannot be authorised until it can. So
  // serving() has to be able to run first, and must not imply liveness.
  it('Should become ready on serving() without claiming to be healthy', function () {
    const files = tmpFiles('serving');
    const health = new MqttHealth(fakeBroker(false), fakeLogger(),
      Object.assign({ exit: () => {} }, files));
    health.start().serving();
    assert.equal(fs.readFileSync(files.readyFile, 'utf8'), 'ready');
    assert.isFalse(fs.existsSync(files.healthyFile),
      'a bridge that is merely serving auth has not proven its input works');
    health.shutdown();
  });

  it('Should still exit when the subscription never arrives after serving', function (done) {
    const files = tmpFiles('serving-then-dead');
    const health = new MqttHealth(fakeBroker(false), fakeLogger(),
      Object.assign({ startupTimeoutMs: 20, exit: () => { done(); } }, files));
    health.start().serving();
  });

  it('Should become ready once the subscription is granted', function () {
    const files = tmpFiles('ready');
    const health = new MqttHealth(fakeBroker(true), fakeLogger(),
      Object.assign({ exit: () => {} }, files));
    health.start().ready();
    assert.equal(fs.readFileSync(files.readyFile, 'utf8'), 'ready');
    assert.equal(fs.readFileSync(files.healthyFile, 'utf8'), 'healthy');
    health.shutdown();
  });

  it('Should exit when the subscription never arrives', function (done) {
    const files = tmpFiles('deadline');
    const logger = fakeLogger();
    const exits = [];
    const health = new MqttHealth(fakeBroker(false), logger,
      Object.assign({ startupTimeoutMs: 30, exit: code => exits.push(code) }, files));
    health.start();
    setTimeout(function () {
      assert.deepEqual(exits, [1]);
      assert.include(logger.errors[0], 'not established');
      health.shutdown();
      done();
    }, 70);
  });

  it('Should not fire the startup deadline once ready', function (done) {
    const files = tmpFiles('deadline-ok');
    const exits = [];
    const health = new MqttHealth(fakeBroker(true), fakeLogger(),
      Object.assign({ startupTimeoutMs: 30, checkIntervalMs: 1000, exit: code => exits.push(code) }, files));
    health.start().ready();
    setTimeout(function () {
      assert.deepEqual(exits, []);
      health.shutdown();
      done();
    }, 70);
  });

  it('Should tolerate a short disconnect and exit on a long one', function (done) {
    const files = tmpFiles('flap');
    const broker = fakeBroker(true);
    const exits = [];
    const health = new MqttHealth(broker, fakeLogger(),
      Object.assign({ graceMs: 60, checkIntervalMs: 10, exit: code => exits.push(code) }, files));
    health.start().ready();

    // A blip mqtt.js repairs by itself must not restart the pod.
    broker.state = false;
    setTimeout(function () { broker.state = true; }, 30);
    setTimeout(function () {
      assert.deepEqual(exits, [], 'a reconnect within the grace window is normal');
      assert.isTrue(fs.existsSync(files.healthyFile));
      // Now stay down past the grace window.
      broker.state = false;
      setTimeout(function () {
        assert.deepEqual(exits, [1]);
        assert.isFalse(fs.existsSync(files.healthyFile));
        done();
      }, 110);
    }, 60);
  });

  it('Should exit when the subscription fails outright', function () {
    const files = tmpFiles('failed');
    const logger = fakeLogger();
    const exits = [];
    const health = new MqttHealth(fakeBroker(false), logger,
      Object.assign({ exit: code => exits.push(code) }, files));
    health.start();
    health.fatal('MQTT subscription failed: ' + new Error('Maximal connection tries reached'));
    assert.deepEqual(exits, [1]);
    assert.include(logger.errors[0], 'Maximal connection tries reached');
  });

  it('Should not report a failure when shutting down gracefully', function (done) {
    const files = tmpFiles('graceful');
    const broker = fakeBroker(true);
    const exits = [];
    const health = new MqttHealth(broker, fakeLogger(),
      Object.assign({ graceMs: 10, checkIntervalMs: 10, exit: code => exits.push(code) }, files));
    health.start().ready();
    health.shutdown();
    broker.state = false;
    setTimeout(function () {
      assert.deepEqual(exits, [], 'SIGTERM must not look like a broker outage');
      done();
    }, 60);
  });
  it('Should ignore a second ready(), so a resubscribe does not stack watchdogs', function (done) {
    const files = tmpFiles('twice');
    const broker = fakeBroker(true);
    const exits = [];
    const health = new MqttHealth(broker, fakeLogger(),
      Object.assign({ graceMs: 20, checkIntervalMs: 5, exit: code => exits.push(code) }, files));
    health.start().ready().ready();
    broker.state = false;
    setTimeout(function () {
      // One watchdog means one report, not one per ready() call.
      assert.equal(exits.length, 1, 'a second ready() must not start a second watchdog');
      done();
    }, 60);
  });
});
