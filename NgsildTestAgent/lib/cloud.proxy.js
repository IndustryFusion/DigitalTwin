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

var jwtDecoder = require('jwt-decode'),
    common = require('./common'),
    conf = require('../config'),
    proxyConnector = require('@open-iot-service-platform/oisp-sdk-js')(conf).lib.proxies.getProxyConnector();
    spBConnector = require('@open-iot-service-platform/oisp-sdk-js')(conf).lib.proxies.getSpBConnector();

function IoTKitCloud(logger, deviceId, customProxy) {
    var deviceConf = common.getDeviceConfig();
    var me = this;
    me.logger = logger;
    me.birthMsgStatus = false;
    me.secret = {'accountId' : deviceConf['account_id'],
                 'deviceToken' : deviceConf['device_token'],
                 'refreshToken' : deviceConf['refresh_token'],
                 'deviceTokenExpire': deviceConf['device_token_expire']};
    me.proxy = customProxy || proxyConnector; // For rest connection to get token and update device
    me.spBProxy = spBConnector;
    me.max_retries = deviceConf.activation_retries || 10;
    me.deviceId = deviceId;
    me.deviceName = deviceConf.device_name;
    me.gatewayId = deviceConf.gateway_id || deviceId;
    me.activationCode = deviceConf.activation_code;
    me.logger.info("Cloud Proxy created with Cloud Handler: " + me.proxy.type);
    
    //set sparkplugBmqtt proxy by default
    me.refreshDevProf();
    if (deviceConf.device_token && me.spBProxy != undefined) {
        me.spBProxy.updateDeviceInfo(deviceConf);
    } else {
        me.logger.info("No credentials found for MQTT");
        me.spBProxy = undefined;
    }
    if (me.spBProxy != undefined ) { 
        /** 
        *  Sending Birth message for SparkplugB (of node/agent and for device),
        * As per standard Birth message is mandatory to send on start before sending Data
        */
        me.spBProxy.nodeBirth(me.devProf, function(err) {
            if (err === "fail") {
                me.logger.error("SparkplugB MQTT NBIRTH Metric not sent");
                me.spBProxy = undefined;
            } else {
                me.logger.info("SparkplugB MQTT NBIRTH Metric sent succesfully for eonid: %j ", me.gatewayId);
                me.sendDevBirthMsg(function(response) {
                    if (response) {
                        me.logger.debug("SparkplugB MQTT DBIRTH Metric sent: %j", me.spbMetricList);
                    }
                });
            }                                        
        });       
    }
       
}

IoTKitCloud.prototype.checkDeviceToken = function (callback) {
    var me = this,
        toCall = callback;
    
    if (!me.secret.deviceTokenExpire) {
        me.secret.deviceTokenExpire = jwtDecoder(me.secret.deviceToken).exp * 1000; // convert to miliseconds
    }

    if (new Date().getTime() < me.secret.deviceTokenExpire) {
        return toCall();
    } else {
        me.logger.info('Device token has expired - refreshing it now...');
        var data = {
            token: me.secret.deviceToken,
            body: {
                refreshToken: me.secret.refreshToken
            }
        };
        return me.proxy.client.auth.refreshAuthToken(data, function(err, res) {
            if (err) {
                me.logger.error('Cannot refresh the device token - exiting: ' + err);
                process.exit(1);
            } else {
                me.secret.deviceToken = res.jwt;
                me.secret.refreshToken = res.refreshToken;
                me.secret.deviceTokenExpire = jwtDecoder(res.jwt).exp * 1000;
                me.logger.info('Saving new device and refresh tokens...');
                common.saveToDeviceConfig('device_token', me.secret.deviceToken);
                common.saveToDeviceConfig('refresh_token', me.secret.refreshToken);
                common.saveToDeviceConfig('device_token_expire', me.secret.deviceTokenExpire);
                me.setDeviceCredentials();
                return toCall();
            }
        });
    }
};


