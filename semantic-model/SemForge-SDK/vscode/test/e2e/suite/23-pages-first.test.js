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

// A click stays in SemForge; the file is an option, never the default. An
// attribute on the Main page opens its type page with it marked; + Attribute
// ends in the attribute editor; ⋯ → Open in .jsonld still opens the file; the
// Package view opens the package page, whose Edit… writes semforge.yaml and
// keeps its comments. And every view and page says what it is.

const assert = require('assert');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, WORKSPACE, semforge, until, answering, read } = require('./helpers');

const ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/';

async function mainPage(api) {
  await vscode.commands.executeCommand('semforge.openModelPage');
  return until(() => api.pages.case.page && api.pages.case.page.kind === 'model' &&
    api.pages.case.panel && api.pages.case.panel.title === 'Entities: Main' &&
    api.pages.case.page, 'the Main page');
}

async function withAnswers(answers, run) {
  const session = answering(answers);
  try {
    await run();
  } finally {
    session.restore();
  }
  assert.strictEqual(session.left(), 0, JSON.stringify(session.asked));
  return session;
}

describe('A click stays in the pages', () => {
  it('an attribute on the Main page opens its type page, the attribute marked', async () => {
    const api = await semforge();
    const page = await mainPage(api);
    const html = api.pages.case.panel.webview.html;
    assert.ok(html.includes('<h1>Entities: Main</h1>'), 'the page says what it is');
    const card = page.files.flatMap((f) => f.cards)
      .find((c) => c.type && (c.attributes || []).length);
    const attribute = card.attributes[0];
    assert.ok(html.includes(`data-names="${'[&quot;'}${attribute.name}${'&quot;]'}"`),
      'the name is a link to the type page');
    await api.pages.case.receive({ command: 'type', name: card.type, names: [attribute.name] });
    await until(() => api.pages.type.panel &&
      api.pages.type.panel.title === `Entity type: ${card.type.split(':').pop()}`, 'its type page');
    const focused = await until(() => {
      const shown = api.pages.type.panel.webview.html;
      return shown.includes('id="focus"') && shown.split('id="focus"')[1].split('</tr>')[0];
    }, 'a marked row');
    assert.ok(focused.replace(/<wbr>/g, '').includes(attribute.name), focused.slice(0, 300));
  });

  it('⋯ → Open in .jsonld opens the file at the row', async () => {
    const api = await semforge();
    const page = await mainPage(api);
    const f = page.files.findIndex((file) => file.cards.some((c) => (c.attributes || []).length));
    const c = page.files[f].cards.findIndex((card) => (card.attributes || []).length);
    const card = page.files[f].cards[c];
    await withAnswers([{ kind: 'pick', label: '$(go-to-file) Open in .jsonld' }],
      () => api.pages.case.receive({ command: 'rowMenu', at: `${f}.${c}.0` }));
    await until(() => vscode.window.activeTextEditor &&
      vscode.window.activeTextEditor.document.fileName === (card.file || page.files[f].path),
    'the .jsonld in the editor');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('+ Attribute ends in the attribute editor on the new row', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openTypePage',
      { raw: { kind: 'type', targetClass: `${ENT}Cutter`, label: 'Cutter', children: [] },
        packageUri: PACKAGE_URI });
    await until(() => api.pages.type.page && api.pages.type.page.label === 'Cutter', 'Cutter');
    // Cutter's one free attribute is the kms' own hasJSON, a JsonProperty: its
    // value is any JSON, so after presence nothing more is asked.
    let picked;
    await withAnswers([
      { kind: 'pick', choose: (items) => {
        picked = items.find((item) => item.option && item.option.status === 'free');
        return picked;
      } },
      { kind: 'pick', label: 'Optional' }],
    () => api.pages.type.receive({ command: 'addAttribute', row: -1 }));
    assert.ok(picked, 'a free attribute was offered');
    const label = picked.option.label;
    await until(() => api.pages.attribute && api.pages.attribute.panel &&
      api.pages.attribute.panel.title === `Attribute: ${label}`, 'its attribute editor');
    const focused = api.pages.type.panel.webview.html.split('id="focus"')[1] || '';
    assert.ok(focused.split('</tr>')[0].replace(/<wbr>/g, '').includes(label), 'the new row marked');
    assert.ok(!vscode.window.visibleTextEditors.some((e) => e.document.fileName.endsWith('shacl.ttl')),
      'shacl.ttl was not opened over the page');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});

describe('The package page', () => {
  it('opens from the Package view, the row marked, its file only a button', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openPackagePage',
      { raw: { kind: 'setting', key: 'context.published', label: 'published context' },
        packageUri: PACKAGE_URI });
    const html = await until(() => api.pages.package.panel &&
      /^Package: /.test(api.pages.package.panel.title) && api.pages.package.panel.webview.html,
    'the package page');
    assert.ok(/<h1>Package: /.test(html));
    const focused = html.split('id="focus"')[1].split('</tr>')[0];
    assert.ok(focused.includes('published context'), focused);
    assert.deepStrictEqual(html.match(/data-open="[^"]*"/g).length, 1, 'one Open button');
    assert.ok(html.includes('>Open semforge.yaml</button>'));
  });

  it('Edit… writes semforge.yaml and keeps every comment', async () => {
    const api = await semforge();
    const before = read('semforge.yaml');
    const comments = before.split('\n').filter((line) => line.trim().startsWith('#'));
    const original = /published: (\S+)/.exec(before)[1];
    const edit = async (value) => {
      const rows = require(path.resolve(__dirname, '..', '..', '..', 'src', 'packagepage.js'))
        .numbered(api.pages.package.payload.roots);
      const row = rows.findIndex(({ row: r }) => r.key === 'context.published');
      await withAnswers([{ kind: 'input', value }, { kind: 'message' }],
        () => api.pages.package.receive({ command: 'edit', row }));
    };
    const changed = 'https://example.org/contexts/v9/context.jsonld';
    await edit(changed);
    const after = read('semforge.yaml');
    assert.ok(after.includes(`published: ${changed}`), 'the new value written');
    assert.deepStrictEqual(after.split('\n').filter((line) => line.trim().startsWith('#')), comments,
      'every comment kept');
    await until(() => api.pages.package.panel.webview.html.includes(changed), 'the page to show it');
    await edit(original);
    assert.strictEqual(read('semforge.yaml'), before, 'back as it was');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});

describe('Views and pages say what they are', () => {
  it('every view opens with its heading', async () => {
    const api = await semforge();
    const said = (tree) => tree && tree.view && tree.view.message;
    await until(() => said(api.trees.project) && said(api.trees.knowledge), 'the headings');
    assert.match(said(api.trees.project), /^This package:/);
    assert.match(said(api.trees.constraints), /^Every entity type/);
    assert.match(said(api.trees.shapes), /^The SHACL shapes as written/);
    assert.match(said(api.trees.model), /^The data:|^⟳/);
    assert.match(said(api.trees.knowledge), /^What the terms mean/);
    const views = vscode.extensions.getExtension('industryfusion.semforge')
      .packageJSON.contributes.views.semforge.map((v) => v.name);
    assert.deepStrictEqual(views, ['Package', 'Entity Types & Constraints', 'SHACL Shapes',
      'Entities & Test Cases', 'Knowledge (Ontology)']);
    assert.ok(WORKSPACE);
  });
});
