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

'use strict';
const mqtt = require('mqtt');
const events = require('events');

function Broker (conf, logger) {
  const me = this;
  me.host = conf.host;
  me.port = conf.port;
  me.key = conf.key;
  me.cert = conf.cert;
  me.ca = conf.ca;
  me.secure = conf.secure;
  me.keepalive = conf.keepalive || 60;
  me.crd = {
    username: conf.adminUsername,
    password: conf.adminPassword
  };
  me.max_retries = conf.retries || 30;
  me.messageHandler = [];
  me.logger = logger;
  me.topics = conf.topics;
  me.pubArgs = {
    qos: conf.qos || 1,
    retain: conf.retain
  };
  me.iamHealthyTopic = 'server/{hash}/healthy';
  me.isLive = false;
  me.pingActivate = true;
  me.client = {
    connected: false,
    end: function () {}
  };

  me.buildPath = function (path, data) {
    const re = /{\w+}/;
    let pathReplace = path;
    if (Array.isArray(data)) {
      data.forEach(function (value) {
        pathReplace = pathReplace.replace(re, value);
      });
    } else {
      pathReplace = pathReplace.replace(re, data);
    }
    return pathReplace;
  };

  me.setCredential = function (newCrd) {
    me.crd = newCrd || me.crd;
    me.credential = {
      username: me.crd.username,
      password: me.crd.password,
      keepalive: me.keepalive
    };
  };
  me.setCredential();

  me.listen = function () {
    me.client.on('message', function (topic, message) {
      try {
        message = JSON.parse(message);
      } catch (e) {
        me.logger.error('Invalid Message: %s', e);
        return;
      }
      me.logger.info('STATUS: %s', topic, message);
      me.onMessage(topic, message);
    });
  };
  me.connect = function (done) {
    let retries = 0;
    try {
      if ((me.client instanceof mqtt.MqttClient) === false) {
        if (me.secure === false) {
          me.logger.info('Non Secure Connection to ' + me.host + ':' + me.port);
          me.client = mqtt.connect('mqtt://' + me.host + ':' + me.port, {
            username: me.crd.username,
            password: me.crd.password
          });
        } else {
          me.logger.debug('Trying with Secure Connection to' + me.host + ':' + me.port);

          me.client = mqtt.connect('mqtts://' + me.host + ':' + me.port, {
            username: me.crd.username,
            password: me.crd.password,
            rejectUnauthorized: false,
            protocolVersion: 5
          });
        }
        me.client.on('error', function (err) {
          console.log(err);
        });
      }
    } catch (e) {
      logger.error('Error in connection ex: ', e);
      done(new Error('Connection Error'));
      return;
    }
    function waitForConnection () {
      if (!me.client.connected) {
        retries++;
        me.logger.info('Waiting for MQTTConnector to connect # ' + retries);
        if (retries < me.max_retries) {
          setTimeout(waitForConnection, 1500);
        } else {
          me.logger.info('MQTTConnector: Error Connecting to ' + me.host + ':' + me.port);
          done(new Error('Maximal connection tries reached'));
        }
        return false;
      }
      me.logger.info('MQTTConnector: Connection successful to ' + me.host + ':' + me.port);
      me.listen();
      if (done) {
        done(null);
      }
      return true;
    }
    waitForConnection();
  };
  me.disconnect = function () {
    me.logger.info('Trying to disconnect ');
    me.client.end();
    me.client = {
      connected: false,
      end: function () {}
    };
  };
  me.attach = function (topic, handler, context) {
    // New feature shared subscription starts topic with $share/topic/
    // This needs to be removed as it will not be the reported topic
    // e.g. subscription is $share/topic/hello/world but received topic is hello/world
    topic = topic.replace(/^\$share\/\w+\//, '');
    me.messageHandler.push({
      t: topic,
      h: handler,
      c: context
    });
  };
  function tryPattern (pattern, text) {
    const a = new RegExp(pattern);
    return a.test(text);
  }
  me.dettach = function (topic) {
    // New feature shared subscription starts topic with $share/topic/
    // This needs to be removed as it will not be the reported topic
    // e.g. subscription is $share/topic/hello/world but received topic is hello/world
    topic = topic.replace(/^\$share\/\w+\//, '');
    me.logger.debug('Filtering Topics ' + topic + ' from local dispatcher');
    me.messageHandler = me.messageHandler.filter(function (obj) {
      return !tryPattern(obj.t, topic);
    });
  };
  me.onMessage = function (topic, message) {
    let i;
    const length = me.messageHandler.length;
    /**
         * Iterate over the messageHandler to match topic patter,
         * and dispatch message to only proper handler
         */
    for (i = 0; i < length; i++) {
      const obj = me.messageHandler[i];
      if (tryPattern(obj.t, topic)) {
        me.logger.debug('Fired STATUS: ' + topic + JSON.stringify(message));
        obj.h.call(obj.c, topic, message);
      }
    }
  };
  me.bind = function (topic, handler, context, callback) {
    /**
         * since the bind and publish connect automatically,
         * it is require to chain the callbacks
         */
    const toCallBack = callback;
    function connectCallback () {
      me.logger.debug('Subscribing to: ' + topic);
      me.client.subscribe(topic, { qos: 1 }, function (err, granted) {
        if (err) {
          throw new Error('Cannot bind handler.');
        }
        me.logger.debug('grant ' + JSON.stringify(granted));
        const topicAsPattern = granted[0].topic.replace(/\+/g, '[^<>]*');
        me.logger.info('Topic Pattern :' + topicAsPattern);
        me.attach(topicAsPattern, handler, context);
        if (toCallBack) {
          toCallBack();
        }
      });
    }
    if (!me.connected()) {
      me.connect(function (err) {
        if (!err) {
          connectCallback();
        } else {
          me.logger.error(err);
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
    me.logger.debug('Unbinding from Topic ' + topic);
    me.client.unsubscribe(topic, function () {
      me.logger.info('Unbound (UNSUBACK) of topic ' + topic);
    });
    me.logger.debug('Filtering Topics ' + topic + ' from local dispatcher');
    me.dettach(topic);
    if (callback) {
      callback();
    }
  };
  /**
     * @description publish broadcast to an specifics topics, the message.
     * @param topic <string> to which will be broadcast the message.
     * @param message <object> that will be sent to topics
     * @param args <object>
     */
  me.publish = function (topic, message, options, callback) {
    if (typeof options === 'function') {
      callback = options;
      options = me.pubArgs;
    } else {
      options = options || me.pubArgs;
    }
    function publishCallback () {
      me.logger.info('Publishing : T => ' + topic + ' MSG => ' + JSON.stringify(message));
      me.client.publish(topic, JSON.stringify(message), options, callback);
    }
    if (!me.connected()) {
      me.connect(function (err) {
        if (!err) {
          publishCallback();
        } else {
          me.logger.error('The connection has failed on publish ' + err);
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

let broker = null;
module.exports.singleton = function (conf, logger) {
  if (!broker) {
    broker = new Broker(conf, logger);
  }
  return broker;
};
module.exports.Broker = Broker;
