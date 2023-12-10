/**
* Copyright (c) 2017 Intel Corporation
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

"use strict";
var mqtt = require('mqtt');
var events = require('events');

var MQTT = 'mqtt://';
var MQTT_SECURE = 'mqtts://';
var WEBSOCKETS = 'ws://';
var WEBSOCKETS_SECURE = 'wss://';

function Broker(conf) {
    var me = this;
    me.host = conf.host;
    me.port = conf.port;
    me.websockets = conf.websockets;
    me.secure = conf.secure;
    me.keepalive = conf.keepalive || 60;
    me.max_retries = conf.retries || 30;
    me.messageHandler = [];
    me.pubArgs = {
        qos: conf.qos || 1,
        retain: conf.retain
    };
    me.isLive = false;
    me.client = {
        connected: false,
        end: function() {}
    };
    me.deviceInfo = {};
    me.updateDeviceInfo = function(deviceInfo) {
        me.deviceInfo = deviceInfo;
    };
    me.listen = function () {
        me.client.on('message',function(topic, message) {
            try {
                message = JSON.parse(message);
            } catch (e) {
                return;
            }

            me.onMessage(topic, message);
        });
    };
    me.connect = function (done) {
        var retries = 0;
        try {
            if ((me.client instanceof mqtt.MqttClient) === false) {
                var protocol = MQTT;
                if (me.secure) {
                    protocol = MQTT_SECURE;
                }
                if (me.websockets) {
                    if (me.secure) {
                        protocol = WEBSOCKETS_SECURE;
                    } else {
                        protocol = WEBSOCKETS;
                    }
                }
                me.client = mqtt.connect(protocol + me.host + ':' + me.port, {
                    username: me.deviceInfo.device_id,
                    password: me.deviceInfo.device_token,
                    rejectUnauthorized: false
                });
            }
        } catch(e) {
            done(new Error("Connection Error", 1002));
            return;
        }
        function waitForConnection() {
            if (!me.client.connected) {
                retries++;
                if (retries < me.max_retries) {
                    setTimeout(waitForConnection, 1500);
                } else {
                    done(new Error("Connection Error", 1001));
                }
                return false;
            }

            me.listen();
            if (done) {
                done(null);
            }
            return true;
        }
        waitForConnection();
    };
    me.disconnect = function () {
        me.client.end();
        me.client = {
            connected: false,
            end: function() {}
        };
    };
    me.attach = function (topic, handler) {
        me.messageHandler.push({"t": topic,
                                "h": handler});
    };
    function tryPattern(pattern, text) {
        var a = new RegExp(pattern);
        return a.test(text);
    }
    me.dettach = function (topic) {
        me.messageHandler = me.messageHandler.filter(function (obj) {
            return !tryPattern(obj.t, topic);
        });
    };
    me.onMessage = function (topic, message) {
        var i,
            length = me.messageHandler.length;
        /**
         * Iterate over the messageHandler to match topic patter,
         * and dispatch message to only proper handler
         */
        for (i = 0; i < length; i++ ) {
            var obj = me.messageHandler[i];
            if (tryPattern(obj.t, topic)) {
                obj.h(topic, message);
            }
        }
    };
    me.bind = function (topic, handler, callback) {
        /**
         * since the bind and publish connect automatically,
         * it is require to chain the callbacks
         */
        var toCallBack = callback;
        function connectCallback() {
            me.client.subscribe(topic, {qos: 1}, function (err, granted) {
                var topicAsPattern = granted[0].topic.replace(/\+/g, "[^<>]*");
                me.attach(topicAsPattern, handler);
                if (toCallBack) {
                    toCallBack();
                }
            });
        }
        if (!me.connected()) {
            me.connect(function(err) {
                if (!err) {
                    connectCallback();
                } else {
                    if (toCallBack) {
                        toCallBack(err);
                    }
                }
            });
        } else {
            connectCallback();
        }
    };
    me.unbind = function (topic, callback) {
        me.client.unsubscribe(topic, function() {
            me.dettach(topic);
            if (callback) {
                callback();
            }
        });
    };
    /**
     * @description publish broadcast to an specifics topics, the message.
     * @param topic <string> to which will be broadcast the message.
     * @param message <object> that will be sent to topics
     * @param args <object>
     */
    me.publish = function (topic, message, options, callback) {
        if ("function" === typeof options) {
            callback = options;
            options = me.pubArgs;
        } else {
            options = options || me.pubArgs;
        }
        function publishCallback() {
            me.client.publish(topic, JSON.stringify(message), options, callback);
        }
        if (!me.connected()) {
            me.connect(function(err) {
                if (!err) {
                    publishCallback();
                } else {
                    if (callback) {
                        callback(err);
                    }
                }
            });
        } else {
            publishCallback();
        }
    };
    me.connected = function () {
        return me.client.connected;
    };
}

Broker.prototype = new events.EventEmitter();

var broker = null;
module.exports.singleton = function (conf) {
    if (!broker) {
        broker = new Broker(conf);
    }
    return broker;
};
module.exports.Broker = Broker;
