/*
Copyright (c) 2014, Intel Corporation

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
"use strict";
var common = require('../common'),
    Broker = require("../../api/mqtt/connector");

var topic = {
    "metric_topic": "server/metric/{accountid}/{deviceid}",
    "health": "server/devices/{deviceid}/health",
    "health_status": "device/{deviceid}/health"
}

function IoTKitMQTTCloud(conf, broker) {

    var me = this;
    me.client = broker;
    me.type = 'mqtt';
    me.topics = topic;
    me.pubArgs = {
        qos: 1,
        retain: false
    };
}

IoTKitMQTTCloud.prototype.pullActuations = function (data, callback) {
    callback(null);
};

IoTKitMQTTCloud.prototype.data = function (data, callback) {
    var me = this;
    delete data.deviceToken;
    var topic = common.buildPath(me.topics.metric_topic, [data.accountId, data.did]);
    delete data.gatewayId;
    return me.client.publish(topic, data.convertToMQTTPayload(), me.pubArgs, function(err) {
        if (err) {
            return callback({status:1});
        }
        return callback({status:0});
    });
};

IoTKitMQTTCloud.prototype.disconnect = function () {
    var me = this;
    me.client.disconnect();
};

IoTKitMQTTCloud.prototype.updateDeviceInfo = function (deviceInfo) {
    var me = this;
    me.client.updateDeviceInfo(deviceInfo);
};


IoTKitMQTTCloud.prototype.getActualTime = function (callback) {
    callback(null);
};

module.exports.init = function(conf) {
    var broker = Broker.singleton(conf.connector.mqtt);
    return new IoTKitMQTTCloud(conf, broker);
};
