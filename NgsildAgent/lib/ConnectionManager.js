/**
* Copyright (c) 2023 Intel Corporation
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
const mqtt = require('mqtt');
const ConnectionError = require('./ConnectionError');

const MQTT = 'mqtt://';
const MQTT_SECURE = 'mqtts://';
const WEBSOCKETS = 'ws://';
const WEBSOCKETS_SECURE = 'wss://';

class ConnectionManager {
  constructor (conf, logger) {
    this.host = conf.host;
    this.port = conf.port;
    this.websockets = conf.websockets;
    this.secure = conf.secure;
    this.keepalive = conf.keepalive || 60;
    this.max_retries = conf.retries || 30;
    this.messageHandler = [];
    this.pubArgs = {
      qos: conf.qos || 1,
      retain: conf.retain
    };
    this.isLive = false;
    this.deviceInfo = {};
    this.logger = logger;
  }

  async init () {
    let protocol = MQTT;
    if (this.secure) {
      protocol = MQTT_SECURE;
    }
    if (this.websockets) {
      if (this.secure) {
        protocol = WEBSOCKETS_SECURE;
      } else {
        protocol = WEBSOCKETS;
      }
    }
    const url = protocol + this.host + ':' + this.port;
    try {
      if (this.client) {
        await this.client.endAsync();
      }
      this.client = await mqtt.connectAsync(url, {
        username: this.deviceInfo.device_id,
        password: this.deviceInfo.device_token,
        rejectUnauthorized: false
      });
    } catch (err) {
      this.logger.info('MQTT connection error: ' + err.message);
      throw this.createConnectionError(err);
    }
    const me = this;
    function connect (ack) {
      me.logger.info('MQTT session connected: ' + JSON.stringify(ack));
    }
    function reconnect () {
      me.logger.info('Trying to reconnect MQTT session.');
    }
    function offline () {
      me.logger.info('MQTT Session is offline.');
    }
    function error (error) {
      me.logger.info('MQTT Error: ' + error.message);
    }
    function end () {
      me.logger.info('Ended MQTT Session.');
    }
    this.client.on('connect', connect);
    this.client.on('reconnect', reconnect);
    this.client.on('offline', offline);
    this.client.on('error', error);
    this.client.on('end', end);
    this.authorized = true;
  }

  async publish (topic, message, options) {
    await this.client.publishAsync(topic, JSON.stringify(message), options);
    return 0;
  };

  connected () {
    if (this.client !== undefined) {
      return this.client.connected;
    } else {
      return false;
    }
  };

  authorized () {
    return this.authorized || false;
  }

  createConnectionError (err) {
    let connerr;
    if (err.errno === -111) {
      connerr = new ConnectionError(err.message, 0);
    }
    if (err.code === 5) {
      connerr = new ConnectionError(err.message, 1);
    }
    if (connerr) {
      return connerr;
    }
    return err;
  }

  updateDeviceInfo (deviceInfo) {
    this.deviceInfo = deviceInfo;
  };
}

module.exports = ConnectionManager;
