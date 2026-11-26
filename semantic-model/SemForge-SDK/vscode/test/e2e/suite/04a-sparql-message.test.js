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


// The message of a SPARQL constraint in a real VS Code: edited in the
// workbench, opened there from the shape page, filled in the result's text;
// then taken away and put back.

const assert = require('assert');
const vscode = require('vscode');
const { PACKAGE_URI, semforge, until, answering, read } = require('./helpers');

const CUTTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape';
const OFF = 'test_StateOnCutterShape/bad/filter-off.jsonld';
const SAYS = 'Cutter running without running filter';
const NEW = 'Filter {?f} is "off" for {$this}';

describe('the message of a SPARQL constraint', () => {
  it('is edited with a variable, saved, and filled in the result', async () => {
    const api = await semforge();
    const bench = api.pages.sparql;
    const posted = [];
    const post = bench.post.bind(bench);
    bench.post = (message) => {
      posted.push(message);
      post(message);
    };
    const before = read('shacl.ttl');
    try {
      const example = vscode.Uri.joinPath(vscode.Uri.parse(PACKAGE_URI), '..', 'examples', OFF).fsPath;
      await vscode.commands.executeCommand('semforge.openCasePage',
        { raw: { kind: 'example', file: example }, packageUri: PACKAGE_URI });
      await until(() => api.pages.case.panel && api.pages.case.panel.webview.html.includes(SAYS),
        'the case page with the old message');

      // From the shape page, straight to the field.
      await vscode.commands.executeCommand('semforge.openShapePage',
        { raw: { shape: CUTTER }, packageUri: PACKAGE_URI });
      await until(() => api.pages.shape.page && api.pages.shape.page.iri === CUTTER, 'the shape page');
      const asked = answering([{ kind: 'pick', label: '$(comment) Edit message…' }]);
      try {
        await api.pages.shape.receive({ command: 'checkMenu', row: 0 });
      } finally {
        asked.restore();
      }
      await until(() => bench.page && bench.page.shape === CUTTER, 'the workbench');
      // The page's own script opened the field: it asked for a check of its text.
      const checked = await until(() => posted.find((m) => m.type === 'messageCheck'),
        'the page script to ask about the message');
      assert.strictEqual(checked.message, SAYS);
      assert.deepStrictEqual(checked.variables, ['this', 'v1', 'f', 'v2']);
      assert.deepStrictEqual(checked.warnings, []);
      const wrong = await bench.receive({ command: 'checkMessage', message: 'it\'s {?nope}' });
      assert.strictEqual(wrong.warnings.length, 2, wrong.warnings.join());

      // An unsaved query edit stays in its editor through the message's save.
      await bench.receive({ command: 'source', source: OFF });
      const doc = await bench.replaceText(`${bench.page.holder.query}# mine`);
      posted.length = 0;
      const saved = await bench.receive({ command: 'saveMessage', message: NEW, expected: SAYS });
      assert.ok(saved.ok, saved.error);
      assert.ok(doc.isDirty && doc.getText().endsWith('# mine'));
      assert.strictEqual(read('shacl.ttl'), before.replace(`"${SAYS}"`, '"Filter {?f} is \\"off\\" for {$this}"'));
      assert.ok(bench.panel.webview.html.includes('Filter {?f} is &quot;off&quot;'), 'the page says it');
      const run = await until(() => posted.find((m) => m.type === 'result' && m.result.ok), 'its own run');
      assert.deepStrictEqual(run.result.focus[0].messages, ['Filter urn:filter:1 is "off" for urn:plasmacutter:1']);

      // A query that no longer selects ?f says so in its editor.
      await bench.replaceText(bench.page.holder.query.replace('?v1 ?f ?v2', '?v1 ?v2'));
      const found = await until(() => vscode.languages.getDiagnostics(doc.uri)
        .find((d) => d.code === 'message-variable'), 'the squiggle on the SELECT');
      assert.ok(found.message.includes('{?f} is not a variable the query selects'), found.message);
      await bench.cancel();

      // The pages that show it follow. A hidden page asks when it is shown.
      await vscode.commands.executeCommand('semforge.openShapePage',
        { raw: { shape: CUTTER }, packageUri: PACKAGE_URI });
      await until(() => api.pages.shape.panel.webview.html.includes('Filter {?f}'), 'the shape page');
      await vscode.commands.executeCommand('semforge.openCasePage',
        { raw: { kind: 'example', file: example }, packageUri: PACKAGE_URI });
      await until(() => /Filter (<[^>]*>)?urn:filter:1/.test(api.pages.case.panel.webview.html) ||
        api.pages.case.panel.webview.html.includes('Filter urn:filter:1 is'), 'the case page');

      // A stale page's save is refused.
      const stale = await bench.receive({ command: 'saveMessage', message: 'x', expected: SAYS });
      assert.ok(!stale.ok && stale.error.includes('changed in the file'), JSON.stringify(stale));
    } finally {
      bench.post = post;
    }
  });

  it('emptied it is removed after asking, the Problems panel says what that means, and it can be added', async () => {
    const api = await semforge();
    const bench = api.pages.sparql;
    await vscode.commands.executeCommand('semforge.openSparqlBench',
      { raw: { shape: CUTTER }, packageUri: PACKAGE_URI }, {});
    await until(() => bench.page && bench.page.holder.message === NEW, 'the workbench');
    const session = answering([{ kind: 'warning', button: 'Remove message' }]);
    try {
      const removed = await bench.receive({ command: 'saveMessage', message: '', expected: NEW });
      assert.ok(removed && removed.ok, JSON.stringify(removed));
    } finally {
      session.restore();
    }
    assert.ok(!read('shacl.ttl').includes('Filter {?f}'));
    assert.ok(bench.panel.webview.html.includes('+ Message'));
    const shapes = vscode.Uri.parse(PACKAGE_URI);
    await until(() => vscode.languages.getDiagnostics(shapes).find((d) => d.code === 'message-missing'),
      'the problem');
    const added = await bench.receive({ command: 'saveMessage', message: SAYS, expected: '' });
    assert.ok(added.ok, added.error);
    await until(() => !vscode.languages.getDiagnostics(shapes).find((d) => d.code === 'message-missing'),
      'the problem to go');
    assert.strictEqual(bench.page.holder.message, SAYS);
    await bench.receive({ command: 'source', source: '@main' });      // as the next suite expects it
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
