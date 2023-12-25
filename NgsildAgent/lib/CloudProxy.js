/*
Copyright (c) 2014, 2023 Intel Corporation

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

'use strict';

const jwtDecoder = require('jwt-decode');
const common = require('./common');
const conf = require('../config');
const http = require('http');
const querystring = require('querystring');
const SparkplugbConnector = require('./SparkplugbConnector');
const ConnectionError = require('./ConnectionError');

function updateToken (token) {
  const parsedToken = JSON.parse(token);
  common.saveToDeviceConfig('device_token', parsedToken.access_token);
  common.saveToDeviceConfig('refresh_token', parsedToken.refresh_token);
}

function updateSecrets (me) {
  const deviceConf = common.getDeviceConfig();
  me.spBProxy.updateDeviceInfo(deviceConf);
  me.secret = {
    deviceToken: deviceConf.device_token,
    refreshToken: deviceConf.refresh_token,
    refreshUrl: deviceConf.keycloak_url + '/' + deviceConf.realm_id,
    deviceTokenExpire: deviceConf.device_token_expire
  };
  return deviceConf;
}

function refreshToken (me) {
  return new Promise(function (resolve, reject) {
    const deviceConf = common.getDeviceConfig();
    const data = querystring.stringify({
      client_id: 'device',
      refresh_token: deviceConf.refresh_token,
      orig_token: deviceConf.device_token,
      grant_type: 'refresh_token',
      audience: 'device'
    });
    const myURL = new URL(me.secret.refreshUrl);
    const myHostname = myURL.hostname;
    const myPath = myURL.pathname + '/protocol/openid-connect/token';
    const options = {
      hostname: myHostname,
      path: myPath,
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(data),
        'X-GatewayID': me.gatewayId,
        'X-DeviceID': me.deviceId
      }
    };

    const req = http.request(options, res => {
      let data = '';

      res.on('data', chunk => {
        data += chunk;
      });

      res.on('end', () => {
        if (res.statusCode === 200) {
          resolve(data);
        } else {
          reject(data);
        }
      });
    })
      .on('error', err => {
        console.log('Error: ', err.message);
        reject(err.message);
      });

    req.write(data);
    req.end();
  });
}

class CloudProxy {
  constructor (logger, deviceId) {
    const deviceConf = common.getDeviceConfig();
    this.logger = logger;
    this.birthMsgStatus = false;
    this.secret = {
      deviceToken: deviceConf.device_token,
      refreshToken: deviceConf.refresh_token,
      refreshUrl: deviceConf.keycloak_url + '/' + deviceConf.realm_id,
      deviceTokenExpire: deviceConf.device_token_expire
    };
    this.max_retries = deviceConf.activation_retries || 10;
    this.deviceId = deviceId;
    this.deviceName = deviceConf.device_name;
    this.gatewayId = deviceConf.gateway_id || deviceId;
    this.activationCode = deviceConf.activation_code;
    if (conf.connector.mqtt !== undefined && conf.connector.mqtt.sparkplugB !== undefined) {
      this.spbMetricList = [];
      this.devProf = {
        groupId: deviceConf.realm_id,
        edgeNodeId: deviceConf.gateway_id,
        clientId: deviceConf.device_name,
        deviceId: deviceConf.device_id,
        componentMetric: this.spbMetricList
      };
      this.spBProxy = new SparkplugbConnector(conf, logger);
      this.logger.info('SparkplugB MQTT proxy found! Configuring  Sparkplug and MQTT for data sending.');
      if (deviceConf.device_token && this.spBProxy !== undefined) {
        this.spBProxy.updateDeviceInfo(deviceConf);
      } else {
        this.logger.info('No credentials found for MQTT. Please check activation.');
        process.exit(1);
      }
    } else {
      this.logger.error('Could not start MQTT Proxy. Please check configuraiton. Bye!');
      process.exit(1);
    }
  }

  async init () {
    try {
      await this.spBProxy.init();
    } catch (err) {
      if (err instanceof ConnectionError && err.errno === 1) {
        this.logger.error('SparkplugB MQTT NBIRTH Metric not sent. Trying to refresh token.');
        await this.checkDeviceToken();
        return 1;
      } else { // unrecoverable
        this.logger.error('Unexpected Error: ' + err.stack);
        return 2;
      }
    }
    try {
      await this.spBProxy.nodeBirth(this.devProf);
    } catch (err) {
      if (err instanceof ConnectionError && err.errno === 1) {
        this.logger.error('SparkplugB MQTT NBIRTH Metric not sent. Trying to refresh token.');
        await this.checkDeviceToken();
        return 1;
      } else { // unrecoverable
        this.logger.error('Unexpected Error: ' + err.stack);
        return 2;
      }
    }
    this.logger.info('SparkplugB MQTT NBIRTH Metric sent succesfully for eonid: ' + this.gatewayId);
    this.logger.debug('SparkplugB MQTT DBIRTH Metric: ' + this.spbMetricList);
    try {
      await this.spBProxy.deviceBirth(this.devProf);
    } catch (err) {
      this.logger.error('SparkplugB MQTT DBIRTH Metric not sent. Check connection and token: ' + err.stack);
      return 2;
    }
    this.birthMsgStatus = true;
    this.logger.info('SparkplugB MQTT DBIRTH Metric sent succesfully for device: ' + this.deviceId);
    return 0;
  };

  async checkDeviceToken () {
    if (!this.secret.deviceTokenExpire) {
      this.secret.deviceTokenExpire = jwtDecoder(this.secret.deviceToken).exp * 1000; // convert to miliseconds
    }

    if (new Date().getTime() < this.secret.deviceTokenExpire) {
      return 0;
    } else {
      this.logger.info('Device token has expired - refreshing it now...');
      const data = await refreshToken(this);
      try {
        await updateToken(data);
        const deviceConf = await updateSecrets(this);
        this.spBProxy.updateDeviceInfo(deviceConf);
        await this.spBProxy.init();
      } catch (err) {
        this.logger.error('Could not refresh token: ' + err.message);
      }
    }
  };

  async dataSubmit (metric) {
    const me = this;
    function getCompMetric (metric) {
      const compMetric = {};
      compMetric.value = metric.v;
      compMetric.name = metric.n;
      compMetric.dataType = 'string';
      compMetric.timestamp = metric.on || new Date().getTime();
      return compMetric;
    }
    // await me.checkDeviceToken();
    if (!me.birthMsgStatus) {
      throw (new Error('Session is not initialized.'));
    } else {
      const componentMetrics = [];
      if (Array.isArray(metric)) {
        metric.forEach(item => {
          componentMetrics.push(getCompMetric(item));
        });
        // Check if we have any data left to submit
      } else {
        componentMetrics.push(getCompMetric(metric));
      }
      if (componentMetrics.length === 0) {
        me.logger.error(' SPB Data submit - no data to submit.');
        return;
      }
      me.logger.debug('SparkplugB MQTT DDATA Metric: ' + componentMetrics);
      me.logger.debug('SparkplugB MQTT device profile: ' + me.devProf);

      await me.spBProxy.publishData(me.devProf, componentMetrics);
      me.logger.info('SparkplugB MQTT DDATA Metric sent successfully');
    }
  };

  async checkOnlineState () {
    this.checkDeviceToken(); // await or not await, that's the question. Do you want delay a sample because it is stuck in refreshing?
    if (this.spBProxy) {
      return this.spBProxy.connected() || false;
    }
    return false;
  }
}

module.exports = CloudProxy;
