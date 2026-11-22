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

// The black-box contract test of openspec/specs/contracts/context-broker: one check per scenario that doesn't need
// Debezium, through the broker's API, its health checks and the notifications it sends only. A known deviation's check passes while the
// broker still shows the deviation, and fails once the broker meets the requirement, naming the workaround that can
// then be removed; one that a patch the platform carries removes passes on the standard's behaviour, and on the
// platform's build fails while it stands. Every other check passes only on the standard's behaviour. Started by
// run.sh, which provides the broker and a notification sink.
//
// Environment: BROKER (the broker's base URL), SINK (the sink as seen from here), SINK_IN (the sink as seen from the
// broker), MQTT (the MQTT server's container on the broker's network), KEY (PEM key that signs tokens), MODE (platform | upstream: no authorisation, its checks are skipped),
// PART (main | subattribute), OUT (directory for results.json).

const childProcess = require('child_process');
const crypto = require('crypto');
const fs = require('fs');

const BROKER = process.env.BROKER;
const A = `${BROKER}/ngsi-ld/v1`;
const SINK = process.env.SINK;
const SINK_IN = process.env.SINK_IN;
const MQTT = process.env.MQTT;
const MODE = process.env.MODE || 'platform';
const PART = process.env.PART || 'main';
const OUT = process.env.OUT || '.';
const RUN = Date.now().toString(36);
const X = 'http://example.org/contract/';
const NGSI = 'https://uri.etsi.org/ngsi-ld/';
const PROP = NGSI + 'Property';
const DOUBLE = 'http://www.w3.org/2001/XMLSchema#double';
const CORE = 'https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld';
const IFF_CONTEXT = 'https://industryfusion.github.io/contexts/staging/example/v0.2/context.jsonld';

const b64 = b => Buffer.from(b).toString('base64url');
const key = fs.readFileSync(process.env.KEY);
function token (claims) {
  const now = Math.floor(Date.now() / 1000);
  const body = Object.assign({ sub: 'contract-test', iat: now, exp: now + 3600, azp: 'scorpio', aud: ['account'] }, claims);
  const unsigned = `${b64(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))}.${b64(JSON.stringify(body))}`;
  return `${unsigned}.${b64(crypto.sign('RSA-SHA256', Buffer.from(unsigned), key))}`;
}
const TOKEN = {
  adminClient: token({ resource_access: { scorpio: { roles: ['Factory-Admin'] } } }),
  adminRealm: token({ realm_access: { roles: ['Factory-Admin'] } }),
  reader: token({ resource_access: { scorpio: { roles: ['Factory-Reader'] } } }),
  noRole: token({})
};
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function call (method, path, body, opts = {}) {
  const headers = { Accept: opts.accept || 'application/json' };
  if (opts.token !== null) headers.Authorization = `Bearer ${opts.token || TOKEN.adminClient}`;
  if (body !== undefined) headers['Content-Type'] = opts.ct || 'application/json';
  if (opts.link) headers.Link = `<${opts.link}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"`;
  const url = path.startsWith('http') ? path : A + path;
  const r = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await r.text();
  let json;
  try { json = text ? JSON.parse(text) : undefined; } catch (e) { json = undefined; }
  return { status: r.status, text, json };
}
const id = name => `urn:ctx:${RUN}:${name}`;
const get = async (eid, opts) => call('GET', `/entities/${encodeURIComponent(eid)}`, undefined, opts);
const create = async (entity, opts) => call('POST', '/entities', entity, opts);
const batchMerge = async entities => call('POST', '/entityOperations/merge', entities);
const mergeEntity = async (eid, fragment) => call('PATCH', `/entities/${encodeURIComponent(eid)}`, fragment);
const appendAttrs = async (eid, fragment) => call('POST', `/entities/${encodeURIComponent(eid)}/attrs`, fragment);
const del = async eid => call('DELETE', `/entities/${encodeURIComponent(eid)}`);
const instances = (entity, name) => {
  const a = entity && entity[name];
  return a === undefined ? [] : Array.isArray(a) ? a : [a];
};
const one = (entity, name) => instances(entity, name)[0];
// A value object as read with Accept: application/json, whatever the compaction
const valueOf = v => (v !== null && typeof v === 'object' && '@value' in v) ? v['@value'] : v;
const typeOf = v => (v !== null && typeof v === 'object') ? (v['@type'] || v.type) : undefined;
const iriOf = v => (v !== null && typeof v === 'object') ? (v['@id'] || v.id) : undefined;

// Refusals of a batch operation. NGSI-LD (CIM 009 clauses 6.31.3.1, 5.2.17) reports them in a 207 as
// errors[{entityId, error}], also when every entity is refused. The fork on 5.0.5 answered 400 then and named the
// members id and ProblemDetails; that form is still read, so that a check names what it got. Each refusal says
// whether its form is the standard's.
function refusals (r) {
  if (![400, 207].includes(r.status) || !r.json || !Array.isArray(r.json.errors)) return [];
  return r.json.errors.map(e => ({
    id: e.entityId || e.id,
    detail: (e.error && e.error.detail) || (e.ProblemDetails && e.ProblemDetails.detail) || '',
    type: (e.error && e.error.type) || (e.ProblemDetails && e.ProblemDetails.type) || '',
    standard: r.status === 207 && 'entityId' in e && 'error' in e
  }));
}
const refusalOf = (r, eid, detail) => refusals(r).find(f => f.id === eid && (!detail || String(f.detail).includes(detail)));
// Any form: for requirements about whether something is refused, not about the form of the answer
const refused = (r, eid, detail) => !!refusalOf(r, eid, detail);
const isType = (problem, type) => !!problem && String(problem.type || problem).endsWith(`/errors/${type}`);

