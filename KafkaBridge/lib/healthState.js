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
'use strict';

const fs = require('fs');

const READY_FILE = '/tmp/ready';
const HEALTHY_FILE = '/tmp/healthy';

/**
 * The liveness/readiness files every bridge exposes, plus the one way they are
 * allowed to fail.
 *
 * Shared so a Kafka bridge and the MQTT bridge report a broken input the same
 * way: remove /tmp/healthy and exit non-zero. Which conditions count as broken
 * is up to the caller -- see kafkaHealth.js and mqttHealth.js.
 *
 * @param {object} logger - winston-style logger
 * @param {object} options - readyFile, healthyFile, exit (optional, for tests)
 */
module.exports = function HealthState (logger, options) {
  const opts = options || {};
  const readyFile = opts.readyFile || READY_FILE;
  const healthyFile = opts.healthyFile || HEALTHY_FILE;
  const exit = opts.exit || function (code) { process.exit(code); };

  let shuttingDown = false;
  const cleanups = [];

  const runCleanups = function () {
    while (cleanups.length > 0) {
      cleanups.pop()();
    }
  };

  return {
    /** Register a timer to stop when the bridge fails or shuts down. */
    addCleanup: function (fn) {
      cleanups.push(fn);
    },

    /** Declare the bridge up. Only call once the input is genuinely working. */
    up: function () {
      fs.writeFileSync(readyFile, 'ready');
      fs.writeFileSync(healthyFile, 'healthy');
    },

    /**
     * Report a broken input. Idempotent, because one failure usually arrives as
     * a cascade of events, and because a bridge that is already on its way down
     * should not log the same thing five times.
     */
    fail: function (reason) {
      if (shuttingDown) {
        return;
      }
      shuttingDown = true;
      logger.error(`Bridge unhealthy: ${reason}. Exiting to force a restart.`);
      runCleanups();
      try {
        fs.unlinkSync(healthyFile);
      } catch (err) {
        // Failing before ever becoming healthy is the normal startup-failure
        // path, so a missing file here is expected, not another problem.
        if (err.code !== 'ENOENT') {
          logger.error(`Could not remove ${healthyFile}: ${err}`);
        }
      }
      exit(1);
    },

    /**
     * Mark an intentional shutdown, so the disconnect events a graceful stop
     * produces are not reported as a failure.
     */
    shutdown: function () {
      shuttingDown = true;
      runCleanups();
    },

    isShuttingDown: function () {
      return shuttingDown;
    }
  };
};
