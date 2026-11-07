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

// The agent's schema and the bridge's real mapper, fed with the messages the dataservice really sent.
// MQTT itself is replaced: the message goes straight from the agent's schema to the bridge's mapping.
'use strict';
const fs = require('fs');
const path = require('path');
const { validateSchema } = require(path.resolve('NgsildAgent/lib/schema-validator.js'));
const dataSchema = require(path.resolve('NgsildAgent/lib/schemas/data.json'));
const mapper = require(path.resolve('KafkaBridge/mqttBridge/spb_ngsild_mapper.js'));

const OUT = process.env.OUT;
const MESSAGES = process.env.MESSAGES || `${OUT}/messages.jsonl`;
const FN = {
  Property: mapper.mapSpbPropertyToKafka,
  LiteralProperty: mapper.mapSpbPropertyToKafka,
  IriProperty: mapper.mapSpbPropertyIriToKafka,
  JsonProperty: mapper.mapSpbPropertyJsonToKafka,
  Relationship: mapper.mapSpbRelationshipToKafka
};
const ingestion = fs.readFileSync('KafkaBridge/mqttBridge/sparkplug_data_ingestion.js', 'utf8');
function check (ok, text) { console.log(`${ok ? 'ok  ' : 'FAIL'} ${text}`); if (!ok) { process.exit(1); } }

const validate = validateSchema(dataSchema);
const last = new Map();
const lines = fs.readFileSync(MESSAGES, 'utf8').split('\n').filter(Boolean);
for (const line of lines) {
  const m = JSON.parse(line);
  delete m._at;
  const errors = validate(m);
  if (errors) { check(false, `the agent's schema accepts ${JSON.stringify(m)}: ${JSON.stringify(errors)}`); }
  last.set(`${m.i} ${m.n}`, m);
}
check(lines.length > 0, `the agent's schema accepts all ${lines.length} messages`);
const labels = new Set([...last.values()].map(m => m.t));
for (const t of labels) {
  check(FN[t] !== undefined && ingestion.includes(`metricType === '${t}'`), `the bridge maps and ingests label ${t}`);
}
const out = [...last.values()].map(m => FN[m.t](m.i, { name: `${m.t}/${m.n}`, value: m.v, timestamp: Date.now() }));
for (const [t, nodeType] of [['Property', '@value'], ['IriProperty', '@id'], ['JsonProperty', '@json']]) {
  const found = out.find(a => a.nodeType === nodeType);
  check(found !== undefined, `${t} -> nodeType ${nodeType}`);
}
fs.writeFileSync(`${OUT}/attributes.jsonl`, out.map(a => JSON.stringify(a)).join('\n') + '\n');
console.log(`ok   ${out.length} attributes mapped`);
