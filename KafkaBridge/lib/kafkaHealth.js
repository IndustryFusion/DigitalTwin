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
 * Ties a bridge's liveness file to its Kafka consumer actually consuming.
 *
 * The bridges' liveness probe is `cat /tmp/healthy`. That file used to be
 * written once at startup and never touched again, so a consumer that died
 * afterwards left a permanently Ready pod that forwarded nothing. Observed on
 * alerta-bridge: its consumer group went to Empty/0 members while the separate
 * heartbeat producer kept logging success every second, so both the logs and
 * the probes looked fine and SHACL alerts stopped reaching Alerta.
 *
 * Two independent detectors, because kafkajs only reports some of the ways a
 * consumer can stop:
 *   - CRASH/STOP/DISCONNECT events, which kafkajs does emit and nobody listened
 *     for;
 *   - a watchdog over the consumer's own loop, for stalls it does not report at
 *     all (a lost `resume` timer, a rebalance that never completes).
 *
 * Both end the process with a non-zero exit so the pod restarts, and remove
 * /tmp/healthy first so the liveness probe also fails if the exit is somehow
 * swallowed. Keeping the staleness logic here rather than in the probe command
 * means the existing `cat /tmp/healthy` charts need no change.
 *
 * @param {object} consumer - a kafkajs consumer
 * @param {object} logger - winston-style logger
 * @param {object} options - staleAfterMs, checkIntervalMs, readyFile,
 *                           healthyFile, exit (all optional, for tests)
 */
module.exports = function KafkaHealth (consumer, logger, options) {
  const opts = options || {};
  // Idle bridges are normal, so the window has to clear the quietest signal
  // the consumer emits by itself. kafkajs fetches on a loop even with no
  // traffic (maxWaitTimeInMs defaults to 5s), so 90s is ~18 missed cycles.
  const staleAfterMs = opts.staleAfterMs || 90000;
  const checkIntervalMs = opts.checkIntervalMs || 10000;
  const readyFile = opts.readyFile || READY_FILE;
  const healthyFile = opts.healthyFile || HEALTHY_FILE;
  const exit = opts.exit || function (code) { process.exit(code); };

  let lastAlive = Date.now();
  let watchdog = null;
  let shuttingDown = false;

  const markAlive = function () {
    lastAlive = Date.now();
  };

  const unhealthy = function (reason) {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    logger.error(`Kafka consumer unhealthy: ${reason}. Exiting to force a restart.`);
    if (watchdog !== null) {
      clearInterval(watchdog);
      watchdog = null;
    }
    try {
      fs.unlinkSync(healthyFile);
    } catch (err) {
      logger.error(`Could not remove ${healthyFile}: ${err}`);
    }
    exit(1);
  };

  // Every sign of life from the consumer's own loop. FETCH and HEARTBEAT keep
  // ticking on an idle topic, so a bridge that legitimately sees no messages is
  // not mistaken for a dead one.
  [
    consumer.events.HEARTBEAT,
    consumer.events.FETCH,
    consumer.events.END_BATCH_PROCESS,
    consumer.events.COMMIT_OFFSETS,
    consumer.events.GROUP_JOIN
  ].forEach(function (event) {
    consumer.on(event, markAlive);
  });

  consumer.on(consumer.events.CRASH, function (e) {
    const payload = (e && e.payload) || {};
    if (payload.restart) {
      // kafkajs recovers by itself here. Say so, but do not kill the process --
      // if the restart does not actually bring the loop back, the watchdog below
      // notices within staleAfterMs.
      logger.error(`Kafka consumer crashed, kafkajs will restart it: ${payload.error}`);
      return;
    }
    unhealthy(`consumer crashed and will not restart: ${payload.error}`);
  });

  consumer.on(consumer.events.STOP, function () {
    unhealthy('consumer stopped');
  });

  consumer.on(consumer.events.DISCONNECT, function () {
    unhealthy('consumer disconnected');
  });

  return {
    /**
     * Declare the bridge up and start the watchdog. Call once the consumer is
     * running, i.e. where the bridges used to write the two files.
     */
    start: function () {
      fs.writeFileSync(readyFile, 'ready');
      fs.writeFileSync(healthyFile, 'healthy');
      markAlive();
      watchdog = setInterval(function () {
        const age = Date.now() - lastAlive;
        if (age > staleAfterMs) {
          unhealthy(`no consumer activity for ${Math.round(age / 1000)}s`);
        }
      }, checkIntervalMs);
      return this;
    },

    /**
     * Mark an intentional shutdown, so the STOP/DISCONNECT that a graceful
     * `consumer.disconnect()` emits is not reported as a failure.
     */
    shutdown: function () {
      shuttingDown = true;
      if (watchdog !== null) {
        clearInterval(watchdog);
        watchdog = null;
      }
    }
  };
};
