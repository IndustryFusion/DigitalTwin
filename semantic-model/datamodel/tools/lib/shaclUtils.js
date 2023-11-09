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
const $rdf = require('rdflib')
const ContextParser = require('jsonld-context-parser').ContextParser
const ContextUtil = require('jsonld-context-parser').Util

const RDF = $rdf.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')
const SHACL = $rdf.Namespace('http://www.w3.org/ns/shacl#')
const IFFK = $rdf.Namespace('https://industry-fusion.org/knowledge/v0.1/')

class NodeShape {
  constructor (targetClass) {
    this.targetClass = targetClass
    this.properties = []
  }

  addPropertyShape (propertyShape) {
    this.properties.push(propertyShape)
  }

  get properties () {
    return this._properties
  }

  set properties (prop) {
    this._properties = prop
  }
}

class PropertyShape {
  constructor (mincount, maxcount, nodeKind, path, isProperty) {
    this.mincount = mincount
    this.maxcount = maxcount
    this.nodeKind = nodeKind
    this.path = path
    this.constraints = []
    this.isProperty = isProperty
  }

  addConstraint (constraint) {
    this.constraints.push(constraint)
  }

  set propertyNode (node) {
    this._propertyNode = node
  }

  get propertyNode () {
    return this._propertyNode
  }
}

class Constraint {
  constructor (type, params) {
    this.type = type
    this.params = params
  }
}

function scanNodeShape (typeschema, globalContext) {
  const id = typeschema.$id

  const nodeShape = new NodeShape(id)
  scanProperties(nodeShape, typeschema, globalContext)
  return nodeShape
}

function scanProperties (nodeShape, typeschema, globalContext) {
  let required = []
  if ('required' in typeschema) {
    required = typeschema.required
  }
  if ('properties' in typeschema) {
    Object.keys(typeschema.properties).forEach(
      (property) => {
        if (property === 'type' || property === 'id') {
          return
        }
        let nodeKind = SHACL('Literal')
        let klass = null
        let isProperty = true
        if ('relationship' in typeschema.properties[property]) {
          nodeKind = SHACL('IRI')
          klass = typeschema.properties[property].relationship
          klass = globalContext.expandTerm(klass, true)
          isProperty = false
        }
        let mincount = 0
        const maxcount = 1
        if (required.includes(property)) {
          mincount = 1
        }
        let path = property
        if (!ContextUtil.isValidIri(path)) {
          path = globalContext.expandTerm(path, true)
        }
        const propertyShape = new PropertyShape(mincount, maxcount, nodeKind, $rdf.sym(path), isProperty)
        nodeShape.addPropertyShape(propertyShape)
        if (klass !== null) {
          propertyShape.addConstraint(new Constraint(SHACL('class'), $rdf.sym(klass)))
        }
        scanConstraints(propertyShape, typeschema.properties[property])
      })
  }
  if ('allOf' in typeschema) {
    typeschema.allOf.forEach((elem) => {
      scanProperties(nodeShape, elem, globalContext)
    })
  }
}

function scanConstraints (propertyShape, typeschema) {
  if ('enum' in typeschema) {
    propertyShape.addConstraint(new Constraint(SHACL('in'), typeschema.enum))
  }
  if ('datatype' in typeschema) {
    // datatype constraints are not used actively. It is not testing the value but only checks if the formal
    // datatype "tag" conforms
    // propertyShape.addConstraint(new Constraint(SHACL('datatype'), typeschema.datatype))
  }
  if ('maxiumum' in typeschema) {
    propertyShape.addConstraint(new Constraint(SHACL('maxInclusive'), typeschema.maximum))
  }
  if ('miniumum' in typeschema) {
    propertyShape.addConstraint(new Constraint(SHACL('minInclusive'), typeschema.minimum))
  }
  if ('exclusiveMiniumum' in typeschema) {
    propertyShape.addConstraint(new Constraint(SHACL('minExclusive'), typeschema.exclusiveMinimum))
  }
  if ('exclusiveMaxiumum' in typeschema) {
    propertyShape.addConstraint(new Constraint(SHACL('maxExclusive'), typeschema.exclusiveMaximum))
  }
  if ('maxLength' in typeschema) {
    propertyShape.addConstraint(new Constraint(SHACL('maxLength'), typeschema.maxLength))
  }
  if ('minLength' in typeschema) {
    propertyShape.addConstraint(new Constraint(SHACL('minLength'), typeschema.minLength))
  }
}

module.exports = {
  NodeShape,
  PropertyShape,
  Constraint,
  scanNodeShape
}
