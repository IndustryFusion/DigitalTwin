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

"use strict";

var jwtDecoder = require('jwt-decode'),
    msg = require('../lib/cloud-message'),
    common = require('./common'),
    utils = require('./utils').init(),
    udpServer = require('./server/udp'),
    conf = require('../config');
const http = require('http');
const url = require('url');
const querystring = require('querystring');

const devicefile = './data/device.json';


function updateToken(token) {
    const parsedToken = JSON.parse(token);
    common.saveToDeviceConfig('device_token', parsedToken.access_token);
    common.saveToDeviceConfig('refresh_token', parsedToken.refresh_token);
}

function updateSecrets(me) {
    var deviceConf = common.getDeviceConfig();
    me.secret = {'deviceToken' : deviceConf['device_token'],
                'refreshToken' : deviceConf['refresh_token'],
                'refreshUrl' : deviceConf['keycloak_url'],
                'deviceTokenExpire': deviceConf['device_token_expire']};
}

function getDeviceToken(me, token) {
    return new Promise(function(resolve, reject) {
        const parsedToken = JSON.parse(token);
        const data = querystring.stringify({
            client_id: 'device',
            orig_token: parsedToken.access_token,
            grant_type: 'refresh_token',
            audience: 'device',
            refresh_token: parsedToken.refreshToken
        })
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
        }

        const req = http.request(options, res => {
            let data = ''
            const statusCode = res.statusCode;

            res.on('data', chunk => {
                data += chunk
            })

            res.on('end', () => {
                
                if (res.statusCode === 200) {
                    resolve(data);
                } else {
                    reject(data);
                }
            })
        })
        .on('error', err => {
            console.log('Error: ', err.message)
            reject(err.message)
        })

        req.write(data)
        req.end()
    });
}

function refreshToken(me) {
    return new Promise(function(resolve, reject) {
        var deviceConf = common.getDeviceConfig();
        const data = querystring.stringify({
            client_id: 'device',
            refresh_token: deviceConf.refresh_token,
            orig_token: deviceConf.device_token,
            grant_type: 'refresh_token',
            audience: 'device'
        })
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
        }

        const req = http.request(options, res => {
            let data = ''
            const statusCode = res.statusCode;

            res.on('data', chunk => {
                data += chunk
            })

            res.on('end', () => {
                
                if (res.statusCode === 200) {
                    resolve(data);
                } else {
                    reject(data);
                }
            })
        })
        .on('error', err => {
            console.log('Error: ', err.message)
            reject(err.message)
        })

        req.write(data)
        req.end()
    });
}


function IoTKitCloud(logger, deviceId, customProxy) {
    var deviceConf = common.getDeviceConfig();
    var me = this;
    me.logger = logger;
    me.birthMsgStatus = false;
    me.secret = {'deviceToken' : deviceConf['device_token'],
                 'refreshToken' : deviceConf['refresh_token'],
                 'refreshUrl' : deviceConf['keycloak_url'],
                 'deviceTokenExpire': deviceConf['device_token_expire']};
    me.max_retries = deviceConf.activation_retries || 10;
    me.deviceId = deviceId;
    me.deviceName = deviceConf.device_name;
    me.gatewayId = deviceConf.gateway_id || deviceId;
    me.activationCode = deviceConf.activation_code;
    //set mqtt proxy if PROVIDED
    if (conf.connector.mqtt != undefined) {
        //Checking if SparkplugB is enabled or not
        if (conf.connector.mqtt.sparkplugB) {
            me.spbMetricList = [];
            me.devProf = {
                groupId   : deviceConf['realm_id'],
                edgeNodeId : deviceConf['gateway_id'],
                clientId   : deviceConf['device_name'],
                deviceId   : deviceConf['device_id'],         
                componentMetric : me.spbMetricList
            };
            me.spBProxy = require('./proxy')(conf).lib.proxies.getSpBConnector();
            me.logger.info("SparkplugB MQTT proxy found! Configuring  Sparkplug and MQTT for data sending.");
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
                        me.logger.info("SparkplugB MQTT NBIRTH Metric sent succesfully for eonid: " + me.gatewayId);
                        me.logger.debug("SparkplugB MQTT DBIRTH Metric: " + me.spbMetricList);
                        me.spBProxy.deviceBirth(me.devProf, function(err) {                
                            if (err === "fail") {
                                me.logger.error("SparkplugB MQTT DBIRTH Metric not sent");
                                me.spBProxy = undefined;
                            } else {
                                me.birthMsgStatus = true; 
                                me.logger.info("SparkplugB MQTT DBIRTH Metric sent succesfully for device: " + me.deviceId);
                            }                          
                        }); 
                    }                                        
                });       
            }
        } else {
            me.mqttProxy = require('./proxy')(conf).lib.proxies.getMQTTConnector();
            me.logger.info("Configuring MQTT...");
            if (deviceConf.device_id && deviceConf.device_token) {
                me.mqttProxy.updateDeviceInfo(deviceConf);
            } else {
                me.logger.info("No credentials found for MQTT!");
                me.mqttProxy = undefined;
            }
        }
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
        //const onboarding_token = require('../data/onboard-token.json');
        var data = {
            token: me.secret.deviceToken,
            body: {
                refreshToken: me.secret.refreshToken
            }
        };
        refreshToken(me)
            //.then(data => getDeviceToken(me, data))
            .then(data => updateToken(data))
            .then(() => updateSecrets(me))
            .then(toCall())
            .catch((err) => this.logger.error("Could not refresh token: " + err.message))
    }
};


IoTKitCloud.prototype.dataSubmit = function (metric, callback) {
    var me = this;
    function getCompMetric(metric) {
        let compMetric = {};    
        compMetric.value = metric.v;
        compMetric.name = metric.n;
        compMetric.dataType = "string";
        compMetric.timestamp = metric.on || new Date().getTime();
        return compMetric;
    }
    var handler = function() {    
        // SparkplugB format data submission to sdk
        let timecount = 0;
        if (me.spBProxy != undefined) {
            let checkFlag = function () {
                if ( !me.birthMsgStatus ) {
                    setTimeout(checkFlag, 250)  /* this checks the flag every 250 milliseconds*/
                    if (timecount == 20) {  /* return if birthmsgstatus not true for 5 seconds */
                        return callback("timeout");
                    }
                    timecount++;
                } else {
                    var componentMetrics = [];
                         
                    if (Array.isArray(metric)) {
                        metric.forEach(item => {
                            componentMetrics.push(getCompMetric(item));
                        })
                        // Check if we have any data left to submit
                    } else {
                        componentMetrics.push(getCompMetric(metric));
                    }
                    if (componentMetrics.length === 0) {
                        me.logger.error(' SPB Data submit - no data to submit.');
                        return callback(false);
                    }
                    me.logger.debug("SparkplugB MQTT DDATA Metric: " + componentMetrics);
                    me.logger.debug("SparkplugB MQTT device profile: " + me.devProf);
                    me.spBProxy.data(me.devProf,componentMetrics, function(response) {
                        if (!response || response === "fail") {
                            me.logger.error("SparkplugB MQTT DDATA Metric not send ");
                            callback(response);
                        } else {
                            me.logger.info("SparkplugB MQTT DDATA Metric sent successfully");
                            callback(response);
                        }
                    });
                }
            }
            checkFlag();
        } else {
            me.logger.error("MQTT proxy not defined.");
        }
    };

    me.checkDeviceToken(handler);
};


exports.init = function(logger, deviceId) {
    return new IoTKitCloud(logger, deviceId);
};
