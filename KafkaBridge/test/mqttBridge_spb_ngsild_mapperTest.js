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
const fileToTest = '../mqttBridge/spb_ngsild_mapper.js';

describe(fileToTest, function () {
  const ToTest = rewire(fileToTest);

  it('Shall create Relationship', function (done) {
    const deviceId = 'deviceId';
    const metric = {
      name: 'Relationship/name',
      value: 'value'
    };
    const expected = {
      id: 'deviceId' + '\\' + 'name',
      entityId: deviceId,
      datasetId: '@none',
      name: 'name',
      type: 'https://uri.etsi.org/ngsi-ld/Relationship',
      attributeValue: 'value',
      nodeType: '@id'
    };
    const result = ToTest.mapSpbRelationshipToKafka(deviceId, metric);
    assert.deepEqual(result, expected);
    done();
  });
  it('Shall create Relationship with datasetId', function (done) {
    const deviceId = 'deviceId';
    const metric = {
      name: 'Relationship/name',
      value: 'value',
      properties: {
        keys: ['datasetId'],
        values: ['datasetId']
      }
    };
    const expected = {
      id: 'deviceId' + '\\' + 'name',
      entityId: deviceId,
      name: 'name',
      type: 'https://uri.etsi.org/ngsi-ld/Relationship',
      attributeValue: 'value',
      nodeType: '@id',
      datasetId: 'datasetId'
    };
    const result = ToTest.mapSpbRelationshipToKafka(deviceId, metric);
    assert.deepEqual(result, expected);
    done();
  });
  it('Shall create default Property', function (done) {
    const deviceId = 'deviceId';
    const metric = {
      name: 'Property/name',
      value: 'value'
    };
    const expected = {
      id: 'deviceId' + '\\' + 'name',
      entityId: deviceId,
      datasetId: '@none',
      name: 'name',
      type: 'https://uri.etsi.org/ngsi-ld/Property',
      attributeValue: 'value',
      nodeType: '@value'
    };
    const result = ToTest.mapSpbPropertyToKafka(deviceId, metric);
    assert.deepEqual(result, expected);
    done();
  });
  it('Shall create literal Property', function (done) {
    const deviceId = 'deviceId';
    const metric = {
      name: 'PropertyLiteral/name',
      value: 'value'
    };
    const expected = {
      id: 'deviceId' + '\\' + 'name',
      entityId: deviceId,
      datasetId: '@none',
      name: 'name',
      type: 'https://uri.etsi.org/ngsi-ld/Property',
      attributeValue: 'value',
      nodeType: '@value'
    };
    const result = ToTest.mapSpbPropertyToKafka(deviceId, metric);
    assert.deepEqual(result, expected);
    done();
  });
  it('Shall create literal Property with datasetId', function (done) {
    const deviceId = 'deviceId';
    const metric = {
      name: 'PropertyLiteral/name',
      value: 'value',
      properties: {
        keys: ['datasetId'],
        values: ['datasetId']
      }
    };
    const expected = {
      id: 'deviceId' + '\\' + 'name',
      entityId: deviceId,
      name: 'name',
      type: 'https://uri.etsi.org/ngsi-ld/Property',
      attributeValue: 'value',
      nodeType: '@value',
      datasetId: 'datasetId'
    };
    const result = ToTest.mapSpbPropertyToKafka(deviceId, metric);
    assert.deepEqual(result, expected);
    done();
  });
  it('Shall create IRI Property with datasetId', function (done) {
    const deviceId = 'deviceId';
    const metric = {
      name: 'PropertyIri/name',
      value: 'value',
      properties: {
        keys: ['datasetId'],
        values: ['datasetId']
      }
    };
    const expected = {
      id: 'deviceId' + '\\' + 'name',
      entityId: deviceId,
      name: 'name',
      type: 'https://uri.etsi.org/ngsi-ld/Property',
      attributeValue: 'value',
      nodeType: '@id',
      datasetId: 'datasetId'
    };
    const result = ToTest.mapSpbPropertyIriToKafka(deviceId, metric);
    assert.deepEqual(result, expected);
    done();
  });
  it('Shall create IRI Property', function (done) {
    const deviceId = 'deviceId';
    const metric = {
      name: 'PropertyIri/name',
      value: 'value'
    };
    const expected = {
      id: 'deviceId' + '\\' + 'name',
      entityId: deviceId,
      datasetId: '@none',
      name: 'name',
      type: 'https://uri.etsi.org/ngsi-ld/Property',
      attributeValue: 'value',
      nodeType: '@id'
    };
    const result = ToTest.mapSpbPropertyIriToKafka(deviceId, metric);
    assert.deepEqual(result, expected);
    done();
  });
  it('Shall create JSON Property', function (done) {
    const deviceId = 'deviceId';
    const metric = {
      name: 'PropertyIri/name',
      value: 'value'
    };
    const expected = {
      id: 'deviceId' + '\\' + 'name',
      entityId: deviceId,
      datasetId: '@none',
      name: 'name',
      type: 'https://uri.etsi.org/ngsi-ld/Property',
      attributeValue: 'value',
      nodeType: '@json'
    };
    const result = ToTest.mapSpbPropertyJsonToKafka(deviceId, metric);
    assert.deepEqual(result, expected);
    done();
  });
  it('Shall create JSON Property with datasetId', function (done) {
    const deviceId = 'deviceId';
    const metric = {
      name: 'PropertyIri/name',
      value: 'value',
      properties: {
        keys: ['datasetId'],
        values: ['datasetId']
      }
    };
    const expected = {
      id: 'deviceId' + '\\' + 'name',
      entityId: deviceId,
      name: 'name',
      type: 'https://uri.etsi.org/ngsi-ld/Property',
      attributeValue: 'value',
      nodeType: '@json',
      datasetId: 'datasetId'
    };
    const result = ToTest.mapSpbPropertyJsonToKafka(deviceId, metric);
    assert.deepEqual(result, expected);
    done();
  });
  it('AddProperties shall add datasetId', function (done) {
    const message = {};
    const metric = {
      properties: {
        keys: ['datasetId'],
        values: ['datasetId']
      }
    };
    const expected = {
      datasetId: 'datasetId'
    };
    const addProperties = ToTest.__get__('addProperties');
    addProperties(message, metric);
    assert.deepEqual(message, expected);
    done();
  });
  it('AddProperties shall ignore unknown properties', function (done) {
    const message = {};
    const metric = {
      properties: {
        keys: ['datasetIdx'],
        values: ['datasetIdx']
      }
    };
    const expected = {
      datasetId: '@none'
    };
    const addProperties = ToTest.__get__('addProperties');
    addProperties(message, metric);
    assert.deepEqual(message, expected);
    done();
  });
  it('AddProperties shall ignore emtpy properties field', function (done) {
    const message = {};
    let metric = {
      properties: {
      }
    };
    const expected = {
      datasetId: '@none'
    };
    const addProperties = ToTest.__get__('addProperties');
    addProperties(message, metric);
    assert.deepEqual(message, expected);
    metric = {
    };
    addProperties(message, metric);
    assert.deepEqual(message, expected);
    done();
  });
});
