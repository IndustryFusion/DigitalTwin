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

'use strict';

// The SPARQL workbench running a query that walks a chain of NGSI-LD
// relationships, on a case of several machines alike. With rdflib's fixed
// join order the chain was a cross product and the run took minutes; the
// order is picked while evaluated now (semforge/sparql/order.py).

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const { WORKSPACE, PACKAGE_URI, semforge, until } = require('./helpers');

const EX = 'http://example.org/';
const CUTTER = 'https://industryfusion.github.io/contexts/example/v0/base_entities/Cutter';
const SHAPE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape';
const CORE = 'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.6.jsonld';
const HAS = (p) => `<${EX}${p}>`;
const OBJ = '<https://uri.etsi.org/ngsi-ld/hasObject>';
const VAL = '<https://uri.etsi.org/ngsi-ld/hasValue>';
const CHAIN = `SELECT $this ?a ?b ?c ?d WHERE {
  $this ${HAS('hasBlock')} [${OBJ} ?mb].
  ?mb ${HAS('hasItem')} [${OBJ} ?mi].
  ?mb ${HAS('hasMode')} [${OBJ} ?mo].
  ?mi ${HAS('state')} [${VAL} ?a].
  ?mo ${HAS('state')} [${VAL} ?b].
  $this ?r1 [${OBJ} ?s1].
  ?s1 ?r2 [${OBJ} ?s2].
  ?s2 ${HAS('hasBlock')} [${OBJ} ?sb].
  ?sb ${HAS('hasItem')} [${OBJ} ?si].
  ?sb ${HAS('hasMode')} [${OBJ} ?so].
  ?si ${HAS('state')} [${VAL} ?c].
  ?so ${HAS('state')} [${VAL} ?d].
}`;

/** Seven cutters, each with a block and 6 x 2 parts that have blocks too. */
function entities() {
  const out = [];
  const rel = (object, datasetId) => Object.assign({ type: 'Relationship', object },
    datasetId ? { datasetId } : {});
  const blocked = (node) => {
    out.push({ id: `${node}:block`, type: `${EX}Block`,
      [`${EX}hasItem`]: rel(`${node}:item`), [`${EX}hasMode`]: rel(`${node}:mode`) },
    { id: `${node}:item`, type: `${EX}Item`, [`${EX}state`]: { type: 'Property', value: 'Executing' } },
    { id: `${node}:mode`, type: `${EX}Mode`, [`${EX}state`]: { type: 'Property', value: 'Processing' } });
    return rel(`${node}:block`);
  };
  for (const name of ['m', 'other0', 'other1', 'other2', 'other3', 'other4', 'other5']) {
    const root = `urn:ex:${name}`;
    const parts = [];
    for (let i = 0; i < 6; i += 1) {
      const sub = `${root}:sub${i}`;
      const grands = [0, 1].map((j) => {
        out.push({ id: `${sub}:part${j}`, type: `${EX}Part`, [`${EX}hasBlock`]: blocked(`${sub}:part${j}`) });
        return rel(`${sub}:part${j}`, `urn:ds:${j}`);
      });
      out.push({ id: sub, type: `${EX}Part`, [`${EX}hasPart`]: grands });
      parts.push(rel(sub, `urn:ds:${i}`));
    }
    out.push({ id: root, type: CUTTER, [`${EX}hasBlock`]: blocked(root), [`${EX}hasPart`]: parts });
  }
  return out.map((e) => Object.assign(e, { '@context': CORE }));
}

describe('The SPARQL workbench on a chain of relationships', () => {
  it('answers in seconds, not minutes', async () => {
    const api = await semforge();
    const folder = path.join(WORKSPACE, 'examples', 'test_ChainE2E');
    const file = path.join(folder, 'good', 'chain.jsonld');
    try {
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, JSON.stringify(entities(), null, 1));
      fs.writeFileSync(path.join(path.dirname(file), 'expectations.yaml'),
        'examples:\n  - path: chain.jsonld\n    expect: valid\n');
      const client = await until(() => api.clientHolder.client, 'the language client');
      const started = Date.now();
      const answer = await client.sendRequest('semforge/sparqlRun', {
        uri: PACKAGE_URI, shape: SHAPE, index: 0, source: file, query: CHAIN });
      const took = Date.now() - started;
      assert.ok(answer.ok, answer.error);
      assert.strictEqual(answer.focusCount, 7, 'seven cutters');
      const mine = answer.focus.find((f) => f.node.endsWith('urn:ex:m') || f.node === 'urn:ex:m');
      assert.ok(mine, JSON.stringify(answer.focus.map((f) => f.node)));
      assert.strictEqual(mine.rows.length, 12, 'one row per part two relationships down');
      assert.ok(took < 30000, `took ${took} ms`);
    } finally {
      fs.rmSync(folder, { recursive: true, force: true });
    }
  });
});