const results = [];
let current;
function record (status, detail) {
  results.push({ requirement: current.requirement, scenario: current.scenario, status, detail });
  const tag = { ok: 'ok  ', deviation: 'dev ', fail: 'FAIL', skip: 'skip' }[status];
  console.log(`${tag} ${current.requirement} / ${current.scenario}${detail ? ' -- ' + detail : ''}`);
}
async function check (requirement, scenario, fn, opts = {}) {
  current = { requirement, scenario };
  if (opts.platformOnly && MODE !== 'platform') {
    return record('skip', typeof opts.platformOnly === 'string' ? opts.platformOnly : 'the upstream image has no authorisation');
  }
  try {
    const outcome = await fn();
    if (outcome === true || outcome === undefined) record('ok');
    else if (outcome && outcome.removed) record('ok', outcome.removed);
    else if (outcome && outcome.deviation) record('deviation', outcome.deviation);
    else record('fail', typeof outcome === 'string' ? outcome : JSON.stringify(outcome));
  } catch (e) {
    record('fail', e.message);
  }
}
// The outcome of a scenario with a registered deviation (design D9 of the change): the standard's behaviour fails
// the check, so that the workaround is removed; the deviation passes it; anything else fails. A deviation that a
// patch the platform carries removes (d.patch) passes on the standard's behaviour, since that patch is expected;
// in MODE=platform it fails while it stands, since the platform's build has to carry the patch. seen, if given,
// says what the broker answered when the deviation stands.
function deviation (d, target, stillThere, observed, seen) {
  const label = `${d.id} ${d.kind}: ${d.name} (${d.issue})`;
  const saw = seen ? `; saw ${seen}` : '';
  if (target && d.patch) return { removed: `${d.id} removed by ${d.patch}` };
  if (target) return `${label} is fixed: remove the workaround, ${d.workaround}`;
  if (stillThere && d.patch && MODE === 'platform') return `${label} stands: the platform's build lacks ${d.patch}${saw}`;
  if (stillThere) return { deviation: `${label} stands${saw}; workaround: ${d.workaround}` };
  return `neither the standard's behaviour nor ${d.id}: ${observed}`;
}
const DEV = {
  A1: { id: 'A1', kind: 'accepted', name: 'a merge of a typed value or language-tagged string fails with 22023', issue: '#967, CIM 009 3.1', workaround: 'the updates bridge writes such entities through /attrs (KafkaBridge/lib/ngsildUpdates.js)', patch: 'the fork patch for IndustryFusion/ScorpioBroker#8' },
  A2: { id: 'A2', kind: 'accepted', name: 'a batch merge with datasetId @none answers 404', issue: 'CIM 009 4.5.5', workaround: 'the updates bridge removes @none before merging (KafkaBridge/lib/ngsildUpdates.js)', patch: 'the fork patch for IndustryFusion/ScorpioBroker#11' },
  A3: { id: 'A3', kind: 'accepted', name: 'a batch merge of one entity with a null value answers 404, not 207, and a fully refused batch leaves success out', issue: 'CIM 009 6.31.3.1, 5.2.16', workaround: 'none needed once Core Services writes no null values (P2)', patch: 'the fork patch for IndustryFusion/ScorpioBroker#12' },
  A4: { id: 'A4', kind: 'accepted', name: 'a notification to an MQTT endpoint without receiverInfo is lost', issue: 'CIM 009 5.2.15', workaround: 'none; a subscriber would have to give receiverInfo', patch: 'the fork patch "Notify over MQTT without receiverInfo"' },
  A5: { id: 'A5', kind: 'accepted', name: 'an attribute instance with a datasetId and a sub-attribute array of instances is refused with 400', issue: 'CIM 009 4.5.2, 4.5.3, 4.5.5', workaround: 'none; such entities cannot be written', patch: 'the fork patch for IndustryFusion/ScorpioBroker#15' }
};

// The notification sink of run.sh: GET returns what it received, DELETE clears it
async function notified () { return (await fetch(SINK + '/')).json(); }
async function clearSink () { await fetch(SINK + '/', { method: 'DELETE' }); }
function notifiedIds (notes) {
  return new Set(notes.flatMap(n => (n && n.data) || []).map(e => e.id));
}
async function waitFor (ids, ms = 15000) {
  const t = Date.now();
  for (;;) {
    const got = notifiedIds(await notified());
    if (ids.every(i => got.has(i)) || Date.now() - t > ms) return got;
    await sleep(500);
  }
}
// The ids notified with the given value of an attribute: a late notification of an earlier change of the same
// entity doesn't count for this one
function notifiedWith (notes, attr, value) {
  return new Set(notes.flatMap(n => (n && n.data) || [])
    .filter(d => instances(d, attr).some(i => i.value === value)).map(d => d.id));
}
async function waitForValue (ids, attr, value, ms = 15000) {
  const t = Date.now();
  for (;;) {
    const got = notifiedWith(await notified(), attr, value);
    if (ids.every(i => got.has(i)) || Date.now() - t > ms) return got;
    await sleep(500);
  }
}
async function subscribe (type, subId) {
  const sub = {
    id: subId,
    type: 'Subscription',
    entities: [{ type }],
    notification: { endpoint: { uri: `${SINK_IN}/notify`, accept: 'application/json' } },
    '@context': CORE
  };
  const r = await call('POST', '/subscriptions', sub, { ct: 'application/ld+json' });
  if (r.status !== 201) throw new Error(`subscription not created: ${r.status} ${r.text}`);
  // A new subscription becomes active after a while; wait until an entity of its type is notified
  for (let i = 0; i < 60; i++) {
    const probe = id(`probe${i}`);
    await create({ id: probe, type, [X + 'p']: { type: 'Property', value: i } });
    const got = await waitFor([probe], 1500);
    if (got.has(probe)) { await clearSink(); return; }
  }
  throw new Error('the subscription never notified');
}
// The messages on a topic of the MQTT server of run.sh, read with mosquitto_sub inside its container. failed()
// says why the subscriber ended before stop(): a broken MQTT setup, not something the broker did
function mqttTopic (topic) {
  const sub = childProcess.spawn('docker', ['exec', MQTT, 'mosquitto_sub', '-t', topic], { stdio: ['ignore', 'pipe', 'inherit'] });
  let text = '';
  let failure;
  let stopped = false;
  sub.stdout.on('data', d => { text += d; });
  sub.on('error', e => { failure = failure || `the MQTT subscriber didn't start: ${e.message}`; });
  sub.on('exit', (code, signal) => {
    if (!stopped) failure = failure || `the MQTT subscriber (docker exec ${MQTT} mosquitto_sub) ended with ${code !== null ? 'exit code ' + code : signal}`;
  });
  return { text: () => text, failed: () => failure, stop: () => { stopped = true; sub.kill(); } };
}
async function mqttWithoutReceiverInfo () {
  const M = `http://example.org/contract/M${RUN}`;
  const topic = `contract/${RUN}`;
  const e = id('mqtt');
  const messages = mqttTopic(topic);
  try {
    await sleep(1000);
    if (messages.failed()) return messages.failed();
    const r0 = await create({ id: e, type: M, [X + 'a']: { type: 'Property', value: 0 } });
    if (r0.status !== 201) return `create answered ${r0.status} ${r0.text}`;
    const subId = id('sub-mqtt');
    const r = await call('POST', '/subscriptions', {
      id: subId,
      type: 'Subscription',
      entities: [{ type: M }],
      notification: { endpoint: { uri: `mqtt://${MQTT}:1883/${topic}`, accept: 'application/json' } },
      '@context': CORE
    }, { ct: 'application/ld+json' });
    if (r.status !== 201) return `subscription not created: ${r.status} ${r.text}`;
    // A new subscription becomes active after a while: change the entity until a change is notified, for 60 s
    let arrived = false;
    for (let v = 1; v <= 40 && !arrived && !messages.failed(); v++) {
      await mergeEntity(e, { [X + 'a']: { type: PROP, value: v } });
      await sleep(1500);
      arrived = messages.text().includes(e);
    }
    await call('DELETE', `/subscriptions/${encodeURIComponent(subId)}`);
    // Without a subscriber that ran to the end, a lost notification says nothing about the broker
    if (!arrived && messages.failed()) return messages.failed();
    return deviation(DEV.A4, arrived, !arrived, 'no notification', 'no notification on the topic in 60 s');
  } finally {
    messages.stop();
  }
}
async function liveness () {
  const r = await call('GET', `${BROKER}/q/health/live`, undefined, { token: null });
  return r.json && r.json.status;
}

