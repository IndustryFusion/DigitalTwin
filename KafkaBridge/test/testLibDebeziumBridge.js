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
const ToTest = rewire('../lib/debeziumBridge.js');

const logger = {
  debug: function () {},
  error: function () {}
};

describe('Test diffAttributes', function () {
  it('Should return no updates and no deletions', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const beforeAttrs = {
      attr1: [{
        value: 'value',
        index: 0
      }]
    };
    const afterAttrs = {
      attr1: [{
        value: 'value',
        index: 0
      }]
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.diffAttributes(beforeAttrs, afterAttrs);
    assert.deepEqual(result.updatedAttrs, {});
    assert.deepEqual(result.deletedAttrs, {});
    revert();
  });
  it('Should update value but no deletions', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const beforeAttrs = {
      attr1: [{
        value: 'value',
        index: 0
      }]
    };
    const afterAttrs = {
      attr1: [{
        value: 'value2',
        index: 0
      }]
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.diffAttributes(beforeAttrs, afterAttrs);
    assert.deepEqual(result.updatedAttrs, afterAttrs);
    assert.deepEqual(result.deletedAttrs, {});
    revert();
  });
  it('Should delete value but no update', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const beforeAttrs = {
      attr1: [{
        id: 'id',
        value: 'value',
        index: 0
      }],
      attr2: [{
        id: 'id2',
        value: 'value3',
        index: 0
      }]
    };
    const afterAttrs = {
      attr1: [{
        id: 'id',
        value: 'value',
        index: 0
      }]
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.diffAttributes(beforeAttrs, afterAttrs);
    assert.deepEqual(result.updatedAttrs, {});
    assert.deepEqual(result.deletedAttrs, { attr2: [{ id: 'id2', index: 0 }] });
    revert();
  });
  it('Should delete higher index value and update changed value', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const beforeAttrs = {
      attr1: [
        {
          id: 'id',
          value: 'value',
          index: 0
        },
        {
          id: 'id',
          value: 'value2',
          index: 1
        }
      ],
      attr2: [{
        id: 'id2',
        value: 'value3',
        index: 0
      }]
    };
    const afterAttrs = {
      attr1: [
        {
          id: 'id3',
          value: 'value4',
          index: 0
        }
      ]
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.diffAttributes(beforeAttrs, afterAttrs);
    assert.deepEqual(result.updatedAttrs, { attr1: [{ id: 'id3', value: 'value4', index: 0 }] });
    assert.deepEqual(result.deletedAttrs, { attr2: [{ id: 'id2', index: 0 }], attr1: [{ id: 'id', index: 1 }] });
    revert();
  });
});
describe('Test diffEntity', function () {
  it('Should return false', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const diff1 = {
      id: 'id',
      typ: 'type',
      attribute: {
        value: 'value',
        type: 'Property'
      }
    };

    const diff2 = {
      id: 'id',
      typ: 'type',
      attribute: {
        value: 'value',
        type: 'Property'
      }
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.diffEntity(diff1, diff2);
    assert.equal(result, false);
    revert();
  });
  it('Should return true', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const diff1 = {
      id: 'id',
      typ: 'type',
      attribute: {
        value: 'value',
        type: 'Property'
      }
    };

    const diff2 = {
      id: 'id',
      typ: 'type',
      attribute: {
        value: 'value2',
        type: 'Property'
      }
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.diffEntity(diff1, diff2);
    assert.equal(result, true);
    revert();
  });
});
describe('Test parseBeforeAfterEntity', function () {
  it('Should return one entity, one Property & one Relationship', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const ba = {
      id: 'id',
      type: 'type',
      data: '{\
                "@id":"id", "@type": ["type"],\
                "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                    "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                    "@value": "2022-02-19T20:31:26.123656Z"\
                }],\
                "https://example/hasRel": [{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Relationship"],\
                    "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/hasObject": [{"@id": "urn:object:1"}]\
                }],\
                "https://example/prop":[{\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [{"@value": "value"}],\
                    "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/modifiedAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T23:11:28.457509Z"\
                    }]\
                }]\
            }'
    };

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.parseBeforeAfterEntity(ba);
    assert.deepEqual(result.entity, { id: 'id', type: 'type', 'https://example/hasRel': 'id\\https://example/hasRel', 'https://example/prop': 'id\\https://example/prop' });
    assert.deepEqual(result.attributes, {
      'https://example/hasRel': [{
        id: 'id\\https://example/hasRel',
        entityId: 'id',
        nodeType: '@id',
        name: 'https://example/hasRel',
        type: 'https://uri.etsi.org/ngsi-ld/Relationship',
        'https://uri.etsi.org/ngsi-ld/hasObject': 'urn:object:1',
        index: 0
      }],
      'https://example/prop': [{
        id: 'id\\https://example/prop',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        'https://uri.etsi.org/ngsi-ld/hasValue': 'value',
        index: 0
      }]
    });
    revert();
  });
  it('Should return one entity, one Property with valuetype', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const ba = {
      id: 'id',
      type: 'type',
      data: '{\
                "@id":"id", "@type": ["type"],\
                "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                    "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                    "@value": "2022-02-19T20:31:26.123656Z"\
                }],\
                "https://example/prop":[{\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "value",\
                        "@type": "https://example/type"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/modifiedAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T23:11:28.457509Z"\
                    }]\
                }]\
            }'
    };

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.parseBeforeAfterEntity(ba);
    assert.deepEqual(result.entity, { id: 'id', type: 'type', 'https://example/prop': 'id\\https://example/prop' });
    assert.deepEqual(result.attributes, {
      'https://example/prop': [{
        id: 'id\\https://example/prop',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        'https://uri.etsi.org/ngsi-ld/hasValue': 'value',
        valueType: 'https://example/type',
        index: 0
      }]
    });
    revert();
  });
  it('Should return `undefined` due to json parse error', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const ba = {
      id: 'id',
      type: 'type',
      data: '{"@id":"id", "@type": ["type"],'
    };

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.parseBeforeAfterEntity(ba);
    assert.equal(result, undefined);
    revert();
  });
});
describe('Test parse', function () {
  it('Should return null result', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const expectedResult = {
      entity: null,
      updatedAttrs: null,
      deletedAttrs: null
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    let result = debeziumBridge.parse(null);
    assert.deepEqual(result, expectedResult);
    result = debeziumBridge.parse(undefined);
    assert.deepEqual(result, expectedResult);
    revert();
  });
  it('Should return no deleted and no updated Entity and no attributes result', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const expectedResult = {
      entity: null,
      deletedEntity: undefined,
      updatedAttrs: null,
      deletedAttrs: null
    };
    const body = {
      before: {
        entity: {},
        attributes: {}
      },
      after: {
        entity: {},
        attributes: {}
      }
    };
    const parseBeforeAfterEntity = function (body) {
      return body;
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    debeziumBridge.parseBeforeAfterEntity = parseBeforeAfterEntity;
    const result = debeziumBridge.parse(body);
    assert.deepEqual(result, expectedResult);
    revert();
  });
  it('Should return deleted and no updated Entity and no attributes result', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const expectedResult = {
      entity: {},
      deletedEntity: {
        id: 'id',
        type: 'type'
      },
      updatedAttrs: {},
      deletedAttrs: {
        attribute: 'attribute'
      }
    };
    const body = {
      before: {
        entity: {
          id: 'id',
          type: 'type'
        },
        attributes: [{
          attribute: 'attribute'
        }]
      },
      after: {
        entity: {},
        attributes: {}
      }
    };
    const updatedAttrs = {};
    const deletedAttrs = {
      attribute: 'attribute'
    };
    const parseBeforeAfterEntity = function (body) {
      return body;
    };
    const diffAttributes = function (beforeAttrs, afterAttrs) {
      assert.deepEqual(body.before.attributes, beforeAttrs);
      assert.deepEqual(body.after.attributes, afterAttrs);
      return {
        updatedAttrs: updatedAttrs,
        deletedAttrs: deletedAttrs
      };
    };
    const diffEntity = function (beforeEntity, afterEntity) {
      assert.deepEqual(body.before.entity, beforeEntity);
      assert.deepEqual(body.after.entity, afterEntity);
      return true;
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    debeziumBridge.parseBeforeAfterEntity = parseBeforeAfterEntity;
    debeziumBridge.diffAttributes = diffAttributes;
    debeziumBridge.diffEntity = diffEntity;
    const result = debeziumBridge.parse(body);
    assert.deepEqual(result, expectedResult);
    revert();
  });
  it('Should return updated Entity and updated attributes result, but no deleted entity/attributes', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const expectedResult = {
      entity: {
        id: 'id',
        type: 'type'
      },
      deletedEntity: undefined,
      updatedAttrs: {
        attribute: 'attribute2'
      },
      deletedAttrs: {
      }
    };
    const body = {
      before: {
        entity: {
          id: 'id',
          type: 'type'
        },
        attributes: [{
          attribute: 'attribute'
        }]
      },
      after: {
        entity: {
          id: 'id',
          type: 'type'
        },
        attributes: {
          attribute: 'attribute2'
        }
      }
    };
    const updatedAttrs = {
      attribute: 'attribute2'
    };
    const deletedAttrs = {
    };
    const parseBeforeAfterEntity = function (body) {
      return body;
    };
    const diffAttributes = function (beforeAttrs, afterAttrs) {
      assert.deepEqual(body.before.attributes, beforeAttrs);
      assert.deepEqual(body.after.attributes, afterAttrs);
      return {
        updatedAttrs: updatedAttrs,
        deletedAttrs: deletedAttrs
      };
    };
    const diffEntity = function (beforeEntity, afterEntity) {
      assert.deepEqual(body.before.entity, beforeEntity);
      assert.deepEqual(body.after.entity, afterEntity);
      return true;
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    debeziumBridge.parseBeforeAfterEntity = parseBeforeAfterEntity;
    debeziumBridge.diffAttributes = diffAttributes;
    debeziumBridge.diffEntity = diffEntity;
    const result = debeziumBridge.parse(body);
    assert.deepEqual(result, expectedResult);
    revert();
  });
  it('Should return updated Entity and updated attributes result and deleted attributes', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const expectedResult = {
      entity: {
        id: 'id',
        type: 'type'
      },
      deletedEntity: undefined,
      updatedAttrs: {
        attribute: 'attribute2'
      },
      deletedAttrs: {
        attribute2: 'attribute2'
      }
    };
    const body = {
      before: {
        entity: {
          id: 'id',
          type: 'type'
        },
        attributes: [{
          attribute: 'attribute',
          attribute2: 'attribute2'
        }]
      },
      after: {
        entity: {
          id: 'id',
          type: 'type'
        },
        attributes: {
          attribute: 'attribute2'
        }
      }
    };
    const updatedAttrs = {
      attribute: 'attribute2'
    };
    const deletedAttrs = {
      attribute2: 'attribute2'
    };
    const parseBeforeAfterEntity = function (body) {
      return body;
    };
    const diffAttributes = function (beforeAttrs, afterAttrs) {
      assert.deepEqual(body.before.attributes, beforeAttrs);
      assert.deepEqual(body.after.attributes, afterAttrs);
      return {
        updatedAttrs: updatedAttrs,
        deletedAttrs: deletedAttrs
      };
    };
    const diffEntity = function (beforeEntity, afterEntity) {
      assert.deepEqual(body.before.entity, beforeEntity);
      assert.deepEqual(body.after.entity, afterEntity);
      return true;
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    debeziumBridge.parseBeforeAfterEntity = parseBeforeAfterEntity;
    debeziumBridge.diffAttributes = diffAttributes;
    debeziumBridge.diffEntity = diffEntity;
    const result = debeziumBridge.parse(body);
    assert.deepEqual(result, expectedResult);
    revert();
  });
});
