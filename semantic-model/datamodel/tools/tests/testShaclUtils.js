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
'use strict'

const { assert } = require('chai')
const chai = require('chai')
global.should = chai.should()

const rewire = require('rewire')
const ToTest = rewire('../lib/shaclUtils.js')

describe('Test class NodeShape', function () {
  it('Should manage properties', function () {
    const nodeShape = new ToTest.NodeShape('targetClass')
    nodeShape.properties = 'property'
    const properties = nodeShape.properties
    properties.should.deep.equal('property')
    const nodeShape2 = new ToTest.NodeShape('targetClass')
    nodeShape2.properties = ['property1']
    nodeShape2.addPropertyShape('propertyShape')
    nodeShape2.addPropertyShape('propertyShape2')
    const properties2 = nodeShape2.properties
    properties2.should.deep.equal(['property1', 'propertyShape', 'propertyShape2'])
  })
})
describe('Test class PropertyShape', function () {
  it('Should manage properties', function () {
    const propertyShape = new ToTest.PropertyShape(0, 1, 'nodeKind', 'path', true)
    propertyShape.addConstraint('property')
    propertyShape.addConstraint('property2')
    const constraints = propertyShape.constraints
    constraints.should.deep.equal(['property', 'property2'])
    propertyShape.mincount.should.equal(0)
    propertyShape.maxcount.should.equal(1)
    propertyShape.nodeKind.should.equal('nodeKind')
    propertyShape.path.should.equal('path')
    propertyShape.isProperty.should.equal(true)
    propertyShape.propertyNode = 'node'
    propertyShape.propertyNode.should.equal('node')
  })
})
describe('Test class Constraint', function () {
  it('Should construct', function () {
    const constraint = new ToTest.Constraint('type', 'param')
    constraint.type.should.equal('type')
    constraint.params.should.equal('param')
  })
})
describe('Test dumpPropertyShape', function () {
  it('Should dump property without constraints', function () {
    const propertyShape = new ToTest.PropertyShape(1, 2, 'nodeKind', 'path', true)
    propertyShape.propertyNode = 'propertyNode'
    const storeAdds = []
    const store = {
      add: (s, p, o) => { storeAdds.push([s, p, o]) }
    }
    const $rdf = {
      blankNode: () => { return {} },
      Namespace: () => (x) => 'ngsild:' + x
    }
    const SHACL = (x) => 'shacl:' + x
    const revert = ToTest.__set__('$rdf', $rdf)
    ToTest.__set__('SHACL', SHACL)
    ToTest.__set__('globalPrefixHash', { 'ngsi-ld': 'ngsi-ld' })
    const dumpPropertyShape = ToTest.__get__('dumpPropertyShape')
    dumpPropertyShape(propertyShape, store)
    storeAdds.should.deep.equal([
      ['propertyNode', 'shacl:minCount', 1],
      ['propertyNode', 'shacl:maxCount', 2],
      ['propertyNode', 'shacl:nodeKind', 'shacl:BlankNode'],
      ['propertyNode', 'shacl:path', 'path'],
      ['propertyNode', 'shacl:property', {}],
      [{}, 'shacl:path', 'ngsild:hasValue'],
      [{}, 'shacl:minCount', 1],
      [{}, 'shacl:maxCount', 1],
      [{}, 'shacl:nodeKind', 'nodeKind']])
    revert()
  })
  it('Should dump property with constraints', function () {
    const propertyShape = new ToTest.PropertyShape(0, 2, 'nodeKind', 'path', true)
    propertyShape.propertyNode = 'propertyNode'
    propertyShape.addConstraint(new ToTest.Constraint('type', 'params'))
    propertyShape.addConstraint(new ToTest.Constraint('type2', ['p1', 'p2']))
    const storeAdds = []
    const store = {
      add: (s, p, o) => { storeAdds.push([s, p, o]) }
    }
    const $rdf = {
      blankNode: () => { return {} },
      Namespace: () => (x) => 'ngsild:' + x
    }
    const SHACL = (x) => 'shacl:' + x
    const revert = ToTest.__set__('$rdf', $rdf)
    ToTest.__set__('SHACL', SHACL)
    ToTest.__set__('globalPrefixHash', { 'ngsi-ld': 'ngsi-ld' })
    const dumpPropertyShape = ToTest.__get__('dumpPropertyShape')
    dumpPropertyShape(propertyShape, store)
    storeAdds.should.deep.equal([
      ['propertyNode', 'shacl:minCount', 0],
      ['propertyNode', 'shacl:maxCount', 2],
      ['propertyNode', 'shacl:nodeKind', 'shacl:BlankNode'],
      ['propertyNode', 'shacl:path', 'path'],
      ['propertyNode', 'shacl:property', {}],
      [{}, 'shacl:path', 'ngsild:hasValue'],
      [{}, 'shacl:minCount', 1],
      [{}, 'shacl:maxCount', 1],
      [{}, 'shacl:nodeKind', 'nodeKind'],
      [{}, 'type', 'params'],
      [{}, 'type2', ['p1', 'p2']]])
    revert()
  })
  it('Should dump relationship without constraints', function () {
    const propertyShape = new ToTest.PropertyShape(1, 1, 'nodeKind', 'relationship', false)
    propertyShape.propertyNode = 'propertyNode'
    const storeAdds = []
    const store = {
      add: (s, p, o) => { storeAdds.push([s, p, o]) }
    }
    const $rdf = {
      blankNode: () => { return {} },
      Namespace: () => (x) => 'ngsild:' + x
    }
    const SHACL = (x) => 'shacl:' + x
    const revert = ToTest.__set__('$rdf', $rdf)
    ToTest.__set__('SHACL', SHACL)
    ToTest.__set__('globalPrefixHash', { 'ngsi-ld': 'ngsi-ld' })
    const dumpPropertyShape = ToTest.__get__('dumpPropertyShape')
    dumpPropertyShape(propertyShape, store)
    storeAdds.should.deep.equal([
      ['propertyNode', 'shacl:minCount', 1],
      ['propertyNode', 'shacl:maxCount', 1],
      ['propertyNode', 'shacl:nodeKind', 'shacl:BlankNode'],
      ['propertyNode', 'shacl:path', 'relationship'],
      ['propertyNode', 'shacl:property', {}],
      [{}, 'shacl:path', 'ngsild:hasObject'],
      [{}, 'shacl:minCount', 1],
      [{}, 'shacl:maxCount', 1],
      [{}, 'shacl:nodeKind', 'nodeKind']])
    revert()
  })
})
describe('Test dumpNodeShape', function () {
  it('Should dump without properties', function () {
    const nodeShape = new ToTest.NodeShape('http://example.com/targetClass')
    const storeAdds = []
    const store = {
      add: (s, p, o) => { storeAdds.push([s, p, o]) }
    }
    const $rdf = {
      blankNode: () => { return {} },
      sym: (x) => 'sym:' + x
    }
    const globalContext = {
      expandTerm: (x) => x
    }
    const revert = ToTest.__set__('SHACL', (x) => 'shacl:' + x)
    ToTest.__set__('IFFK', (x) => 'iffk:' + x)
    ToTest.__set__('RDF', (x) => 'rdf:' + x)
    ToTest.__set__('globalContext', globalContext)
    ToTest.__set__('$rdf', $rdf)
    const dumpNodeShape = ToTest.__get__('dumpNodeShape')
    dumpNodeShape(nodeShape, store)
    storeAdds.should.deep.equal([
      ['iffk:targetClassShape', 'rdf:type', 'shacl:NodeShape'],
      ['iffk:targetClassShape', 'shacl:targetClass', 'sym:http://example.com/targetClass']
    ])
    revert()
  })
  it('Should dump relationship with properties', function () {
    const nodeShape = new ToTest.NodeShape('http://example.com/targetClass')
    const propertyShape = new ToTest.PropertyShape(0, 2, 'nodeKind', 'path', true)
    nodeShape.addPropertyShape(propertyShape)
    const storeAdds = []
    const store = {
      add: (s, p, o) => { storeAdds.push([s, p, o]) }
    }
    const $rdf = {
      blankNode: () => { return {} },
      sym: (x) => 'sym:' + x
    }
    const globalContext = {
      expandTerm: (x) => x
    }
    const dumpPropertyShape = (x, y) => { x.propertyNode.should.deep.equal({}) }
    const revert = ToTest.__set__('SHACL', (x) => 'shacl:' + x)
    ToTest.__set__('IFFK', (x) => 'iffk:' + x)
    ToTest.__set__('RDF', (x) => 'rdf:' + x)
    ToTest.__set__('globalContext', globalContext)
    ToTest.__set__('dumpPropertyShape', dumpPropertyShape)
    ToTest.__set__('$rdf', $rdf)
    const dumpNodeShape = ToTest.__get__('dumpNodeShape')
    dumpNodeShape(nodeShape, store)
    storeAdds.should.deep.equal([
      ['iffk:targetClassShape', 'rdf:type', 'shacl:NodeShape'],
      ['iffk:targetClassShape', 'shacl:targetClass', 'sym:http://example.com/targetClass'],
      ['iffk:targetClassShape', 'shacl:property', {}]
    ])
    revert()
  })
})
