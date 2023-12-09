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
    msg = require('../lib/cloud-message'),
    common = require('./common'),
    utils = require('./utils').init(),
    udpServer = require('./server/udp'),
    Sensor = require('./sensors-store'),
    conf = require('../config'),
    configurator = require('../admin/configurator'),
    proxyConnector = require('@open-iot-service-platform/oisp-sdk-js')(conf).lib.proxies.getProxyConnector();

function IoTKitCloud(logger, deviceId, customProxy) {
    var deviceConf = common.getDeviceConfig();
    var me = this;
    me.logger = logger;
    me.birthMsgStatus = false;
    me.secret = {'accountId' : deviceConf['account_id'],
                 'deviceToken' : deviceConf['device_token'],
                 'refreshToken' : deviceConf['refresh_token'],
                 'deviceTokenExpire': deviceConf['device_token_expire']};
    me.proxy = customProxy || proxyConnector;
    me.max_retries = deviceConf.activation_retries || 10;
    me.deviceId = deviceId;
    me.deviceName = deviceConf.device_name;
    me.gatewayId = deviceConf.gateway_id || deviceId;
    me.store = Sensor.init("device.json", me.logger);
    me.activationCode = deviceConf.activation_code;
    me.logger.info("Cloud Proxy created with Cloud Handler: " + me.proxy.type);
    //set mqtt proxy if PROVIDED
    if (conf.connector.mqtt != undefined) {
        //Checking if SparkplugB is enabled or not
        if (conf.connector.mqtt.sparkplugB) {
            me.spbMetricList = [];
            deviceConf['sensor_list'].forEach(comp => {               
                utils.getItemFromCatalog(comp.type, function (item) {               
                    if (item) {
                        var compMetric = {
                            "name" : comp.name,
                            "alias"  : comp.cid ,
                            "timestamp" : new Date().getTime(),
                            "dataType" : item.format,
                            "value" : 0
                        }
                        me.spbMetricList.push(compMetric);
                    }
                });
            });
            me.devProf = {
                groupId   : deviceConf['account_id'],
                edgeNodeId : deviceConf['gateway_id'],
                clientId   : deviceConf['device_name'],
                deviceId   : deviceConf['device_id'],         
                componentMetric : me.spbMetricList
            };
            me.spBProxy = require('@open-iot-service-platform/oisp-sdk-js')(conf).lib.proxies.getSpBConnector();
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
            me.mqttProxy = require('@open-iot-service-platform/oisp-sdk-js')(conf).lib.proxies.getMQTTConnector();
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

IoTKitCloud.prototype.isActivated = function () {
    return true;
    var me = this;
    if (!me.secret) {
        me.secret = {
            deviceToken: null,
            accountId: null,
            refreshToken: null,
            deviceTokenExpire: null,
        };
    }
    var token  = me.secret.deviceToken;
    var account  = me.secret.accountId;
    if (token && token.length > 0) {
        if (account) {
            return true;
        }
    }
    return false;
};

IoTKitCloud.prototype.checkDeviceToken = function (callback) {
    var me = this,
        toCall = callback;
    if (!me.isActivated()) {
        return me.activate(callback);
    }

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

/**
 * Handler to wait the token from server,
 * the token is use to auth metrics send by the device
 * @param data
 */
IoTKitCloud.prototype.activationComplete = function (callback) {
    var me = this,
        toCall = callback;

    var handler = function (data) {
        me.logger.debug('Activation Data Received: ', data);
        if (data && (data.status === 0)) {
            me.secret.deviceToken = data.deviceToken;
            me.secret.accountId = data.accountId;
            me.secret.refreshToken = data.refreshToken;
            me.secret.deviceTokenExpire = jwtDecoder(data.deviceToken).exp * 1000;
            me.activationCompleted = true;
            me.logger.info('Saving device and refresh tokens...');
            common.saveToDeviceConfig('device_token', me.secret.deviceToken);
            common.saveToDeviceConfig('refresh_token', me.secret.refreshToken);
            common.saveToDeviceConfig('device_token_expire', me.secret.deviceTokenExpire);
            common.saveToDeviceConfig('account_id', me.secret.accountId);
        }
        me.setDeviceCredentials();
        toCall(data.status);
    };
    return handler;
};

/**
 * It will activate the device, by sending the activation code and receiving the token
 * from server if the token is at device the activation will not called.
 * @param callback
 */
IoTKitCloud.prototype.activate = function (code, callback) {
    var me = this,
        toCall = callback;
    me.logger.debug('Starting Activate Process function');
    if ("function" === typeof code) {
        toCall = code;
        code = null;
    }
    function complete (status) {
        /**
        * It were sent ever activation the update Metadata,
         * since every start/stop the HW could change.
        */
        if (status === 0) {
            me.update(null, function() {
                toCall(status);
            });
        } else {
            toCall(status);
        }
    }
    if (!me.isActivated()) {
        var ActMessage = {
            deviceId: me.deviceId,
            code: code || me.activationCode,
            gatewayId: me.gatewayId,
            name: me.deviceName
        };
        if (ActMessage.code == null) {
            me.logger.error("Device has not been activated, and activation code has not been set - exiting");
            process.exit(1);
        }
        me.logger.info('Activating ...');
        me.proxy.activation(ActMessage, me.activationComplete(complete));
    } else {
        // skip the update since we were already activated
        me.logger.info('Device has already been activated. Updating ...');
        me.setDeviceCredentials();
        complete(0);
    }
};

IoTKitCloud.prototype.setDeviceCredentials = function() {
    var me = this;
    me.proxy.setCredential(me.deviceId, me.secret.deviceToken);
};

IoTKitCloud.prototype.update = function(doc, callback) {
    var me = this;

    var handler = function() {
        msg.metadataExtended(me.gatewayId , function (metadata) {
            if(me.deviceName) {
                metadata.name = me.deviceName;
            }
            metadata.deviceToken = me.secret.deviceToken;
            metadata.deviceId = me.deviceId;
            me.logger.info("Updating metadata...");

            if(proxyConnector.type === "rest") {
                // Get device to read existing attributes
                me.proxy.getDevice(metadata, function(result) {
                    // Append custom attributes to update
                    for (var attribute in result.attributes) {
                        if(metadata.attributes[attribute] === undefined) {
                            metadata.attributes[attribute] = result.attributes[attribute];
                        }
                    }

                    // Update supported attributes
                    if(doc) {
                        // Attributes
                        if(doc.attributes) {
                            for (attribute in doc.attributes) {
                                metadata.attributes[attribute] = doc.attributes[attribute];
                            }
                        }

                        // Location
                        if(doc.loc) {
                            metadata.loc = doc.loc;
                        }

                        // Tags
                        if(doc.tags) {
                            // Append existing tags to update
                            if(result.tags) {
                                for(var tag in result.tags) {
                                    if(!doc.tags.includes(tag)) {
                                        doc.tags.push(tag);
                                    }
                                }
                            }
                            metadata.tags = doc.tags;
                        }
                    }
                    // Update attributes
                    me.updateAttributes(metadata, callback);

                    // Sync componentlist from cloud with local cache
                    me.updateComponents(result.components)
                });
            } else {
                me.updateAttributes(metadata, callback);
            }
            me.logger.info("Metadata updated.");

        });
    };

    me.checkDeviceToken(handler);
};

IoTKitCloud.prototype.updateAttributes = function(doc, callback) {
    var me = this;
    me.proxy.attributes(doc, function (response) {
        me.logger.debug("Attributes returned from " + me.proxy.type);
        if (callback) {
            callback(response);
        }
    });
};


IoTKitCloud.prototype.updateOld = function(callback) {
    var me = this;

    var handler = function() {
        var doc = new msg.Metadata(me.gatewayId);
        doc.deviceToken = me.secret.deviceToken;
        doc.deviceId = me.deviceId;
        me.proxy.attributes(doc, function () {
            me.logger.debug("Attributes returned from " + me.proxy.type);
            if (callback) {
                callback();
            }
        });
    };

    me.checkDeviceToken(handler);
};

IoTKitCloud.prototype.disconnect = function () {
    var me = this;
    me.proxy.disconnect();
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
        } else if (me.mqttProxy != undefined) {

            metric.accountId = me.secret.accountId;
            metric.did = me.deviceId;
            metric.gatewayId = me.gatewayId;
            metric.deviceToken = me.secret.deviceToken;
            //the next few lines are needed as workaround to work with current sdk
            //once SDK has been updated this can be removed ...
            metric.data.forEach(function(element) {
                element.componentId = element.cid
                delete element.cid
            });
            var data = {
                deviceId: me.deviceId,
                deviceToken: metric.deviceToken,
                body: {
                    accountId: metric.accountId,
                    on: new Date().getTime(),
                    data: metric.data
                }
            }
            data.convertToMQTTPayload = function() {
                delete this.convertToMQTTPayload;
                return this.body;
            }
            data.did = metric.did;
            data.accountId = metric.accountId;
            me.logger.debug("MQTT Metric: %j", data, {});
            me.mqttProxy.data(data, function(err, response) {
                if (err) {
                    callback(err);
                } else {
                    if (response) {
                        callback(null, response);
                    }
                }
            });
        // ...until here
        } else {
            me.logger.debug("Rest Metric: %j", metric, {});
            me.proxy.data(metric, function (dato) {
                if (callback) {
                    return callback(dato);
                }
                return true;
            })
        }
    };

    me.checkDeviceToken(handler);
};

IoTKitCloud.prototype.regComponent = function(comp, callback) {
    var me = this;

    // Check and update catalog
    utils.getItemFromCatalog(comp.type, function (item) {
        if (!item) {
            me.catalog(function (catalog) {
                if (catalog) {
                    utils.updateCatalog(catalog);
                }
            });
        }
    });

    var handler = function() {
        var doc = JSON.parse(JSON.stringify(comp)); //HardCopy to remove reference bind
        doc.deviceToken = me.secret.deviceToken;
        doc.deviceId =  me.deviceId;
        me.logger.debug("Reg Component doc: %j", doc, {});
        me.proxy.addComponent(doc, callback);
    };

    me.checkDeviceToken(handler);
};

IoTKitCloud.prototype.desRegComponent = function() {
    /*
    var me = this;
    var doc =  JSON.parse(JSON.stringify(comp)); //HardCopy to remove reference bind
    doc.deviceToken = me.secret.deviceToken;
    me.logger.debug("DesReg Component doc: %j", doc, {});
    me.client.publish(buildPath(me.topics.device_component_del, me.deviceId),
                                doc,
                                me.pubArgs);*/
};

IoTKitCloud.prototype.test = function(callback) {
    var me = this;
    me.logger.info("Trying to connect to host with REST...");
    me.proxy.health(me.deviceId, function (result) {
        me.logger.info("Response: ", result);
        callback(result);
        //TODO: Add healthcheck for MQTT
    });
};

IoTKitCloud.prototype.catalog = function (callback) {
    var me = this;

    var handler = function() {
        var data = {
            deviceToken: me.secret.deviceToken,
            deviceId: me.deviceId
        };
        me.proxy.getCatalog(data , function (result) {
            if (result) {
                me.logger.debug("Catalog Response : %j ", result);
                var length = result.length;
                for (var i = 0; i < length; ++i) {
                    var o = result[i];
                    me.logger.info("Comp: ", o.id, " ", o.dimension, " ", o.type );
                }
            }
            callback(result);
        });
    };

    me.checkDeviceToken(handler);
};

IoTKitCloud.prototype.pullActuations = function () {
    var me = this;

    var handler = function() {
        var data = {
            deviceToken: me.secret.deviceToken,
            deviceId: me.deviceId,
            accountId: me.secret.accountId
        };
        configurator.getLastActuationsPullTime(function(lastPullTimestamp) {
            if(lastPullTimestamp) {
                me.logger.info("Pulling actuations from last pull time: " + new Date(lastPullTimestamp));
                data.from = lastPullTimestamp;
            } else {
                me.logger.info("Pulling actuations from last 24 hours");
            }
            me.proxy.pullActuations(data, function (result) {
                if (result && result.length) {
                    me.logger.info("Running " + result.length + " actuations.");
                    var udp = udpServer.singleton(conf.listeners.udp_port, me.logger);
                    var receiverInfo = {
                        port: conf.receivers.udp_port,
                        address: conf.receivers.udp_address
                    };
                    for (var i = 0; i < result.length; i++ ) {
                        var actuation = result[i];
                        me.logger.debug('Received actuation content: ' + JSON.stringify(actuation));
                        var comp = me.store.byCid(actuation.componentId);
                        var udpMessage = {
                            component: comp.name,
                            command: actuation.command,
                            argv: actuation.params
                        };
                        me.logger.info("Sending actuation: " + JSON.stringify(udpMessage));
                        udp.send(receiverInfo, udpMessage);
                    }
                    configurator.setLastActuationsPullTime(Date.now());
                    udp.close();
                }
            });
        });
    };

    me.checkDeviceToken(handler);
};

IoTKitCloud.prototype.getActualTime = function (callback) {
    var me = this;
    me.proxy.getActualTime(function (result) {
        me.logger.debug("Response: ", result);
        callback(result);
    });
};

/**
 * @brief Update components in storage
 * @description Update components in storage. This is used to sync sensors/actuators between cloud and agent.
 * @param <string> data Contains the components of the API device object
 */
IoTKitCloud.prototype.updateComponents = function (data) {
    var me = this;
    if (data == undefined) {
        return;
    }
    data.forEach(function(cloudSensor) {
        var sen = {}
        sen.cid = cloudSensor.cid;
        sen.name = cloudSensor.name;
        sen.type = cloudSensor.componentType.id
        //if already in store, delete old sensor and sync with cloud
        if (me.store.byName(sen.name) !== undefined) {
            me.store.del(sen.cid);
        }
        me.store.add(sen);
    })
    me.store.save();
};


exports.init = function(logger, deviceId) {
    return new IoTKitCloud(logger, deviceId);
};
