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

const HealthState = require('./healthState.js');

/**
 * Ties the MQTT bridge's liveness file to its subscription actually existing.
 *
 * Same failure shape as the Kafka bridges, reached by a different route. The
 * MQTT bridge used to write /tmp/ready and /tmp/healthy immediately after
 * calling bind(), but bind() only *starts* connecting: the broker connection is
 * retried for up to retries*1500ms in the background and its failure was
 * reported through a callback nobody passed. So the pod went Ready within
 * milliseconds whether or not it ever subscribed, and a bridge that never
 * connected forwarded nothing while looking perfectly healthy.
 *
 * Two detectors:
 *   - a startup deadline, so never coming up is a failure rather than a wait;
 *   - a connection watchdog, since mqtt.js reconnects silently on its own and a
 *     permanently refused reconnect (expired credentials, revoked ACL) is
 *     otherwise indistinguishable from an idle broker.
 *
 * The watchdog polls rather than listening for 'close', because a disconnect
 * that mqtt.js immediately repairs is normal and must not restart the pod.
 * Only being down continuously for longer than graceMs counts.
 *
 * @param {object} broker - lib/mqtt_connector Broker (needs connected())
 * @param {object} logger - winston-style logger
 * @param {object} options - startupTimeoutMs, graceMs, checkIntervalMs,
 *                           readyFile, healthyFile, exit (optional, for tests)
 */
module.exports = function MqttHealth (broker, logger, options) {
  const opts = options || {};
  // Must outlast Broker.connect's own retry budget (max_retries * 1500ms,
  // 45s by default), otherwise this fires while the connector is still
  // legitimately retrying.
  const startupTimeoutMs = opts.startupTimeoutMs || 120000;
  // mqtt.js reconnects every second by default; 60s is a long outage, not a blip.
  const graceMs = opts.graceMs || 60000;
  const checkIntervalMs = opts.checkIntervalMs || 10000;
  const state = new HealthState(logger, opts);

  let subscribed = false;
  let lastConnected = Date.now();

  return {
    /**
     * Start the startup deadline. Call before binding, so a bind that never
     * completes is caught.
     */
    start: function () {
      const deadline = setTimeout(function () {
        if (!subscribed) {
          state.fail(`MQTT subscription not established within ${Math.round(startupTimeoutMs / 1000)}s`);
        }
      }, startupTimeoutMs);
      state.addCleanup(function () {
        clearTimeout(deadline);
      });
      return this;
    },

    /**
     * The subscription is granted and messages can flow. This -- not the call
     * to bind() -- is what makes the bridge ready.
     */
    ready: function () {
      if (subscribed) {
        return this;
      }
      subscribed = true;
      lastConnected = Date.now();
      state.up();
      logger.info('MQTT bridge is ready: subscription established.');

      const watchdog = setInterval(function () {
        if (broker.connected()) {
          lastConnected = Date.now();
          return;
        }
        const down = Date.now() - lastConnected;
        if (down > graceMs) {
          state.fail(`MQTT broker connection down for ${Math.round(down / 1000)}s`);
        } else {
          logger.warn(`MQTT broker connection is down, waiting for mqtt.js to reconnect (${Math.round(down / 1000)}s)`);
        }
      }, checkIntervalMs);
      state.addCleanup(function () {
        clearInterval(watchdog);
      });
      return this;
    },

    /**
     * Anything that means the bridge can no longer do its job -- the
     * subscription never came up, or the Kafka side can no longer guarantee
     * delivery. Reported the same way as a dead broker connection.
     */
    fatal: function (reason) {
      state.fail(reason);
    },

    shutdown: function () {
      state.shutdown();
    }
  };
};
