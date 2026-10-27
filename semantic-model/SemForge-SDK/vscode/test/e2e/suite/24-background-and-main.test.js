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

// Validation in the background: after an edit a page answers at once, and
// the verdicts follow when the worker has them -- here, a maximum lowered
// below what Main's workpiece says makes it violate, and raising it back
// clears that. And the Main page's tools for many entities: the filter, the
// graph, the type link that opens THAT type.

const assert = require('assert');
const vscode = require('vscode');
const path = require('path');
const { WORKSPACE, PACKAGE_URI, semforge, until, request, rows } = require('./helpers');

const ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/';

async function workpiecePage(api) {
  const page = await request(api, 'semforge/typePage', { entityType: `${ENT}Workpiece` });
  assert.ok(page.ok, page.error);
  return page;
}

function width(page) {
  return page.attributes.find((a) => a.label === 'hasWidth');
}

async function setMaximum(api, value) {
  const row = width(await workpiecePage(api));
  const done = await request(api, 'semforge/editValueForms', { shape: row.shape, path: row.path,
    action: { op: 'set', form: 0, node: [0], parameter: 'sh:maxInclusive', value } });
  assert.ok(done.ok, done.error);
}

describe('Validation in the background', () => {
  it('a page answers at once after an edit, and the verdicts follow', async () => {
    const api = await semforge();
    const before = await until(async () => {
      const page = await workpiecePage(api);
      return page.verdicts.state === 'ready' && page;
    }, 'the first verdicts');
    // What violates hasWidth already -- an earlier suite adds a workpiece
    // without one -- stays the baseline: the edit adds the one at 100.
    const already = width(before).violations.slice().sort();

    await setMaximum(api, '50');
    const started = Date.now();
    const asked = await workpiecePage(api);
    const seconds = (Date.now() - started) / 1000;
    assert.ok(seconds < 5, `the page took ${seconds}s: it waited for the validation`);
    assert.ok(['ready', 'evaluating'].includes(asked.verdicts.state), JSON.stringify(asked.verdicts));
    assert.match(width(asked).value, /50/, 'the structure is new at once');

    const judged = await until(async () => {
      const page = await workpiecePage(api);
      return page.verdicts.state === 'ready' &&
        width(page).violations.some((id) => !already.includes(id)) && page;
    }, 'the verdicts: Main’s workpiece at 100 now violates hasWidth');
    assert.ok(width(judged).violations.some((id) => /workpiece/i.test(id) && !already.includes(id)),
      width(judged).violations);
    const entity = width(judged).violations.find((id) => !already.includes(id));

    // The ways to it. A problem on its row in the data, for F8 -- in the
    // Problems panel before the file is opened ...
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    const modelUri = vscode.Uri.file(path.join(WORKSPACE, 'model-instance.jsonld'));
    await until(() => vscode.languages.getDiagnostics(modelUri).some((d) =>
      String(d.code && (d.code.value || d.code)) === 'model-violation' &&
      d.message.startsWith(`${entity} · hasWidth:`)), 'the problem with no file open');
    const model = await vscode.workspace.openTextDocument(modelUri);
    await vscode.window.showTextDocument(model);
    const problem = await until(() => vscode.languages.getDiagnostics(model.uri).find((d) =>
      String(d.code && (d.code.value || d.code)) === 'model-violation' &&
      d.message.startsWith(`${entity} · hasWidth:`)), 'a problem on the hasWidth row');
    assert.match(model.lineAt(problem.range.start.line).text, /hasWidth/);
    // ... the Main page's list, which leads to the row ...
    await vscode.commands.executeCommand('semforge.openModelPage');
    const listed = await until(() => api.pages.case.page && api.pages.case.page.kind === 'model' &&
      /<h2 id="violations">Violations/.test(api.pages.case.panel.webview.html) &&
      api.pages.case.panel.webview.html,
    'the Violations list');
    assert.match(listed, new RegExp(`data-jump="[0-9.]+"[^>]*><a tabindex="0" role="link">${entity} · hasWidth</a>`));
    // ... and the tree, which says it first.
    const tree = api.trees.model;
    const row = await until(async () => (await rows(tree)).find((node) =>
      node.raw.kind === 'attribute' && node.raw.label === 'hasWidth' && node.raw.entity === entity &&
      node.raw.severity === 'violation'), 'the violating row in the tree');
    assert.match(tree.getTreeItem(row).description, /^✗ hasWidth is above its maximum/);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');

    await setMaximum(api, '100');
    await until(async () => {
      const page = await workpiecePage(api);
      return page.verdicts.state === 'ready' &&
        JSON.stringify(width(page).violations.slice().sort()) === JSON.stringify(already);
    }, 'the violation to clear');
  });

  // The edit is the server's (no editor saves anything): the open page used
  // to keep the verdicts it had -- a user's type page still said what it said
  // before a case gained a value.
  it('an open type page follows an edit no editor saved', async () => {
    const api = await semforge();
    const before = await until(async () => {
      const page = await workpiecePage(api);
      return page.verdicts.state === 'ready' && page;
    }, 'the first verdicts');
    const already = width(before).violations.slice().sort();
    await vscode.commands.executeCommand('semforge.openTypePage',
      { raw: { kind: 'type', targetClass: `${ENT}Workpiece`, children: [] },
        packageUri: PACKAGE_URI });
    await until(() => api.pages.type.page && api.pages.type.page.label === 'Workpiece' &&
      api.pages.type.page.verdicts.state === 'ready', 'the Workpiece page');

    await setMaximum(api, '50');
    await until(() => {
      const page = api.pages.type.page;
      return page && page.verdicts.state === 'ready' &&
        width(page).violations.some((id) => !already.includes(id));
    }, 'the open page to show the new violation', 90000);

    await setMaximum(api, '100');
    await until(() => {
      const page = api.pages.type.page;
      return page && page.verdicts.state === 'ready' &&
        JSON.stringify(width(page).violations.slice().sort()) === JSON.stringify(already);
    }, 'the open page to show it cleared', 90000);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});

describe('The Main page with many entities', () => {
  it('offers Cards and Graph, and a filter by type, attribute and id from the data', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openModelPage');
    const page = await until(() => api.pages.case.page && api.pages.case.page.kind === 'model' &&
      api.pages.case.page, 'the Main page');
    const html = api.pages.case.panel.webview.html;
    assert.ok(html.includes('data-view="cards"') && html.includes('data-view="graph"'));
    const cards = page.files.flatMap((f) => f.cards);
    for (const type of new Set(cards.map((c) => c.type).filter(Boolean))) {
      assert.ok(html.includes(`<option value="${type}">`), `the filter offers ${type}`);
    }
    // What the graph is drawn from: every entity, its type and its relationships.
    const index = JSON.parse(html.split('<script type="application/json" id="entities">')[1]
      .split('</script>')[0].replace(/\\u003c/g, '<'));
    assert.deepStrictEqual(index.map((e) => e.id).sort(), cards.map((c) => c.id || '').sort());
    const drawn = index.flatMap((e) => e.rels.map((r) => `${e.id} ${r.name} ${r.target}`));
    const said = cards.flatMap((c) => (c.attributes || [])
      .filter((a) => a.kind === 'Relationship' && a.value && !a.superseded)
      .map((a) => `${c.id || ''} ${a.name} ${a.value}`));
    assert.ok(said.length, 'Main has relationships');
    for (const edge of said) {
      assert.ok(drawn.includes(edge), `the graph draws ${edge}`);
    }
  });

  it('a type link opens that type’s page, a card does not', async () => {
    const api = await semforge();
    const html = api.pages.case.panel.webview.html;
    // The regression: the whole card carried data-type, so a click anywhere on
    // it -- on a relationship to another type too -- opened the card's type.
    assert.ok(!/class="card[^"]*"[^>]*data-type=/.test(html), 'a card carries no data-type');
    assert.ok(/class="card[^"]*"[^>]*data-ftype=/.test(html), 'the filter reads data-ftype');
    const card = api.pages.case.page.files.flatMap((f) => f.cards).find((c) => c.type);
    await api.pages.case.receive({ command: 'type', name: card.type });
    await until(() => api.pages.type.panel &&
      api.pages.type.panel.title === `Entity type: ${card.type.split(':').pop()}`, 'its type page');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});

describe('A count is a way in', () => {
  it('every row of every view runs its click, every time it is clicked', async () => {
    const api = await semforge();
    const views = { project: 'semforge.clickPackageRow', constraints: 'semforge.clickTypesRow',
      shapes: 'semforge.clickShapesRow', model: 'semforge.clickEntitiesRow',
      knowledge: 'semforge.clickKnowledgeRow' };
    for (const [name, command] of Object.entries(views)) {
      const tree = api.trees[name];
      const [first] = await until(async () => (await tree.getChildren()) || [], `${name} rows`);
      const item = await tree.getTreeItem(first);
      assert.strictEqual(item.command && item.command.command, command, name);
    }
    // Main, which counts violations, clicked; the page closed; clicked
    // again -- the selection does not change, and it did nothing.
    const tree = api.trees.model;
    const main = await until(async () => (await rows(tree)).find((node) =>
      node.raw.kind === 'group' && node.raw.label === 'Main' && node.raw.severity), 'Main');
    const click = (await tree.getTreeItem(main)).command;
    for (const time of [1, 2]) {
      await vscode.commands.executeCommand(click.command, ...click.arguments);
      await until(() => api.pages.case.panel && api.pages.case.current &&
        api.pages.case.current.only === true, `the Main page, only what violates (click ${time})`);
      assert.match(api.pages.case.panel.webview.html, /data-only="1"/);
      await vscode.commands.executeCommand('workbench.action.closeAllEditors');
      await until(() => !api.pages.case.panel, 'the page closed');
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  });

  it('the Health page\u2019s violations tile opens them', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openHealthPage');
    const html = await until(() => api.pages.health.panel && api.pages.health.panel.webview.html
      .includes('data-act="violations"') && api.pages.health.panel.webview.html, 'the tile');
    assert.match(html, /<button class="tile warn" data-act="violations"/);
    await api.pages.health.receive({ command: 'violations' });
    await until(() => api.pages.case.panel && api.pages.case.current &&
      api.pages.case.current.only === true, 'the Main page, only what violates');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