async function main () {
  const T = 'http://example.org/contract/T';

  await check('Requests need a token with a platform role', 'No token', async () => {
    const r = await call('GET', '/types', undefined, { token: null });
    return r.status === 401 || `answered ${r.status}`;
  }, { platformOnly: true });
  await check('Requests need a token with a platform role', 'No platform role', async () => {
    const r = await call('GET', '/types', undefined, { token: TOKEN.noRole });
    return r.status === 403 || `answered ${r.status}`;
  }, { platformOnly: true });

  await check('Factory-Admin may do what the platform does', 'Administrator by client role or by realm role', async () => {
    for (const [name, tok] of [['client', TOKEN.adminClient], ['realm', TOKEN.adminRealm]]) {
      const e = id(`admin-${name}`);
      const steps = [
        ['create', await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 } }, { token: tok }), [201]],
        ['merge', await call('POST', '/entityOperations/merge', [{ id: e, [X + 'a']: [{ type: PROP, value: 2 }] }], { token: tok }), [204]],
        ['read', await get(e, { token: tok }), [200]],
        ['delete', await call('DELETE', `/entities/${encodeURIComponent(e)}`, undefined, { token: tok }), [204]]
      ];
      const bad = steps.find(([, r, ok]) => !ok.includes(r.status));
      if (bad) return `${name} role: ${bad[0]} answered ${bad[1].status}`;
    }
  }, { platformOnly: true });

  await check('Factory-Reader only reads', 'Reader', async () => {
    const read = await call('GET', '/types', undefined, { token: TOKEN.reader });
    const write = await create({ id: id('reader'), type: T, [X + 'a']: { type: 'Property', value: 1 } }, { token: TOKEN.reader });
    return (read.status === 200 && write.status === 403) || `read ${read.status}, create ${write.status}`;
  }, { platformOnly: true });

  await check("The broker runs with the platform's configuration", "Start with the chart's variables", async () => {
    const started = await call('GET', `${BROKER}/q/health/started`, undefined, { token: null });
    const live = await liveness();
    return (started.json && started.json.status === 'UP' && live === 'UP') || `started ${started.status} ${started.json && started.json.status}, live ${live}`;
  });
  await check("The broker runs with the platform's configuration", 'Without an identity provider', async () => {
    const r = await call('GET', '/types', undefined, { token: TOKEN.adminRealm });
    return r.status === 200 || `answered ${r.status}`;
  }, { platformOnly: true });
  await check("The broker runs with the platform's configuration", 'No history by default', async () => {
    const e = id('history');
    const c = await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 } });
    const m = await mergeEntity(e, { [X + 'a']: { type: 'Property', value: 2 } });
    if (c.status !== 201 || m.status !== 204) return `create ${c.status}, merge ${m.status} ${m.text.slice(0, 200)}`;
    // The temporal API answers 404 for an entity without recorded history (CIM 009 6.19.3.1). With recording on,
    // the build answers 200 with both instances within 2 s; 10 s without it is taken as "no history".
    for (let t = 0; t < 5; t++) {
      await sleep(2000);
      const h = await call('GET', `/temporal/entities/${encodeURIComponent(e)}`);
      if (h.status !== 404) return `the temporal API answered ${h.status}, not 404: ${h.text.slice(0, 300)}`;
    }
    return true;
  }, { platformOnly: 'upstream records entity history by default' });

  // Batch operation results (CIM 009 6.14.3.1, 6.31.3.1, 5.2.16, 5.2.17)
  await check('Batch operation results', 'Every entity succeeds', async () => {
    const [b1, b2] = [id('ok-1'), id('ok-2')];
    const c = await call('POST', '/entityOperations/create', [b1, b2].map(e => ({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 } })));
    const ids = Array.isArray(c.json) ? c.json : [];
    if (c.status !== 201 || !ids.includes(b1) || !ids.includes(b2)) return `batch create answered ${c.status} ${c.text}`;
    const m = await batchMerge([b1, b2].map(e => ({ id: e, [X + 'a']: [{ type: PROP, value: 2 }] })));
    return m.status === 204 || `batch merge answered ${m.status} ${m.text}`;
  });
  await check('Batch operation results', 'One entity of two refused', async () => {
    const ok = id('batch-ok');
    const no = id('batch-no');
    await create({ id: ok, type: T, [X + 'a']: { type: 'Property', value: 1 } });
    await create({ id: no, type: T, [X + 'j']: { type: 'JsonProperty', json: { a: 1 } } });
    const r = await batchMerge([{ id: ok, [X + 'a']: [{ type: PROP, value: 2 }] }, { id: no, [X + 'j']: [{ type: PROP, value: 1 }] }]);
    const merged = one((await get(ok)).json, X + 'a').value === 2;
    const f = refusalOf(r, no);
    const success = r.json && Array.isArray(r.json.success) && r.json.success.includes(ok);
    if (!merged || r.status !== 207 || !f || !success || refused(r, ok)) return `answered ${r.status} ${r.text}, other entity merged: ${merged}`;
    return f.standard || `the refusal isn't errors[{entityId, error}] in a 207 (CIM 009 5.2.17): ${r.text}`;
  });
  await check('Batch operation results', 'The only entity refused', async () => {
    const no = id('batch-only');
    await create({ id: no, type: T, [X + 'j']: { type: 'JsonProperty', json: { a: 1 } } });
    const r = await batchMerge([{ id: no, [X + 'j']: [{ type: PROP, value: 1 }] }]);
    const f = refusalOf(r, no);
    if (!f) return `the entity isn't named as refused: ${r.status} ${r.text}`;
    const noSuccess = Array.isArray(r.json.success) && r.json.success.length === 0;
    if (r.status === 207 && f.standard && noSuccess) return true;
    // Upstream 6.0.2 leaves success out (A3); the platform's build carries the patch, so there it is a failure
    if (r.status === 207 && f.standard && !('success' in r.json)) {
      return deviation(DEV.A3, false, true, r.text, `a 207 without success: ${r.text.slice(0, 200)}`);
    }
    return `answered ${r.status}, not a 207 naming the entity under errors with an empty success (CIM 009 6.31.3.1, 5.2.16): ${r.text}`;
  });

  // Merge keeps what it doesn't name (CIM 009 5.6.17, 5.6.20, 5.5.12)
  await check("Merge keeps what it doesn't name", 'Sub-attributes kept', async () => {
    const e = id('keep');
    await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1, unitCode: 'CEL', [X + 'sub']: { type: 'Property', value: 'kept' } } });
    const r = await batchMerge([{ id: e, [X + 'a']: [{ type: PROP, value: 2 }] }]);
    if (r.status !== 204) return `batch merge answered ${r.status} ${r.text}`;
    const a = one((await get(e)).json, X + 'a');
    return (a.value === 2 && a.unitCode === 'CEL' && one(a, X + 'sub') && one(a, X + 'sub').value === 'kept') || `read back ${JSON.stringify(a)}`;
  });
  await check("Merge keeps what it doesn't name", 'New attribute', async () => {
    const e = id('newattr');
    await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 } });
    const r = await batchMerge([{ id: e, [X + 'b']: [{ type: PROP, value: 2 }] }]);
    if (r.status !== 204) return `batch merge answered ${r.status} ${r.text}`;
    const g = (await get(e)).json;
    return (one(g, X + 'a').value === 1 && one(g, X + 'b').value === 2) || `read back ${JSON.stringify(g)}`;
  });
  await check("Merge keeps what it doesn't name", 'Relationship deleted', async () => {
    const e = id('reldel');
    await create({ id: e, type: T, [X + 'r']: { type: 'Relationship', object: 'urn:ctx:target:1' }, [X + 'a']: { type: 'Property', value: 1 } });
    const r = await mergeEntity(e, { [X + 'r']: { type: 'Relationship', object: 'urn:ngsi-ld:null' } });
    if (r.status !== 204) return `merge entity answered ${r.status} ${r.text}`;
    const g = (await get(e)).json;
    return (g[X + 'r'] === undefined && one(g, X + 'a').value === 1) || `read back ${JSON.stringify(g)}`;
  });

  // Typed and language-tagged values (CIM 009 3.1)
  const valueObjects = {
    [X + 'd']: { '@value': 82, '@type': DOUBLE },
    [X + 't']: { '@value': 'Pumpe', '@language': 'de' }
  };
  function valueObjectsBack (g) {
    const wrong = [];
    const d = one(g, X + 'd') && one(g, X + 'd').value;
    if (valueOf(d) !== 82 || typeOf(d) !== DOUBLE) wrong.push(`declared ${JSON.stringify(d)}`);
    const t = one(g, X + 't') && one(g, X + 't').value;
    if (!t || t['@value'] !== 'Pumpe' || t['@language'] !== 'de') wrong.push(`tagged ${JSON.stringify(t)}`);
    return wrong;
  }
  async function entityWithValueObjects (name) {
    const e = id(name);
    const r = await create({
      id: e,
      type: T,
      [X + 'd']: { type: 'Property', value: { '@value': 1.5, '@type': DOUBLE } },
      [X + 't']: { type: 'Property', value: { '@value': 'Kreisel', '@language': 'de' } }
    });
    if (r.status !== 201) throw new Error(`create answered ${r.status} ${r.text}`);
    return e;
  }
  await check('Merge of typed and language-tagged values', 'Typed and tagged values through a merge', async () => {
    const eb = await entityWithValueObjects('vo-batch');
    const em = await entityWithValueObjects('vo-entity');
    const batch = await batchMerge([Object.assign({ id: eb },
      Object.fromEntries(Object.entries(valueObjects).map(([k, v]) => [k, [{ type: PROP, value: v }]])))]);
    const entity = await mergeEntity(em, Object.fromEntries(Object.entries(valueObjects).map(([k, v]) => [k, { type: PROP, value: v }])));
    const batchOk = batch.status === 204 && valueObjectsBack((await get(eb)).json).length === 0;
    const entityOk = entity.status === 204 && valueObjectsBack((await get(em)).json).length === 0;
    const batchDev = refused(batch, eb, '22023');
    const entityDev = entity.status === 500 && entity.text.includes('22023');
    return deviation(DEV.A1, batchOk && entityOk, batchDev && entityDev,
      `batch merge ${batch.status} ${batch.text.slice(0, 200)}, merge entity ${entity.status} ${entity.text.slice(0, 200)}`);
  });

  // Append attributes and upsert (CIM 009 5.6.3, 5.6.8, 5.6.2)
  await check('Append attributes and upsert', 'Append with overwrite', async () => {
    const e = await entityWithValueObjects('attrs');
    const frag = Object.fromEntries(Object.entries(valueObjects).map(([k, v]) => [k, { type: 'Property', value: v }]));
    frag[X + 'n'] = { type: 'Property', value: 7 };
    const r = await appendAttrs(e, frag);
    if (r.status !== 204) return `/attrs answered ${r.status} ${r.text}`;
    const g = (await get(e)).json;
    const wrong = valueObjectsBack(g);
    if (!(one(g, X + 'n') && one(g, X + 'n').value === 7)) wrong.push('new attribute');
    return wrong.length === 0 || `read back differs: ${wrong.join('; ')}`;
  });
  await check('Append attributes and upsert', 'Upsert', async () => {
    const e = id('upsert');
    const r0 = await call('POST', '/entityOperations/upsert', [{ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 } }]);
    if (![201, 204].includes(r0.status)) return `first upsert answered ${r0.status}`;
    const r1 = await call('POST', '/entityOperations/upsert?options=update',
      [{ id: e, type: T, [X + 'a']: { type: 'Property', value: 2 }, [X + 'b']: { type: 'Property', value: 5 } }]);
    if (![201, 204].includes(r1.status)) return `upsert with options=update answered ${r1.status} ${r1.text}`;
    const g1 = (await get(e)).json;
    const a = one(g1, X + 'a') && one(g1, X + 'a').value;
    if (!(one(g1, X + 'b') && one(g1, X + 'b').value === 5)) return `options=update didn't add the new attribute: ${JSON.stringify(g1)}`;
    const r2 = await call('POST', '/entityOperations/upsert?options=replace', [{ id: e, type: T, [X + 'c']: { type: 'Property', value: 3 } }]);
    if (![201, 204].includes(r2.status)) return `upsert with options=replace answered ${r2.status} ${r2.text}`;
    const g2 = (await get(e)).json;
    if (!(g2[X + 'a'] === undefined && g2[X + 'b'] === undefined && one(g2, X + 'c') && one(g2, X + 'c').value === 3)) {
      return `after options=replace: ${JSON.stringify(g2)}`;
    }
    return a === 2 || `after options=update the existing attribute holds ${a}, not 2 (CIM 009 5.6.8, 5.6.2)`;
  });

  // Batch update without overwriting (CIM 009 6.16.3.1, 5.6.9, 5.6.3)
  const noOverwrite = async entities => call('POST', '/entityOperations/update?options=noOverwrite', entities);
  await check('Batch update without overwriting', 'Nothing new', async () => {
    const e = id('noow-same');
    await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 } });
    const r = await noOverwrite([{ id: e, type: T, [X + 'a']: { type: 'Property', value: 2 } }]);
    const kept = one((await get(e)).json, X + 'a').value === 1;
    if (!kept) return `the existing value was overwritten: ${r.status} ${r.text}`;
    return r.status === 204 || `answered ${r.status} ${r.text}, not 204 (CIM 009 6.16.3.1, 5.6.9)`;
  });
  await check('Batch update without overwriting', 'New attribute and new instance', async () => {
    const e = id('noow-new');
    const ds = id('noow-ds');
    await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1, datasetId: ds } });
    const r = await noOverwrite([{ id: e, type: T, [X + 'a']: { type: 'Property', value: 2 }, [X + 'b']: { type: 'Property', value: 3 } }]);
    if (r.status >= 300) return `answered ${r.status} ${r.text}`;
    const g = (await get(e)).json;
    const a = instances(g, X + 'a');
    const keptInstance = a.some(i => i.datasetId === ds && i.value === 1);
    const appendedDefault = a.some(i => !i.datasetId && i.value === 2);
    const newAttribute = one(g, X + 'b') && one(g, X + 'b').value === 3;
    if (!keptInstance || !newAttribute) return `read back ${JSON.stringify(g)}`;
    return appendedDefault || `the new default instance wasn't appended (CIM 009 5.6.3): read back ${JSON.stringify(g)}`;
  });

  // Value forms the broker stores (CIM 009 4.5.2, 4.5.3, 4.5.18, 4.5.20, 4.5.21, 4.5.24)
  await check('Value forms the broker stores', 'Every form', async () => {
    const e = id('forms');
    const r = await create({
      id: e,
      type: T,
      [X + 'n']: { type: 'Property', value: 42.5 },
      [X + 'b']: { type: 'Property', value: true },
      [X + 's']: { type: 'Property', value: 'say "hi"' },
      [X + 'd']: { type: 'Property', value: { '@value': 80, '@type': DOUBLE } },
      [X + 't']: { type: 'Property', value: { '@value': 'Pumpe', '@language': 'de' } },
      [X + 'r']: { type: 'Relationship', object: 'urn:ctx:target:1' },
      [X + 'j']: { type: 'JsonProperty', json: { a: 1, b: [2] } },
      [X + 'li']: { type: 'ListProperty', valueList: [3, 1, 2] },
      [X + 'g']: { type: 'GeoProperty', value: { type: 'Point', coordinates: [13.4, 52.5] } },
      [X + 'la']: { type: 'LanguageProperty', languageMap: { de: 'Pumpe', en: 'pump' } },
      [X + 'v']: { type: 'VocabProperty', vocab: 'http://example.org/contract/On' }
    });
    if (r.status !== 201) return `create answered ${r.status} ${r.text}`;
    const g = (await get(e)).json;
    const val = k => one(g, X + k) || {};
    const wrong = [];
    if (val('n').value !== 42.5) wrong.push('number');
    if (val('b').value !== true) wrong.push('boolean');
    if (val('s').value !== 'say "hi"') wrong.push('string');
    if (valueOf(val('d').value) !== 80 || typeOf(val('d').value) !== DOUBLE) wrong.push('typed value');
    if (!val('t').value || val('t').value['@language'] !== 'de') wrong.push('tagged string');
    if (String(val('r').object) !== 'urn:ctx:target:1') wrong.push('relationship');
    if (JSON.stringify(val('j').json) !== JSON.stringify({ a: 1, b: [2] })) wrong.push('json');
    if (JSON.stringify(val('li').valueList) !== JSON.stringify([3, 1, 2])) wrong.push('list');
    if (!val('g').value || JSON.stringify(val('g').value.coordinates) !== JSON.stringify([13.4, 52.5])) wrong.push('geo');
    if (!val('la').languageMap || val('la').languageMap.en !== 'pump') wrong.push('language map');
    if (val('v').vocab !== 'http://example.org/contract/On') wrong.push('vocabulary');
    return wrong.length === 0 || `read back differs: ${wrong.join(', ')}: ${JSON.stringify(g)}`;
  });
  await check('Value forms the broker stores', 'Plain values through a batch merge', async () => {
    const e = id('plain');
    const ds = id('ds');
    await create({
      id: e,
      type: T,
      [X + 'n']: { type: 'Property', value: 1, datasetId: ds },
      [X + 'j']: { type: 'JsonProperty', json: { a: 1 } },
      [X + 'l']: { type: 'ListProperty', valueList: [1, 2] },
      [X + 'r']: { type: 'Relationship', object: 'urn:ctx:target:1' }
    });
    const at = new Date().toISOString();
    const r = await batchMerge([{
      id: e,
      [X + 'n']: [{ type: PROP, value: 42.5, observedAt: at, datasetId: ds }],
      [X + 'j']: [{ type: NGSI + 'JsonProperty', json: { a: 2, b: [1] }, observedAt: at }],
      [X + 'l']: [{ type: NGSI + 'ListProperty', valueList: [3, 4, 5], observedAt: at }],
      [X + 'r']: [{ type: NGSI + 'Relationship', object: 'urn:ctx:target:2', observedAt: at }]
    }]);
    if (r.status !== 204) return `batch merge answered ${r.status} ${r.text}`;
    const g = (await get(e)).json;
    const wrong = [];
    if (one(g, X + 'n').value !== 42.5 || one(g, X + 'n').datasetId !== ds || !one(g, X + 'n').observedAt) wrong.push('number');
    if (JSON.stringify(one(g, X + 'j').json) !== JSON.stringify({ a: 2, b: [1] })) wrong.push('json');
    if (JSON.stringify(one(g, X + 'l').valueList) !== JSON.stringify([3, 4, 5])) wrong.push('list');
    if (String(one(g, X + 'r').object) !== 'urn:ctx:target:2') wrong.push('relationship');
    return wrong.length === 0 || `read back differs: ${wrong.join(', ')}`;
  });

  await check('Value forms the broker stores', 'Sub-attribute array on an instance with a datasetId', async () => {
    const e = id('subarray');
    const ds = id('subarray-ds');
    const sx = id('subarray-sx');
    const r = await call('POST', '/entityOperations/upsert', [{
      id: e,
      type: T,
      [X + 'a']: [{
        type: 'Property',
        value: 'A',
        datasetId: ds,
        [X + 'p']: [{ type: 'Property', value: 1 }, { type: 'Property', value: 2, datasetId: sx }]
      }]
    }]);
    const g = await get(e);
    const a = g.status === 200 ? one(g.json, X + 'a') : undefined;
    const p = a ? instances(a, X + 'p') : [];
    const stored = !!a && a.datasetId === ds && p.length === 2 && p.some(i => !i.datasetId && i.value === 1) &&
      p.some(i => i.datasetId === sx && i.value === 2);
    const refusedWith400 = (r.status === 400 || refused(r, e)) && g.status === 404;
    // Which refusal: a 400 of the request, or the entity refused inside a 207 (or a 400 naming it), in which form
    const f = refusalOf(r, e);
    const problem = f ? `${f.type} ${String(f.detail).slice(0, 120)}` : `${(r.json && r.json.type) || ''} ${(r.json && r.json.detail) || r.text.slice(0, 120)}`;
    const seen = f
      ? `the entity refused in a ${r.status}, ${f.standard ? 'as errors[{entityId, error}]' : 'not in the form errors[{entityId, error}]'}: ${problem}`
      : `a ${r.status} of the whole request: ${problem}`;
    return deviation(DEV.A5, [201, 204].includes(r.status) && stored, refusedWith400,
      `upsert ${r.status} ${r.text.slice(0, 200)}, read ${g.status} ${g.text.slice(0, 300)}`, seen);
  });

  // Declared types in the broker (CIM 009 5.5.12; contracts/typed-literals)
  const declaredEntity = id('declared');
  await check('Declared types in the broker', 'Declared value stored', async () => {
    const r = await call('POST', '/entityOperations/upsert', [{ id: declaredEntity, type: T, [X + 'd']: { type: 'Property', value: { '@value': 0, '@type': DOUBLE } } }]);
    if (![201, 204].includes(r.status)) return `upsert answered ${r.status} ${r.text}`;
    const v = one((await get(declaredEntity)).json, X + 'd').value;
    return (valueOf(v) === 0 && typeOf(v) === DOUBLE) || `read back ${JSON.stringify(v)}`;
  });
  await check('Declared types in the broker', 'Plain value merged onto a declared one', async () => {
    for (const plain of [42.5, '42.5']) {
      const r = await batchMerge([{ id: declaredEntity, [X + 'd']: [{ type: PROP, value: plain }] }]);
      if (r.status !== 204) return `batch merge of ${JSON.stringify(plain)} answered ${r.status} ${r.text}`;
      const v = one((await get(declaredEntity)).json, X + 'd').value;
      if (typeOf(v) !== DOUBLE || String(valueOf(v)) !== '42.5') return `after ${JSON.stringify(plain)}: ${JSON.stringify(v)}`;
    }
  });
  await check('Declared types in the broker', 'Plain value through /attrs', async () => {
    const r = await appendAttrs(declaredEntity, { [X + 'd']: { type: 'Property', value: 42.5 } });
    if (r.status !== 204) return `/attrs answered ${r.status} ${r.text}`;
    const v = one((await get(declaredEntity)).json, X + 'd').value;
    return v === 42.5 || `read back ${JSON.stringify(v)}`;
  });

  // Refusals the platform relies on (CIM 009 4.5.0, 4.5.5)
  await check('Refusals the platform relies on', 'Null value', async () => {
    const e = id('null');
    const other = id('null-other');
    await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 }, [X + 'b']: { type: 'Property', value: 2 } });
    await create({ id: other, type: T, [X + 'a']: { type: 'Property', value: 1 } });
    const m = await mergeEntity(e, { [X + 'a']: { type: PROP, value: null } });
    const b = await batchMerge([{ id: e, [X + 'b']: [{ type: PROP, value: null }] }, { id: other, [X + 'a']: [{ type: PROP, value: 2 }] }]);
    const g = (await get(e)).json;
    const unchanged = one(g, X + 'a').value === 1 && one(g, X + 'b').value === 2;
    const otherMerged = one((await get(other)).json, X + 'a').value === 2;
    const f = refusalOf(b, e);
    const ok = m.status === 400 && isType(m.json, 'BadRequestData') && f && isType(f.type, 'BadRequestData') && unchanged && otherMerged;
    return ok || `merge entity ${m.status} ${m.text.slice(0, 120)}, batch merge ${b.status} ${b.text.slice(0, 200)}, unchanged ${unchanged}, other merged ${otherMerged}`;
  });
  await check('Refusals the platform relies on', 'Null value in a batch of one', async () => {
    const e = id('null-one');
    await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 } });
    const r = await batchMerge([{ id: e, [X + 'a']: [{ type: PROP, value: null }] }]);
    const f = refusalOf(r, e);
    return deviation(DEV.A3, r.status === 207 && f && f.standard && isType(f.type, 'BadRequestData'), r.status === 404, `answered ${r.status} ${r.text}`,
      `${r.status} ${r.text.slice(0, 200)}`);
  });
  await check('Refusals the platform relies on', 'Malformed observedAt', async () => {
    const good = id('obs-good');
    const bad = id('obs-bad');
    const r = await call('POST', '/entityOperations/upsert', [
      { id: good, type: T, [X + 'a']: { type: 'Property', value: 1, observedAt: '2024-02-28T13:52:32.000Z' } },
      { id: bad, type: T, [X + 'a']: { type: 'Property', value: 1, observedAt: '2024-02-28 13:52:32.0' } }
    ]);
    const notCreated = (await get(bad)).status === 404;
    return (r.status === 207 && refused(r, bad) && notCreated) || `answered ${r.status} ${r.text.slice(0, 300)}, refused entity created: ${!notCreated}`;
  });
  await check('Refusals the platform relies on', 'Two default instances', async () => {
    const e = id('dup');
    const r = await call('POST', '/entityOperations/upsert', [{ id: e, type: T, [X + 'a']: [{ type: 'Property', value: 1 }, { type: 'Property', value: 2 }] }]);
    const g = await get(e);
    const both = g.status === 200 && instances(g.json, X + 'a').length === 2;
    return (refused(r, e) && g.status === 404) || `two default instances not refused (CIM 009 4.5.5): upsert ${r.status} ${r.text.slice(0, 200)}, read ${g.status}, both stored ${both}`;
  });
  await check('Refusals the platform relies on', "Id that isn't a URI", async () => {
    const r = await create({ id: `urn:ctx:${RUN}:with space`, type: T, [X + 'a']: { type: 'Property', value: 1 } });
    return (r.status === 400 && isType(r.json, 'BadRequestData')) || `answered ${r.status} ${r.text.slice(0, 200)}, not 400 BadRequestData (CIM 009 6.3)`;
  });

  // The broker's own refusals (not stated by CIM 009)
  await check("The broker's own refusals", 'Type change', async () => {
    const e = id('typechange');
    await create({ id: e, type: T, [X + 'j']: { type: 'JsonProperty', json: { a: 1 } } });
    const r = await batchMerge([{ id: e, [X + 'j']: [{ type: PROP, value: 1 }] }]);
    return refused(r, e, 'SB001') || `answered ${r.status} ${r.text}`;
  });

  // Default attribute instance (CIM 009 4.5.5)
  await check('Default attribute instance', 'Default dataset id', async () => {
    const e = id('none');
    await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 } });
    const r = await batchMerge([{ id: e, [X + 'a']: [{ type: PROP, value: 5, datasetId: '@none' }] }]);
    const g = (await get(e)).json;
    const merged = r.status === 204 && instances(g, X + 'a').length === 1 && one(g, X + 'a').value === 5;
    return deviation(DEV.A2, merged, r.status === 404, `answered ${r.status}, read back ${JSON.stringify(g)}`);
  });

  // Reads (CIM 009 6.3.6, 6.4, 6.5)
  await check('Reads', 'Read in both forms', async () => {
    const e = id('read');
    await create({ id: e, type: T, [X + 'a']: { type: 'Property', value: 1 }, [X + 'r']: { type: 'Relationship', object: 'urn:ctx:target:1' } });
    const plain = await get(e, { accept: 'application/json' });
    const ld = await get(e, { accept: 'application/ld+json' });
    const other = await get(e, { accept: 'text/plain' });
    const has = g => !!(g && one(g, X + 'a') && one(g, X + 'r'));
    return (plain.status === 200 && ld.status === 200 && has(plain.json) && has(ld.json) && other.status === 406) ||
      `application/json ${plain.status}, application/ld+json ${ld.status}, text/plain ${other.status}`;
  });
  await check('Reads', 'Missing entity', async () => {
    const r = await get(id('missing'));
    return (r.status === 404 && isType(r.json, 'ResourceNotFound')) || `answered ${r.status} ${r.text}`;
  });
  // Over MQTT first: on upstream 6.0.2 a notification without receiverInfo is lost on a freshly started broker (A4)
  await check('Subscriptions and notifications', 'MQTT endpoint without receiverInfo', mqttWithoutReceiverInfo);

  // Notifications, over HTTP to the sink of run.sh
  const N = `http://example.org/contract/N${RUN}`;
  const subId = id('sub');
  await subscribe(N, subId);
  const ne = name => ({ id: id(name), type: N, [X + 'a']: { type: 'Property', value: 1 } });
  await check('Subscriptions and notifications', 'Create and merge', async () => {
    const [c1, b1, b2] = [ne('n-c1'), ne('n-b1'), ne('n-b2')];
    const steps = [];
    await create(c1);
    steps.push(['create', c1.id]);
    const r = await call('POST', '/entityOperations/create', [b1, b2]);
    if (r.status !== 201) return `batch create answered ${r.status}`;
    steps.push(['batch create', b1.id], ['batch create', b2.id]);
    let got = await waitFor(steps.map(s => s[1]));
    const missing = steps.filter(s => !got.has(s[1])).map(s => s[0]);
    await clearSink();
    await mergeEntity(c1.id, { [X + 'a']: { type: PROP, value: 2 } });
    got = await waitForValue([c1.id], X + 'a', 2);
    if (!got.has(c1.id)) missing.push('merge entity');
    await clearSink();
    await appendAttrs(b1.id, { [X + 'a']: { type: 'Property', value: 3 } });
    got = await waitForValue([b1.id], X + 'a', 3);
    if (!got.has(b1.id)) missing.push('/attrs');
    await clearSink();
    return missing.length === 0 || `not notified after: ${missing.join(', ')}`;
  });
  await check('Subscriptions and notifications', 'Batch merge of several entities', async () => {
    const es = [ne('n-m1'), ne('n-m2'), ne('n-m3')];
    await call('POST', '/entityOperations/create', es);
    const created = await waitForValue(es.map(e => e.id), X + 'a', 1);
    if (es.some(e => !created.has(e.id))) return 'the creation of the entities was not notified';
    await clearSink();
    const r = await batchMerge(es.map(e => ({ id: e.id, [X + 'a']: [{ type: PROP, value: 7 }] })));
    if (r.status !== 204) return `batch merge answered ${r.status}`;
    const newValue = await waitForValue(es.map(e => e.id), X + 'a', 7);
    const notes = await notified();
    await clearSink();
    const missing = es.filter(e => !newValue.has(e.id)).map(e => e.id);
    console.log(`     measured: ${notes.length} notification(s) for a batch merge of 3 entities`);
    return missing.length === 0 || `not notified with the new value: ${missing.join(', ')}`;
  });
  await check('Subscriptions and notifications', 'Delete', async () => {
    const e = ne('n-del');
    await create(e);
    if (!(await waitFor([e.id])).has(e.id)) return 'the creation was not notified, so the delete proves nothing';
    // Let a late duplicate of the creation notification arrive before the sink is cleared
    await sleep(2000);
    await clearSink();
    await del(e.id);
    await sleep(5000);
    const got = notifiedIds(await notified());
    return !got.has(e.id) || 'the delete was notified';
  });
  await check('Subscriptions and notifications', 'A subscription read by its id', async () => {
    const r = await call('GET', `/subscriptions/${encodeURIComponent(subId)}`);
    return (r.status === 200 && r.json && r.json.id === subId) || `answered ${r.status} ${r.text.slice(0, 200)}, not 200 with the subscription (CIM 009 6.11.3.1)`;
  }, { platformOnly: true });
  await call('DELETE', `/subscriptions/${encodeURIComponent(subId)}`);

  await check("The broker's health reflects its notifications", 'Healthy broker', async () => {
    const started = await call('GET', `${BROKER}/q/health/started`, undefined, { token: null });
    const live = await liveness();
    return (started.json && started.json.status === 'UP' && live === 'UP') || `started ${started.json && started.json.status}, live ${live}`;
  });

  await check('Remote contexts', 'Entity with a remote context', async () => {
    const e = id('remote');
    const r = await call('POST', '/entityOperations/upsert',
      [{ '@context': IFF_CONTEXT, id: e, type: 'eclass:Contract', 'eclass:hasLevel': { type: 'Property', value: 3 } }],
      { ct: 'application/ld+json' });
    if (![201, 204].includes(r.status)) return `upsert answered ${r.status} ${r.text}`;
    const g = (await get(e, { link: IFF_CONTEXT })).json;
    return (g && one(g, 'eclass:hasLevel') && one(g, 'eclass:hasLevel').value === 3) || `read with the context: ${JSON.stringify(g)}`;
  });
}

