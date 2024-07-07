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

const $rdf = require('rdflib');
const chai = require('chai');
global.should = chai.should();

const rewire = require('rewire');
const ToTest = rewire('../lib/owlUtils.js');

const RDF = $rdf.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#');
const RDFS = $rdf.Namespace('http://www.w3.org/2000/01/rdf-schema#');
const OWL = $rdf.Namespace('http://www.w3.org/2002/07/owl#');
const NGSILD = $rdf.Namespace('https://uri.etsi.org/ngsi-ld/');
const BASE = $rdf.Namespace('https://industryfusion.github.io/contexts/ontology/v0/base/');

describe('Test class Entity', function () {
  it('Should create Entity with IRI', function () {
    const entity = new ToTest.Entity('IRI');
    entity.iri.should.equal('IRI');
  });
});
describe('Test class Attribute', function () {
  it('Should create attributes', function () {
    const attribute = new ToTest.Attribute('attributename');
    attribute.entities.should.deep.equal([]);
    attribute.addEntity('entity');
    attribute.entities.should.deep.equal(['entity']);
    attribute.isProperty.should.equal(true);
    attribute.addEntity('entity2');
    attribute.entities.should.deep.equal(['entity', 'entity2']);
    attribute.isProperty = false;
    attribute.isProperty.should.equal(false);
  });
});
describe('Test dumpAttribute', function () {
  it('Should create a Property', function () {
    const attributeName = 'http://example.com/attributename';
    const entityName = 'http://example.com/entity';
    const attribute = new ToTest.Attribute(attributeName);
    const entity = new ToTest.Entity(entityName);
    const added = [];
    const expected = [
      [$rdf.namedNode(attributeName), RDF('type'), OWL('Property')],
      [$rdf.namedNode(attributeName), RDFS('domain'), $rdf.namedNode(entityName)],
      [$rdf.namedNode(attributeName), RDFS('range'), NGSILD('Property')]
    ];
    const store = {
      add: (s, p, o) => { added.push([s, p, o]); }
    };
    const dumpAttribute = ToTest.__get__('dumpAttribute');
    dumpAttribute(attribute, entity, store);
    added.should.deep.equal(expected);
  });
  it('Should create a Relationship', function () {
    const attributeName = 'http://example.com/attributename';
    const entityName = 'http://example.com/entity';
    const attribute = new ToTest.Attribute(attributeName);
    attribute.isProperty = false;
    const entity = new ToTest.Entity(entityName);
    const added = [];
    const expected = [
      [$rdf.namedNode(attributeName), RDF('type'), OWL('Property')],
      [$rdf.namedNode(attributeName), RDFS('domain'), $rdf.namedNode(entityName)],
      [$rdf.namedNode(attributeName), RDFS('range'), NGSILD('Relationship')],
      [$rdf.namedNode(attributeName), RDF('type'), BASE('PeerRelationship')]
    ];
    const store = {
      add: (s, p, o) => { added.push([s, p, o]); }
    };
    const dumpAttribute = ToTest.__get__('dumpAttribute');
    dumpAttribute(attribute, entity, store);
    added.should.deep.equal(expected);
  });
});
describe('Test dumpEntity', function () {
  it('Should dump entity only', function () {
    const dumpEntity = ToTest.__get__('dumpEntity');
    const entityName = 'http://example.com/entity';
    const entity = new ToTest.Entity(entityName);
    const expected = [
      [$rdf.namedNode(entityName), RDF('type'), OWL('Class')]
    ];
    const added = [];
    const store = {
      add: (s, p, o) => { added.push([s, p, o]); }
    };
    const contextManager = {
      expandTerm: term => term
    };
    dumpEntity(entity, contextManager, store);
    added.should.deep.equal(expected);
  });
  it('Should dump entity and one attribute', function () {
    const globalAttributes = [];
    const attributeName = 'http://example.com#attributename';
    globalAttributes.push(new ToTest.Attribute(attributeName));
    ToTest.__set__('globalAttributes', globalAttributes);
    const dumpEntity = ToTest.__get__('dumpEntity');
    const entityName = 'http://example.com/entity';
    const entity = new ToTest.Entity(entityName);
    const expected = [
      [$rdf.namedNode(entityName), RDF('type'), OWL('Class')],
      [$rdf.namedNode(attributeName), RDF('type'), OWL('Property')],
      [$rdf.namedNode(attributeName), RDFS('domain'), $rdf.namedNode(entityName)],
      [$rdf.namedNode(attributeName), RDFS('range'), NGSILD('Property')]
    ];
    const added = [];
    const store = {
      add: (s, p, o) => { added.push([s, p, o]); }
    };
    const contextManager = {
      expandTerm: term => term
    };
    dumpEntity(entity, contextManager, store);
    added.should.deep.equal(expected);
  });
});

