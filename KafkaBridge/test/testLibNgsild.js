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
'use strict';

const { assert } = require('chai');
const chai = require('chai');
global.should = chai.should();

const rewire = require('rewire');
const ToTest = rewire('../lib/ngsild.js');

const logger = {
  debug: function () {},
  error: function () {}
};

const config = {
  ngsildServer: {
    hostname: 'hostname',
    protocol: 'http:',
    port: 1234
  }
};

describe('Test getNgsildEntity', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      path: '/ngsi-ld/v1/entities/id',
      method: 'GET',
      headers: {
        Accept: 'application/ld+json'
      }
    };
    const rest = {
      getBody: function (options) {
        assert.deepEqual(options, expectedOptions);
        return 'body';
      }
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.getNgsildEntity('id');
    result.should.equal('body');
    revert();
  });
});
describe('Test getNgsildEntities', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'GET',
      path: '/ngsi-ld/v1/entities?id=urn1,urn2&idPattern=pattern&attrs=attr1,attr2&type=type&q=query1|query2',
      headers: {
        Accept: 'application/ld+json'
      }
    };
    const rest = {
      getBody: function (options) {
        assert.deepEqual(options, expectedOptions);
        return 'body';
      }
    };
    const params = {
      ids: ['urn1', 'urn2'],
      idPattern: 'pattern',
      attrs: ['attr1', 'attr2'],
      type: ['type'],
      queries: ['query1', 'query2']
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.getNgsildEntities(params);
    result.should.equal('body');
    revert();
  });
});

