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
const expect = chai.expect;

const logger = {
  debug: function () {},
  info: function () {},
  error: function () {}
};

const Logger = function () {
  return logger;
};

describe('Test timescaledb processMessage', function () {
  it('Should send an attribute', async function () {
    const upsertSpy = sinon.spy(async function (datapoint) {
      assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.entityId, 'entityId');
      assert.equal(datapoint.attributeId, 'name');
      assert.equal(datapoint.nodeType, '@value');
      assert.equal(datapoint.datasetId, '@none');
      assert.equal(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Property');
      assert.equal(datapoint.value, 123);
      assert.equal(datapoint.deleted, false);
      return Promise.resolve(datapoint);
    });

    const attributeHistoryTable = { upsert: upsertSpy };

    const kafkamessage = {
      topic: 'iff.ngsild.attributes',
      partition: 'partition',
      message: {
        value: JSON.stringify({
          id: 'id',
          entityId: 'entityId',
          name: 'name',
          type: 'https://uri.etsi.org/ngsi-ld/Property',
          attributeValue: 123,
          nodeType: '@value',
          datasetId: '@none'
        }),
        timestamp: '1689344953110'
      }
    };
    toTest.__set__('attributeHistoryTable', attributeHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processMessage');
    await processMessage(kafkamessage);
    sinon.assert.calledOnce(upsertSpy);
  });
  it('Should send an entity', async function () {
    const upsertSpy = sinon.spy(async function (datapoint) {
      assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.id, 'id');
      assert.equal(datapoint.type, 'https://example.com/type');
      assert.equal(datapoint.deleted, false);
      return Promise.resolve(datapoint);
    });
    const entityHistoryTable = { upsert: upsertSpy };
    const kafkamessage = {
      topic: 'iff.ngsild.entities',
      partition: 'partition',
      message: {
        value: JSON.stringify({
          id: 'id',
          type: 'https://example.com/type'
        }),
        timestamp: '1689344953110'
      }
    };
    toTest.__set__('entityHistoryTable', entityHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processMessage');
    await processMessage(kafkamessage);
    sinon.assert.calledOnce(upsertSpy);
  });
});
describe('Test timescaledb processAttributeMessage', function () {
  it('Should send a Property with @value nodetype', function () {
    const upsertSpy = sinon.spy(function (datapoint) {
      assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.entityId, 'entityId');
      assert.equal(datapoint.attributeId, 'name');
      assert.equal(datapoint.nodeType, '@value');
      assert.equal(datapoint.datasetId, '@none');
      assert.equal(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Property');
      assert.equal(datapoint.value, 123);
      assert.equal(datapoint.deleted, false);
      assert.equal(datapoint.unitCode, 'MTR');
      return Promise.resolve(datapoint);
    });
    const attributeHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        entityId: 'entityId',
        name: 'name',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        attributeValue: 123,
        nodeType: '@value',
        unitCode: 'MTR',
        index: 0
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('attributeHistoryTable', attributeHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processAttributeMessage');
    processMessage(message);
    sinon.assert.calledOnce(upsertSpy);
    upsertSpy.threw().should.equal(false);
  });
  it('Should delete a Property', function () {
    const upsertSpy = sinon.spy(function (datapoint) {
      assert.equal(datapoint.deleted, true);
      return Promise.resolve(datapoint);
    });
    const attributeHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        entityId: 'entityId',
        name: 'name',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        attributeValue: 123,
        nodeType: '@value',
        deleted: true
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('attributeHistoryTable', attributeHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processAttributeMessage');
    processMessage(message);
    sinon.assert.calledOnce(upsertSpy);
    upsertSpy.threw().should.equal(false);
  });
  it('Should explicitly undelete a Property', async function () {
    const upsertSpy = sinon.spy(async function (datapoint) {
      assert.equal(datapoint.deleted, false);
      return Promise.resolve(datapoint);
    });
    const attributeHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        entityId: 'entityId',
        name: 'name',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        attributeValue: 123,
        nodeType: '@value',
        deleted: false
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('attributeHistoryTable', attributeHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processAttributeMessage');
    await processMessage(message);
    sinon.assert.calledOnce(upsertSpy);
    upsertSpy.threw().should.equal(false);
  });
  it('Should send a Relationship', async function () {
    const upsertSpy = sinon.spy(async function (datapoint) {
      assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.entityId, 'entityId');
      assert.equal(datapoint.attributeId, 'relationship');
      assert.equal(datapoint.nodeType, '@id');
      assert.equal(datapoint.datasetId, '@none');
      assert.equal(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Relationship');
      assert.equal(datapoint.value, 'object');
      assert.equal(datapoint.deleted, false);
      return Promise.resolve(datapoint);
    });
    const attributeHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        entityId: 'entityId',
        name: 'relationship',
        type: 'https://uri.etsi.org/ngsi-ld/Relationship',
        attributeValue: 'object',
        nodeType: '@id'
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('attributeHistoryTable', attributeHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processAttributeMessage');
    await processMessage(message);

    sinon.assert.calledOnce(upsertSpy);
    upsertSpy.threw().should.equal(false);
  });
  it('Should send a GeoProperty', function () {
    const upsertSpy = sinon.spy(function (datapoint) {
      assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.entityId, 'entityId');
      assert.equal(datapoint.attributeId, 'geoproperty');
      assert.equal(datapoint.nodeType, '@json');
      assert.equal(datapoint.datasetId, '@none');
      assert.equal(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/GeoProperty');
      assert.equal(datapoint.value, '{"@type":["https://purl.org/geojson/vocab#Point"],"https://purl.org/geojson/vocab#coordinates":[{"@list":[{"@value":13.3698},{"@value":52.5163}]}]}');
      assert.equal(datapoint.deleted, false);
      assert.equal(datapoint.valueType, 'https://purl.org/geojson/vocab#Point');
      return Promise.resolve(datapoint);
    });
    const attributeHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        entityId: 'entityId',
        name: 'geoproperty',
        type: 'https://uri.etsi.org/ngsi-ld/GeoProperty',
        attributeValue: '{"@type":["https://purl.org/geojson/vocab#Point"],"https://purl.org/geojson/vocab#coordinates":[{"@list":[{"@value":13.3698},{"@value":52.5163}]}]}',
        nodeType: '@json',
        valueType: 'https://purl.org/geojson/vocab#Point'
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('attributeHistoryTable', attributeHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processAttributeMessage');
    processMessage(message);
    sinon.assert.calledOnce(upsertSpy);
    sinon.assert.calledOnce(upsertSpy);
    upsertSpy.threw().should.equal(false);
  });

  it('Should send a Property with @value nodetype and valueType string', function () {
    const upsertSpy = sinon.spy(function (datapoint) {
      assert.equal(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.entityId, 'entityId');
      assert.equal(datapoint.attributeId, 'property');
      assert.equal(datapoint.nodeType, '@value');
      assert.equal(datapoint.datasetId, '@none');
      assert.equal(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Property');
      assert.equal(datapoint.value, 'value');
      assert.equal(datapoint.valueType, 'http://www.w3.org/2001/XMLSchema#string');
      assert.equal(datapoint.deleted, false);
      return Promise.resolve(datapoint);
    });
    const attributeHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        entityId: 'entityId',
        name: 'property',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        attributeValue: 'value',
        nodeType: '@value',
        valueType: 'http://www.w3.org/2001/XMLSchema#string',
        index: 0
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('attributeHistoryTable', attributeHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processAttributeMessage');
    processMessage(message);
    sinon.assert.calledOnce(upsertSpy);
    upsertSpy.threw().should.equal(false);
  });

  it('Should reject wrong object type- property/relationship with @value nodetype and valueType string', function () {
    const upsertSpy = sinon.spy(function (datapoint) {
      return Promise.resolve(datapoint);
    });
    const attributeHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        entityId: 'entityId',
        name: 'property',
        type: 'https://uri.etsi.org/ngsi-ld',
        attributeValue: 'value',
        nodeType: '@value',
        valueType: 'http://www.w3.org/2001/XMLSchema#string',
        index: 0
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('attributeHistoryTable', attributeHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processAttributeMessage');
    processMessage(message);
    sinon.assert.notCalled(upsertSpy);
  });

  it('Should send a Property with wrong timestamp and attributeType', function () {
    const upsertSpy = sinon.spy(function (datapoint) {
      assert.notEqual(datapoint.observedAt, '2023-07-14T14:29:13.110Z');
      assert.notEqual(datapoint.modifiedAt, '2023-07-14T14:29:13.110Z');
      assert.equal(datapoint.entityId, 'entityId');
      assert.equal(datapoint.attributeId, 'property');
      assert.equal(datapoint.nodeType, '@value');
      assert.equal(datapoint.datasetId, '@none');
      assert.notEqual(datapoint.attributeType, 'https://uri.etsi.org/ngsi-ld/Relationship');
      assert.equal(datapoint.value, 'value');
      return Promise.resolve(datapoint);
    });
    const attributeHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        entityId: 'entityId',
        name: 'property',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        attributeValue: 'value',
        nodeType: '@value',
        index: 0
      }),
      timestamp: '168934495320'
    };
    toTest.__set__('attributeHistoryTable', attributeHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processAttributeMessage');
    processMessage(message);
    sinon.assert.calledOnce(upsertSpy);
    upsertSpy.threw().should.equal(false);
  });
});
describe('Test timescaledb processEntityMessage', function () {
  it('Should send an entity', async function () {
    const upsertSpy = sinon.spy(async function (datapoint) {
      assert.equal(datapoint.id, 'id');
      assert.equal(datapoint.type, 'https://example.com/type');
      assert.equal(datapoint.deleted, false);
      return Promise.resolve(datapoint);
    });
    const entityHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        type: 'https://example.com/type'
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('entityHistoryTable', entityHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processEntityMessage');
    await processMessage(message);
    sinon.assert.calledOnce(upsertSpy);
  });
  it('Should delete an entity', async function () {
    const upsertSpy = sinon.spy(async function (datapoint) {
      assert.equal(datapoint.id, 'id');
      assert.equal(datapoint.type, 'https://example.com/type');
      assert.equal(datapoint.deleted, true);
      return Promise.resolve(datapoint);
    });
    const entityHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        type: 'https://example.com/type',
        deleted: true
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('entityHistoryTable', entityHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processEntityMessage');
    await processMessage(message);
    sinon.assert.calledOnce(upsertSpy);
  });
  it('Should explicitly undelete an entity', async function () {
    const upsertSpy = sinon.spy(async function (datapoint) {
      assert.equal(datapoint.id, 'id');
      assert.equal(datapoint.type, 'https://example.com/type');
      assert.equal(datapoint.deleted, false);
      return Promise.resolve(datapoint);
    });
    const entityHistoryTable = { upsert: upsertSpy };
    const message = {
      value: JSON.stringify({
        id: 'id',
        type: 'https://example.com/type',
        deleted: false
      }),
      timestamp: '1689344953110'
    };
    toTest.__set__('entityHistoryTable', entityHistoryTable);
    toTest.__set__('Logger', Logger);
    const processMessage = toTest.__get__('processEntityMessage');
    await processMessage(message);
    sinon.assert.calledOnce(upsertSpy);
  });
});
describe('Test startListener', function () {
  const entityTableName = 'entities';
  const attributeTableName = 'attributes';
  const htAttributeChecksqlquery = 'SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = \'' + attributeTableName + '\';';
  const htEntityChecksqlquery = 'SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = \'' + entityTableName + '\';';
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
      assert.oneOf(sqlquery, [htAttributeChecksqlquery, htEntityChecksqlquery, htAttributeCreateSqlquery, htEntityCreateSqlquery, htCreateRole, htGrant], 'Wrong query message for timescaledb table.');
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
      assert.oneOf(obj.topic, ['attributeTopic', 'entityTopic']);
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
    const revert = toTest.__set__('consumer', consumer);
    toTest.__set__('sequelize', sequelizeObj);
    toTest.__set__('fs', fs);
    toTest.__set__('config', config);
    toTest.__set__('process', process);
    const startListener = toTest.__get__('startListener');
    await startListener();
    consumerDisconnectSpy.callCount.should.equal(5);
    assert(consumerConnectSpy.calledOnce);
    assert(processOnceSpy.calledThrice);
    revert();
  });
});
