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
