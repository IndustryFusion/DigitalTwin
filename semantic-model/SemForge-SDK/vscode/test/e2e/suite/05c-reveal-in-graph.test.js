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

// Reveal in graph view, in a real VS Code: from the rows of the views and from
// the pages, into the page that holds the entity. The page says where its path
// ended (`landed`: the path, and whether the entity is in sight).

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, PACKAGE_URI, OPCUA, OPCUA_URI, semforge, until, row } = require('./helpers');

const run = (name, ...args) => vscode.commands.executeCommand(name, ...args);

describe('Reveal in graph view', () => {
  afterEach(() => run('workbench.action.closeAllEditors'));

  async function start() {
    const api = await semforge();
    const pages = api.pages.case;
    pages.landed = undefined;
    return { api, pages, model: api.trees.model.provider || api.trees.model };
  }
  const landed = (pages, entity, from = 'reveal') => until(() => pages.landed && pages.landed.from === from &&
    pages.landed.entity === entity && pages.landed, `the path to ${entity}`, 90000);

  it('from an entity of the main model, again on its open page, and after a redraw', async () => {
    const { api, pages, model } = await start();
    const cartridge = await row(model, (raw) => raw.kind === 'entity' && raw.entity === 'urn:cartridge:1' &&
      /model-instance/.test(raw.file || 'model-instance'), 'urn:cartridge:1 in the view');
    await run('semforge.revealRowInGraph', cartridge);
    const there = await landed(pages, 'urn:cartridge:1');
    assert.ok(there.inView, JSON.stringify(there));
    assert.strictEqual(there.path[there.path.length - 1], 'urn:cartridge:1');
    assert.strictEqual(pages.page.kind, 'model');
    // What points at it, as the suites before left the model: the card before it.
    const rows = (list) => list.flatMap((r) => [r].concat(rows(r.children || [])));
    const owner = pages.page.files.flatMap((f) => f.cards).find((card) => rows(card.attributes)
      .some((r) => r.kind === 'Relationship' && (r.target || r.value) === 'urn:cartridge:1'));
    if (owner) {
      assert.ok(there.path.length > 1, `${owner.id} leads to it: ${there.path}`);
    }

    // A right click on an id of the page: the page does it, nothing is fetched.
    // (Once the validation is done: its verdicts redraw the page, as they should.)
    await until(() => pages.page.verdicts && pages.page.verdicts.state === 'ready' && !pages.refreshPending,
      'the validation to be done', 90000);
    const client = api.clientHolder.client;
    const real = client.sendRequest;
    const asked = [];
    let second;
    client.sendRequest = function (method, ...rest) { asked.push(method); return real.call(client, method, ...rest); };
    try {
      pages.landed = undefined;
      await run('semforge.revealInGraph', { webview: 'semforgeCasePage', webviewSection: 'semforgeEntity',
        entity: 'urn:workpiece:1' });
      second = await landed(pages, 'urn:workpiece:1');
      assert.ok(second.inView);
      assert.ok(!asked.includes('semforge/modelPage'), asked.join());
    } finally {
      client.sendRequest = real;
    }
    // Drawn again -- what a validation or an edit does -- the path stays.
    await new Promise((resolve) => setTimeout(resolve, 1500));
    pages.landed = undefined;
    await pages.render();
    const kept = await landed(pages, 'urn:workpiece:1', 'kept');
    assert.ok(second.path.length && kept !== second, 'drawn again, said again');
    assert.deepStrictEqual(kept.path, second.path);
  });

  it('from an entity of a test case: in the page of that case', async () => {
    const { pages, model } = await start();
    const filter = await row(model, (raw) => raw.kind === 'entity' && raw.entity === 'urn:filter:9',
      'urn:filter:9 in its case');
    await run('semforge.revealRowInGraph', filter);
    await landed(pages, 'urn:filter:9');
    assert.ok(pages.page.file.endsWith('without-cartridge.jsonld'), pages.page.file);
  });

  it('from an instance on a type page, and from a use in Knowledge', async () => {
    const { api, pages } = await start();
    await run('semforge.openTypePage', { packageUri: PACKAGE_URI, raw: {
      targetClass: 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter' } });
    await until(() => api.pages.type.page && (api.pages.type.page.instances || []).length, 'the instances');
    await api.pages.type.receive({ command: 'revealGraph', entity: 'urn:filter:1' });
    await landed(pages, 'urn:filter:1');
    assert.strictEqual(pages.page.kind, 'model');

    pages.landed = undefined;
    const knowledge = api.trees.knowledge.provider || api.trees.knowledge;
    // A file a case includes: the page of a case that includes it.
    const instance = await row(knowledge, (raw) => raw.kind === 'usage' && raw.file &&
      raw.file.includes(`${path.sep}subobjects${path.sep}`), 'a use in an included file, in Knowledge');
    await run('semforge.revealRowInGraph', instance);
    await landed(pages, instance.raw.entity);
    assert.strictEqual(pages.page.kind, undefined, 'a test case page');
  });

  it('an id written with a prefix, from Knowledge; a relative one, from the type page', async () => {
    const { api, pages } = await start();
    const file = path.join(WORKSPACE, 'examples', 'test_FilterShape', 'bad', 'without-cartridge.jsonld');
    const saved = fs.readFileSync(file, 'utf-8');
    fs.writeFileSync(file, saved.replace('"urn:filter:9"', '"iffBaseEntities:filter9"'));
    try {
      await run('semforge.refreshKnowledge');
      const knowledge = api.trees.knowledge.provider || api.trees.knowledge;
      const use = await row(knowledge, (raw) => raw.kind === 'usage' && raw.entity === 'iffBaseEntities:filter9',
        'the use of the prefixed id, as written');
      await run('semforge.revealRowInGraph', use);
      await landed(pages, 'iffBaseEntities:filter9');
      assert.strictEqual(pages.page.file, file);
    } finally {
      fs.writeFileSync(file, saved);
    }
    // The type page names an entity as the graph has it; the page finds its card.
    pages.landed = undefined;
    const pump = 'http://opcfoundation.org/UA/Pumps/PumpType';
    await run('semforge.openTypePage', { packageUri: OPCUA_URI, raw: { targetClass: pump } });
    const instance = await until(() => api.pages.type.page && api.pages.type.page.label === 'PumpType' &&
      (api.pages.type.page.instances || [])[0], 'the pump on its type page', 90000);
    assert.ok(!/^[a-z]+:/.test(instance.id), `a relative id: ${instance.id}`);
    await api.pages.type.receive({ command: 'revealGraph', entity: instance.id });
    const there = await landed(pages, instance.id);
    assert.deepStrictEqual(there.path, [instance.id]);
  });

  // The OPC UA pump twenty times over: 400 entities whose ids have no scheme.
  it('in a package of hundreds of entities, every way ends at its entity, in sight', async () => {
    const { pages } = await start();
    const file = path.join(OPCUA, 'model-instance.jsonld');
    const saved = fs.readFileSync(file, 'utf-8');
    const one = JSON.parse(saved);
    const ids = new Set(one.map((d) => d.id));
    const copy = (value, n) => (Array.isArray(value) ? value.map((v) => copy(v, n))
      : value && typeof value === 'object' ? Object.fromEntries(Object.entries(value).map(([k, v]) =>
        [k, (k === 'id' || k === 'object') && ids.has(v) ? `${v}-${n}` : copy(v, n)])) : value);
    const many = [];
    for (let n = 0; n < 20; n += 1) { many.push(...one.map((d) => copy(d, n))); }
    fs.writeFileSync(file, JSON.stringify(many, null, 2));
    try {
      const owner = {};
      many.forEach((d) => Object.values(d).forEach((v) => [].concat(v).forEach((a) => {
        if (a && a.type === 'Relationship') { owner[a.object] = d.id; }
      })));
      const deepest = many.map((d) => d.id).reduce((best, id) => {
        const depth = (at) => (owner[at] ? 1 + depth(owner[at]) : 0);
        return depth(id) > depth(best) ? id : best;
      });
      const expected = [deepest];
      while (owner[expected[0]]) { expected.unshift(owner[expected[0]]); }
      const started = Date.now();
      await run('semforge.revealInGraph', { entity: deepest, file, packageUri: OPCUA_URI });
      const there = await until(() => pages.landed && pages.landed.entity === deepest &&
        pages.page.summary.entities === 400 && pages.landed, 'the path in the large page', 120000);
      assert.deepStrictEqual(there.path, expected);
      assert.ok(there.inView, JSON.stringify(there));
      assert.ok(Date.now() - started < 60000, `${Date.now() - started} ms`);
      for (const entity of [many[0].id, many[many.length - 1].id, `${one[2].id}-7`]) {
        pages.landed = undefined;
        await run('semforge.revealInGraph', { webview: 'semforgeCasePage', entity });
        const step = await landed(pages, entity);
        assert.strictEqual(step.path[step.path.length - 1], entity);
        assert.ok(step.path.every((id) => id.endsWith(entity.slice(entity.lastIndexOf('-')))), step.path.join());
      }
    } finally {
      fs.writeFileSync(file, saved);
    }
  });
});
