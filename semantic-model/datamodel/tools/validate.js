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
const url = require('url')
const Ajv = require('ajv/dist/2020')
const yargs = require('yargs')

const removedKeywords = [
  'anyOf', 'oneOf', 'if', 'then', 'else', 'prefixItems', 'items',
  'valid', 'error', 'annotation', 'additionalProperties', 'propertyNames',
  '$vocabulary', '$defs', 'multipleOf', 'uniqueItems', 'maxContains',
  'minContains', 'maxProperties', 'minPropeties', 'dependentRequired']
const addedKeywords = ['relationship']

const argv = yargs
  .option('schema', {
    alias: 's',
    description: 'Schema File',
    demandOption: true,
    type: 'string'
  })
  .option('datafile', {
    alias: 'd',
    description: 'File to validate',
    demandOption: true,
    type: 'string'
  })
  .option('schemaid', {
    alias: 'i',
    description: 'Schema-id to validate',
    demandOption: true,
    type: 'string'
  })
  .help()
  .alias('help', 'h')
  .argv

const ajv = new Ajv({
  strict: true,
  strictTypes: true,
  strictSchema: true,
  strictTuples: false
})

const schema = fs.readFileSync(argv.s, 'utf8')
const parsedSchema = JSON.parse(schema)

ajv.addSchema(parsedSchema)

// This special processing is needed to allow ECLASS integration with
// URL. ECLASS uses IRDI which makes a lot of use of '#' which is
// incompatible with $id definition of JSON-Schema. Workaround
// is to use URL-encoding

const id = url.URL(argv.i)
let idFragment = ''
let idPath = ''
if (id.hash !== null) {
  idFragment = encodeURIComponent(id.hash)
}
if (id.path !== null) {
  idPath = id.path
}
const idUrl = id.protocol + '//' + id.host + idPath + idFragment

const data = JSON.parse(fs.readFileSync(argv.d, 'utf8'))

// Remove all non supported and add all proprietary keywords.
removedKeywords.forEach(kw => ajv.removeKeyword(kw))
addedKeywords.forEach(kw => ajv.addKeyword({ keyword: kw }))

if (ajv.validate(idUrl, data)) {
  console.log('The Datafile is compliant with Schema')
} else {
  console.log('Not Compliant:')
  console.log(ajv.errors)
};
