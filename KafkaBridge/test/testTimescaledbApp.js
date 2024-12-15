/**
* Copyright (c) 2022, 2023 Intel Corporation
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

const { assert } = require('chai');
const chai = require('chai');
global.should = chai.should();
const rewire = require('rewire');
const sinon = require('sinon');
const toTest = rewire('../timescaledb/app.js');

const logger = {
  debug: function () {},
  info: function () {},
  error: function () {}
};

const Logger = function () {
  return logger;
};

describe('Test timescaledb processMessage', function () {
  it('Should send a Property with @value nodetype', async function () {
    const entityHistoryTable = {
      upsert: async function (datapoint) {
        assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
        assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
        assert.equal(datapoint.entityId, 'entityId');
        assert.equal(datapoint.attributeId, 'name');
        assert.equal(datapoint.nodeType, '@value');
        assert.equal(datapoint.index, 0);
        assert.equal(datapoint.datasetId, '@none');
        assert.equal(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Property');
        assert.equal(datapoint.value, 123);
        return Promise.resolve(datapoint);
      }
    };

    const kafkamessage = {
      topic: 'topic',
      partition: 'partition',
      message: {
        value: JSON.stringify({
          id: 'id',
          entityId: 'entityId',
          name: 'name',
          type: 'https://uri.etsi.org/ngsi-ld/Property',
          'https://uri.etsi.org/ngsi-ld/hasValue': 123,
          nodeType: '@value',
          index: 0
        }),
        timestamp: '1689344953110'
      }
    };
    toTest.__set__('entityHistoryTable', entityHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processMessage');
    await processMessage(kafkamessage);
  });

  it('Should send a Relationship', async function () {
    const entityHistoryTable = {
      upsert: async function (datapoint) {
        assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
        assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
        assert.equal(datapoint.entityId, 'entityId');
        assert.equal(datapoint.attributeId, 'relationship');
        assert.equal(datapoint.nodeType, '@id');
        assert.equal(datapoint.index, 0);
        assert.equal(datapoint.datasetId, '@none');
        assert.equal(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Relationship');
        assert.equal(datapoint.value, 'object');
        return Promise.resolve(datapoint);
      }
    };

    const kafkamessage = {
      topic: 'topic',
      partition: 'partition',
      message: {
        value: JSON.stringify({
          id: 'id',
          entityId: 'entityId',
          name: 'relationship',
          type: 'https://uri.etsi.org/ngsi-ld/Relationship',
          'https://uri.etsi.org/ngsi-ld/hasObject': 'object',
          nodeType: '@id',
          index: 0
        }),
        timestamp: '1689344953110'
      }
    };
    toTest.__set__('entityHistoryTable', entityHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processMessage');
    await processMessage(kafkamessage);
  });

  it('Should send a Property with @value nodetype and valueType string', async function () {
    const entityHistoryTable = {
      upsert: async function (datapoint) {
        assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
        assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
        assert.equal(datapoint.entityId, 'entityId');
        assert.equal(datapoint.attributeId, 'property');
        assert.equal(datapoint.nodeType, '@value');
        assert.equal(datapoint.index, 0);
        assert.equal(datapoint.datasetId, '@none');
        assert.equal(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Property');
        assert.equal(datapoint.value, 'value');
        assert.equal(datapoint.valueType, 'http://www.w3.org/2001/XMLSchema#string');
        return Promise.resolve(datapoint);
      }
    };

    const kafkamessage = {
      topic: 'topic',
      partition: 'partition',
      message: {
        value: JSON.stringify({
          id: 'id',
          entityId: 'entityId',
          name: 'property',
          type: 'https://uri.etsi.org/ngsi-ld/Property',
          'https://uri.etsi.org/ngsi-ld/hasValue': 'value',
          nodeType: '@value',
          valueType: 'http://www.w3.org/2001/XMLSchema#string',
          index: 0
        }),
        timestamp: '1689344953110'
      }
    };
    toTest.__set__('entityHistoryTable', entityHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processMessage');
    await processMessage(kafkamessage);
  });

  it('Should reject wrong object type- property/relationship with @value nodetype and valueType string', async function () {
    const entityHistoryTable = {
      upsert: async function (datapoint) {
        assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
        assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
        assert.equal(datapoint.entityId, 'entityId');
        assert.equal(datapoint.attributeId, 'property');
        assert.equal(datapoint.nodeType, '@value');
        assert.equal(datapoint.index, 0);
        assert.equal(datapoint.datasetId, '@none');
        assert.notEqual(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Property');
        assert.equal(datapoint.value, 'value');
        assert.equal(datapoint.valueType, 'http://www.w3.org/2001/XMLSchema#string');
        return Promise.resolve(datapoint);
      }
    };

    const kafkamessage = {
      topic: 'topic',
      partition: 'partition',
      message: {
        value: JSON.stringify({
          id: 'id',
          entityId: 'entityId',
          name: 'property',
          type: 'https://uri.etsi.org/ngsi-ld',
          'https://uri.etsi.org/ngsi-ld/hasValue': 'value',
          nodeType: '@value',
          valueType: 'http://www.w3.org/2001/XMLSchema#string',
          index: 0
        }),
        timestamp: '1689344953110'
      }
    };
    toTest.__set__('entityHistoryTable', entityHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processMessage');
    await processMessage(kafkamessage);
  });

  it('Should send a Property with wrong timestamp and attributeType', async function () {
    const entityHistoryTable = {
      upsert: async function (datapoint) {
        assert.notEqual(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
        assert.notEqual(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
        assert.equal(datapoint.entityId, 'entityId');
        assert.equal(datapoint.attributeId, 'property');
        assert.equal(datapoint.nodeType, '@value');
        assert.equal(datapoint.index, 0);
        assert.equal(datapoint.datasetId, '@none');
        assert.notEqual(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Relationship');
        assert.equal(datapoint.value, 'value');
        return Promise.resolve(datapoint);
      }
    };

    const kafkamessage = {
      topic: 'topic',
      partition: 'partition',
      message: {
        value: JSON.stringify({
          id: 'id',
          entityId: 'entityId',
          name: 'property',
          type: 'https://uri.etsi.org/ngsi-ld/Property',
          'https://uri.etsi.org/ngsi-ld/hasValue': 'value',
          nodeType: '@value',
          index: 0
        }),
        timestamp: '168934495320'
      }
    };
    toTest.__set__('entityHistoryTable', entityHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processMessage');
    await processMessage(kafkamessage);
  });
});

describe('Test startListener', function () {
  const entityTableName = 'entities';
  const attributeTableName = 'attributes';
  const htAttributeChecksqlquery = 'SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = \'' + attributeTableName + '\';';
  const htEntitieChecksqlquery = 'SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = \'' + entityTableName + '\';';
  const htAttributeCreateSqlquery = 'SELECT create_hypertable(\'' + attributeTableName + '\', \'observedAt\', migrate_data => true);';
  const htEntityCreateSqlquery = 'SELECT create_hypertable(\'' + entityTableName + '\', \'observedAt\', migrate_data => true);';
  const htCreateRole = 'CREATE ROLE tsdbuser;';
  const htGrant = 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO tsdbuser;';

  const SequelizeClass = class Sequelize {
    authenticate () {
      return Promise.resolve();
    }

    sync () {
      return Promise.resolve();
    }

    query (sqlquery) {
      assert.oneOf(sqlquery, [htAttributeChecksqlquery, htEntitieChecksqlquery, htAttributeCreateSqlquery, htEntitieChecksqlquery, htCreateRole, htGrant], 'Wrong query message for timescaledb table.');
      return Promise.resolve(sqlquery);
    }
  };

  const consumer = {
    run: function (run) {
      return new Promise(function (resolve, reject) {
        resolve();
      });
    },
    connect: function () {},
    subscribe: function (obj) {
      assert.oneOf(obj.topic, ['attributeTopic', 'entityTopic'])
      obj.fromBeginning.should.equal(false);
    },
    disconnect: function () {
    }
  };
  const fs = {
    writeFileSync: function (file, message) {
      assert.oneOf(file, ['/tmp/ready', '/tmp/healthy'], 'Wrong file for filesync');
      assert.oneOf(message, ['ready', 'healthy'], 'Wrong filesync message.');
    }
  };
  const config = {
    timescaledb: {
      attributeTopic: 'attributeTopic',
      entityTopic: 'entityTopic',
      tsdbuser: 'tsdbuser'
    }
  };
  const process = {
    on: async function (type, f) {
      expect(type).to.satisfy(function (type) {
        if (type === 'unhandledRejection' || type === 'uncaughtException') {
          return true;
        }
      });
      await f('Test Error');
    },
    exit: function (value) {
    },
    once: async function (type, f) {
      await f('Test Error');
    }
  };

  it('Should check database reject handling', async function () {
    const errorMsg = 'error on processing';
    const SequelizeClassNoQuery = class Sequelize {
      authenticate () {
        return Promise.reject(errorMsg);
      }

      sync () {
        return Promise.reject(errorMsg);
      }

      query (sqlquery) {
        return Promise.reject(errorMsg);
      }
    };

    const sequelizeObj = new SequelizeClassNoQuery();
    const revert = toTest.__set__('consumer', consumer);
    toTest.__set__('sequelize', sequelizeObj);
    toTest.__set__('fs', fs);
    toTest.__set__('config', config);
    toTest.__set__('process', process);
    const startListener = toTest.__get__('startListener');
    await startListener();
    revert();
  });

  it('Setup Kafka listener, readiness and health status', async function () {
    const sequelizeObj = new SequelizeClass();
    const consumerDisconnectSpy = sinon.spy(consumer, 'disconnect');
    const consumerConnectSpy = sinon.spy(consumer, 'connect');
    const processOnceSpy = sinon.spy(process, 'once');
    // const processExitSpy = sinon.spy(process, 'exit');
    const revert = toTest.__set__('consumer', consumer);
    toTest.__set__('sequelize', sequelizeObj);
    toTest.__set__('fs', fs);
    toTest.__set__('config', config);
    toTest.__set__('process', process);
    const startListener = toTest.__get__('startListener');
    await startListener();
    consumerDisconnectSpy.callCount.should.equal(3);
    assert(consumerConnectSpy.calledOnce);
    assert(processOnceSpy.calledThrice);
    revert();
  });
});
