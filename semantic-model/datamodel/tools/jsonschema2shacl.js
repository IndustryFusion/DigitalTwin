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

const $RefParser = require('json-schema-ref-parser')
const $rdf = require('rdflib')
const fs = require('fs')
const yargs = require('yargs')
// const N3 = require('n3')
const url = require('url')
// const { DataFactory } = N3
// const { namedNode, literal, blankNode, defaultGraph, quad } = DataFactory
// const { URL } = require('url')
const ContextParser = require('jsonld-context-parser').ContextParser
const ContextUtil = require('jsonld-context-parser').Util
const myParser = new ContextParser()

const RDF = $rdf.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#')
const SHACL = $rdf.Namespace('http://www.w3.org/ns/shacl#')
const IFFK = $rdf.Namespace('https://industry-fusion.org/knowledge/v0.1/')
const argv = yargs
  .command('$0', 'Converting an IFF Schema file for NGSI-LD objects into a SHACL constraint.')
  .option('schema', {
    alias: 's',
    description: 'Schema File containing array of Schemas',
    demandOption: true,
    type: 'string'
  })
  .option('schemaid', {
    alias: 'i',
    description: 'Schma-id of object to generate SHACL for',
    demandOption: true,
    type: 'string'
  })
  .option('context', {
    alias: 'c',
    description: 'JSON-LD-Context',
    demandOption: true,
    type: 'string'
  })
  .help()
  .alias('help', 'h')
  .argv

// Read in an array of JSON-Schemas
const jsonSchemaText = fs.readFileSync(argv.s, 'utf8')
const jsonSchema = JSON.parse(jsonSchemaText)
let globalContext
let globalPrefixHash

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

function scanNodeShape (typeschema) {
  const id = typeschema.$id

  const nodeShape = new NodeShape(id)
  scanProperties(nodeShape, typeschema)
  return nodeShape
}

function scanProperties (nodeShape, typeschema) {
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
      scanProperties(nodeShape, elem)
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

function dumpShacl (nodeShape, store) {
  dumpNodeShape(nodeShape, store)
}

function dumpNodeShape (nodeShape, store) {
  const nodeName = decodeURIComponent(globalContext.expandTerm(nodeShape.targetClass))
  const parsedUrl = new url.URL(nodeName)
  const fragment = parsedUrl.hash.substring(1)
  const shapeName = fragment + 'Shape'
  store.add(IFFK(shapeName), RDF('type'), SHACL('NodeShape'))
  store.add(IFFK(shapeName), SHACL('targetClass'), $rdf.sym(nodeName))
  nodeShape.properties.forEach((property) => {
    const propNode = $rdf.blankNode()
    property.propertyNode = propNode
    store.add(IFFK(shapeName), SHACL('property'), propNode)
    dumpPropertyShape(property, store)
  })
}

function dumpPropertyShape (propertyShape, store) {
  const propNode = propertyShape.propertyNode
  store.add(propNode, SHACL('minCount'), propertyShape.mincount)
  store.add(propNode, SHACL('maxCount'), propertyShape.maxcount)
  store.add(propNode, SHACL('nodeKind'), SHACL('BlankNode'))
  store.add(propNode, SHACL('path'), propertyShape.path)
  const attributeNode = $rdf.blankNode()
  store.add(propNode, SHACL('property'), attributeNode)
  const ngsildPrefix = globalPrefixHash['ngsi-ld']
  const NGSILD = $rdf.Namespace(ngsildPrefix)
  if (propertyShape.isProperty) {
    store.add(attributeNode, SHACL('path'), NGSILD('hasValue'))
  } else {
    store.add(attributeNode, SHACL('path'), NGSILD('hasObject'))
  }
  store.add(attributeNode, SHACL('minCount'), 1)
  store.add(attributeNode, SHACL('maxCount'), 1)
  store.add(attributeNode, SHACL('nodeKind'), propertyShape.nodeKind)
  const constraints = propertyShape.constraints
  constraints.forEach((constraint) => {
    store.add(attributeNode, constraint.type, constraint.params)
  })
}

function encodeHash (id) {
  const url = new URL(id)
  const hash = encodeURIComponent(url.hash)
  return `${url.protocol}//${url.hostname}${url.pathname}${hash}`
}

function shaclize (schemas, id) {
  id = encodeHash(id)
  const store = new $rdf.IndexedFormula()
  const typeschema = schemas.find((schema) => schema.$id === id)
  const nodeShape = scanNodeShape(typeschema)
  dumpShacl(nodeShape, store)
  const serializer = new $rdf.Serializer(store)
  serializer.setFlags('u')
  serializer.setNamespaces(globalPrefixHash)
  const turtle = serializer.statementsToN3(store.statementsMatching(undefined, undefined, undefined, undefined))
  console.log(turtle)
}

async function loadContext (uriOrContext) {
  const parseUrl = new url.URL(uriOrContext)
  if (parseUrl.protocol === 'file:') {
    uriOrContext = JSON.parse(fs.readFileSync(parseUrl.pathname, 'utf-8'))
  }
  const context = await myParser.parse(uriOrContext)
  globalContext = context
  const prefixHash = {}
  Object.keys(context.getContextRaw()).filter((key) => key !== '@vocab').forEach((key) => {
    const value = context.getContextRaw()[key]
    if (typeof value === 'string') {
      if (ContextUtil.isPrefixIriEndingWithGenDelim(value)) {
        prefixHash[key] = value
      }
    } else if (typeof value === 'object') {
      if (ContextUtil.isPrefixIriEndingWithGenDelim(value['@id'])) {
        prefixHash[key] = value['@id']
      }
    }
  })
  globalPrefixHash = prefixHash
}

(async (jsconSchema) => {
  const myResolver = {
    order: 1,

    canRead: function (file) {
      return true
    },

    read: function (file, callback, $refs) {
      return jsonSchema.find((schema) => schema.$id === file.url)
    }
  }
  const options = {
    resolve: {
      file: false,
      http: false,
      test: myResolver
    }
  }
  try {
    const schema = await $RefParser.dereference(jsonSchema, options)
    return schema
  } catch (err) {
    console.error(err)
  }
})(jsonSchema)
  .then(async (schema) => {
    await loadContext(argv.c)
    return schema
  })
  .then(schema => {
    shaclize(schema, argv.i)
  })
