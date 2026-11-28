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

// A test that should fail, from New test… to its end: it fails without a
// reason, its data is broken on the case page, what fires is asserted, the
// assert is taken out again, the attribute editor lists it and deletes it.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, semforge, until, answering } = require('./helpers');

const FILTER = 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter';
const NAME = 'strength-e2e';

describe('a test that should fail', () => {
  it('fails until its reason is asserted, and can be deleted where it is listed', async () => {
    const api = await semforge();
    const answered = async (answers, run) => {
      const session = answering(answers);
      try {
        await run();
      } finally {
        session.restore();
      }
    };
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    await vscode.commands.executeCommand('semforge.openTypePage',
      { raw: { targetClass: FILTER }, packageUri: PACKAGE_URI });
    const type = await until(() => api.pages.type.page, 'the type page');
    const row = type.attributes.findIndex((a) => a.label === 'hasStrength');
    // The attribute editor, open and then covered by the case page: hidden while
    // the runs end that its list follows.
    await api.pages.type.receive({ command: 'attribute', row });
    const editor = api.pages.attribute;
    // The case page opens where the focus is: on the editor, so it covers it.
    // When the editor gets the focus after opening is a matter of timing.
    editor.panel.reveal(editor.panel.viewColumn, false);
    await until(() => editor.panel.active, 'the attribute editor focused');
    await answered([{ kind: 'pick', label: '$(error) Should fail' }, { kind: 'input', value: NAME }],
      () => api.pages.type.receive({ command: 'test', row }));

    const pages = api.pages.case;
    const settled = (check, what) => until(() => pages.page && pages.page.file &&
      pages.page.file.endsWith(`${NAME}.jsonld`) && pages.page.verdicts.state === 'ready' &&
      check(pages.page) && pages.page, what);
    let page = await settled((p) => p.passed === false, 'the case, failing');
    assert.ok(page.failures.some((f) => f.startsWith('asserts nothing')), page.failures.join());
    assert.ok(pages.panel.webview.html.includes('No reason yet'));
    const file = page.file;

    const of = (card) => card.attributes.findIndex((a) => a.name === 'hasStrength');
    const card = page.files[0].cards.findIndex((c) => of(c) >= 0);
    const at = `0.${card}.${of(page.files[0].cards[card])}`;
    await answered([{ kind: 'input', value: '100000' }], () => pages.receive({ command: 'edit', at }));
    page = await settled((p) => p.unasserted.length, 'what fires');
    assert.strictEqual(page.passed, false, 'it violates, and still has no reason');

    for (let i = 0; i < 10 && page.unasserted.length; i += 1) {
      const left = page.unasserted.length;
      await pages.receive({ command: 'assert', index: 0 });
      page = await settled((p) => p.unasserted.length < left, 'the assert');
    }
    assert.strictEqual(page.passed, true, page.failures.join());

    while (page.claims.length) {
      const left = page.claims.length;
      await pages.receive({ command: 'removeAssert', index: 0 });
      page = await settled((p) => p.claims.length < left, 'the assert gone');
    }
    assert.strictEqual(page.passed, false);

    // The attribute editor lists it, and deletes it.
    assert.ok(!editor.panel.visible, `the case page covers it: ${pages.panel.viewColumn}, ${editor.panel.viewColumn}`);
    editor.panel.reveal();
    await until(() => editor.panel.visible && editor.panel.webview.html.includes(`${NAME}.jsonld`),
      'the list as the last run saw it');
    await until(async () => (await editor.tests()).some((t) => t.file === file && t.fires.length),
      'the test in the attribute editor');
    await answered([{ kind: 'warning', button: 'Delete' }],
      () => editor.receive({ command: 'deleteTest', file }));
    assert.ok(!fs.existsSync(file), 'deleted');
    const declared = path.join(path.dirname(file), 'expectations.yaml');
    assert.ok(!fs.existsSync(declared) || !fs.readFileSync(declared, 'utf-8').includes(NAME));
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
