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
const common = require('./common');
const ConnectionManager = require('./ConnectionManager');

const topic = {
  metric_topic: '{namespace}/{group_id}/{message_type}/{edge_node_id}/{deviceid}',
  health: 'server/devices/{deviceid}/health',
  health_status: 'device/{deviceid}/health'
};

// Sequence number increase
let seq = 0;

const incSeqNum = function () {
  if (seq === 255) {
    seq = 0;
    return seq;
  }
  seq++;
  return seq;
};

/* Create  Metrics for the Edge Node Birth
*  with SparkplugB default standard metrics and its values based on config file client data
*/

const createNodeBirthMetrics = function (clientData) {
  const metrics = [{
    name: 'bdseq',
    timestamp: new Date().getTime(),
    dataType: 'Uint64',
    value: 0
  }, {
    name: 'Node Control/Reboot',
    timestamp: new Date().getTime(),
    dataType: 'Boolean',
    value: false
  }, {
    name: 'Node Control/Rebirth',
    timestamp: new Date().getTime(),
    dataType: 'Boolean',
    value: false
  }, {
    name: 'Properties/HardwareModel',
    timestamp: new Date().getTime(),
    dataType: 'String',
    value: clientData.hwVersion || 'HWDefaultv1.0'
  }, {
    name: 'Properties/AgentVersion',
    timestamp: new Date().getTime(),
    dataType: 'String',
    value: clientData.swVersion || 'SWDefaultv1.0'
  }];

  return metrics;
};

class SparkplugbConnector {
  constructor (conf, logger) {
    this.logger = logger;
    this.spbConf = conf.connector.mqtt;
    this.type = 'mqtt';
    this.topics = topic;
    this.pubArgs = {
      qos: 1,
      retain: false
    };
    this.client = new ConnectionManager(conf.connector.mqtt, logger);
  }

  async init () {
    await this.client.init();
  }

  /* For publishing sparkplugB standard Node Birth message
    * @devProf: Conatains all the device information and default component registered with
    *   its component ids
    * Payload for device birth is by default created in function createNodeBirthMetrics
    */
  async nodeBirth (devProf) {
    const topic = common.buildPath(this.topics.metric_topic, [this.spbConf.version, devProf.groupId, 'NBIRTH', devProf.edgeNodeId, '']);
    const clientData = {
      hwVersion: null,
      swVersion: null
    };
    const payload = {
      timestamp: new Date().getTime(),
      metrics: createNodeBirthMetrics(clientData),
      seq: 0
    };

    return await this.client.publish(topic, payload, this.pubArgs);
  };

  /* For publishing sparkplugB standard device BIRTH message
    * @devProf: Contains all the device information and default component registered with
    *   its component ids
    * Payload for device birth is in device profile componentMetric
    */
  async deviceBirth (devProf) {
    const topic = common.buildPath(this.topics.metric_topic, [this.spbConf.version, devProf.groupId, 'DBIRTH', devProf.edgeNodeId, devProf.deviceId]);
    const payload = {
      timestamp: new Date().getTime(),
      metrics: devProf.componentMetric,
      seq: incSeqNum()
    };
    return await this.client.publish(topic, payload, this.pubArgs);
  };

  /* For publishing sparkplugB standard device DATA message
    * @devProf: Contains all the device information and default component registered with
    *   its component ids
    * @payloadMetric: Contains submitted data value in spB metric format to be sent to server
    */
  publishData = async function (devProf, payloadMetric) {
    const topic = common.buildPath(this.topics.metric_topic, [this.spbConf.version, devProf.groupId, 'DDATA', devProf.edgeNodeId, devProf.deviceId]);
    const payload = {
      timestamp: new Date().getTime(),
      metrics: payloadMetric,
      seq: incSeqNum()
    };
    await this.client.publish(topic, payload, this.pubArgs);
  };

  disconnect = function () {
    this.client.disconnect();
  };

  updateDeviceInfo = function (deviceInfo) {
    const me = this;
    me.client.updateDeviceInfo(deviceInfo);
  };

  healthResponse = function (device, callback, syncCallback) {
    const me = this;
    const healthStatus = common.buildPath(me.topics.health_status, device);
    const handler = function (topic, message) {
      me.client.unbind(healthStatus);
      callback(message);
    };
    me.client.bind(healthStatus, handler, syncCallback);
  };

  /* health = function (device, callback) {
    const me = this;
    me.healthResponse(device, callback, function (err) {
      if (!err) {
        const topic = common.buildPath(me.topics.health, device);
        const data = { detail: 'mqtt' };
        me.client.publish(topic, data, me.pubArgs);
        callback(1);
      } else {
        callback(0);
      }
    });
  }; */

  setCredential = function (user, password) {
    const me = this;
    me.crd = {
      username: user || '',
      password: password || ''
    };

    me.client.setCredential(me.crd);
  };

  connected () {
    if (this.client) {
      return this.client.connected() || false;
    }
    return false;
  }
}

module.exports = SparkplugbConnector;
