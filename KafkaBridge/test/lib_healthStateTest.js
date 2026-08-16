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

const HealthState = require('../lib/healthState.js');

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
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `healthstate-${name}-`));
  return {
    dir,
    readyFile: path.join(dir, 'ready'),
    healthyFile: path.join(dir, 'healthy')
  };
};

describe('Test HealthState', function () {
  it('Should write both files on up and remove only the healthy one on fail', function () {
    const files = tmpFiles('updown');
    const exits = [];
    const state = new HealthState(fakeLogger(),
      Object.assign({ exit: code => exits.push(code) }, files));
    state.up();
    assert.isTrue(fs.existsSync(files.readyFile));
    assert.isTrue(fs.existsSync(files.healthyFile));

    state.fail('because');

    assert.deepEqual(exits, [1]);
    assert.isFalse(fs.existsSync(files.healthyFile), 'liveness must fail');
    assert.isTrue(fs.existsSync(files.readyFile),
      'readiness is left alone: the pod is going away, not being taken out of service');
  });

  it('Should not complain that the healthy file is missing when it never became healthy', function () {
    const files = tmpFiles('never-up');
    const logger = fakeLogger();
    const state = new HealthState(logger, Object.assign({ exit: () => {} }, files));
    // No up() first -- this is the normal startup-failure path.
    state.fail('failed before ever being ready');
    assert.equal(logger.errors.length, 1, 'the failure itself, and no noise about a missing file');
    assert.include(logger.errors[0], 'failed before ever being ready');
  });

  it('Should report a healthy file it genuinely cannot remove', function () {
    const files = tmpFiles('unremovable');
    const logger = fakeLogger();
    // A directory where the file should be: unlink refuses with something that
    // is not ENOENT, which is worth saying out loud.
    fs.mkdirSync(files.healthyFile);
    const state = new HealthState(logger, Object.assign({ exit: () => {} }, files));
    state.fail('some reason');
    assert.equal(logger.errors.length, 2);
    assert.include(logger.errors[1], 'Could not remove');
  });

  it('Should run cleanups on fail and on shutdown', function () {
    ['fail', 'shutdown'].forEach(function (method) {
      const files = tmpFiles('cleanup-' + method);
      const state = new HealthState(fakeLogger(), Object.assign({ exit: () => {} }, files));
      let cleaned = 0;
      state.addCleanup(() => { cleaned += 1; });
      state.addCleanup(() => { cleaned += 1; });
      state[method]('reason');
      assert.equal(cleaned, 2, `${method} must stop the timers it was given`);
    });
  });

  it('Should report only the first failure', function () {
    const files = tmpFiles('once');
    const logger = fakeLogger();
    const exits = [];
    const state = new HealthState(logger, Object.assign({ exit: code => exits.push(code) }, files));
    state.up();
    state.fail('first');
    state.fail('second');
    assert.deepEqual(exits, [1]);
    assert.equal(logger.errors.length, 1);
    assert.include(logger.errors[0], 'first');
  });

  it('Should stay quiet when a shutdown is followed by a failure report', function () {
    const files = tmpFiles('shutdown-first');
    const logger = fakeLogger();
    const exits = [];
    const state = new HealthState(logger, Object.assign({ exit: code => exits.push(code) }, files));
    state.up();
    state.shutdown();
    state.fail('disconnect during SIGTERM');
    assert.deepEqual(exits, [], 'a graceful stop must not be reported as a crash');
    assert.deepEqual(logger.errors, []);
  });
});
