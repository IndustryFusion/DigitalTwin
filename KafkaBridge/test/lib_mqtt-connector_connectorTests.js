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

const assert = require('chai').assert;
const rewire = require('rewire');

const fileToTest = '../lib/mqtt_connector';

describe(fileToTest, function () {
  const toTest = rewire(fileToTest);

  const mqtt = {
    createSecureClient: function () {},
    createClient: function () {},
    MqttClient: function () {
      this.subscribe = function (topic, option, callback) {
        return callback(null, [{ topic: topic, qos: 0 }]);
      };
      this.publish = function (topic) {
        console.log('Publishing Topic ', topic);
      };
      this.unsubscribe = function () {

      };
      this.listen = function () {
        console.log('Called Listen()');
      };
      this.on = function () {};
    }
  };
  const logger = {
    info: function () {},
    error: function () {},
    debug: function () {}
  };
  console.debug = function () {
    console.log(arguments);
  };
  beforeEach(function (done) {
    toTest.__set__('broker', null);
    done();
  });
  it('Shall Connect to Specific Broker using None Secure Connection >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const username = 'username';
    const password = 'password';
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2,
      adminUsername: username,
      adminPassword: password
    };

    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    const client = new mqtt.MqttClient();
    mqtt.connect = function (url, options) {
      assert.lengthOf(arguments, 2, 'Missing Argument for Secure Connection');
      assert.equal(options.username, config.adminUsername, 'The port has override');
      assert.equal(options.password, config.adminPassword, 'The host has override');
      assert.equal(url, 'mqtt://' + config.host + ':' + config.port);
      client.connected = true;
      return client;
    };

    myBroker.connect(function (err) {
      assert.isNull(err, 'None error shall returned');
      done();
    });
  });
  it('Shall Connect to Specific Broker using Secure Connection >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: true,
      retries: 2
    };
    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    const client = new mqtt.MqttClient();
    mqtt.connect = function (url, options) {
      assert.lengthOf(arguments, 2, 'Missing Argument for Secure Connection');
      assert.equal(options.username, config.username, 'The port has override');
      assert.equal(options.password, config.password, 'The host has override');
      assert.equal(url, 'mqtts://' + config.host + ':' + config.port);
      client.connected = true;
      return client;
    };
    myBroker.connect(function (err) {
      assert.isNull(err, 'Not Spected error Returned');
      done();
    });
  });
  it('Shall Catch a Exception at Connect >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: true,
      retries: 2
    };
    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    const client = new mqtt.MqttClient();
    mqtt.connect = function () {
      client.connected = false;
      throw new Error('Invalid Command');
    };

    myBroker.connect(function (err) {
      assert.instanceOf(err, Error, 'An error shall be returned');
      done();
    });
  });
  it('Shall wait to Connect to Specific Broker >', function (done) {
    toTest.__set__('mqtt', mqtt);

    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: true,
      retries: 5
    };

    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    const client = new mqtt.MqttClient();

    mqtt.connect = function (url, options) {
      assert.lengthOf(arguments, 2, 'Missing Argument for Secure Connection');
      assert.equal(options.username, config.username, 'The port has override');
      assert.equal(options.password, config.password, 'The host has override');
      assert.equal(url, 'mqtts://' + config.host + ':' + config.port);
      client.connected = false;
      return client;
    };

    myBroker.connect(function (err) {
      assert.isNull(err, 'None error shall be returned');
      done();
    });

    setTimeout(function () {
      client.connected = true;
    }, 2000);
  }).timeout(5000);
  it('Shall Report Error After # Retries >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: true,
      retries: 2,
      adminUsername: 'username',
      adminPassword: 'password'
    };
    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    const client = new mqtt.MqttClient();
    mqtt.connect = function (url, options) {
      assert.lengthOf(arguments, 2, 'Missing Argument for Secure Connection');
      assert.equal(options.username, config.adminUsername, 'The port has override');
      assert.equal(options.password, config.adminPassword, 'The host has override');
      assert.equal(url, 'mqtts://' + config.host + ':' + config.port);
      client.connected = false;
      return client;
    };
    myBroker.connect(function (err) {
      assert.instanceOf(err, Error, 'Invalid error reported');
      done();
    });
  });
  it('Shall Publish to Specific Broker Topic >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: true,
      retries: 12
    };
    const myTopic = '/device/topox/{1}/xxxx';
    const myMessage = {
      a: 'test',
      b: 12323
    };
    const crd = {
      username: 'TuUser',
      password: 'tuPassword'
    };
    const client = new mqtt.MqttClient();
    mqtt.connect = function (url, options) {
      assert.lengthOf(arguments, 2, 'Missing Argument for Secure Connection');
      assert.equal(options.username, crd.username, 'The port has override');
      assert.equal(options.password, crd.password, 'The host has override');
      assert.equal(url, 'mqtts://' + config.host + ':' + config.port);
      client.connected = true;
      return client;
    };

    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    myBroker.setCredential(crd);
    client.publish = function (topic, message) {
      assert.equal(topic, myTopic, 'Missing the topics');
      assert.equal(message, JSON.stringify(myMessage), 'Missing the Message');
      done();
    };
    myBroker.connect(function (err) {
      assert.isNull(err, Error, 'Invalid error reported');
      myBroker.publish(myTopic, myMessage, {}, done);
    });
  });
  it('Shall Notified to Specific topic handler >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const id = '0a-03-12-22';
    const realTopic = 'dev/' + id + '/act';
    const msg = {
      a: 1,
      c: 2
    };
    const crd = {
      username: 'TuUser',
      password: 'tuPassword'
    };
    const myBroker = toTest.singleton(config, logger);
    const client = new mqtt.MqttClient();
    myBroker.pingActivate = false;
    myBroker.setCredential(crd);
    mqtt.connect = function () {
      client.connected = true;
      return client;
    };

    const topicPattern = 'dev/+/act';
    const topicHandler = function (topic) {
      assert.equal(topic, realTopic, 'The topis is not the expected');
      done();
    };
    client.subscribe = function (vtopic, option, cb) {
      const granted = [{ topic: vtopic }];
      cb(null, granted);
    };
    myBroker.connect(function (err) {
      assert.isNull(err, 'None error shall returned');
      myBroker.bind(topicPattern, topicHandler);
      myBroker.onMessage(realTopic, msg);
    });
  });
  it('Shall Listen to on Message >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const msg = {
      a: 1,
      c: 2
    };
    const myBroker = toTest.singleton(config, logger);
    const client = new mqtt.MqttClient();
    myBroker.pingActivate = false;
    let callHandler = null;
    client.on = function (event, handler) {
      assert.isFunction(handler, 'The handle shall be a function');
      assert.isString(event, 'The event shall be string');
      callHandler = handler;
    };

    mqtt.connect = function () {
      client.connected = true;
      return client;
    };

    myBroker.connect(function (err) {
      assert.isNull(err, 'None error shall returned');
      callHandler('conmector', JSON.stringify(msg));
      done();
    });
  });
  it('Shall Listen to on Message > with specific topic handler >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const id = '0a-03-12-22';
    const realTopic = 'dev/' + id + '/act';
    const msg = {
      a: 1,
      c: 2
    };
    let callHandler = null;
    const client = new mqtt.MqttClient();

    client.on = function (event, handler) {
      assert.isFunction(handler, 'The handle shall be a function');
      assert.isString(event, 'The event shall be string');
      // assert.equal(event, "message", "Invalid event listeneter");
      callHandler = handler;
    };

    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    mqtt.connect = function () {
      client.connected = true;
      return client;
    };

    const topicPattern = 'dev/+/act';
    const topicHandler = function (topic, message) {
      assert.equal(topic, realTopic, 'The topis is not the expected');
      assert.deepEqual(message, msg, 'The message is missing');
      done();
    };
    client.subscribe = function (vtopic, option, cb) {
      const granted = [{ topic: vtopic }];
      cb(null, granted);
    };
    myBroker.connect(function (err) {
      assert.isNull(err, 'None error shall returned');
      myBroker.bind(topicPattern, topicHandler);
      callHandler('dev/' + id + '/act', JSON.stringify(msg));
    });
  });
  it('Shall Listen to on Message > discard improper message format >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const id = '0a-03-12-22';
    let callHandler = null;
    const client = new mqtt.MqttClient();
    client.on = function (event, handler) {
      assert.isFunction(handler, 'The handle shall be a function');
      assert.isString(event, 'The event shall be string');
      callHandler = handler;
    };
    const crd = {
      username: 'TuUser',
      password: 'tuPassword'
    };
    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    mqtt.connect = function () {
      client.connected = true;
      return client;
    };

    const topicPattern = 'dev/+/act';
    const topicHandler = function (topic) {
      assert.isFalse(topic, 'Wrong path, the messaga shall be discarded');
    };
    client.subscribe = function (vtopic, option, cb) {
      const granted = [{ topic: vtopic }];
      cb(null, granted);
    };
    myBroker.setCredential(crd);
    myBroker.connect(function (err) {
      assert.isNull(err, 'None error shall returned');
      myBroker.bind(topicPattern, topicHandler);
      callHandler('dev/' + id + '/act', 'pepep');
      // myBroker.onMessage(realTopic, msg);
      done();
    });
  });
  it('Shall Listen to on Message > with specific topic handler >', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const id = '0a-03-12-22';
    const realTopic = 'dev/' + id + '/act';
    const msg = {
      a: 1,
      c: 2
    };
    let callHandler = null;
    const client = new mqtt.MqttClient();
    client.on = function (event, handler) {
      assert.isFunction(handler, 'The handle shall be a function');
      assert.isString(event, 'The event shall be string');
      callHandler = handler;
    };

    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    mqtt.connect = function () {
      client.connected = true;
      return client;
    };

    const topicPattern = 'dev/+/act';
    const topicHandler = function (topic, message) {
      assert.equal(topic, realTopic, 'The topis is not the expected');
      assert.deepEqual(message, msg, 'The message is missing');
      done();
    };
    client.subscribe = function (vtopic, optoin, cb) {
      const granted = [{ topic: vtopic }];
      cb(null, granted);
    };
    myBroker.connect(function (err) {
      assert.isNull(err, 'None error shall returned');
      myBroker.bind(topicPattern, topicHandler, null, function () {
        callHandler('dev/' + id + '/act', JSON.stringify(msg));
      });
      // myBroker.onMessage(realTopic, msg);
    });
  });
  it('Shall Disconnect from Broker>', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const myBroker = toTest.singleton(config, logger);
    const client = new mqtt.MqttClient();
    myBroker.pingActivate = false;
    mqtt.connect = function () {
      client.connected = true;
      return client;
    };

    client.end = function () {
      done();
    };
    myBroker.connect(function (err) {
      assert.isNull(err, 'None error shall returned');
      myBroker.disconnect();
    });
  });

  it('Shall build path with array, non-array and no input', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const myBroker = toTest.singleton(config, logger);
    let result = myBroker.buildPath('topic/{accountid}/test/{deviceid}', ['account', 'did']);
    assert.equal(result, 'topic/account/test/did', 'Wrong path built.');
    result = myBroker.buildPath('topic/{accountid}/test', '123.abc');
    assert.equal(result, 'topic/123.abc/test', 'Wrong path built.');
    result = myBroker.buildPath('topic/{accountid}/test', ['987.xyz']);
    assert.equal(result, 'topic/987.xyz/test', 'Wrong path built.');
    result = myBroker.buildPath('topic/{accountid}/test', null);
    assert.equal(result, 'topic/null/test', 'Wrong path built.');
    done();
  });
  it('Shall attach topic and call message handler', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const myBroker = toTest.singleton(config, logger);
    const handler = function (topic, message) {
      assert.equal(message, 'mymessage', 'wrong message received');
      assert.equal(topic, 'mytopic', 'wrong topic received');
      done();
    };
    myBroker.attach('mytopic', handler);
    assert.equal(myBroker.messageHandler[0].t, 'mytopic', 'Wrong topic in messageHandler');
    myBroker.onMessage('mytopic', 'mymessage');
  });
  it('Shall attach topic, and remove it', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const myBroker = toTest.singleton(config, logger);
    const handler = function () {
      done('Handler should not be called!');
    };
    myBroker.attach('mytopic', handler);
    myBroker.dettach('mytopic');
    assert.equal(myBroker.messageHandler.length, 0, 'Wrong topic in messageHandler');
    myBroker.onMessage('mytopic', 'mymessage');
    setTimeout(function () { done(); }, 500); // give it some time to fail ...
  });
  it('Shall bind in unconnected state initiate connection', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const client = new mqtt.MqttClient();
    const crd = {
      username: 'TuUser',
      password: 'tuPassword'
    };
    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    mqtt.connect = function () {
      client.connected = true;
      return client;
    };

    const topicPattern = 'dev/+/act';
    const topicHandler = function () {
      assert.fail();
    };

    myBroker.setCredential(crd);
    const callback = function () {
      done();
    };
    myBroker.bind(topicPattern, topicHandler, null, callback);
  });
  it('Shall unbind and detach topic', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: false,
      retries: 2
    };
    const client = new mqtt.MqttClient();
    const crd = {
      username: 'TuUser',
      password: 'tuPassword'
    };
    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    mqtt.connect = function () {
      client.connected = true;
      return client;
    };
    client.unsubscribe = function (topic, cb) {
      cb(topic);
    };
    const topicPattern = 'dev/+/act';
    const topicHandler = function () {
      assert.fail();
    };

    myBroker.setCredential(crd);
    const callback = function () {
      assert.equal(myBroker.messageHandler.length, 1, 'topic not added from messageHandler');
    };
    const finalCallback = function () {
      assert.equal(myBroker.messageHandler.length, 0, 'topic not deleted from messageHandler');
      done();
    };
    myBroker.bind(topicPattern, topicHandler, callback);
    myBroker.unbind(topicPattern, finalCallback);
  });
  it('Shall connect in publish', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: true,
      retries: 12
    };
    const myTopic = '/device/topox/{1}/xxxx';
    const myMessage = {
      a: 'test',
      b: 12323
    };
    const crd = {
      username: 'TuUser',
      password: 'tuPassword'
    };
    const client = new mqtt.MqttClient();
    mqtt.connect = function () {
      client.connected = true;
      return client;
    };

    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    myBroker.setCredential(crd);
    client.publish = function (topic, message) {
      assert.equal(topic, myTopic, 'Missing the topics');
      assert.equal(message, JSON.stringify(myMessage), 'Missing the Message');
      done();
    };
    myBroker.publish(myTopic, myMessage, {}, done);
  });
  it('Shall try connect in publish and throw error', function (done) {
    toTest.__set__('mqtt', mqtt);
    const config = {
      host: 'myHosttest',
      port: 9090909,
      secure: true,
      retries: 12
    };
    const myTopic = '/device/topox/{1}/xxxx';
    const myMessage = {
      a: 'test',
      b: 12323
    };
    const crd = {
      username: 'TuUser',
      password: 'tuPassword'
    };
    const client = new mqtt.MqttClient();
    mqtt.connect = function () {
      client.connected = false;
      throw new Error('Could not connect');
    };

    const myBroker = toTest.singleton(config, logger);
    myBroker.pingActivate = false;
    myBroker.setCredential(crd);
    client.publish = function () {
      assert.fail();
    };
    const callback = function (err) {
      console.log(err);
      assert.equal(err.message, 'Connection Error', 'wrong error returned');
      done();
    };
    myBroker.publish(myTopic, myMessage, {}, callback);
  });
});