describe('Test scanEntity', function () {
  it('Should add entity to global entities', function () {
    const globalEntities = [];
    ToTest.__set__('globalEntities', globalEntities);
    const scanProperties = function () {};
    const revert = ToTest.__set__('scanProperties', scanProperties);
    const scanEntity = ToTest.__get__('scanEntity');
    const typeschema = {
      $id: 'id'
    };
    const entity = scanEntity(typeschema, null);
    entity.iri.should.equal('id');
    globalEntities[0].iri.should.equal('id');
    revert();
  });
});
describe('Test scanProperty', function () {
  it('Should add property and relationsip to global attributes', function () {
    const globalAttributes = [];
    const attribute1name = 'http://example.com/property';
    const attribute2name = 'http://example.com/relationship';
    const attribute1 = new ToTest.Attribute(attribute1name);
    const attribute2 = new ToTest.Attribute(attribute2name);
    const entity = new ToTest.Entity('http://example.com/entity');
    attribute1.addEntity(entity);
    attribute2.addEntity(entity);
    attribute2.isProperty = false;
    const expected = [attribute1, attribute2];

    ToTest.__set__('globalAttributes', globalAttributes);
    const scanProperties = ToTest.__get__('scanProperties');

    const typeschema = {
      properties: {
        type: {},
        id: {},
        'http://example.com/property': { },
        'http://example.com/relationship': { relationship: {} }
      }
    };
    const contextManager = {
      isValidIri: function () { return true; },
      expandTerm: function (term) { return term; }
    };
    scanProperties(entity, typeschema, contextManager);
    globalAttributes.should.deep.equal(expected);
  });
});
describe('Test encodeHash', function () {
  it('Should encode id', function () {
    const encodeHash = ToTest.__get__('encodeHash');
    const result = encodeHash('http://example.com#hash#hash');
    result.should.equal('http://example.com/%23hash%23hash');
  });
});
// describe('Test class Constraint', function () {
//   it('Should construct', function () {
//     const constraint = new ToTest.Constraint('type', 'param');
//     constraint.type.should.equal('type');
//     constraint.params.should.equal('param');
//   });
// });
// describe('Test dumpPropertyShape', function () {
//   it('Should dump property without constraints', function () {
//     const propertyShape = new ToTest.PropertyShape(1, 2, 'nodeKind', 'path', true);
//     propertyShape.propertyNode = 'propertyNode';
//     const storeAdds = [];
//     const store = {
//       add: (s, p, o) => { storeAdds.push([s, p, o]); }
//     };
//     const $rdf = {
//       blankNode: () => { return {}; },
//       Namespace: () => (x) => 'ngsild:' + x
//     };
//     const SHACL = (x) => 'shacl:' + x;
//     const revert = ToTest.__set__('$rdf', $rdf);
//     ToTest.__set__('SHACL', SHACL);
//     ToTest.__set__('globalPrefixHash', { 'ngsi-ld': 'ngsi-ld' });
//     const dumpPropertyShape = ToTest.__get__('dumpPropertyShape');
//     dumpPropertyShape(propertyShape, store);
//     storeAdds.should.deep.equal([
//       ['propertyNode', 'shacl:minCount', 1],
//       ['propertyNode', 'shacl:maxCount', 2],
//       ['propertyNode', 'shacl:nodeKind', 'shacl:BlankNode'],
//       ['propertyNode', 'shacl:path', 'path'],
//       ['propertyNode', 'shacl:property', {}],
//       [{}, 'shacl:path', 'ngsild:hasValue'],
//       [{}, 'shacl:minCount', 1],
//       [{}, 'shacl:maxCount', 1],
//       [{}, 'shacl:nodeKind', 'nodeKind']]);
//     revert();
//   });
//   it('Should dump property with constraints', function () {
//     const propertyShape = new ToTest.PropertyShape(0, 2, 'nodeKind', 'path', true);
//     propertyShape.propertyNode = 'propertyNode';
//     propertyShape.addConstraint(new ToTest.Constraint('type', 'params'));
//     propertyShape.addConstraint(new ToTest.Constraint('type2', ['p1', 'p2']));
//     const storeAdds = [];
//     const store = {
//       add: (s, p, o) => { storeAdds.push([s, p, o]); }
//     };
//     const $rdf = {
//       blankNode: () => { return {}; },
//       Namespace: () => (x) => 'ngsild:' + x
//     };
//     const SHACL = (x) => 'shacl:' + x;
//     const revert = ToTest.__set__('$rdf', $rdf);
//     ToTest.__set__('SHACL', SHACL);
//     ToTest.__set__('globalPrefixHash', { 'ngsi-ld': 'ngsi-ld' });
//     const dumpPropertyShape = ToTest.__get__('dumpPropertyShape');
//     dumpPropertyShape(propertyShape, store);
//     storeAdds.should.deep.equal([
//       ['propertyNode', 'shacl:minCount', 0],
//       ['propertyNode', 'shacl:maxCount', 2],
//       ['propertyNode', 'shacl:nodeKind', 'shacl:BlankNode'],
//       ['propertyNode', 'shacl:path', 'path'],
//       ['propertyNode', 'shacl:property', {}],
//       [{}, 'shacl:path', 'ngsild:hasValue'],
//       [{}, 'shacl:minCount', 1],
//       [{}, 'shacl:maxCount', 1],
//       [{}, 'shacl:nodeKind', 'nodeKind'],
//       [{}, 'type', 'params'],
//       [{}, 'type2', ['p1', 'p2']]]);
//     revert();
//   });
//   it('Should dump relationship without constraints', function () {
//     const propertyShape = new ToTest.PropertyShape(1, 1, 'nodeKind', 'relationship', false);
//     propertyShape.propertyNode = 'propertyNode';
//     const storeAdds = [];
//     const store = {
//       add: (s, p, o) => { storeAdds.push([s, p, o]); }
//     };
//     const $rdf = {
//       blankNode: () => { return {}; },
//       Namespace: () => (x) => 'ngsild:' + x
//     };
//     const SHACL = (x) => 'shacl:' + x;
//     const revert = ToTest.__set__('$rdf', $rdf);
//     ToTest.__set__('SHACL', SHACL);
//     ToTest.__set__('globalPrefixHash', { 'ngsi-ld': 'ngsi-ld' });
//     const dumpPropertyShape = ToTest.__get__('dumpPropertyShape');
//     dumpPropertyShape(propertyShape, store);
//     storeAdds.should.deep.equal([
//       ['propertyNode', 'shacl:minCount', 1],
//       ['propertyNode', 'shacl:maxCount', 1],
//       ['propertyNode', 'shacl:nodeKind', 'shacl:BlankNode'],
//       ['propertyNode', 'shacl:path', 'relationship'],
//       ['propertyNode', 'shacl:property', {}],
//       [{}, 'shacl:path', 'ngsild:hasObject'],
//       [{}, 'shacl:minCount', 1],
//       [{}, 'shacl:maxCount', 1],
//       [{}, 'shacl:nodeKind', 'nodeKind']]);
//     revert();
//   });
// });
// describe('Test dumpNodeShape', function () {
//   it('Should dump without properties', function () {
//     const nodeShape = new ToTest.NodeShape('http://example.com/targetClass');
//     const storeAdds = [];
//     const store = {
//       add: (s, p, o) => { storeAdds.push([s, p, o]); }
//     };
//     const $rdf = {
//       blankNode: () => { return {}; },
//       sym: (x) => 'sym:' + x
//     };
//     const globalContext = {
//       expandTerm: (x) => x
//     };
//     const revert = ToTest.__set__('SHACL', (x) => 'shacl:' + x);
//     ToTest.__set__('IFFK', (x) => 'iffk:' + x);
//     ToTest.__set__('RDF', (x) => 'rdf:' + x);
//     ToTest.__set__('globalContext', globalContext);
//     ToTest.__set__('$rdf', $rdf);
//     const dumpNodeShape = ToTest.__get__('dumpNodeShape');
//     dumpNodeShape(nodeShape, store);
//     storeAdds.should.deep.equal([
//       ['iffk:targetClassShape', 'rdf:type', 'shacl:NodeShape'],
//       ['iffk:targetClassShape', 'shacl:targetClass', 'sym:http://example.com/targetClass']
//     ]);
//     revert();
//   });
//   it('Should dump relationship with properties', function () {
//     const nodeShape = new ToTest.NodeShape('http://example.com/targetClass');
//     const propertyShape = new ToTest.PropertyShape(0, 2, 'nodeKind', 'path', true);
//     nodeShape.addPropertyShape(propertyShape);
//     const storeAdds = [];
//     const store = {
//       add: (s, p, o) => { storeAdds.push([s, p, o]); }
//     };
//     const $rdf = {
//       blankNode: () => { return {}; },
//       sym: (x) => 'sym:' + x
//     };
//     const globalContext = {
//       expandTerm: (x) => x
//     };
//     const dumpPropertyShape = (x, y) => { x.propertyNode.should.deep.equal({}); };
//     const revert = ToTest.__set__('SHACL', (x) => 'shacl:' + x);
//     ToTest.__set__('IFFK', (x) => 'iffk:' + x);
//     ToTest.__set__('RDF', (x) => 'rdf:' + x);
//     ToTest.__set__('globalContext', globalContext);
//     ToTest.__set__('dumpPropertyShape', dumpPropertyShape);
//     ToTest.__set__('$rdf', $rdf);
//     const dumpNodeShape = ToTest.__get__('dumpNodeShape');
//     dumpNodeShape(nodeShape, store);
//     storeAdds.should.deep.equal([
//       ['iffk:targetClassShape', 'rdf:type', 'shacl:NodeShape'],
//       ['iffk:targetClassShape', 'shacl:targetClass', 'sym:http://example.com/targetClass'],
//       ['iffk:targetClassShape', 'shacl:property', {}]
//     ]);
//     revert();
//   });
//   it('Should dump with hash type', function () {
//     const nodeShape = new ToTest.NodeShape('http://example.com/example#targetClass#1#2');
//     const storeAdds = [];
//     const store = {
//       add: (s, p, o) => { storeAdds.push([s, p, o]); }
//     };
//     const $rdf = {
//       blankNode: () => { return {}; },
//       sym: (x) => 'sym:' + x
//     };
//     const globalContext = {
//       expandTerm: (x) => x
//     };
//     const revert = ToTest.__set__('SHACL', (x) => 'shacl:' + x);
//     ToTest.__set__('IFFK', (x) => 'iffk:' + x);
//     ToTest.__set__('RDF', (x) => 'rdf:' + x);
//     ToTest.__set__('globalContext', globalContext);
//     ToTest.__set__('$rdf', $rdf);
//     const dumpNodeShape = ToTest.__get__('dumpNodeShape');
//     dumpNodeShape(nodeShape, store);
//     storeAdds.should.deep.equal([
//       ['iffk:targetClass#1#2Shape', 'rdf:type', 'shacl:NodeShape'],
//       ['iffk:targetClass#1#2Shape', 'shacl:targetClass', 'sym:http://example.com/example#targetClass#1#2']
//     ]);
//     revert();
//   });
// });
// describe('Test scanProperties', function () {
//   it('Should dump without properties', function () {
//     const scanProperties = ToTest.__get__('scanProperties');
//     const typeSchema = {
//       properties: {
//         type: {
//           const: 'Plasmacutter'
//         },
//         id: {
//           type: 'string',
//           pattern: "^urn:[a-zA-Z0-9][a-zA-Z0-9-]{1,31}:([a-zA-Z0-9()+,.:=@;$_!*'-]|%[0-9a-fA-F]{2})*$"
//         }

