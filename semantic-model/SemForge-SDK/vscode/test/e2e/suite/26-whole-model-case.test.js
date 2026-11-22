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

// New test case… from the whole main model, in a real VS Code: the documents
// of the model are written into the new case, which is declared in its
// suite's expectations.yaml, run once and opened on its case page; the model
// file is left as it was.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, PACKAGE_URI, semforge, until, answering, read } = require('./helpers');

const SUITE = 'test_whole-model';

describe('New test case… from the whole main model', () => {
  after(async () => {
    // The suites after this one expect the corpus's suites as they were.
    fs.rmSync(path.join(WORKSPACE, 'examples', SUITE), { recursive: true, force: true });
    await vscode.commands.executeCommand('semforge.refreshModel');
  });

  it('a bad case holding every document of the model, declared and run', async () => {
    const api = await semforge();
    const model = read('model-instance.jsonld');
    // Saved before anything is replaced, and put back whatever happens.
    const originals = { showInformationMessage: vscode.window.showInformationMessage,
      showWarningMessage: vscode.window.showWarningMessage };
    const session = answering([
      { kind: 'pick', label: '$(new-folder) New suite…' },
      { kind: 'input', value: 'whole-model' },
      { kind: 'pick', label: '$(error) Should violate' },
      { kind: 'pick', label: '$(symbol-namespace) The whole main model' },
      { kind: 'input', value: 'everything' }]);
    // What the case says once written depends on whether the model conforms
    // when this runs (the suites before may have edited it): a notice either
    // way, read and dismissed here.
    const notices = [];
    for (const name of ['showInformationMessage', 'showWarningMessage']) {
      const inner = vscode.window[name];
      vscode.window[name] = async (message, ...rest) => {
        if (String(message).includes(SUITE)) {
          notices.push(message);
          return undefined;
        }
        return inner(message, ...rest);
      };
    }
    let made;
    try {
      made = await vscode.commands.executeCommand('semforge.newTestCase',
        { packageUri: PACKAGE_URI });
    } finally {
      session.restore();
      Object.assign(vscode.window, originals);
    }
    assert.ok(made && made.ok, JSON.stringify(made));
    const file = path.join(WORKSPACE, 'examples', SUITE, 'bad', 'everything.jsonld');
    assert.strictEqual(made.file, file);
    assert.strictEqual(made.expect, 'invalid');
    const documents = JSON.parse(model);
    assert.deepStrictEqual(JSON.parse(fs.readFileSync(file, 'utf-8')),
      Array.isArray(documents) ? documents : [documents], 'every document of the model');
    assert.strictEqual(read('model-instance.jsonld'), model, 'the model is left as it was');

    const declared = read(`examples/${SUITE}/bad/expectations.yaml`);
    assert.ok(declared.includes('path: everything.jsonld'), declared);
    assert.ok(declared.includes('expect: invalid'), declared);
    assert.ok(!declared.includes('include:'), 'written in, not included');
    // Run once: whether the model conforms decides what the case still needs.
    // (A long description is folded over lines.)
    assert.ok(declared.replace(/\s+/g, ' ')
      .includes(made.violations ? 'violates already' : 'which conforms'), declared);
    if (!made.violations) {
      assert.strictEqual(made.passes, false, 'a conforming model fails as a bad case');
      assert.ok(notices.some((text) => text.includes('Nothing fires yet')), notices.join('\n'));
    } else {
      assert.strictEqual(notices.length, 1, 'it was said whether it passes');
    }
    await until(() => api.pages.case.page && api.pages.case.page.file === file, 'its case page');

    // The case is edited on its own: the model does not follow.
    fs.writeFileSync(file, '[]\n');
    assert.strictEqual(read('model-instance.jsonld'), model);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