describe('Test getNgsildCSourceRegistrations', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'GET',
      path: '/ngsi-ld/v1/csourceRegistrations?id=urn1,urn2&idPattern=pattern&attrs=attr1,attr2&type=type',
      headers: {
        Accept: 'application/ld+json',
        'Content-type': 'application/ld+json'
      }
    };
    const rest = {
      getBody: function (options) {
        assert.deepEqual(options, expectedOptions);
        return 'body';
      }
    };
    const params = {
      ids: ['urn1', 'urn2'],
      idPattern: 'pattern',
      attrs: ['attr1', 'attr2'],
      types: ['type']
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.getNgsildCSourceRegistrations(params);
    result.should.equal('body');
    revert();
  });
});
describe('Test deleteNgsildCSourceRegistration', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'DELETE',
      path: '/ngsi-ld/v1/csourceRegistrations/id'
    };
    const rest = {
      getBody: function (options) {
        assert.deepEqual(options, expectedOptions);
        return 'body';
      }
    };

    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.deleteNgsildCSourceRegistration('id');
    result.should.equal('body');
    revert();
  });
});
describe('Test createNgsildCSourceRegistration', function () {
  it('Should use correct options and used Content-Type ld+json', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/csourceRegistrations',
      headers: {
        'Content-Type': 'application/ld+json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        return 'posted';
      }
    };

    const entity = {
      entity: 'entity'
    };

    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.createNgsildCSourceRegistration(entity, true);
    result.should.equal('posted');
    revert();
  });
  it('Should use correct options and used Content-Type json', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/csourceRegistrations',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        return 'posted';
      }
    };

    const entity = {
      entity: 'entity'
    };

    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.createNgsildCSourceRegistration(entity, false);
    result.should.equal('posted');
    revert();
  });
});
describe('Test getAllObjectsOfType', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'GET',
      path: '/ngsi-ld/v1/entities?type=type',
      headers: {
        Accept: 'application/ld+json'
      }
    };
    const rest = {
      getBody: function (options) {
        assert.deepEqual(options, expectedOptions);
        return 'body';
      }
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.getAllObjectsOfType('type');
    result.should.equal('body');
    revert();
  });
});
describe('Test deleteEntities', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entityOperations/delete',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, ids);
        return 'deleted';
      }
    };
    const ids = ['id1', 'id2'];
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.deleteEntities(ids);
    result.should.equal('deleted');
    revert();
  });
});
describe('Test createEntities', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entityOperations/create',
      headers: {
        'Content-Type': 'application/ld+json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entities);
        return 'created';
      }
    };

    const entities = [
      {
        entity: 'entity'
      },
      {
        entity: 'entity2'
      }
    ];

    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.createEntities(entities);
    result.should.equal('created');
    revert();
  });
});
describe('Test replaceEntities', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entityOperations/upsert?options=replace',
      headers: {
        'Content-Type': 'application/ld+json',
        header: 'header'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entities);
        return 'replaced';
      }
    };

    const entities = [
      {
        entity: 'entity'
      },
      {
        entity: 'entity2'
      }
    ];
    const headers = {
      header: 'header'
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.replaceEntities(entities, true, { headers });
    result.should.equal('replaced');
    revert();
  });
  it('Should use correct options and add ?option=update to path', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entityOperations/upsert?options=update',
      headers: {
        'Content-Type': 'application/ld+json',
        header: 'header'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entities);
        return 'replaced';
      }
    };

    const entities = [
      {
        entity: 'entity'
      },
      {
        entity: 'entity2'
      }
    ];
    const headers = {
      header: 'header'
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.replaceEntities(entities, false, { headers });
    result.should.equal('replaced');
    revert();
  });
});
describe('Test updateProperties', function () {
  it('Should use correct options ', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entities/id/attrs?options=noOverwrite',
      headers: {
        'Content-Type': 'application/json',
        header: 'header'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        assert.equal(obj.disableChunks, false);
        assert.equal(obj.noStringify, true);
        return 'updated';
      }
    };

    const entity = {
      entity: 'entity'
    };
    const headers = {
      header: 'header'
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.updateProperties('id', entity, true, { headers });
    result.then((ret) => ret.should.equal('updated'));
    revert();
  });
  it('Should use correct options and not use noOverwrite', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entities/id/attrs',
      headers: {
        'Content-Type': 'application/json',
        header: 'header'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        assert.equal(obj.disableChunks, false);
        assert.equal(obj.noStringify, true);
        return 'updated';
      }
    };

    const entity = {
      entity: 'entity'
    };
    const headers = {
      header: 'header'
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.updateProperties('id', entity, false, { headers });
    result.then(ret => ret.should.equal('updated'));
    revert();
  });
});
describe('Test subscribe', function () {
  it('Should use correct options ', async function () {
    const config = {
      ngsildServer: {
        hostname: 'hostname',
        protocol: 'http:',
        port: 1234
      },
      bridgeConfig: {
        host: 'host',
        port: 123
      }
    };
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/subscriptions/',
      headers: {
        'Content-Type': 'application/ld+json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        return 'subscribed';
      }
    };

    const entity = {
      '@context': [
        'https://fiware.github.io/data-models/context.jsonld',
        'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.3.jsonld',
        'host:123/jsonld/undefined'
      ],
      description: 'Notify me if type are changed',
      entities: [
        {
          type: 'http://example/type'
        }
      ],
      id: 'id',
      notification: {
        endpoint: {
          accept: 'application/json',
          uri: 'host:123/subscription'
        }
      },
      timeInterval: 200,
      type: 'Subscription'
    };

    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.subscribe('id', 'http://example/type', 200);
    result.should.equal('subscribed');
    revert();
  });
});
describe('Test updateNgsildCSourceRegistration', function () {
  it('Should use correct options and used Content-Type ld+json', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'PATCH',
      path: '/ngsi-ld/v1/csourceRegistrations/id',
      headers: {
        'Content-Type': 'application/ld+json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        return 'posted';
      }
    };

    const entity = {
      id: 'id'
    };

    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.updateNgsildCSourceRegistration(entity, true);
    result.should.equal('posted');
    revert();
  });
  it('Should use correct options and used Content-Type json', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'PATCH',
      path: '/ngsi-ld/v1/csourceRegistrations/id',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        return 'posted';
      }
    };

    const entity = {
      id: 'id'
    };

    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.updateNgsildCSourceRegistration(entity, false);
    result.should.equal('posted');
    revert();
  });
});
describe('Test createEntity', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entities',
      headers: {
        'Content-Type': 'application/ld+json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        return 'created';
      }
    };
    const entity = {
      id: 'id'
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.createEntity(entity);
    result.should.equal('created');
    revert();
  });
});
describe('Test updateProperty', function () {
  it('Should use correct options and Property', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entities/id/attrs',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        assert.equal(obj.disableChunks, false);
        assert.equal(obj.noStringify, true);
        return 'updated';
      }
    };

    const entity = {
      key: {
        type: 'Property',
        value: 'value'
      }
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.updateProperty('id', 'key', 'value', false, false);
    result.then(ret => ret.should.equal('updated'));
    revert();
  });
  it('Should use correct options and Relationship ', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entities/id/attrs',
      headers: {
        'Content-Type': 'application/json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        assert.equal(obj.disableChunks, false);
        assert.equal(obj.noStringify, true);
        return 'updated';
      }
    };

    const entity = {
      key: {
        type: 'Relationship',
        object: 'value'
      }
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.updateProperty('id', 'key', 'value', true, false);
    result.then(ret => ret.should.equal('updated'));
    revert();
  });
});
describe('Test updateSubscription', function () {
  it('Should use correct options', async function () {
    const config = {
      ngsildServer: {
        hostname: 'hostname',
        protocol: 'http:',
        port: 1234
      },
      bridgeConfig: {
        host: 'host',
        port: 123
      }
    };
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'PATCH',
      path: '/ngsi-ld/v1/subscriptions/id',
      headers: {
        'Content-Type': 'application/ld+json'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entity);
        return 'updated';
      }
    };

    const entity = {
      '@context': [
        'https://fiware.github.io/data-models/context.jsonld',
        'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.3.jsonld',
        'host:123/jsonld/undefined'
      ],
      description: 'Notify me if type are changed',
      entities: [
        {
          type: 'http://example/type'
        }
      ],
      notification: {
        endpoint: {
          accept: 'application/json',
          uri: 'host:123/subscription'
        }
      },
      timeInterval: 200,
      type: 'Subscription'
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.updateSubscription('id', 'http://example/type', 200);
    result.should.equal('updated');
    revert();
  });
});
describe('Test updateEntities', function () {
  it('Should use correct options', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entityOperations/update',
      headers: {
        'Content-Type': 'application/ld+json',
        header: 'header'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entities);
        return 'replaced';
      }
    };

    const entities = [
      {
        entity: 'entity'
      },
      {
        entity: 'entity2'
      }
    ];
    const headers = {
      header: 'header'
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.updateEntities(entities, true, { headers });
    result.should.equal('replaced');
    revert();
  });
  it('Should use correct options and add ?options=noOverwrite to path', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };

    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entityOperations/update?options=noOverwrite',
      headers: {
        'Content-Type': 'application/ld+json',
        header: 'header'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entities);
        return 'replaced';
      }
    };

    const entities = [
      {
        entity: 'entity'
      },
      {
        entity: 'entity2'
      }
    ];
    const headers = {
      header: 'header'
    };
    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = ngsild.updateEntities(entities, false, { headers });
    result.should.equal('replaced');
    revert();
  });
});
describe('Test batchMerge', function () {
  it('Should use correct options and headers', async function () {
    const Logger = function () {
      return logger;
    };
    const Rest = function () {
      return rest;
    };
    const headers = { Authorization: 'Bearer token' };
    const expectedOptions = {
      hostname: 'hostname',
      protocol: 'http:',
      port: 1234,
      method: 'POST',
      path: '/ngsi-ld/v1/entityOperations/merge',
      headers: {
        'Content-Type': 'application/ld+json',
        Authorization: 'Bearer token'
      }
    };
    const rest = {
      postBody: function (obj) {
        assert.deepEqual(obj.options, expectedOptions);
        assert.deepEqual(obj.body, entities);
        return Promise.resolve('merged');
      }
    };

    const entities = [
      { id: 'id1', type: 'type1', attr1: 'value1' },
      { id: 'id2', type: 'type2', attr2: 'value2' }
    ];

    const revert = ToTest.__set__('Logger', Logger);
    ToTest.__set__('Rest', Rest);
    const ngsild = new ToTest(config);
    const result = await ngsild.batchMerge(entities, { headers });
    result.should.equal('merged');
    revert();
  });
});
