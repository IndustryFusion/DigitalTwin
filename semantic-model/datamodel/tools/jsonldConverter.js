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

// const $RefParser = require('json-schema-ref-parser');
// const $rdf = require('rdflib')
const fs = require('fs')
const yargs = require('yargs')
// const path = require('path')
// const N3 = require('n3')
const url = require('url')
// const { DataFactory } = N3
// const { namedNode, literal, blankNode, defaultGraph, quad } = DataFactory;
// const { URL } = require('url'); // Import the URL module
// const ContextParser = require('jsonld-context-parser').ContextParser
// const ContextUtil = require('jsonld-context-parser').Util;
// const myParser = new ContextParser()
const jsonld = require('jsonld')
// const exp = require('constants');

// const RDF = $rdf.Namespace('http://www.w3.org/1999/02/22-rdf-syntax-ns#');
// const SHACL = $rdf.Namespace('http://www.w3.org/ns/shacl#');
// const IFFK = $rdf.Namespace('https://industry-fusion.org/knowledge/v0.1/');
let jsonFileName
const argv = yargs
  .option('concise', {
    alias: 'n',
    description: 'Create concise/compacted from',
    demandOption: false,
    type: 'boolean'
  })
  .option('expand', {
    alias: 'x',
    description: 'Create expanded from',
    demandOption: false,
    type: 'boolean'
  })
  .option('normalize', {
    alias: 'r',
    description: 'Create normalized from',
    demandOption: false,
    type: 'boolean'
  })
  .option('context', {
    alias: 'c',
    description: 'JSON-LD-Context',
    demandOption: false,
    type: 'string'
  })
  .command({
    command: '$0 <filename>',
    describe: 'Convert a JSON-LD file into different normal forms.',
    handler: (argv) => {
      const { filename } = argv
      jsonFileName = filename
    }
  })
  .help()
  .alias('help', 'h')
  .argv

const jsonText = fs.readFileSync(jsonFileName, 'utf8')
const jsonObj = JSON.parse(jsonText)
let jsonArr

if (!(argv.x === undefined) && !(argv.n === undefined)) {
  console.error('Expand and Concise are mutally exclusive. Bye!')
  process.exit(1)
}
if (!(argv.r === undefined) && !(argv.n === undefined)) {
  console.error('Normalized and Concise are mutally exclusive. Bye!')
  process.exit(1)
}
if (!(argv.x === undefined) && !(argv.r === undefined)) {
  console.error('Normalized and Expanded are mutally exclusive. Bye!')
  process.exit(1)
}
if (argv.x === undefined && argv.r === undefined && argv.n === undefined) {
  console.error('No processing switch selected. Bye!')
  process.exit(1)
}

if (!Array.isArray(jsonObj)) {
  jsonArr = [jsonObj]
} else {
  jsonArr = jsonObj
}

function loadContextFromFile (fileName) {
  const context = fs.readFileSync(fileName, 'utf8')
  const contextParsed = JSON.parse(context)
  return contextParsed
}

// Merge Contexts
function mergeContexts (jsonArr, context) {
  function mergeContext (localContext, context) {
    let mergedContext = []
    if (!Array.isArray(localContext) && localContext !== undefined) {
      mergedContext = [localContext]
    }
    if (context === undefined) {
      if (mergedContext.length === 0) {
        return null
      }
      return mergedContext
    } else if (!Array.isArray(context)) {
      context = [context]
    }
    context.forEach(c => {
      if (typeof (c) !== 'string' || mergedContext.find(x => c === x) === undefined) {
        mergedContext.push(c)
      }
    })
    return mergedContext
  }
  if (context !== undefined) {
    const parseContextUrl = new url.URL(context)
    if (parseContextUrl.protocol === 'file:') {
      context = loadContextFromFile(parseContextUrl.pathname)
    }
  }
  return jsonArr.map(jsonObj => {
    const localContext = jsonObj['@context']
    return mergeContext(localContext, context)
  })
}

