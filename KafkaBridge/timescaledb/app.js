/**
* Copyright (c) 2023 Intel Corporation
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

const GROUPID = 'timescaledbkafkabridge';
const CLIENTID = 'timescaledbkafkaclient';
const { Kafka } = require('kafkajs');
const fs = require('fs');
const config = require('../config/config.json');
const sequelize = require('./utils/tsdb-connect'); // Import sequelize object, Database connection pool managed by Sequelize.
const { QueryTypes } = require('sequelize');
const Logger = require('../lib/logger.js');
const entityHistoryTable = require('./model/entity_history.js'); // Import entityHistory model/table defined
const historyTableName = config.timescaledb.tablename;
const runningAsMain = require.main === module;
const logger = new Logger(config);

const kafka = new Kafka({
  clientId: CLIENTID,
  brokers: config.kafka.brokers
});
const consumer = kafka.consumer({ groupId: GROUPID, allowAutoTopicCreation: false });
const processMessage = async function ({ topic, partition, message }) {
  try {
    const body = JSON.parse(message.value);
    if (body.type === undefined) {
      return;
    }
    const datapoint = {};
    const kafkaTimestamp = Number(message.timestamp);
    const epochDate = new Date(kafkaTimestamp);
    const utcTime = epochDate.toISOString();

    // Creating datapoint which will be inserted to tsdb
    datapoint.observedAt = utcTime;
    datapoint.modifiedAt = utcTime;
    datapoint.entityId = body.entityId;
    datapoint.attributeId = body.name;
    datapoint.nodeType = body.nodeType;
    datapoint.index = body.index;
    datapoint.datasetId = body.id;

    if (body.type === 'https://uri.etsi.org/ngsi-ld/Property') {
      let value = body['https://uri.etsi.org/ngsi-ld/hasValue'];
      if (!isNaN(value)) {
        value = Number(value);
      }
      datapoint.attributeType = body.type;
      datapoint.value = value;
      if (body.valueType !== undefined && body.valueType !== null) {
        datapoint.valueType = body.valueType;
      }
    } else if (body.type === 'https://uri.etsi.org/ngsi-ld/Relationship') {
      datapoint.attributeType = body.type;
      datapoint.value = body['https://uri.etsi.org/ngsi-ld/hasObject'];
    } else {
      logger.error('Could not send Datapoints: Neither Property nor Relationship');
      return;
    }

    entityHistoryTable.create(datapoint).then(() => {
      logger.debug('Datapoint succefully stored in tsdb table');
    })
      .catch((err) => logger.error('Error in storing datapoint in tsdb: ' + err));
  } catch (e) {
    logger.error('could not process message: ' + e.stack);
  }
};

const startListener = async function () {
  let hypertableStatus = false;
  sequelize.authenticate().then(() => {
    logger.info('TSDB connection has been established.');
  })
    .catch(error => {
      logger.error('Unable to connect to TSDB:', error);
      process.exit(1);
    });

  await sequelize.sync().then(() => {
    logger.debug('Succesfully created/synced tsdb table : ' + historyTableName);
  })
    .catch(error => {
      logger.error('Unable to create/sync table in  tsdb:', error);
    });

  const createUserQuery = 'CREATE ROLE ' + config.timescaledb.tsdbuser + ';';
  await sequelize.query(createUserQuery, { type: QueryTypes.SELECT }).then(() => {
    logger.error('User ' + config.timescaledb.tsdbuser + 'created');
  }).catch(error => {
    logger.warn('Cannot create user, probably already existing.', error);
  });

  const grantUserQuery = 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO ' + config.timescaledb.tsdbuser + ';';
  await sequelize.query(grantUserQuery, { type: QueryTypes.SELECT }).then(() => {
    logger.info('Granted access to user ' + config.timescaledb.tsdbuser);
  }).catch(error => {
    logger.warn('Cannot grant access to user.', error);
  });
  const htChecksqlquery = 'SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = \'' + historyTableName + '\';';
  await sequelize.query(htChecksqlquery, { type: QueryTypes.SELECT }).then((hypertableInfo) => {
    if (hypertableInfo.length) {
      hypertableStatus = true;
    }
  })
    .catch(error => {
      logger.warn('Hypertable was not created, creating one', error);
    });

  if (!hypertableStatus) {
    const htCreateSqlquery = 'SELECT create_hypertable(\'' + historyTableName + '\', \'observedAt\', migrate_data => true);';
    await sequelize.query(htCreateSqlquery, { type: QueryTypes.SELECT }).then((hyperTableCreate) => {
      logger.debug('Hypertable created, return from sql query: ' + JSON.stringify(hyperTableCreate));
    })
      .catch(error => {
        logger.error('Unable to create hypertable', error);
      });
  };

  // Kafka topic subscription
  await consumer.connect();
  await consumer.subscribe({ topic: config.timescaledb.topic, fromBeginning: false });
  await consumer.run({
    eachMessage: async ({ topic, partition, message }) => processMessage({ topic, partition, message })
  }).catch(e => console.error(`[example/consumer] ${e.message}`, e));

  const errorTypes = ['unhandledRejection', 'uncaughtException'];
  const signalTraps = ['SIGTERM', 'SIGINT', 'SIGUSR2'];

  errorTypes.map(type =>
    process.on(type, async e => {
      try {
        console.log(`process.on ${type}`);
        console.error(e);
        await consumer.disconnect();
        process.exit(0);
      } catch (_) {
        process.exit(1);
      }
    }));

  signalTraps.map(type =>
    process.once(type, async () => {
      try {
        await consumer.disconnect();
      } finally {
        process.kill(process.pid, type);
      }
    }));

  try {
    fs.writeFileSync('/tmp/ready', 'ready');
    fs.writeFileSync('/tmp/healthy', 'healthy');
  } catch (err) {
    logger.error(err);
  }
};

if (runningAsMain) {
  logger.info('Now staring Kafka listener');
  startListener();
}
