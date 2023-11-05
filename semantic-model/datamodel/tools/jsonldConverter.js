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

const fs = require('fs')
const yargs = require('yargs')
const jsonld = require('jsonld')
const jsonldUtils = require('./lib/jsonldUtils')
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
    const mergedContexts = jsonldUtils.mergeContexts(jsonArr, argv.c)
    if (mergedContexts !== undefined && mergedContexts.find(x => x === null)) {
      console.error('Error: For Compaction, context must be either defined in all objects or externally. Exiting!')
      process.exit(1)
    }
    // Compaction to find Properties in compacted form
    const expanded = await expand(jsonArr, mergedContexts)
    const concised = jsonldUtils.conciseExpandedForm(expanded)
    const compacted = await compact(concised, mergedContexts)
    console.log(JSON.stringify(compacted, null, 2))
  }
  if (!(argv.x === undefined)) {
    const mergedContexts = jsonldUtils.mergeContexts(jsonArr, argv.c)
    if (mergedContexts !== undefined && mergedContexts.find(x => x === null)) {
      console.error('Error: For Extraction, context must be either defined in all objects or externally. Exiting!')
      process.exit(1)
    }
    const expanded = await expand(jsonArr, mergedContexts)
    console.log(JSON.stringify(expanded, null, 2))
  }
  if (!(argv.r === undefined)) {
    const mergedContexts = jsonldUtils.mergeContexts(jsonArr, argv.c)
    if (mergedContexts !== undefined && mergedContexts.find(x => x === null)) {
      console.error('Error: For Normalization, context must be either defined in all objects or externally. Exiting!')
      process.exit(1)
    }
    const expanded = await expand(jsonArr, mergedContexts)
    const normalized = jsonldUtils.normalizeExpandedForm(expanded)
    const compacted = await compact(normalized, mergedContexts)
    console.log(JSON.stringify(compacted, null, 2))
  }
})(jsonArr)