IoTKitCloud.prototype.setDeviceCredentials = function() {
    var me = this;
    me.proxy.setCredential(me.deviceId, me.secret.deviceToken);
};

IoTKitCloud.prototype.disconnect = function () {
    var me = this;
    me.proxy.disconnect();
};

IoTKitCloud.prototype.refreshDevProf = function() {
    let me = this;
    me.spbMetricList = [];
    let deviceConf = common.getDeviceConfig();
    deviceConf['attribute_list'].forEach(comp => {                      
                var compMetric = {
                    "name" : comp.name,
                    "timestamp" : new Date().getTime(),
                    "dataType" : "string",
                    "value" : 0
                }
                me.spbMetricList.push(compMetric);      
    });
    me.devProf = {
        groupId   : deviceConf['realm_id'],
        edgeNodeId : deviceConf['gateway'],
        clientId   : deviceConf['device_name'],
        deviceId   : deviceConf['device_id'],         
        componentMetric : me.spbMetricList
    };
};

IoTKitCloud.prototype.prepareSpbMetric = function(data) {
    let me = this;
    let compMetric = me.spbMetricList.find(element => element.alias === data.alias);
    if (!compMetric) {
        return null;
    }
    compMetric.value = data.v;
    compMetric.timestamp = data.on || new Date().getTime();
    return compMetric;
};

IoTKitCloud.prototype.sendDevBirthMsg = function(callback) {
    var me = this;
    me.refreshDevProf();
    me.birthMsgStatus = false;
    me.spBProxy.deviceBirth(me.devProf, function(response) {
        if (response === "fail") {
            me.logger.error("SparkplugB MQTT DBIRTH Metric not sent");
            me.spBProxy = undefined;
            return callback(me.birthMsgStatus);
        } else {
            me.birthMsgStatus = true;
            me.logger.info("SparkplugB MQTT updated DBIRTH Metric sent succesfully for device: %j ", me.deviceId);
            return callback(me.birthMsgStatus);
        }
    });
};

IoTKitCloud.prototype.dataSubmit = function (metric, callback) {
    var me = this; 
    var handler = function() {
        // SparkplugB format data submission to sdk
        let timecount = 0;
        if (me.spBProxy != undefined) {
            let checkFlag = function () {
                if ( !me.birthMsgStatus ) {
                    setTimeout(checkFlag, 250)  /* this checks the flag every 250 milliseconds*/
                    if (timecount == 40) {  /* return if birthmsgstatus not true for 10 seconds */
                        return callback("timeout");
                    }
                    timecount++;
                } else {
                    var componentMetrics = [];        

                    if (Array.isArray(metric)) {
                        metric.forEach(item => {
                            let compMetric = me.prepareSpbMetric(item);
                            if (compMetric) {
                                componentMetrics.push(compMetric);
                            }
                        })
                        // Check if we have any data left to submit
                        if (componentMetrics.length === 0) {
                            me.logger.error(' SPB Data submit - no data to submit.');
                            return callback(false);
                        }
                    } else {
                        let compMetric = me.prepareSpbMetric(metric);
                        if (compMetric) {
                            componentMetrics.push(compMetric); 
                        } else {
                            me.logger.error('Data submission - could not find alias in stored metric');
                            return callback(false);
                        }
                    }
                    me.logger.debug("SparkplugB MQTT DDATA Metric: %j", componentMetrics);
                    me.logger.debug("SparkplugB MQTT device profile: %j", me.devProf);
                    me.spBProxy.data(me.devProf,componentMetrics, function(response) {
                        if (!response || response === "fail") {
                            me.logger.error("SparkplugB MQTT DDATA Metric not send ");
                            callback(response);
                        } else {
                            me.logger.info("SparkplugB MQTT DDATA Metric sent successfully with payload %j", componentMetrics);
                            callback(response);
                        }
                    });
                }
            }
            checkFlag();
        }
    };
    me.checkDeviceToken(handler);
};

exports.init = function(logger, deviceId) {
    return new IoTKitCloud(logger, deviceId);
};
