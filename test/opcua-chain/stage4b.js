/**
* Copyright (c) 2026 IndustryFusion Foundation
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

// The real updates bridge code against the real context broker. Keycloak is the only part replaced.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const Module = require('module');
const { toUpdate } = require('./core_services_format.js');
const { literalValue } = require('./literal.js');

const OUT = process.env.OUT;
const A = 'http://127.0.0.1:19090/ngsi-ld/v1';
const P = 'http://opcfoundation.org/UA/Pumps/';
const b64 = b => Buffer.from(b).toString('base64url');
const now = Math.floor(Date.now() / 1000);
const claims = {
  sub: 'chain-test',
  preferred_username: 'bridge',
  iat: now,
  exp: now + 3600,
  azp: 'ngsild-updates',
  aud: ['account'],
  realm_access: { roles: ['Factory-Admin', 'Factory-Writer'] }
};
const unsigned = `${b64(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))}.${b64(JSON.stringify(claims))}`;
const signature = crypto.sign('RSA-SHA256', Buffer.from(unsigned), fs.readFileSync(`${OUT}/key.pem`));
const TOKEN = `${unsigned}.${b64(signature)}`;

// The bridge gets its token from Keycloak, so it gets the self-signed one instead
const load = Module._load;
Module._load = function (request, ...rest) {
  if (request === 'keycloak-connect') {
    return function () { this.grantManager = { obtainFromClientCredentials: async () => ({ access_token: { token: TOKEN } }) }; };
  }
  return load.call(this, request, ...rest);
};
const NgsildUpdates = require(path.resolve('KafkaBridge/lib/ngsildUpdates.js'));
const config = {
  ngsildServer: { hostname: '127.0.0.1', port: '19090', protocol: 'http:' },
  logger: { loglevel: 'error' },
  ngsildUpdates: { clientSecretVariable: 'NONE', refreshIntervalInSeconds: 200 },
  bridgeCommon: { kafkaSyncOnAttribute: 'https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn', hashLength: 24 },
  keycloak: { ngsildUpdatesAuthService: {} }
};

const headers = { Authorization: `Bearer ${TOKEN}` };
const get = async id => (await fetch(`${A}/entities/${encodeURIComponent(id)}`, { headers: { ...headers, Accept: 'application/json' } })).json();
function check (ok, text) { console.log(`${ok ? 'ok  ' : 'FAIL'} ${text}`); if (!ok) { throw new Error(text); } }
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const instances = fs.readFileSync('semantic-model/opcua/instances.jsonld');
  const loaded = await fetch(`${A}/entityOperations/upsert`, {
    method: 'POST', headers: { ...headers, 'Content-Type': 'application/ld+json' }, body: instances
  });
  check(loaded.status === 201, `the 21 entities of stage 1 load: ${loaded.status}`);
  await sleep(2000);

  const bridge = new NgsildUpdates(config);
  await sleep(300);
  const attributes = fs.readFileSync(`${OUT}/attributes.jsonl`, 'utf8').split('\n').filter(Boolean).map(JSON.parse);
  for (const a of attributes) await bridge.ngsildUpdates(toUpdate(a), Date.now());
  console.log(`${attributes.length} updates through the updates bridge`);
  await sleep(2000);

  const by = {};
  for (const a of attributes) by[a.name.replace(P, '')] = a.entityId;
  const read = async n => (await get(by[n]))[P + n];
  // Declared doubles come back as value objects (contracts/typed-literals, D6).
  const value = async n => literalValue((await read(n)).value);
  check(await value('hasMotorTemperature') === 42.5, 'a number is a JSON number, the value after the recovery');
  check(await value('hasNumberOfStarts') === 17, 'a UInt32 is a JSON number');
  check(await value('hasRotorBlocked') === true, 'a boolean is a JSON boolean');
  check(await value('hasTechnicalDataLink') === 'with "quotes"', 'a string with quotes is unchanged');
  check(JSON.stringify(await value('hasInstallationDate')).includes('2025-07-14T08:30:00'), 'a timestamp is ISO 8601');
  const pumpClass = JSON.stringify(await value('hasPumpClass'));
  check(pumpClass.includes('PositiveDisplacementPump') && !pumpClass.includes('@value'), 'an enum is the IRI, with no leftover number');
  const modes = await read('hasOfferedControlModes');
  check(modes.type === 'JsonProperty' && JSON.stringify(modes.json).includes('AQA='), 'a structure is a JsonProperty');
  check((await read('hasMotorTemperature')).observedAt !== undefined, 'observedAt is set');

  // A declared double merged into an existing entity (contracts/typed-literals, #967): the broker's merge refuses
  // it, so the bridge has to write it another way, and it comes back with its type.
  const DOUBLE = 'http://www.w3.org/2001/XMLSchema#double';
  const declared = { type: 'Property', value: { '@value': 80, '@type': DOUBLE }, observedAt: new Date().toISOString(), datasetId: '@none' };
  await bridge.ngsildUpdates({
    op: 'update',
    overwriteOrReplace: true,
    noForward: true,
    entities: JSON.stringify([{ id: by.hasMotorTemperature, [P + 'hasMotorTemperature']: [declared] }])
  }, Date.now());
  await sleep(1000);
  const typed = (await read('hasMotorTemperature')).value;
  check(literalValue(typed) === 80 && typed !== null && (typed.type || typed['@type']) === DOUBLE,
    `a declared double through the updates bridge comes back with its type: ${JSON.stringify(typed)}`);

  console.log('--- what the broker refuses and accepts (contracts/context-broker)');
  const merge = async (id, attr) => fetch(`${A}/entityOperations/merge`, {
    method: 'POST',
    headers: {
      ...headers,
      'Content-Type': 'application/json',
      Link: '<https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld>; rel="http://www.w3.org/ns/json-ld#context"'
    },
    body: JSON.stringify([{ id, ...attr }])
  });
  const onto = await merge(by.hasOfferedControlModes, { [P + 'hasOfferedControlModes']: [{ type: 'Property', value: 'x' }] });
  check(onto.status === 400 && (await onto.text()).includes('SB001'), 'a Property merged onto a JsonProperty: 400 SB001');
  // The pinned broker carries the fork's patch for merging value objects (IndustryFusion/ScorpioBroker#8), which
  // removes the 22023 of #967 (contracts/context-broker, accepted deviation A1): merges of value objects succeed.
  const iri = await merge(by.hasPumpClass, { [P + 'hasPumpClass']: [{ type: 'Property', value: { '@id': P + 'LiquidPump' } }] });
  check(iri.status === 204, `an IRI value in a batch merge: 204 (${iri.status})`);
  const value80 = { [P + 'hasMotorTemperature']: [{ type: 'Property', value: { '@value': 80, '@type': DOUBLE } }] };
  const batch = await merge(by.hasMotorTemperature, value80);
  check(batch.status === 204, `a declared value in a batch merge: 204 (${batch.status})`);
  const patch = await fetch(`${A}/entities/${encodeURIComponent(by.hasMotorTemperature)}`, {
    method: 'PATCH', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(value80)
  });
  check(patch.status === 204, `a declared value in a merge entity: 204 (${patch.status})`);
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
