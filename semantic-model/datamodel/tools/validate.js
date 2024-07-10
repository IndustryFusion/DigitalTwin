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

const fs = require('fs');
const url = require('url');
const Ajv = require('ajv/dist/2020');
const yargs = require('yargs');

const removedKeywords = [
  'anyOf', 'oneOf', 'if', 'then', 'else', 'prefixItems', 'items',
  'valid', 'error', 'annotation', 'additionalProperties', 'propertyNames',
  '$vocabulary', '$defs', 'multipleOf', 'uniqueItems', 'maxContains',
  'minContains', 'maxProperties', 'minPropeties', 'dependentRequired'];
const addedKeywords = ['relationship', 'relationship_type', 'datatype', 'unit'];

const argv = yargs
  .command('$0', 'Validate a concise NGSI-LD object with IFF Schema.')
  .option('schema', {
    alias: 's',
    description: 'Schema File',
    demandOption: true,
    type: 'string'
  })
  .option('datafile', {
    alias: 'd',
    description: 'File to validate. "-" reads from stdin',
    demandOption: false,
    type: 'string',
    default: '-'
  })
  .option('schemaid', {
    alias: 'i',
    description: 'Schema-id to validate',
    demandOption: true,
    type: 'string'
  })
  .help()
  .alias('help', 'h')
  .argv;

const ajv = new Ajv({
  strict: true,
  strictTypes: true,
  strictSchema: true,
  strictTuples: false,
  allErrors: true
});

const schema = fs.readFileSync(argv.s, 'utf8');
const parsedSchema = JSON.parse(schema);

ajv.addSchema(parsedSchema);

// This special processing is needed to allow ECLASS integration with
// URL. ECLASS uses IRDI which makes a lot of use of '#' which is
// incompatible with $id definition of JSON-Schema. Workaround
// is to use URL-encoding

const id = new url.URL(argv.i);
let idFragment = '';
let idPath = '';
if (id.hash !== null) {
  idFragment = encodeURIComponent(id.hash);
}
if (id.pathname !== null) {
  idPath = id.pathname;
}
const idUrl = id.protocol + '//' + id.host + idPath + idFragment;

function readDataFile (dataFile, callback) {
  if (dataFile === '-') {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => {
      data += chunk;
    });
    process.stdin.on('end', () => {
      callback(null, data);
    });
    process.stdin.on('error', err => {
      callback(err);
    });
  } else {
    fs.readFile(dataFile, 'utf8', callback);
  }
}

readDataFile(argv.d, (err, data) => {
  if (err) {
    console.error('Error reading data file:', err.message);
    process.exit(1);
  }

  const jsonData = JSON.parse(data);

  // Remove all non-supported and add all proprietary keywords.
  removedKeywords.forEach(kw => ajv.removeKeyword(kw));
  addedKeywords.forEach(kw => ajv.addKeyword({ keyword: kw }));

  if (ajv.validate(idUrl, jsonData)) {
    console.log('The Datafile is compliant with Schema');
  } else {
    console.log('Not Compliant:');
    console.log(ajv.errors);
  }
});