//       },
//       required: ['type', 'id']
//     };
//     const expectedNodeShape = {
//       _properties: [],
//       targetClass: 'targetClass'
//     };
//     const nodeShape = new ToTest.NodeShape('targetClass');
//     scanProperties(nodeShape, typeSchema);
//     nodeShape.should.deep.equal(expectedNodeShape);
//   });
// });
// describe('Test scanProperties', function () {
//   it('Should scan without properties', function () {
//     const scanProperties = ToTest.__get__('scanProperties');
//     const typeSchema = {
//       properties: {
//         type: {
//           const: 'Plasmacutter'
//         },
//         id: {
//           type: 'string',
//           pattern: "^urn:[a-zA-Z0-9][a-zA-Z0-9-]{1,31}:([a-zA-Z0-9()+,.:=@;$_!*'-]|%[0-9a-fA-F]{2})*$"
//         }

//       },
//       required: ['type', 'id']
//     };
//     const expectedNodeShape = {
//       _properties: [],
//       targetClass: 'targetClass'
//     };
//     const nodeShape = new ToTest.NodeShape('targetClass');
//     scanProperties(nodeShape, typeSchema);
//     nodeShape.should.deep.equal(expectedNodeShape);
//   });
//   it('Should scan with property', function () {
//     const scanProperties = ToTest.__get__('scanProperties');
//     const typeSchema = {
//       properties: {
//         machine_state: {
//           type: 'string',
//           title: 'Machine Status',
//           description: 'Current status of the machine (Online_Idle, Run, Online_Error, Online_Maintenance, Setup, Testing)',
//           enum: [
//             'Testing'
//           ]
//         }
//       }
//     };
//     const expectedNodeShape = {
//       targetClass: 'targetClass',
//       _properties: [
//         {
//           mincount: 0,
//           maxcount: 1,
//           nodeKind: 'shacl:Literal',
//           path: 'sym:machine_state',
//           constraints: [
//             {
//               type: 'shacl:in',
//               params: [
//                 'Testing']
//             }],
//           isProperty: true
//         }
//       ]
//     };
//     const nodeShape = new ToTest.NodeShape('targetClass');
//     scanProperties(nodeShape, typeSchema);
//     nodeShape.should.deep.equal(expectedNodeShape);
//   });
//   it('Should scan with relationship', function () {
//     const scanProperties = ToTest.__get__('scanProperties');
//     const typeSchema = {
//       properties: {
//         hasFilter: {
//           relationship: 'eclass:0173-1#01-ACK991#016',
//           $ref: 'https://industry-fusion.org/base-objects/v0.1/link'
//         }
//       }
//     };
//     const expectedNodeShape = {
//       targetClass: 'targetClass',
//       _properties: [
//         {
//           mincount: 0,
//           maxcount: 1,
//           nodeKind: 'shacl:IRI',
//           path: 'sym:hasFilter',
//           constraints: [
//             {
//               type: 'shacl:class',
//               params: 'sym:eclass:0173-1#01-ACK991#016'
//             }
//           ],
//           isProperty: false
//         }]
//     };
//     const nodeShape = new ToTest.NodeShape('targetClass');
//     scanProperties(nodeShape, typeSchema);
//     nodeShape.should.deep.equal(expectedNodeShape);
//   });
//   it('Should scan with allOf', function () {
//     const scanProperties = ToTest.__get__('scanProperties');
//     const typeSchema = {
//       allOf: [
//         {
//           properties: {
//             machine_state: {
//               type: 'string',
//               title: 'Machine Status',
//               description: 'Current status of the machine (Online_Idle, Run, Online_Error, Online_Maintenance, Setup, Testing)',
//               enum: [
//                 'Setup',
//                 'Testing'
//               ]
//             }
//           }
//         }
//       ]
//     };
//     const expectedNodeShape = {
//       targetClass: 'targetClass',
//       _properties: [
//         {
//           mincount: 0,
//           maxcount: 1,
//           nodeKind: 'shacl:Literal',
//           path: 'sym:machine_state',
//           constraints: [
//             {
//               type: 'shacl:in',
//               params:
//           [
//             'Setup',
//             'Testing'
//           ]
//             }
//           ],
//           isProperty: true
//         }
//       ]
//     };
//     const nodeShape = new ToTest.NodeShape('targetClass');
//     scanProperties(nodeShape, typeSchema);
//     nodeShape.should.deep.equal(expectedNodeShape);
//   });
// });
// describe('Test scanConstraints', function () {
//   it('Should dump without properties', function () {
//     const scanConstraints = ToTest.__get__('scanConstraints');
//     const propertyShape = new ToTest.PropertyShape(0, 2, 'nodeKind', 'path', true);
//     const typeSchema = {
//       type: 'string',
//       title: 'Machine Status',
//       description: 'Current status of the machine (Online_Idle, Run, Online_Error, Online_Maintenance, Setup, Testing)',
//       enum: [
//         'Online_Idle'
//       ],
//       maximum: 2,
//       minimum: 1,
//       exclusiveMinimum: 0,
//       exclusiveMaximum: 3,
//       maxLength: 100,
//       minLength: 10
//     };
//     const expectedConstraints = [
//       { type: 'shacl:in', params: ['Online_Idle'] },
//       { type: 'shacl:maxInclusive', params: 2 },
//       { type: 'shacl:minInclusive', params: 1 },
//       { type: 'shacl:minExclusive', params: 0 },
//       { type: 'shacl:maxExclusive', params: 3 },
//       { type: 'shacl:maxLength', params: 100 },
//       { type: 'shacl:minLength', params: 10 }
//     ];
//     scanConstraints(propertyShape, typeSchema);
//     propertyShape.constraints.should.deep.equal(expectedConstraints);
//   });
// });
// describe('Test encodeHash', function () {
//   it('Should uri-encode hash', function () {
//     const encodeHash = ToTest.__get__('encodeHash');
//     const result = encodeHash('https://example.com/test#1#2#3');
//     result.should.equal('https://example.com/test%231%232%233');
//   });
// });
// describe('Test loadContext', function () {
//   it('Should resolve https uri', async function () {
//     const loadContext = ToTest.__get__('loadContext');
//     const context = {
//       getContextRaw: () => {
//         return {
//           '@vocab': 'https://industry-fusion.org/base/v0.1/',
//           eclass: {
//             '@id': 'https://industry-fusion.org/eclass#',
//             '@prefix': true
//           },
//           xsd: {
//             '@id': 'http://www.w3.org/2001/XMLSchema#',
//             '@prefix': true
//           },
//           iffb: {
//             '@id': 'https://industry-fusion.org/base/v0.1/',
//             '@prefix': true
//           }
//         };
//       }
//     };
//     const myParser = {
//       parse: async (x) => { return context; }
//     };
//     const expectedResult = {
//       eclass: 'https://industry-fusion.org/eclass#',
//       xsd: 'http://www.w3.org/2001/XMLSchema#',
//       iffb: 'https://industry-fusion.org/base/v0.1/'
//     };
//     const revert = ToTest.__set__('myParser', myParser);
//     await loadContext('https://example.com/context');
//     const globalPrefixHash = ToTest.__get__('globalPrefixHash');
//     globalPrefixHash.should.deep.equal(expectedResult);
//     revert();
//   });
// });