// On a broker of its own, last: on the fork on 5.0.5 it stopped all notifications (#969)
async function subAttribute () {
  const N = `http://example.org/contract/S${RUN}`;
  await subscribe(N, id('sub-s'));
  await check('A merge with a sub-attribute keeps notifications working', 'Sub-attribute merged', async () => {
    const e = id('subattr');
    await create({ id: e, type: N, [X + 'a']: { type: 'Property', value: 1 } });
    if (!(await waitFor([e])).has(e)) return 'the creation was not notified';
    await clearSink();
    const r1 = await mergeEntity(e, { [X + 'a']: { type: PROP, value: 2, [X + 'sub']: { type: PROP, value: 'sub' } } });
    await waitForValue([e], X + 'a', 2);
    await clearSink();
    const r2 = await mergeEntity(e, { [X + 'a']: { type: PROP, value: 3 } });
    const secondNotified = (await waitForValue([e], X + 'a', 3, 10000)).has(e);
    const a = one((await get(e)).json, X + 'a');
    const subKept = !!(a && one(a, X + 'sub') && one(a, X + 'sub').value === 'sub');
    // Liveness fails about a minute after the channel died; give it 90 s, or stay up for 75 s
    let live = 'UP';
    for (let t = 0; t < 90 && live === 'UP'; t += 5) {
      await sleep(5000);
      live = await liveness();
      if (t >= 75 && secondNotified) break;
    }
    return (r1.status === 204 && r2.status === 204 && subKept && secondNotified && live === 'UP') ||
      `merges ${r1.status}/${r2.status}, sub-attribute kept ${subKept}, second merge notified ${secondNotified}, liveness ${live}`;
  });
}

(async () => {
  if (PART === 'subattribute') await subAttribute();
  else await main();
  fs.writeFileSync(`${OUT}/results-${PART}.json`, JSON.stringify(results, null, 1));
  const failed = results.filter(r => r.status === 'fail');
  const count = s => results.filter(r => r.status === s).length;
  console.log(`${count('ok')} ok, ${count('deviation')} known deviations, ${count('skip')} skipped, ${failed.length} failed`);
  process.exit(failed.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
