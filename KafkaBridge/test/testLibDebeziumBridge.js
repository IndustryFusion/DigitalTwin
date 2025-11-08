/**
* Copyright (c) 2022, 2024 Intel Corporation
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
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        value: 'value'
      }],
      attr2: [{
        id: 'id2',
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        value: 'value3'
      }]
    };
    const afterAttrs = {
      attr1: [{
        id: 'id',
        type: 'type',
        name: 'name',
        entityId: 'entityId',
        value: 'value'
      }]
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.diffAttributes(beforeAttrs, afterAttrs);
    assert.deepEqual(result.updatedAttrs, {});
    assert.deepEqual(result.deletedAttrs, {
      attr2: [{
        id: 'id2',
        entityId: 'entityId',
        name: 'name',
        type: 'type',
        datasetId: '@none'
      }]
    });
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
          id: 'id3',
          value: 'value',
          observedAt: 'observedAt'
        },
        {
          id: 'id',
          value: 'value2',
          datasetId: 'urn:iff:index:1'
        }
      ],
      attr2: [{
        id: 'id2',
        value: 'value3'
      }]
    };
    const afterAttrs = {
      attr1: [
        {
          id: 'id3',
          value: 'value4'
        }
      ]
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.diffAttributes(beforeAttrs, afterAttrs, 'observedAt');
    assert.deepEqual(result.updatedAttrs, {
      attr1: [{
        id: 'id3',
        value: 'value4',
        datasetId: '@none'
      }]
    });
    assert.deepEqual(result.deletedAttrs, {
      attr2:
      [{
        id: 'id2',
        datasetId: '@none'
      }],
      attr1:
      [{
        id: 'id',
        datasetId: 'urn:iff:index:1'
      }]
    });
    revert();
  });
  it('Should create 3 subcomponents, update 3 subcomponents and delete 3 subcomponent', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn'
      }
    };
    const Logger = function () {
      return logger;
    };
    const beforeAttrs = {
      attr2: [
        {
          id: 'id5',
          name: 'attr2',
          entityId: 'entityId',
          attrbuteValue: 'value5',
          datasetId: 'urn:iff:index:1'
        },
        {
          id: 'id6',
          name: 'attr2',
          entityId: 'entityId',
          attrbuteValue: 'value6',
          parentId: 'id5',
          datasetId: 'urn:iff:index:1'
        },
        {
          id: 'id7',
          name: 'attr2',
          entityId: 'entityId',
          attrbuteValue: 'value7',
          parentId: 'id5'
        }
      ],
      attr3: [
        {
          id: 'id8',
          name: 'attr3',
          entityId: 'entityId',
          attrbuteValue: 'value8',
          datasetId: 'urn:iff:index:1'
        },
        {
          id: 'id9',
          name: 'attr3',
          entityId: 'entityId',
          attrbuteValue: 'value9',
          parentId: 'id8',
          datasetId: 'urn:iff:index:1'
        },
        {
          id: 'id10',
          name: 'attr3',
          entityId: 'entityId',
          attrbuteValue: 'value10',
          parentId: 'id9'
        }
      ]
    };
    const afterAttrs = {
      attr1: [
        {
          id: 'id1',
          name: 'attr1',
          entityId: 'entityId',
          attributeValue: 'value1',
          observedAt: 'observedAt'
        },
        {
          id: 'id2',
          name: 'attr1',
          entityId: 'entityId',
          parentId: 'id1',
          attrbuteValue: 'value2',
          datasetId: 'urn:iff:index:1'
        },
        {
          id: 'id3',
          name: 'attr1',
          entityId: 'entityId',
          parentId: 'id1',
          attrbuteValue: 'value3'
        },
        {
          id: 'id4',
          name: 'attr1',
          entityId: 'entityId',
          parentId: 'id3',
          attrbuteValue: 'value4',
          datasetId: 'urn:iff:index:1'
        }
      ],
      attr2: [
        {
          id: 'id5',
          name: 'attr2',
          entityId: 'entityId',
          attrbuteValue: 'value11',
          datasetId: 'urn:iff:index:1'
        },
        {
          id: 'id6',
          name: 'attr2',
          entityId: 'entityId',
          attrbuteValue: 'value12',
          parentId: 'id5',
          datasetId: 'urn:iff:index:1'
        },
        {
          id: 'id7',
          name: 'attr2',
          entityId: 'entityId',
          attrbuteValue: 'value13',
          parentId: 'id5'
        }
      ]
    };
    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.diffAttributes(beforeAttrs, afterAttrs, 'observedAt');
    assert.deepEqual(result.updatedAttrs, {
      attr2: [
        {
          id: 'id7',
          name: 'attr2',
          entityId: 'entityId',
          attrbuteValue: 'value13',
          datasetId: '@none',
          parentId: 'id5'
        },
        {
          id: 'id6',
          name: 'attr2',
          entityId: 'entityId',
          attrbuteValue: 'value12',
          parentId: 'id5',
          datasetId: 'urn:iff:index:1'
        },
        {
          id: 'id5',
          name: 'attr2',
          entityId: 'entityId',
          attrbuteValue: 'value11',
          datasetId: 'urn:iff:index:1'
        }
      ]
    });
    assert.deepEqual(result.deletedAttrs, {
      attr3: [
        {
          id: 'id10',
          name: 'attr3',
          entityId: 'entityId',
          datasetId: '@none',
          parentId: 'id9'
        },
        {
          id: 'id9',
          name: 'attr3',
          entityId: 'entityId',
          parentId: 'id8',
          datasetId: 'urn:iff:index:1'
        },
        {
          id: 'id8',
          name: 'attr3',
          entityId: 'entityId',
          datasetId: 'urn:iff:index:1'
        }
      ]
    });
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
  it('Should return one entity, one Property & one Relationship & one JsonProperty & one ListProperty', async function () {
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
      e_types: ['type'],
      entity: '{\
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
                "https://example/hasJson": [{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/JsonProperty"],\
                    "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/hasJSON": [{"@value":{"my": "object"}}]\
                }],\
                "https://example/hasList": [{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/ListProperty"],\
                    "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/hasValueList": [{ "@list": [{"@value": 1}, {"@value": 2}, {"@value": 3}]}]\
                }],\
                "https://example/prop":[{\
                  "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
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
    assert.deepEqual(result.entity, { id: 'id', type: 'type' });
    assert.deepEqual(result.attributes, {
      'https://example/hasJson': [
        {
          attributeValue: '{"my":"object"}',
          datasetId: '@none',
          entityId: 'id',
          id: 'id\\286e9bdcd44df99ba2253c0a',
          name: 'https://example/hasJson',
          nodeType: '@json',
          type: 'https://uri.etsi.org/ngsi-ld/JsonProperty'
        }
      ],
      'https://example/hasList': [
        {
          attributeValue: '[1,2,3]',
          datasetId: '@none',
          entityId: 'id',
          id: 'id\\8e35d5b0ad8ef2eadef775d2',
          name: 'https://example/hasList',
          nodeType: '@list',
          type: 'https://uri.etsi.org/ngsi-ld/JsonProperty'
        }
      ],
      'https://example/hasRel': [{
        id: 'id\\cf3dbdad8b699fc18bbcc2c3',
        entityId: 'id',
        nodeType: '@id',
        name: 'https://example/hasRel',
        type: 'https://uri.etsi.org/ngsi-ld/Relationship',
        datasetId: '@none',
        attributeValue: 'urn:object:1'
      }],
      'https://example/prop': [{
        id: 'id\\b3800f46b939df60bf0ce0bd',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        datasetId: '@none',
        attributeValue: 'value',
        'https://uri.etsi.org/ngsi-ld/observedAt': [{
          '@type': 'https://uri.etsi.org/ngsi-ld/DateTime',
          '@value': '2022-02-19T23:11:28.457509Z'
        }]
      }]
    });
    revert();
  });

  it('Should return one entity, one Property & one Relationship with observedAt field', async function () {
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
      e_types: ['type'],
      entity: '{\
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
                    "https://uri.etsi.org/ngsi-ld/modifiedAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/observedAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:32:26.123656Z"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/hasObject": [{"@id": "urn:object:1"}]\
                }],\
                "https://example/prop":[{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [{"@value": "value"}],\
                    "https://uri.etsi.org/ngsi-ld/observedAt":[{\
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
    assert.deepEqual(result.entity, { id: 'id', type: 'type' });
    assert.deepEqual(result.attributes, {
      'https://example/hasRel': [{
        id: 'id\\cf3dbdad8b699fc18bbcc2c3',
        entityId: 'id',
        nodeType: '@id',
        name: 'https://example/hasRel',
        type: 'https://uri.etsi.org/ngsi-ld/Relationship',
        datasetId: '@none',
        'https://uri.etsi.org/ngsi-ld/observedAt': [{
          '@type': 'https://uri.etsi.org/ngsi-ld/DateTime',
          '@value': '2022-02-19T20:32:26.123656Z'
        }],
        attributeValue: 'urn:object:1'
      }],
      'https://example/prop': [{
        id: 'id\\b3800f46b939df60bf0ce0bd',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        attributeValue: 'value',
        datasetId: '@none',
        'https://uri.etsi.org/ngsi-ld/observedAt': [{
          '@type': 'https://uri.etsi.org/ngsi-ld/DateTime',
          '@value': '2022-02-19T20:31:26.123656Z'
        }]
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
      e_types: ['type'],
      entity: '{\
                "@id":"id", "@type": ["type"],\
                "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                    "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                    "@value": "2022-02-19T20:31:26.123656Z"\
                }],\
                "https://example/prop":[{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
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
    assert.deepEqual(result.entity, { id: 'id', type: 'type' });
    assert.deepEqual(result.attributes, {
      'https://example/prop': [{
        id: 'id\\b3800f46b939df60bf0ce0bd',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        datasetId: '@none',
        attributeValue: 'value',
        'https://uri.etsi.org/ngsi-ld/observedAt': [{
          '@type': 'https://uri.etsi.org/ngsi-ld/DateTime',
          '@value': '2022-02-19T23:11:28.457509Z'
        }],
        valueType: 'https://example/type'
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
      e_types: ['type'],
      entity: '{"@id":"id", "@type": ["type"],'
    };

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.parseBeforeAfterEntity(ba);
    assert.equal(result, undefined);
    revert();
  });
  it('Should return a subproperty with parentId', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn',
        hashLength: 24
      }
    };
    const Logger = function () {
      return logger;
    };
    const ba = {
      id: 'id',
      e_types: ['type'],
      entity: '{\
                "@id":"id", "@type": ["type"],\
                "https://example/prop":[{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "value",\
                        "@type": "https://example/type"\
                    }],\
                    "https://example/subprop": [{\
                        "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                        "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "subvalue"}]\
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
    assert.deepEqual(result.entity, { id: 'id', type: 'type' });
    assert.deepEqual(result.attributes, {
      'https://example/prop': [{
        id: 'id\\b3800f46b939df60bf0ce0bd',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        datasetId: '@none',
        attributeValue: 'value',
        'https://uri.etsi.org/ngsi-ld/observedAt': [{
          '@type': 'https://uri.etsi.org/ngsi-ld/DateTime',
          '@value': '2022-02-19T23:11:28.457509Z'
        }],
        valueType: 'https://example/type'
      }],
      'https://example/subprop': [{
        attributeValue: 'subvalue',
        datasetId: '@none',
        entityId: 'id',
        id: 'id\\4bafa5f59929194a5327dc19',
        name: 'https://example/subprop',
        nodeType: '@value',
        parentId: 'id\\b3800f46b939df60bf0ce0bd',
        type: 'https://uri.etsi.org/ngsi-ld/Property'
      }]
    });
    revert();
  });
  it('Should return 3 subproperties with parentId and datasetId', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn',
        hashLength: 24
      }
    };
    const Logger = function () {
      return logger;
    };
    const ba = {
      id: 'id',
      e_types: ['type'],
      entity: '{\
                "@id":"id", "@type": ["type"],\
                "https://example/prop":[{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "value",\
                        "@type": "https://example/type"\
                    }],\
                    "https://example/subprop": [{\
                        "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                        "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "subvalue"}]\
                    }],\
                    "https://example/subprop2": [{\
                        "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                        "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "subvalue"}],\
                        "https://uri.etsi.org/ngsi-ld/datasetId": [{"@id": "http://dataset.id/1"}]\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/modifiedAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T23:11:28.457509Z"\
                    }]\
                }],\
                "https://example/prop2":[{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "value3",\
                        "@type": "https://example/type3"\
                    }],\
                    "https://example/subprop2": [{\
                        "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                        "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "subvalue3"}],\
                         "https://uri.etsi.org/ngsi-ld/datasetId": [{"@id": "http://dataset.id/2"}]\
                    }]\
                }]\
            }'
    };

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.parseBeforeAfterEntity(ba);
    assert.deepEqual(result.entity, { id: 'id', type: 'type' });
    assert.deepEqual(result.attributes, {
      'https://example/prop': [{
        id: 'id\\b3800f46b939df60bf0ce0bd',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        datasetId: '@none',
        attributeValue: 'value',
        'https://uri.etsi.org/ngsi-ld/observedAt': [{
          '@type': 'https://uri.etsi.org/ngsi-ld/DateTime',
          '@value': '2022-02-19T23:11:28.457509Z'
        }],
        valueType: 'https://example/type'
      }],
      'https://example/prop2': [{
        attributeValue: 'value3',
        datasetId: '@none',
        entityId: 'id',
        id: 'id\\c81b7f87902b3ee5c99dd5b4',
        name: 'https://example/prop2',
        nodeType: '@value',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        valueType: 'https://example/type3'
      }],
      'https://example/subprop': [{
        attributeValue: 'subvalue',
        datasetId: '@none',
        entityId: 'id',
        id: 'id\\4bafa5f59929194a5327dc19',
        name: 'https://example/subprop',
        nodeType: '@value',
        parentId: 'id\\b3800f46b939df60bf0ce0bd',
        type: 'https://uri.etsi.org/ngsi-ld/Property'
      }],
      'https://example/subprop2': [{
        attributeValue: 'subvalue3',
        datasetId: 'http://dataset.id/2',
        entityId: 'id',
        id: 'id\\76690702a6e19da54040e9dd',
        name: 'https://example/subprop2',
        nodeType: '@value',
        parentId: 'id\\c81b7f87902b3ee5c99dd5b4',
        type: 'https://uri.etsi.org/ngsi-ld/Property'
      },
      {
        attributeValue: 'subvalue',
        datasetId: 'http://dataset.id/1',
        entityId: 'id',
        id: 'id\\9e24f93f46dec1c3c8481700',
        name: 'https://example/subprop2',
        nodeType: '@value',
        parentId: 'id\\b3800f46b939df60bf0ce0bd',
        type: 'https://uri.etsi.org/ngsi-ld/Property'
      }]
    });
    revert();
  });
  it('Should return 1 subproperty and 2 subsubproperties with parentId and datasetId', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn',
        hashLength: 24
      }
    };
    const Logger = function () {
      return logger;
    };
    const ba = {
      id: 'id',
      e_types: ['type'],
      entity: '{\
                "@id":"id", "@type": ["type"],\
                "https://example/prop":[{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "value",\
                        "@type": "https://example/type"\
                    }],\
                    "https://example/subprop": [{\
                        "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                        "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                          "@value": "subvalue"}],\
                          "https://example/subsubprop": [{\
                            "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                            "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                              "@value": "subsubvalue"}],\
                            "https://uri.etsi.org/ngsi-ld/datasetId": [{"@id": "http://dataset.id/1"}]\
                          }],\
                          "https://example/subsubprop2": [{\
                          "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                            "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                              "@value": "subsubvalue2"}],\
                            "https://uri.etsi.org/ngsi-ld/datasetId": [{"@id": "http://dataset.id/1"}],\
                            "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                              "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                              "@value": "2022-02-19T20:31:26.123656Z"\
                            }],\
                            "https://uri.etsi.org/ngsi-ld/modifiedAt":[{\
                              "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                              "@value": "2022-02-19T23:11:28.457509Z"\
                          }]\
                      }]\
                    }]\
                }]\
              }'
    };

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.parseBeforeAfterEntity(ba);
    assert.deepEqual(result.entity, { id: 'id', type: 'type' });
    assert.deepEqual(result.attributes, {
      'https://example/prop': [{
        id: 'id\\b3800f46b939df60bf0ce0bd',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        datasetId: '@none',
        attributeValue: 'value',
        valueType: 'https://example/type'
      }],
      'https://example/subprop': [{
        attributeValue: 'subvalue',
        datasetId: '@none',
        entityId: 'id',
        id: 'id\\4bafa5f59929194a5327dc19',
        name: 'https://example/subprop',
        nodeType: '@value',
        parentId: 'id\\b3800f46b939df60bf0ce0bd',
        type: 'https://uri.etsi.org/ngsi-ld/Property'
      }],
      'https://example/subsubprop': [{
        attributeValue: 'subsubvalue',
        datasetId: 'http://dataset.id/1',
        entityId: 'id',
        id: 'id\\4f677b846038b9c5a32a2b1c',
        name: 'https://example/subsubprop',
        nodeType: '@value',
        parentId: 'id\\4bafa5f59929194a5327dc19',
        type: 'https://uri.etsi.org/ngsi-ld/Property'
      }],
      'https://example/subsubprop2': [{
        attributeValue: 'subsubvalue2',
        datasetId: 'http://dataset.id/1',
        entityId: 'id',
        'https://uri.etsi.org/ngsi-ld/observedAt': [{
          '@type': 'https://uri.etsi.org/ngsi-ld/DateTime',
          '@value': '2022-02-19T23:11:28.457509Z'
        }],
        id: 'id\\5422384716dc1f20910eb95e',
        name: 'https://example/subsubprop2',
        nodeType: '@value',
        parentId: 'id\\4bafa5f59929194a5327dc19',
        type: 'https://uri.etsi.org/ngsi-ld/Property'
      }]
    });
    revert();
  });
  it('Should return 1 subproperty and 2 subrelationship with parentId and datasetId', async function () {
    const config = {
      bridgeCommon: {
        kafkaSyncOnAttribute: 'kafkaSyncOn',
        hashLength: 24
      }
    };
    const Logger = function () {
      return logger;
    };
    const ba = {
      id: 'id',
      e_types: ['type'],
      entity: '{\
                "@id":"id", "@type": ["type"],\
                "https://example/prop":[{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "value",\
                        "@type": "https://example/type"\
                    }],\
                    "https://example/subprop": [{\
                        "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                        "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                          "@value": "subvalue"}],\
                          "https://example/subsubprop": [{\
                            "@type": ["https://uri.etsi.org/ngsi-ld/Relationship"],\
                            "https://uri.etsi.org/ngsi-ld/hasObject": [{\
                              "@id": "urn:test:1"}],\
                            "https://uri.etsi.org/ngsi-ld/datasetId": [{"@id": "http://dataset.id/1"}]\
                          }],\
                          "https://example/subsubprop2": [{\
                            "@type": ["https://uri.etsi.org/ngsi-ld/Relationship"],\
                            "https://uri.etsi.org/ngsi-ld/hasObject": [{\
                              "@id": "urn:test:2"}],\
                            "https://uri.etsi.org/ngsi-ld/datasetId": [{"@id": "http://dataset.id/1"}],\
                            "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                              "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                              "@value": "2022-02-19T20:31:26.123656Z"\
                            }],\
                            "https://uri.etsi.org/ngsi-ld/modifiedAt":[{\
                              "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                              "@value": "2022-02-19T23:11:28.457509Z"\
                          }]\
                      }]\
                    }]\
                }]\
              }'
    };

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.parseBeforeAfterEntity(ba);
    assert.deepEqual(result.entity, { id: 'id', type: 'type' });
    assert.deepEqual(result.attributes, {
      'https://example/prop': [{
        id: 'id\\b3800f46b939df60bf0ce0bd',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        datasetId: '@none',
        attributeValue: 'value',
        valueType: 'https://example/type'
      }],
      'https://example/subprop': [{
        attributeValue: 'subvalue',
        datasetId: '@none',
        entityId: 'id',
        id: 'id\\4bafa5f59929194a5327dc19',
        name: 'https://example/subprop',
        nodeType: '@value',
        parentId: 'id\\b3800f46b939df60bf0ce0bd',
        type: 'https://uri.etsi.org/ngsi-ld/Property'
      }],
      'https://example/subsubprop': [{
        attributeValue: 'urn:test:1',
        datasetId: 'http://dataset.id/1',
        entityId: 'id',
        id: 'id\\4f677b846038b9c5a32a2b1c',
        name: 'https://example/subsubprop',
        nodeType: '@id',
        parentId: 'id\\4bafa5f59929194a5327dc19',
        type: 'https://uri.etsi.org/ngsi-ld/Relationship'
      }],
      'https://example/subsubprop2': [{
        attributeValue: 'urn:test:2',
        datasetId: 'http://dataset.id/1',
        entityId: 'id',
        'https://uri.etsi.org/ngsi-ld/observedAt': [{
          '@type': 'https://uri.etsi.org/ngsi-ld/DateTime',
          '@value': '2022-02-19T23:11:28.457509Z'
        }],
        id: 'id\\5422384716dc1f20910eb95e',
        name: 'https://example/subsubprop2',
        nodeType: '@id',
        parentId: 'id\\4bafa5f59929194a5327dc19',
        type: 'https://uri.etsi.org/ngsi-ld/Relationship'
      }]
    });
    revert();
  });
  it('Keep last element of elements with same datasetId', async function () {
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
      e_types: ['type'],
      entity: '{\
                "@id":"id", "@type": ["type"],\
                "https://example/prop":[{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "value1",\
                        "@type": "https://example/type"\
                    }]\
                },\
                {\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                    "https://uri.etsi.org/ngsi-ld/hasValue": [\
                    {\
                        "@value": "value2",\
                        "@type": "https://example/type"\
                    }]\
                }],\
                "https://example/rel":[{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Relationship"],\
                    "https://uri.etsi.org/ngsi-ld/hasObject": [{\
                            "@id": "urn:test:1"\
                        }],\
                        "https://uri.etsi.org/ngsi-ld/datasetId": [{"@id": "http://dataset.id/1"}]\
                },\
                {\
                    "@type": ["https://uri.etsi.org/ngsi-ld/Relationship"],\
                    "https://uri.etsi.org/ngsi-ld/hasObject": [{\
                        "@id": "urn:test:2"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/datasetId": [{"@id": "http://dataset.id/1"}]\
                }]\
              }'
    };

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.parseBeforeAfterEntity(ba);
    assert.deepEqual(result.entity, { id: 'id', type: 'type' });
    assert.deepEqual(result.attributes, {
      'https://example/prop': [{
        id: 'id\\b3800f46b939df60bf0ce0bd',
        entityId: 'id',
        nodeType: '@value',
        name: 'https://example/prop',
        type: 'https://uri.etsi.org/ngsi-ld/Property',
        datasetId: '@none',
        attributeValue: 'value2',
        valueType: 'https://example/type'
      }],
      'https://example/rel': [{
        attributeValue: 'urn:test:2',
        datasetId: 'http://dataset.id/1',
        entityId: 'id',
        id: 'id\\ccd0f05344a0ae4e25c16b68',
        name: 'https://example/rel',
        nodeType: '@id',
        type: 'https://uri.etsi.org/ngsi-ld/Relationship'
      }]
    });
    revert();
  });
  it('Should drop silently incorrect Property, Relationship, JsonProperty & ListProperty', async function () {
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
      e_types: ['type'],
      entity: '{\
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
                    }]\
                }],\
                "https://example/hasJson": [{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/JsonProperty"],\
                    "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }]\
                }],\
                "https://example/hasList": [{\
                    "@type": ["https://uri.etsi.org/ngsi-ld/ListProperty"],\
                    "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }]\
                }],\
                "https://example/prop":[{\
                  "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                    "https://uri.etsi.org/ngsi-ld/createdAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T20:31:26.123656Z"\
                    }],\
                    "https://uri.etsi.org/ngsi-ld/modifiedAt":[{\
                        "@type": "https://uri.etsi.org/ngsi-ld/DateTime",\
                        "@value": "2022-02-19T23:11:28.457509Z"\
                    }]\
                }],\
                "https://example/prop2":[{\
                  "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                   "https://uri.etsi.org/ngsi-ld/hasValue": [],\
                    "https://example/subprop": [{\
                        "@type": ["https://uri.etsi.org/ngsi-ld/Property"],\
                        "https://uri.etsi.org/ngsi-ld/hasValue": [{\
                        "@value": "subvalue"}]\
                    }]\
                }]\
            }'
    };

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    const result = debeziumBridge.parseBeforeAfterEntity(ba);
    assert.deepEqual(result.entity, { id: 'id', type: 'type' });
    assert.deepEqual(result.attributes, {
      'https://example/subprop': [
        {
          attributeValue: 'subvalue',
          datasetId: '@none',
          entityId: 'id',
          id: 'id\\6d6cab5b1707785e3a5ce6be',
          parentId: 'id\\c81b7f87902b3ee5c99dd5b4',
          name: 'https://example/subprop',
          nodeType: '@value',
          type: 'https://uri.etsi.org/ngsi-ld/Property'
        }
      ]
    });
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

    const revert = ToTest.__set__('Logger', Logger);
    const debeziumBridge = new ToTest(config);
    let result = debeziumBridge.parse(null);
    assert.deepEqual(result, null);
    result = debeziumBridge.parse(undefined);
    assert.deepEqual(result, null);
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
    assert.deepEqual(result, null);
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
      insertedAttrs: {},
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
        deletedAttrs: deletedAttrs,
        insertedAttrs: {}
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
      deletedEntity: null,
      updatedAttrs: {
        attribute: 'attribute2'
      },
      insertedAttrs: {},
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
        deletedAttrs: deletedAttrs,
        insertedAttrs: {}
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
      deletedEntity: null,
      updatedAttrs: {
        attribute: 'attribute2'
      },
      deletedAttrs: {
        attribute2: 'attribute2'
      },
      insertedAttrs: {}
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
        deletedAttrs: deletedAttrs,
        insertedAttrs: {}
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
  it('Should return updated Entity and inserted attributes', async function () {
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
      deletedEntity: null,
      updatedAttrs: {},
      deletedAttrs: {},
      insertedAttrs: {
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
        }]
      },
      after: {
        entity: {
          id: 'id',
          type: 'type'
        },
        attributes: {
          attribute: 'attribute'

        }
      }
    };
    const updatedAttrs = {
    };
    const deletedAttrs = {
    };
    const insertedAttrs = {
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
        deletedAttrs: deletedAttrs,
        insertedAttrs: insertedAttrs
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