function conciseExpandedForm (expanded) {
  function filterAttribute (attr) {
    if (typeof (attr) === 'object') {
      if ('@type' in attr && (attr['@type'][0] === 'https://uri.etsi.org/ngsi-ld/Property' ||
                                    attr['@type'][0] === 'https://uri.etsi.org/ngsi-ld/Relationship')) {
        delete attr['@type']
      }
      if ('https://uri.etsi.org/ngsi-ld/hasValue' in attr) {
        attr['@value'] = attr['https://uri.etsi.org/ngsi-ld/hasValue'][0]['@value']
        delete attr['https://uri.etsi.org/ngsi-ld/hasValue']
      }
    }
  }
  expanded.forEach(c => {
    Object.keys(c).forEach(key => {
      if (Array.isArray(c[key])) {
        c[key].forEach(a => filterAttribute(a))
      } else {
        filterAttribute(c[key])
      }
    })
  })
  return expanded
}

function normalizeExpandedForm (expanded) {
  function extendAttribute (attr) {
    if (typeof (attr) === 'object') {
      if (!('@type' in attr)) {
        if ('https://uri.etsi.org/ngsi-ld/hasValue' in attr || '@value' in attr || '@id' in attr) {
          attr['@type'] = 'https://uri.etsi.org/ngsi-ld/Property'
        } else if ('https://uri.etsi.org/ngsi-ld/hasObject' in attr) {
          attr['@type'] = 'https://uri.etsi.org/ngsi-ld/Relationship'
        }
        if ('@value' in attr) {
          attr['https://uri.etsi.org/ngsi-ld/hasValue'] = attr['@value']
          delete attr['@value']
        } else if ('@id' in attr) {
          attr['https://uri.etsi.org/ngsi-ld/hasValue'] = { '@id': attr['@id'] }
          delete attr['@id']
        }
      }
    }
  }
  expanded.forEach(c => {
    Object.keys(c).forEach(key => {
      if (Array.isArray(c[key])) {
        c[key].forEach(a => extendAttribute(a))
      } else {
        extendAttribute(c[key])
      }
    })
  })
  return expanded
}

async function expand (objArr, contextArr) {
  const expanded = await Promise.all(objArr.map(async (jsonObj, index) => {
    jsonObj['@context'] = contextArr[index]
    const res = await jsonld.expand(jsonObj)
    return res[0]
  }))
  return expanded
}

async function compact (objArr, contextArr) {
  return await Promise.all(objArr.map(async (jsonObj, index) => jsonld.compact(jsonObj, contextArr[index])))
}

(async (jsonArr) => {
  if (!(argv.n === undefined)) {
    const mergedContexts = mergeContexts(jsonArr, argv.c)
    if (mergedContexts !== undefined && mergedContexts.find(x => x === null)) {
      console.error('Error: For Compaction, context must be either defined in all objects or externally. Exiting!')
      process.exit(1)
    }
    // Compaction to find Properties in compacted form
    const expanded = await expand(jsonArr, mergedContexts)
    const concised = conciseExpandedForm(expanded)
    const compacted = await compact(concised, mergedContexts)
    console.log(JSON.stringify(compacted, null, 2))
  }
  if (!(argv.x === undefined)) {
    const mergedContexts = mergeContexts(jsonArr, argv.c)
    if (mergedContexts !== undefined && mergedContexts.find(x => x === null)) {
      console.error('Error: For Extraction, context must be either defined in all objects or externally. Exiting!')
      process.exit(1)
    }
    const expanded = await expand(jsonArr, mergedContexts)
    console.log(JSON.stringify(expanded, null, 2))
  }
  if (!(argv.r === undefined)) {
    const mergedContexts = mergeContexts(jsonArr, argv.c)
    if (mergedContexts !== undefined && mergedContexts.find(x => x === null)) {
      console.error('Error: For Normalization, context must be either defined in all objects or externally. Exiting!')
      process.exit(1)
    }
    const expanded = await expand(jsonArr, mergedContexts)
    const normalized = normalizeExpandedForm(expanded)
    const compacted = await compact(normalized, mergedContexts)
    console.log(JSON.stringify(compacted, null, 2))
  }
})(jsonArr)
