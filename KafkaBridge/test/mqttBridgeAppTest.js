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
const rewire = require('rewire');

const toTest = rewire('../mqttBridge/app.js');

// The point of these: bind() only *starts* connecting, so readiness has to come
// from the subscription callback. config.mqtt.retries is 30000, i.e. a ~12.5h
// connect budget, so the callback is not a fast path either -- the startup
// deadline in mqttHealth is what actually bounds it.
const stubHealth = function () {
  const calls = [];
  const health = {
    calls,
    start: function () { calls.push('start'); return health; },
    ready: function () { calls.push('ready'); return health; },
    fail: function (reason) { calls.push('fail:' + reason); },
    shutdown: function () { calls.push('shutdown'); }
  };
  return health;
};

const runApp = async function (bindBehaviour) {
  const health = stubHealth();
  const captured = {};
  const revert = toTest.__set__({
    MqttHealth: function () { return health; },
    authService: { init: async function () {} },
    SparkplugApiData: function () {
      return {
        init: function () {},
        bind: function (broker, context, callback) {
          captured.callback = callback;
          bindBehaviour(callback);
        }
      };
    },
    process: {
      on: function () {},
      once: function () {},
      exit: function () {},
      env: {},
      kill: function () {}
    }
  });
  const startListener = toTest.__get__('startListener');
  await startListener();
  revert();
  return health;
};

describe('Test mqttBridge app wiring', function () {
  it('Should arm the health watchdog before it can block on the broker', async function () {
    const health = await runApp(function () {});
    assert.equal(health.calls[0], 'start',
      'the startup deadline must be armed first, or a broker that never answers is never noticed');
  });

  it('Should not become ready until the subscription callback succeeds', async function () {
    const health = await runApp(function () {});
    assert.notInclude(health.calls, 'ready',
      'returning from bind() is not evidence of a subscription');
  });

  it('Should become ready when the subscription is granted', async function () {
    const health = await runApp(function (callback) { callback(); });
    assert.include(health.calls, 'ready');
    assert.notInclude(health.calls.join(','), 'fail');
  });

  it('Should report a failure when the subscription errors', async function () {
    const health = await runApp(function (callback) { callback(new Error('Maximal connection tries reached')); });
    assert.include(health.calls.join(','), 'fail:');
    assert.include(health.calls.join(','), 'Maximal connection tries reached');
    assert.notInclude(health.calls, 'ready');
  });
});
