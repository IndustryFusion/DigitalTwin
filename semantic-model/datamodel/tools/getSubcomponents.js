/**
* Copyright (c) 2024 Intel Corporation
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
const yargs = require('yargs');
const { QueryEngine } = require('@comunica/query-sparql-rdfjs');
const N3 = require('n3');
const { DataFactory } = N3;
const { namedNode } = DataFactory;
const http = require('http');
const https = require('https');
const jsonld = require('jsonld');

const myEngine = new QueryEngine();
const subids = [];

const argv = yargs
  .command('$0', 'Creating list of subcomponents of objects.')
  .positional('root-id', {
    describe: 'ID of the object',
    type: 'string'
  })
  .positional('broker-url', {
    describe: 'URL of NGSI-LD broker',
    type: 'string',
    default: 'http://ngsild.local/ngsi-ld'
  })
  .option('entities', {
    alias: 'e',
    description: 'Entity Files containing description of attributes',
    type: 'array'
  })
  .option('shacl', {
    alias: 's',
    description: 'SHACL File for the object model',
    type: 'array'
  })
  .option('token', {
    alias: 't',
    description: 'Token for rest call',
    demandOption: true,
    type: 'string'
  })
  .help()
  .alias('help', 'h')
  .argv;

function namespace (baseIRI) {
  return (suffix) => namedNode(baseIRI + suffix);
}
const NGSILD = namespace('https://uri.etsi.org/ngsi-ld/');

// Read in all the entity files
const ontstore = new N3.Store();

const loadOntologies = async (ont) => {
  if (ont && ont.length > 0) {
    for (const entity of ont) {
      const parser = new N3.Parser();
      const ttlContent = fs.readFileSync(entity, 'utf8');
      parser.parse(ttlContent, (error, quad) => {
        if (quad) {
          ontstore.addQuad(quad);
        } else if (error) {
          console.error('Parsing error:', error);
        }
      });
    }
  }
};

const getNgsildObject = function (id, brokerUrl, token) {
  const fullurl = brokerUrl + `/v1/entities/${id}`;
  const parsedUrl = new URL(fullurl);
  return new Promise((resolve, reject) => {
    const options = {
      hostname: parsedUrl.hostname,
      port: parsedUrl.port,
      path: parsedUrl.pathname + parsedUrl.search,
      method: 'GET',
      rejectUnauthorized: false,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/ld+json'
      }
    };

    const protocol = parsedUrl.protocol === 'https:' ? https : http;
    const req = protocol.get(options, (res) => {
      let data = '';

      if (res.statusCode !== 200) {
        console.error(`Request failed with status code: ${res.statusCode} and message: ${res.statusMessage}`);
        res.resume();
        reject(new Error(res.statusMessage));
        return;
      }

      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        try {
          const parsedData = JSON.parse(data);
          resolve(parsedData);
        } catch (e) {
          reject(e);
        }
      });

      res.on('error', (err) => {
        console.error('Request error: ', err.message);
        reject(err);
      });
    });

    req.on('error', (err) => {
      console.error('Request error: ', err.message);
      reject(err);
    });
  });
};

const analyseNgsildObject = async (id, brokerUrl, token) => {
  let result;
  try {
    result = await getNgsildObject(id, brokerUrl, token);
  } catch (e) {
    console.error(`Could not retrieve id=${id} Error: ${e.message}`);
    return;
  }

  const store = new N3.Store();
  try {
    const expanded = await jsonld.expand(result);
    const quads = await jsonld.toRDF(expanded, { format: 'application/n-quads' });
    const parser = new N3.Parser();
    parser.parse(quads, (error, quad) => {
      if (quad) {
        store.addQuad(quad);
      } else if (error) {
        console.error('Parsing error:', error);
      }
    });
  } catch (error) {
    console.error('Error processing JSON-LD:', error);
    return;
  }

  const quadsFromEntitiesStore = ontstore.getQuads(null, null, null, null);
  store.addQuads(quadsFromEntitiesStore);

  const bindingsStream = await myEngine.queryBindings(`
  PREFIX base: <https://industryfusion.github.io/contexts/ontology/v0/base/>
  PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>
  PREFIX sh: <http://www.w3.org/ns/shacl#>
  SELECT ?id ?type ?attribute
    WHERE {
     ?id a ?type .
     ?id ?attribute ?blank .
     ?blank a ngsild:Relationship .
     ?shape a sh:NodeShape .
     ?shape sh:property ?property .
     ?property sh:path ?attribute .
     ?property a base:SubComponentRelationship .
    }`,
  { sources: [store] }
  );

  const bindings = await bindingsStream.toArray();
  for (const binding of bindings) {
    const s = binding.get('attribute').value;
    const triples = store.getQuads(null, s, null, null);
    for (const quad of triples) {
      const ngsildObjects = store.getQuads(quad.object, NGSILD('hasObject'), null, null);
      for (const ngsildObject of ngsildObjects) {
        const subId = ngsildObject.object.value;
        if (!subids.includes(subId)) {
          subids.push(subId);
          await analyseNgsildObject(subId, brokerUrl, token);
        }
      }
    }
  }
};

(async () => {
  const ontologies = argv.entities;
  const shacls = argv.shacl;
  for (const shacl of shacls) {
    ontologies.push(shacl);
  }
  await loadOntologies(ontologies);
  await analyseNgsildObject(argv._[0], argv['broker-url'], argv.token);

  let cmdlineargs = '';
  subids.forEach((id) => {
    cmdlineargs += ` -d ${id}`;
  });
  console.log(cmdlineargs);
})();
