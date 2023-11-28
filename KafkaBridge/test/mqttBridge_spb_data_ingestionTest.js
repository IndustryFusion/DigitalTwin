/**
* Copyright (c) 2022 Intel Corporation
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
const fileToTest = '../mqttBridge/sparkplug_data_ingestion.js';

describe(fileToTest, function () {
  process.env.OISP_KEYCLOAK_CONFIG = '{\
        "listenerPort": 4080, \
        "auth-server-url": "keycloak" \
    }';
  process.env.OISP_KAFKA_CONFIG = '{\
        "uri": "uri", \
        "partitions": 1, \
        "metricsPartitions": 1, \
        "replication": 1, \
        "timeoutMs": 10000, \
        "topicsObservations": "metricsTopic", \
        "topicsRuleEngine": "rules-update", \
        "topicsHeartbeatName": "heartbeat", \
        "topicsHeartbeatInterval": 5000, \
        "maxPayloadSize": 1234456, \
        "retries": 10, \
        "requestTimeout": 4, \
        "maxRetryTime": 10 \
    }';
  process.env.OISP_MQTT_GATEWAY_CONFIG = '{ \
        "mqttBrokerUrl": "brokerUrl", \
        "mqttBrokerLocalPort": "1234", \
        "mqttBrokerUsername": "brokerUsername", \
        "mqttBrokerPassword": "brokerPassword", \
        "authServicePort": "2345", \
        "redisConf": "@@OISP_REDIS_CONFIG", \
        "kafkaConfig": "@@OISP_KAFKA_CONFIG", \
        "keycloakConfig": "@@OISP_KEYCLOAK_CONFIG", \
        "aesKey": "/app/keys/mqtt/mqtt_gw_secret.key" \
    }';

  process.env.OISP_REDIS_CONFIG = '{\
        "hostname": "redis",\
        "port": "6379",\
        "password": "password" \
    }';

  const config = {
    mqttBrokerUrl: 'brokerUrl',
    mqttBrokerLocalPort: '1234',
    mqttBrokerUsername: 'brokerUsername',
    mqttBrokerPassword: 'brokerPassword',
    authServicePort: '2345',
    topics: {
      subscribe: 'topic/subscribe'
    },
    cache: {
      hostname: 'redis',
      port: '6379',
      password: 'password'
    },
    kafka: {
      host: 'uri',
      partitions: 1,
      metricsPartitions: 1,
      replication: 1,
      timeoutMs: 10000,
      metricsTopic: 'metricsTopic',
      topicsRuleEngine: 'rules-update',
      topicsHeartbeatName: 'heartbeat',
      topicsHeartbeatInterval: 5000,
      maxPayloadSize: 1234456,
      retries: 10,
      requestTimeout: 4,
      maxRetryTime: 10
    },
    mqtt: {
      sparkplug: {
        spBKafkaProduce: true,
        spBkafkaTopic: 'sparkplugB',
        ngsildKafkaProduce: true,
        ngsildKafkaTopic: 'ngsildSpB',
        topics: {
          subscribe: {
            sparkplugb_data_ingestion: 'spBv1.0/+/+/+/+'
          }
        }
      },
      kafka: {
        linger: 'linger'
      }
    },
    aesKey: '/app/keys/mqtt/mqtt_gw_secret.key'
  };

  const config_ngsild = {
    mqttBrokerUrl: 'brokerUrl',
    mqttBrokerLocalPort: '1234',
    mqttBrokerUsername: 'brokerUsername',
    mqttBrokerPassword: 'brokerPassword',
    authServicePort: '2345',
    topics: {
      subscribe: 'topic/subscribe'
    },
    cache: {
      hostname: 'redis',
      port: '6379',
      password: 'password'
    },
    kafka: {
      host: 'uri',
      partitions: 1,
      metricsPartitions: 1,
      replication: 1,
      timeoutMs: 10000,
      metricsTopic: 'metricsTopic',
      topicsRuleEngine: 'rules-update',
      topicsHeartbeatName: 'heartbeat',
      topicsHeartbeatInterval: 5000,
      maxPayloadSize: 1234456,
      retries: 10,
      requestTimeout: 4,
      maxRetryTime: 10
    },
    aesKey: '/app/keys/mqtt/mqtt_gw_secret.key'
  };

  const ToTest = rewire(fileToTest);

  const Kafka = function () {
    return {
      producer: function () {
        return {
          connect: function () {
          },
          on: function () {
          },
          send: function () {
            done();
          },
          events: 'event'
        };
      }
    };
  };

  class Logger {
    error () {}
    debug () {}
    warn () {}
    info () {}
  };

  const broker = {
    bind: function (subscribeTopics) {
      assert.equal(subscribeTopics, 'spBv1.0/+/+/+/+', 'sparkplugb Topic subscribed');
      return true;
    },
    on: function () {
      return true;
    },
    unbind: function () {
      return true;
    },
    publish: function () {
      return true;
    },
    buildPath: function () {
      return true;
    }
  };
  class KafkaAggregator {
    start () {}
    stop () {}
    addMessage () {}
  }
  class Validator {};
  const cid = '0c574252-31d5-4b76-bce6-53f2c56b544d';
  class Cache {
    getValue (seqKey, type) {
      assert.equal(seqKey, 'accountId/eonID', 'Wrong accountId/deviceID subtopic');
      assert.equal(type, 'seq', 'Wrong key value');
      return 0;
    }

    setValue (key, type) {
      assert.oneOf(key, ['accountId/eonID', cid], 'Wrong key on cache value received.');
      assert.oneOf(type, ['seq', 'id', 'dataType'], 'Wrong type to se value received.');
      return true;
    }
  }
  // let origKafkaAggregator;
  it('Shall initialize data ingestion modules Kafka and Cache', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    assert.isObject(spbdataIngestion);
    revert();
    done();
  });

  it('Validate SparkplugB Node Birth message device seq', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const birthMessage = {
      timestamp: 12345,
      metrics: [{
        name: 'bdseq',
        alias: cid,
        timestamp: 12345,
        dataType: 'Uint64',
        value: 123
      }],
      seq: 0
    };
    spbdataIngestion.validateSpbDevSeq('spBv1.0/accountId/NBIRTH/eonID/deviceId', birthMessage)
      .then((result) => {
        assert.equal(result, true, 'Invalid Seq for NBIRTH Message received');
        revert();
        done();
      })
      .catch((e) => done(e));
  });

  it('Validate SparkplugB Node Birth message  wrong device seq', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const birthMessage = {
      timestamp: 12345,
      metrics: [{
        name: 'bdseq',
        timestamp: 12345,
        dataType: 'Uint64',
        value: 123
      }],
      seq: 1
    };
    spbdataIngestion.validateSpbDevSeq('spBv1.0/accountId/NBIRTH/eonID/deviceId', birthMessage)
      .then((result) => {
        assert.equal(result, false, 'Invalid Seq for BIRTH Message received');
        revert();
        done();
      });
  });

  it('Validate SparkplugB Device Birth message device seq >0', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const birthMessage = {
      timestamp: 12345,
      metrics: [{
        name: 'temp',
        timestamp: 12345,
        dataType: 'Uint64',
        value: 123
      }],
      seq: 1
    };
    spbdataIngestion.validateSpbDevSeq('spBv1.0/accountId/DBIRTH/eonID/deviceId', birthMessage)
      .then((result) => {
        assert.equal(result, true, 'Invalid Seq for BIRTH Message received');
        revert();
        done();
      })
      .catch((e) => done(e));
  });

  it('Validate SparkplugB DBirth message device wrong seq i.e =0', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const birthMessage = {
      timestamp: 12345,
      metrics: [{
        name: 'bdseq',
        alias: cid,
        timestamp: 12345,
        dataType: 'Uint64',
        value: 123
      }],
      seq: 0
    };
    spbdataIngestion.validateSpbDevSeq('spBv1.0/accountId/DBIRTH/eonID/deviceId', birthMessage)
      .then((result) => {
        assert.deepEqual(result, false, 'Valid Seq for BIRTH Message received');
        revert();
        done();
      })
      .catch((e) => done(e));
  });

  it('Validate SparkplugB Device Data message device seq <255', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const DataMessage = {
      timestamp: 12345,
      metrics: [{
        name: 'temp',
        alias: cid,
        timestamp: 12345,
        dataType: 'Uint64',
        value: 123
      }],
      seq: 1
    };
    spbdataIngestion.validateSpbDevSeq('spBv1.0/accountId/DDATA/eonID/deviceId', DataMessage)
      .then((result) => {
        assert.deepEqual(result, true, 'Invalid Seq for Data Message received');
        revert();
        done();
      })
      .catch((e) => done(e));
  });

  it('Validate SparkplugB Device Data message wrong device seq >255', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const DataMessage = {
      timestamp: 12345,
      metrics: [{
        name: 'temp',
        alias: cid,
        timestamp: 12345,
        dataType: 'Uint64',
        value: 123
      }],
      seq: 256
    };
    spbdataIngestion.validateSpbDevSeq('spBv1.0/accountId/DDATA/eonID/deviceId', DataMessage)
      .then((result) => {
        assert.deepEqual(result, false, 'Invalid Seq for Data Message received');
        revert();
        done();
      })
      .catch((e) => done(e));
  });

  it(' Send Warning message for INVALID SparkplugB Device Data message with device seq >255', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const DataMessage = {
      timestamp: 12345,
      metrics: [{
        name: 'temp',
        alias: cid,
        timestamp: 12345,
        dataType: 'Uint64',
        value: 123
      }],
      seq: 256
    };
    spbdataIngestion.validateSpbDevSeq('spBv1.0/accountId/DDATA/eonID/deviceId', DataMessage)
      .then((result) => {
        assert.deepEqual(result, false, 'Invalid Seq for Data Message received');
        revert();
        done();
      })
      .catch((e) => done(e));
  });

  it('KafkaProduce for SparkplugB metric fails due to empty sparkplugB message', function (done) {
    config.mqtt.sparkplug.spBKafkaProduce = true;
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const DataMessage = {
      timestamp: 12345,
      metrics: [],
      seq: 2
    };
    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    const sendErrorOverChannel = function () {
      return true;
    };
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    spbdataIngestion.sendErrorOverChannel = sendErrorOverChannel;

    const kafkaPubReturn = spbdataIngestion.createKafakaPubData('spBv1.0/accountId/DBIRTH/eonID/deviceId', DataMessage);
    assert.oneOf(kafkaPubReturn, [false, undefined], ' Possible to produce kafka message for wrong alias/CID id: ' + kafkaPubReturn);
    revert();
    done();
  });

  it('KafkaProduce for SparkplugB metric fails for only ngsild topic due to empty sparkplugB message', function (done) {
    config.mqtt.sparkplug.spBKafkaProduce = false;
    config.mqtt.sparkplug.ngsildKafkaProduce = true;

    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const DataMessage = {
      timestamp: 12345,
      metrics: [],
      seq: 2
    };
    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    const sendErrorOverChannel = function () {
      return true;
    };
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    spbdataIngestion.sendErrorOverChannel = sendErrorOverChannel;

    const kafkaPubReturn = spbdataIngestion.createKafakaPubData('spBv1.0/accountId/DBIRTH/eonID/deviceId', DataMessage);
    assert.oneOf(kafkaPubReturn, [false, undefined], ' Possible to produce kafka message for wrong alias/CID id: ' + kafkaPubReturn);
    revert();
    done();
  });

  it('Create Kafka  publish data on Spb topic', function (done) {
    const Kafka = function () {
      return {
        producer: function () {
          return {
            connect: function () {
            },
            on: function () {
            },
            send: function (payload) {
              message = payload.messages[0];
              assert.oneOf(message.key, ['spBv1.0/accountId/NBIRTH/eonID/', 'spBv1.0/accountId/DBIRTH/eonID/deviceId', 'spBv1.0/accountId/DDATA/eonID/deviceId'], 'Received Kafka payload key not correct');
              const value = {
                name: 'temp',
                alias: cid,
                timestamp: 12345,
                dataType: 'Uint64',
                value: 'value'
              };
              assert.deepEqual(JSON.parse(message.value), value, 'Received Kafke message not correct');
              spbdataIngestion.stopAggregator();
              revert();
              done();
              return new Promise(() => {});
            },
            events: 'event'
          };
        }
      };
    };

    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    class Validator {
      validate () {
        return { errors: [] };
      }
    }
    config.mqtt.sparkplug.spBKafkaProduce = true;
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator
    });
    const spbdataIngestion = new ToTest(config);
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    let message = {
      timestamp: 12345,
      metrics: [{
        name: 'temp',
        alias: cid,
        timestamp: 12345,
        dataType: 'Uint64',
        value: 'value'
      }],
      seq: 0
    };
    spbdataIngestion.processDataIngestion('spBv1.0/accountId/NBIRTH/eonID/', message);
    spbdataIngestion.processDataIngestion('spBv1.0/accountId/DBIRTH/eonID/deviceId', message);
    spbdataIngestion.processDataIngestion('spBv1.0/accountId/DDATA/eonID/deviceId', message);
    //revert();
    //done();
  });

  it('Create Kafka  publish Relationship data on NGSI-LD Spb topic', function (done) {
    const Kafka = function () {
      return {
        producer: function () {
          return {
            connect: function () {
            },
            on: function () {
            },
            send: function (payload) {
              message = payload.messages[0];
              assert.oneOf(message.key, ['spBv1.0/accountId/NBIRTH/eonID/', 'spBv1.0/accountId/DBIRTH/eonID/deviceId',
                'spBv1.0/accountId/DDATA/eonID/deviceId'], 'Received Kafka payload key not correct');
              const value = {
                id: 'deviceId' + '\\' + 'https://industry-fusion.com/types/v0.9/hasFilter',
                entityId: 'deviceId',
                name: 'https://industry-fusion.com/types/v0.9/hasFilter',
                type: 'https://uri.etsi.org/ngsi-ld/Relationship',
                'https://uri.etsi.org/ngsi-ld/hasObject': 'value',
                nodeType: '@id',
                index: 0
              };
              assert.deepEqual(JSON.parse(message.value), value, 'Received Kafke message not correct');
              spbdataIngestion.stopAggregator();
              revert()
              done();
              return new Promise(() => {});
            },
            events: 'event'
          };
        }
      };
    };

    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    class Validator {
      validate () {
        return { errors: [] };
      }
    }
    config.mqtt.sparkplug.spBKafkaProduce = false;
    config.mqtt.sparkplug.ngsildKafkaProduce = true;
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator
    });
    const spbdataIngestion = new ToTest(config);
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    var message = {
      timestamp: 12345,
      metrics: [{
        name: 'Relationship/https://industry-fusion.com/types/v0.9/hasFilter',
        alias: cid,
        timestamp: 12345,
        dataType: 'string',
        value: 'value'
      }],
      seq: 0
    };
    spbdataIngestion.processDataIngestion('spBv1.0/accountId/DBIRTH/eonID/deviceId', message);
    spbdataIngestion.processDataIngestion('spBv1.0/accountId/DDATA/eonID/deviceId', message);
    //revert();
    //done();
  });

  it('Create Kafka  publish Properties data on NGSI-LD Spb topic', function (done) {
    const Kafka = function () {
      return {
        producer: function () {
          return {
            connect: function () {
            },
            on: function () {
            },
            send: function (payload) {
              message = payload.messages[0];
              assert.oneOf(message.key, ['spBv1.0/accountId/NBIRTH/eonID/', 'spBv1.0/accountId/DBIRTH/eonID/deviceId', 'spBv1.0/accountId/DDATA/eonID/deviceId'], 'Received Kafka payload key not correct');
              const value = {
                id: 'deviceId' + '\\' + 'https://industry-fusion.com/types/v0.9/hasFilter',
                entityId: 'deviceId',
                nodeType: '@value',
                name: 'https://industry-fusion.com/types/v0.9/hasFilter',
                type: 'https://uri.etsi.org/ngsi-ld/Property',
                'https://uri.etsi.org/ngsi-ld/hasValue': 'value',
                index: 0
              };
              assert.deepEqual(JSON.parse(message.value), value, 'Received Kafke message not correct');
              spbdataIngestion.stopAggregator();
              revert();
              done();
              return new Promise(() => {});
            },
            events: 'event'
          };
        }
      };
    };

    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    class Validator {
      validate () {
        return { errors: [] };
      }
    }
    config.mqtt.sparkplug.spBKafkaProduce = false;
    config.mqtt.sparkplug.ngsildKafkaProduce = true;
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator
    });
    const spbdataIngestion = new ToTest(config);
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    var message = {
      timestamp: 12345,
      metrics: [{
        name: 'Property/https://industry-fusion.com/types/v0.9/hasFilter',
        alias: cid,
        timestamp: 12345,
        dataType: 'Uint64',
        value: 'value'
      }],
      seq: 0
    };
    spbdataIngestion.processDataIngestion('spBv1.0/accountId/DBIRTH/eonID/deviceId', message);
    spbdataIngestion.processDataIngestion('spBv1.0/accountId/DDATA/eonID/deviceId', message);
    //revert();
    //done();
  });

  it('Process data Ingestion for sparkplugB topic', function (done) {
    class Validator {
      validate () {
        return { errors: [] };
      }
    }
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    const createKafakaPubData = function () {
      return true;
    };
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    spbdataIngestion.createKafakaPubData = createKafakaPubData;

    const message = {
      timestamp: 12345,
      metrics: [{
        name: 'temp',
        alias: cid,
        timestamp: 12345,
        dataType: 'Uint64',
        value: 'value'
      }],
      seq: 0
    };

    spbdataIngestion.processDataIngestion('spBv1.0/accountId/DDATA/eonID/deviceId', message);
    revert();
    done();
  });

  it('Process data Ingestion for wrong SparkplugB topic', function (done) {
    class Validator {
      validate () {
        return { errors: [] };
      }
    }
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      Validator: Validator,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    const createKafakaPubData = function () {
      return true;
    };
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    spbdataIngestion.createKafakaPubData = createKafakaPubData;

    const message = {
      timestamp: 12345,
      metrics: [{
        name: 'temp',
        alias: cid,
        timestamp: 12345,
        dataType: 'Uint64',
        value: 'value'
      }],
      seq: 0
    };
    const processDataIngestReturn = spbdataIngestion.processDataIngestion('spBv1.0/accountId/MATA/eonID/deviceId', message);
    assert.deepEqual(processDataIngestReturn, undefined, 'Unable to validate SParkplugB schema');
    revert();
    done();
  });

  it('Process data Ingestion with 2nd array component of SparkplugB Metric empty', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    const createKafakaPubData = function () {
      return true;
    };
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    spbdataIngestion.createKafakaPubData = createKafakaPubData;

    const message = {
      timestamp: 12345,
      metrics: [
        {
          name: 'temp',
          alias: cid,
          timestamp: 12345,
          dataType: 'Uint64',
          value: 'value'
        }, {}],
      seq: 0
    };
    const processDataIngestReturn = spbdataIngestion.processDataIngestion('spBv1.0/accountId/DDATA/eonID/deviceId', message);
    assert.deepEqual(processDataIngestReturn, undefined, 'Unable to validate SParkplugB schema');
    revert();
    done();
  });

  it('Process data Ingestion with wrong type for SparkplugB Metric', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    const createKafakaPubData = function () {
      return true;
    };
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    spbdataIngestion.createKafakaPubData = createKafakaPubData;

    const message = {
      timestamp: 12345,
      metrics: [
        {
          name: 345,
          alias: cid,
          timestamp: 12345,
          dataType: 'Uint64',
          value: 'value'
        }],
      seq: 0
    };
    const processDataIngestReturn = spbdataIngestion.processDataIngestion('spBv1.0/accountId/DDATA/eonID/deviceId', message);
    assert.deepEqual(processDataIngestReturn, undefined, 'Unable to validate SParkplugB schema');
    revert();
    done();
  });

  it('Process data Ingestion with wrong format SparkplugB Metric', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      KafkaAggregator: KafkaAggregator
    });

    const spbdataIngestion = new ToTest(config);
    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    const createKafakaPubData = function () {
      return true;
    };
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    spbdataIngestion.createKafakaPubData = createKafakaPubData;

    const message = {
      timestamp: 12345,
      metrics: [{}],
      seq: 0
    };
    const processDataIngestReturn = spbdataIngestion.processDataIngestion('spBv1.0/accountId/DDATA/eonID/deviceId', message);
    assert.deepEqual(processDataIngestReturn, undefined, 'Unable to validate SParkplugB schema');
    revert();
    done();
  });
  it('Process data Ingestion with missing metric in SparkplugB payload', function (done) {
    class Validator {
      validate () {
        return { errors: [] };
      }
    }
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    const validateSpbDevSeq = function () {
      return Promise.resolve(true);
    };
    const createKafakaPubData = function () {
      return true;
    };
    spbdataIngestion.validateSpbDevSeq = validateSpbDevSeq;
    spbdataIngestion.createKafakaPubData = createKafakaPubData;

    const message = {
      timestamp: 12345,
      seq: 0
    };
    const processDataIngestReturn = spbdataIngestion.processDataIngestion('spBv1.0/accountId/DDATA/eonID/deviceId', message);
    assert.deepEqual(processDataIngestReturn, undefined, 'Unable to validate SParkplugB schema');
    revert();
    done();
  });

  it('Process data Ingestion with INVALID seq of SparkplugB Metric', function (done) {
    class Validator {
      validate () {
        return { errors: [] };
      }
    }
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);
    // var validateSpbDevSeq = function(){
    //     return Promise.resolve(true);
    // };
    const createKafakaPubData = function () {
      return true;
    };
    // spbdataIngestion.validateSpbDevSeq =validateSpbDevSeq;
    spbdataIngestion.createKafakaPubData = createKafakaPubData;

    const message = {
      timestamp: 12345,
      metrics: [
        {
          name: 'temp',
          alias: cid,
          timestamp: 12345,
          dataType: 'Uint64',
          value: 'value'
        }],
      seq: 290
    };
    const processDataIngestReturn = spbdataIngestion.processDataIngestion('spBv1.0/accountId/DDATA/eonID/deviceId', message);
    assert.deepEqual(processDataIngestReturn, true, 'Unable to validate SParkplugB schema');
    revert();
    done();
  });

  it('Shall check mqtt bind to topic', function (done) {
    const revert = ToTest.__set__({
      Kafka: Kafka,
      Cache: Cache,
      Logger: Logger,
      KafkaAggregator: KafkaAggregator
    });
    const spbdataIngestion = new ToTest(config);

    spbdataIngestion.bind(broker);
    revert();
    done();
  });
});
