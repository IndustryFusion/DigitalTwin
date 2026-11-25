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

// Search…: typed, the views show only what fits; cleared, everything is back.
// And from a line of the shapes file, Open in SemForge goes to its page.

const assert = require('assert');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, semforge, until, rows } = require('./helpers');

describe('search in the views', () => {
  const search = require('../../../src/search');
  afterEach(async () => {
    await vscode.commands.executeCommand('semforge.clearSearch');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('filters all four while one types, keeps on Enter, and clears', async () => {
    const api = await semforge();
    const trees = ['model', 'constraints', 'shapes', 'knowledge'].map((name) => [name,
      api.trees[name].provider || api.trees[name]]);
    const before = {};
    for (const [name, provider] of trees) {
      before[name] = (await until(async () => { const r = await rows(provider); return r.length && r; }, name))
        .map((n) => n.raw);
    }
    // A person types into the box and presses Enter.
    const real = vscode.window.createInputBox;
    let box;
    vscode.window.createInputBox = () => {
      box = real.call(vscode.window);
      const accept = box.onDidAccept.bind(box);
      box.onDidAccept = (handler) => { box.enter = handler; return accept(handler); };
      return box;
    };
    await vscode.commands.executeCommand('semforge.hideDetails');
    try {
      const asked = vscode.commands.executeCommand('semforge.search');
      await until(() => box && box.enter, 'the search box');
      box.value = 'hasStrength';
      await box.enter();
      assert.strictEqual(await asked, 'hasStrength');
      assert.strictEqual(api.details.shown(), true, 'a search shows the details');

      // Escape puts back what was: the search kept.
      box = undefined;
      const again = vscode.commands.executeCommand('semforge.search');
      await until(() => box && box.enter, 'the search box again');
      assert.strictEqual(box.value, 'hasStrength');
      // Typed: the views follow (a value set by a test fires no change, so
      // the search is set as the box would after the pause).
      box.value = 'no such thing';
      await search.set('no such thing');
      box.hide();
      assert.strictEqual(await again, 'hasStrength');
    } finally {
      vscode.window.createInputBox = real;
    }
    for (const [name, provider] of trees) {
      const found = await rows(provider);
      assert.ok(found.length && found.length < before[name].length,
        `${name}: ${found.length} of ${before[name].length}`);
      const hits = found.filter((node) => node.raw.hit);
      assert.ok(hits.length, name);
      const open = found.find((node) => node.raw.expand);
      if (open) {
        assert.strictEqual(provider.getTreeItem(open).collapsibleState,
          vscode.TreeItemCollapsibleState.Expanded, name);
      }
      await until(() => /hasStrength.*found/.test((provider.view || {}).message || ''), `${name} says how many`);
    }
    // A row of the search opens its page, as always.
    const shape = (await rows(api.trees.shapes.provider || api.trees.shapes)).find((n) => n.raw.label === 'FilterShape');
    await vscode.commands.executeCommand('semforge.openShapePage', shape);
    await until(() => api.pages.shape.page && api.pages.shape.page.label === 'FilterShape', 'the shape page');

    await vscode.commands.executeCommand('semforge.clearSearch');
    for (const [name, provider] of trees) {
      // Not the same number: verdicts that arrived meanwhile add rows (Violations).
      const whole = (await rows(provider)).filter((n) => !/^violation/.test(n.raw.kind));
      const was = before[name].filter((n) => !/^violation/.test(n.kind));
      assert.deepStrictEqual(whole.map((n) => n.raw.label), was.map((n) => n.label), `${name} is whole again`);
      assert.ok(!whole.some((n) => n.raw.searchId !== undefined), `${name} has no row of the search`);
    }
  });

  it('Open in SemForge goes from a line of the shapes file to its page', async () => {
    const api = await semforge();
    const document = await vscode.workspace.openTextDocument(path.join(WORKSPACE, 'shacl.ttl'));
    const editor = await vscode.window.showTextDocument(document);
    const at = document.positionAt(document.getText().indexOf('iffBaseEntities:hasStrength'));
    editor.selection = new vscode.Selection(at, at);
    await vscode.commands.executeCommand('semforge.openHere');
    await until(() => api.pages.shape.page && api.pages.shape.page.label === 'FilterShape', 'the shape page');
  });

  it('a line of unsaved text is found where it is shown', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    const document = await vscode.workspace.openTextDocument(path.join(WORKSPACE, 'shacl.ttl'));
    const editor = await vscode.window.showTextDocument(document);
    await editor.edit((edit) => edit.insert(new vscode.Position(0, 0), '# one more\n'.repeat(500)));
    assert.ok(document.isDirty);
    const at = document.positionAt(document.getText().indexOf('iffBaseEntities:hasStrength'));
    editor.selection = new vscode.Selection(at, at);
    await vscode.commands.executeCommand('semforge.openHere');
    await until(() => api.pages.shape.page && api.pages.shape.page.label === 'FilterShape', 'the shape page');
    await vscode.window.showTextDocument(document);
    await vscode.commands.executeCommand('workbench.action.files.revert');
  });

  it('a file outside any package says so, and a line without a page is searched for', async () => {
    const api = await semforge();
    const document = await vscode.workspace.openTextDocument(path.join(WORKSPACE, 'shacl.ttl'));
    const editor = await vscode.window.showTextDocument(document);
    const at = document.positionAt(document.getText().indexOf('prefix') + 1);
    assert.strictEqual(at.line, 0);
    editor.selection = new vscode.Selection(at, at);
    const found = await vscode.commands.executeCommand('semforge.openHere');
    assert.strictEqual(found.page, 'search');
    assert.strictEqual(search.current(), 'prefix');
    const answer = await api.clientHolder.client.sendRequest('semforge/pageAt',
      { uri: vscode.Uri.file(path.join(path.dirname(WORKSPACE), 'none.ttl')).toString(), line: 1 });
    assert.ok(!answer.ok && /no SemForge package/.test(answer.error));
  });
});
