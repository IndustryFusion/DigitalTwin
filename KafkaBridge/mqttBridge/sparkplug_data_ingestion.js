/**
* Copyright (c) 2017, 2020 Intel Corporation
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
const config = require('../config/config.json');
const { Kafka, logLevel } = require('kafkajs');
const { Partitioners } = require('kafkajs');
const CacheFactory = require('../lib/cache');
const ngsildMapper = require('./spb-ngsild-mapper');
const Logger = require('../lib/logger');
const dataSchema = require('./schemas/data.json');
const Validator = require('jsonschema').Validator;

let me;
const MESSAGE_TYPE = {
  WITHSEQ: {
    NBIRTH: 'NBIRTH',
    DBIRTH: 'DBIRTH',
    NDATA: 'NDATA',
    DDATA: 'DDATA',
    DDEATH: 'DDEATH'
  },
  CMD: {
    NCMD: 'NCMD',
    DCMD: 'DCMD'
  },
  NDEATH: 'NDEATH'
};

// Round Robin partitioner used to handle single clients with
// too high throughput
const RoundRobinPartitioner = () => {
  let curPartition = 0;
  return ({ partitionMetadata }) => {
    const numPartitions = partitionMetadata.length;
    const partition = curPartition % numPartitions;
    curPartition++;
    return partition;
  };
};

// @brief Aggregates messages for periodic executed Kafka producer
class KafkaAggregator {
  constructor (config) {
    this.logger = new Logger(config);
    this.config = config;
    this.spbMessageArray = [];
    this.ngsildMessageArray = [];
    try {
      const kafka = new Kafka({
        logLevel: logLevel.INFO,
        brokers: config.kafka.brokers,
        clientId: 'spBFrontend-metrics',
        requestTimeout: config.mqtt.kafka.requestTimeout,
        retry: {
          maxRetryTime: config.mqtt.kafka.maxRetryTime,
          retries: config.mqtt.kafka.retries
        }
      });
      if (config.mqtt.kafka.partitioner === 'roundRobinPartitioner') {
        this.kafkaProducer = kafka.producer({ createPartitioner: RoundRobinPartitioner });
        this.logger.info('Round Robin partitioner enforced');
      } else {
        this.kafkaProducer = kafka.producer({ createPartitioner: Partitioners.DefaultPartitioner });
        this.logger.info('Default partitioner is used');
      }
      const { CONNECT, DISCONNECT } = this.kafkaProducer.events;
      this.kafkaProducer.on(DISCONNECT, e => {
        this.logger.warn(`SparkplugB Metric producer disconnected!: ${e.timestamp}`);
        this.kafkaProducer.connect();
      });
      this.kafkaProducer.on(CONNECT, e => this.logger.debug('Kafka SparkplugB metric producer connected: ' + e));
      this.kafkaProducer.connect();
    } catch (e) {
      this.logger.error('Exception occured while creating Kafka SparkplugB Producer: ' + e);
    }
  }

  start (timer) {
    this.intervalObj = setInterval(() => {
      if (this.spbMessageArray.length === 0 && this.ngsildMessageArray.length === 0) {
        return;
      }
      let spbKafkaPayloads, ngsildKafkaPayloads;
      // If config enabled for producing kafka message on SparkPlugB topic
      if (this.spbMessageArray.length !== 0) {
        spbKafkaPayloads = {
          topic: this.config.mqtt.sparkplug.spBkafKaTopic,
          messages: this.spbMessageArray
        };
        this.logger.info('will now deliver Kafka message  on topic :  ' + spbKafkaPayloads.topic + ' with message: ' + JSON.stringify(spbKafkaPayloads));
        this.kafkaProducer.send(spbKafkaPayloads)
          .catch((err) => {
            return this.logger.error('Could not send message to Kafka on topic: ' + spbKafkaPayloads.topic + ' with error msg:  ' + err);
          }
          );
      }
      // If config enabled for producing kafka message on NGSI-LDSpB topic
      if (this.ngsildMessageArray.length !== 0) {
        ngsildKafkaPayloads = {
          topic: this.config.mqtt.sparkplug.ngsildKafkaTopic,
          messages: this.ngsildMessageArray
        };
        this.logger.info('will now deliver Kafka message  on topic :  ' + ngsildKafkaPayloads.topic + ' with message:  ' + JSON.stringify(ngsildKafkaPayloads));
        this.kafkaProducer.send(ngsildKafkaPayloads)
          .catch((err) => {
            return this.logger.error('Could not send message to Kafka on topic: ' + ngsildKafkaPayloads.topic + ' with error msg:  ' + err);
          }
          );
      }
      this.spbMessageArray = [];
      this.ngsildMessageArray = [];
    }, timer);
  }

  stop () {
    clearInterval(this.intervalObj);
  }

  addMessage (message, topic) {
    if (topic === this.config.mqtt.sparkplug.spBkafKaTopic) {
      this.spbMessageArray.push(message);
    } else if (topic === this.config.mqtt.sparkplug.ngsildKafkaTopic) {
      this.ngsildMessageArray.push(message);
    }
  }
}

module.exports = async function SparkplugHandler (config) {
  const logger = new Logger(config);
  const topics_subscribe = config.mqtt.sparkplug.topics.subscribe;
  const topics_publish = config.mqtt.sparkplug.topics.publish;

  const validator = new Validator();
  const cacheFactory = await new CacheFactory(config, logger);
  const cache = cacheFactory.getInstance();
  me = this;
  me.kafkaAggregator = new KafkaAggregator(config);
  me.kafkaAggregator.start(config.mqtt.kafka.linger);

  me.logger = logger;
  me.cache = cache;
  me.token = null;
  me.config = config;

  me.stopAggregator = function () {
    me.kafkaAggregator.stop();
  };

  me.getToken = function (did) {
    /* jshint unused:false */
    return new Promise(function (resolve, reject) {
      resolve(null);
    });
  };

  /* Validate SpB Node & Device are with proper seq number and store in cache
    * To Do: In future add function to send node command for RE-BIRTH message in case seq number or CID/alias not matched
    */
  me.validateSpbDevSeq = async function (topic, bodyMessage) {
    const subTopic = topic.split('/');
    const accountId = subTopic[1];
    const devID = subTopic[4];
    const eonID = subTopic[3];
    const redisSeqKey = accountId + '/' + eonID;
    try {
      if (subTopic[2] === 'NBIRTH') {
        if (bodyMessage.seq === 0) {
          const redisResult = await me.cache.setValue(redisSeqKey, 'seq', 0);
          if (redisResult !== null || redisResult !== undefined) {
            me.logger.debug('NBIRTH  message of eonid: ' + eonID + ' has right seq no. 0  and stored in redis ');
            return true;
          } else {
            me.logger.warn('Could not store birth seq value in redis with key: ' + redisSeqKey + ', this will effect seq no verification for data message');
            return false;
          }
        } else {
          me.logger.error('Sequence is not 0, so ignoring BIRTH message for eonID: ' + eonID + ', and seq no: ' + bodyMessage.seq);
          return false;
        }
      } else if (subTopic[2] === 'DDATA' || subTopic[2] === 'DBIRTH' || subTopic[2] === 'DDEATH' || subTopic[2] === 'NDATA') {
        let redisSeq = await me.cache.getValue(redisSeqKey, 'seq');
        if (redisSeq === null || redisSeq === undefined) {
          me.logger.warn('Could not load seq value from redis for topic: ' + subTopic[2] + ' and dev :' + devID);
          return false;
        }
        if ((bodyMessage.seq > redisSeq && bodyMessage.seq <= 255) || (bodyMessage.seq === 0 && redisSeq === 255)) {
          redisSeq = bodyMessage.seq;
          const redisResult = await me.cache.setValue(redisSeqKey, 'seq', redisSeq);
          if (!redisResult) {
            me.logger.warn('Could not store seq value in redis, this will effect seq no verification for data message');
            return false;
          } else {
            me.logger.debug('Valid seq, Data Seq: ' + redisSeq + ' added for dev: ' + devID);
            return true;
          }
        } else {
          me.logger.error('Sequence is not more than previous seq number so ignoring message for devID: ' + devID + ', and seq no: ' + bodyMessage.seq);
          return false;
        }
      }
    } catch (err) {
      me.logger.error('ERROR in validating the SparkPlugB payload ' + err);
      return false;
    }
  };

  me.createKafakaPubData = function (topic, bodyMessage) {
    /** * For forwarding sparkplugB data directly without kafka metrics format
        * @param ngsildKafkaProduce is set in the config file
        *  */
    const subTopic = topic.split('/');
    const devID = subTopic[4];

    if (config.sparkplug.spBKafkaProduce) {
      /* Validating each component of metric payload if they are valid or not
            * By verifying there existence in DB or cache
            */
      bodyMessage.metrics.forEach(item => {
        const kafkaMessage = item;
        if (subTopic[2] === 'NBIRTH' || subTopic[2] === 'DDATA' || subTopic[2] === 'DBIRTH') {
          const key = topic;
          const message = { key, value: JSON.stringify(kafkaMessage) };
          me.logger.debug('Selecting kafka message topic SparkplugB with spB format payload for data type: ' + subTopic[2]);
          me.kafkaAggregator.addMessage(message, config.sparkplug.spBkafKaTopic);
          return true;
        }
      });
    }
    if (config.sparkplug.ngsildKafkaProduce) {
      /* Validating each component of metric payload if they are valid or not
            * By verifying there existence in DB or cache
            */
      bodyMessage.metrics.forEach(item => {
        const kafkaMessage = item;
        if (subTopic[2] === 'NBIRTH' || subTopic[2] === 'DBIRTH') {
          me.logger.info('Received spB NBIRTH/DBIRTH message, ignoring currently kafka forward for SpBNGSI-LD topic');
          return true;
        }
        /** Validating component id in the database to check for DDATA */
        else if (subTopic[2] === 'DDATA') {
          const metricName = kafkaMessage.name.split('/');
          const metricType = metricName[0];
          const key = topic;
          let ngsiMappedKafkaMessage;
          if (metricType === 'Relationship') {
            ngsiMappedKafkaMessage = ngsildMapper.mapSpbRelationshipToKafka(devID, kafkaMessage);
            me.logger.debug(' Mapped SpB Relationship data to NGSI-LD relationship type:  ' + JSON.stringify(ngsiMappedKafkaMessage));
            const message = { key, value: JSON.stringify(ngsiMappedKafkaMessage) };
            me.kafkaAggregator.addMessage(message, config.sparkplug.ngsildKafkaTopic);
          } else if (metricType === 'Property') {
            ngsiMappedKafkaMessage = ngsildMapper.mapSpbPropertyToKafka(devID, kafkaMessage);
            me.logger.debug(' Mapped SpB Properties data to NGSI-LD properties type:  ' + JSON.stringify(ngsiMappedKafkaMessage));
            const message = { key, value: JSON.stringify(ngsiMappedKafkaMessage) };
            me.kafkaAggregator.addMessage(message, config.sparkplug.ngsildKafkaTopic);
          } else {
            me.logger.debug(' Unable to create kafka message topic for SpBNGSI-LD topic for Metric Name: ' + kafkaMessage.name + " ,doesn't match NGSI-LD Name type: ");
          }
          return true;
        }
      });
    }
  };

  me.processDataIngestion = function (topic, message) {
    /*  It will be checked if the ttl exist, if it exits the package need to be discarded
        */
    const subTopic = topic.split('/');
    me.logger.debug('Data Submission Detected : ' + topic + ' Message: ' + JSON.stringify(message));
    if (Object.values(MESSAGE_TYPE.WITHSEQ).includes(subTopic[2])) {
      const validationResult = validator.validate(message, dataSchema.SPARKPLUGB);
      if (validationResult.errors.length > 0) {
        me.logger.warn('Schema rejected message! Message will be discarded: ' + message);
      } else {
        /* Validating SpB seq number if it is alligned with previous or not
            *  To Do: If seq number is incorrect, send command to device for resend Birth Message
            */
        me.validateSpbDevSeq(topic, message).then(values => {
          if (values) {
            //          me.createKafakaPubData(topic,message);
            me.logger.info('Valid SpB Seq Number, creating Kafka pub data ');
            //            return;
          }
        }).catch(function (err) {
          //      me.logger.warn("Could not send data to Kafka due to SpB Validity failure " + err);
          me.logger.warn('Invalid SpB Sequance number, still moving forward to create Kafka pub data ' + err);
          //        return null;
        });
        me.createKafakaPubData(topic, message);
        return true;
      }
    } else {
      me.logger.warn('Invalid SparkplugB topic');
    }
  };
  me.connectTopics = function () {
    me.broker.bind(topics_subscribe.sparkplugb_data_ingestion, me.processDataIngestion);
    return true;
  };
  me.handshake = function () {
    if (me.broker) {
      me.broker.on('reconnect', function () {
        me.logger.debug('Reconnect topics');
        me.broker.unbind(topics_subscribe.sparkplugb_data_ingestion, function () {
          me.token = null;
          me.connectTopics();
          me.sessionObject = {};
        });
      });
    }
  };

  // setup channel to provide error feedback to device agent
  me.sendErrorOverChannel = function (topic, did, message) {
    const path = me.broker.buildPath(topics_publish.error, [topic, did]);
    me.broker.publish(path, message, null);
  };
  /**
    * @description It's bind to the MQTT topics
    * @param broker
    */
  me.bind = function (broker) {
    me.broker = broker;
    me.handshake();
    me.connectTopics();
  };
};
