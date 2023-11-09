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
const fs = require('fs')
const yargs = require('yargs')
const ShaclUtils = require('./lib/shaclUtils')

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
const jsonSchema = JSON.parse(jsonSchemaText);

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
    await ShaclUtils.loadContext(argv.c)
    return schema
  })
  .then(schema => {
    ShaclUtils.shaclize(schema, argv.i)
  })
