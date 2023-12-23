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
    common = require('./common'),
    conf = require('../config');
const http = require('http');
const querystring = require('querystring');
const devicefile = './data/device.json';


function updateToken(token) {
    const parsedToken = JSON.parse(token);
    common.saveToDeviceConfig('device_token', parsedToken.access_token);
    common.saveToDeviceConfig('refresh_token', parsedToken.refresh_token);
}

function updateSecrets(me) {
    var deviceConf = common.getDeviceConfig();
    me.spBProxy.updateDeviceInfo(deviceConf);
    me.secret = {'deviceToken' : deviceConf['device_token'],
                'refreshToken' : deviceConf['refresh_token'],
                'refreshUrl' : deviceConf['keycloak_url'],
                'deviceTokenExpire': deviceConf['device_token_expire']};
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

class CloudProxy {

    constructor(logger, deviceId) {
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
        if (conf.connector.mqtt !== undefined && conf.connector.mqtt.sparkplugB !== undefined) {
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
                me.logger.info("No credentials found for MQTT. Please check activation.");
                process.exit(1);
            }
            if (me.spBProxy != undefined ) { 
                /** 
                *  Sending Birth message for SparkplugB (of node/agent and for device),
                * As per standard Birth message is mandatory to send on start before sending Data
                */
            
            }
        } else {
            me.logger.error("Could not start MQTT Proxy. Please check configuraiton. Bye!");
            process.exit(1);
        }
    }
    

    async init () {
        let me = this;

        try {
            await me.spBProxy.nodeBirth(me.devProf);
        } catch (err) {
            me.logger.error("SparkplugB MQTT NBIRTH Metric not sent. Trying to refresh token.");
            await me.checkDeviceToken()
            return 1;
        }
        me.logger.info("SparkplugB MQTT NBIRTH Metric sent succesfully for eonid: " + me.gatewayId);
        me.logger.debug("SparkplugB MQTT DBIRTH Metric: " + me.spbMetricList);
        try {
            await me.spBProxy.deviceBirth(me.devProf);
        } catch (err) {
            me.logger.error("SparkplugB MQTT DBIRTH Metric not sent. Check connection and token: " + err.message);
            return 1;
        } 
        me.birthMsgStatus = true; 
        me.logger.info("SparkplugB MQTT DBIRTH Metric sent succesfully for device: " + me.deviceId);
        return 0;
    }; 


    async checkDeviceToken () {
        var me = this;

        if (!me.secret.deviceTokenExpire) {
            me.secret.deviceTokenExpire = jwtDecoder(me.secret.deviceToken).exp * 1000; // convert to miliseconds
        }

        if (new Date().getTime() < me.secret.deviceTokenExpire) {
            return 0;
        } else {
            me.logger.info('Device token has expired - refreshing it now...');
            //const onboarding_token = require('../data/onboard-token.json');
            /*var data = {
                token: me.secret.deviceToken,
                body: {
                    refreshToken: me.secret.refreshToken
                }
            };*/
            const data = await refreshToken(me)
            try {
                await updateToken(data)
                await updateSecrets(me)
            } catch (err) {
                this.logger.error("Could not refresh token: " + err.message)
            }
        }
    };


    async dataSubmit (metric) {
        var me = this;
        function getCompMetric(metric) {
            let compMetric = {};    
            compMetric.value = metric.v;
            compMetric.name = metric.n;
            compMetric.dataType = "string";
            compMetric.timestamp = metric.on || new Date().getTime();
            return compMetric;
        }
        await me.checkDeviceToken();
        if ( !me.birthMsgStatus ) {
            throw(new Error("Session is not initialized."));
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
                return;
            }
            me.logger.debug("SparkplugB MQTT DDATA Metric: " + componentMetrics);
            me.logger.debug("SparkplugB MQTT device profile: " + me.devProf);
            
            await me.spBProxy.data(me.devProf,componentMetrics);
            me.logger.info("SparkplugB MQTT DDATA Metric sent successfully");
        }
    };

}

module.exports = CloudProxy;
