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

// Delete… a case and a suite in a real VS Code, from their rows: the file and
// its entry go, the folders left empty go, what is left still tests -- and
// the question named the evidence the deletion costs. The case deleted is
// a failing twin it clones first, as 12-clone does.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, semforge, row, until, answering, read } = require('./helpers');

const EXAMPLES = path.join(WORKSPACE, 'examples');

async function suiteRow(api, folder) {
  return row(api.trees.model, (raw) => raw.kind === 'suite' && (raw.term || raw.label) === folder,
    folder);
}

/** The good case's failing twin, cloned as 12-clone does: the case deleted here. */
async function twinOf(api) {
  const original = (await api.trees.model.getChildren(await suiteRow(api, 'test_WorkpieceShape')))
    .find((n) => n.raw.kind === 'example' && n.raw.file.includes(`${path.sep}good${path.sep}`));
  const session = answering([
    { kind: 'pick', label: '$(arrow-swap) Expect the opposite' },
    { kind: 'input', value: `${path.basename(original.raw.file, '.jsonld')}-violates` },
    { kind: 'warning' }]);
  try {
    const made = await vscode.commands.executeCommand('semforge.cloneTestCase', original);
    assert.ok(made && made.ok, JSON.stringify(made));
  } finally {
    session.restore();
  }
  await vscode.commands.executeCommand('workbench.action.closeAllEditors');
}

describe('Delete… a test case and a suite', () => {
  it('a case, from its row', async () => {
    const api = await semforge();
    await twinOf(api);
    const children = await until(async () => {
      const now = await api.trees.model.getChildren(await suiteRow(api, 'test_WorkpieceShape'));
      return now.some((n) => n.raw.kind === 'example' && n.raw.file.endsWith('-violates.jsonld')) && now;
    }, 'the clone in the suite');
    const twin = children.find((n) => n.raw.kind === 'example' && n.raw.file.endsWith('-violates.jsonld'));
    const others = children.filter((n) => n !== twin && n.raw.kind === 'example').map((n) => n.raw.file);
    const session = answering([{ kind: 'warning', button: 'Delete' }]);
    let done;
    try {
      done = await vscode.commands.executeCommand('semforge.deleteTestCase', twin);
    } finally {
      session.restore();
    }
    assert.ok(done && done.ok, JSON.stringify(done));
    assert.ok(session.asked[0].offered.message.startsWith(`Delete ${path.basename(twin.raw.file)}?`));
    assert.ok(!fs.existsSync(twin.raw.file));
    assert.ok(!read('examples/test_WorkpieceShape/bad/expectations.yaml')
      .includes(path.basename(twin.raw.file)));
    for (const file of others) {
      assert.ok(fs.existsSync(file), `${file} stays`);
    }
    await until(async () => (await api.trees.model.getChildren(
      await suiteRow(api, 'test_WorkpieceShape'))).length === children.length - 1,
    'the view without it');
  });

  it('a suite, from its row, naming the evidence it costs', async () => {
    const api = await semforge();
    const suite = await suiteRow(api, 'test_CartridgeShape');
    const session = answering([{ kind: 'warning', button: 'Delete' }]);
    let done;
    try {
      done = await vscode.commands.executeCommand('semforge.deleteSuite', suite);
    } finally {
      session.restore();
    }
    assert.ok(done && done.ok, JSON.stringify(done));
    const asked = session.asked[0].offered.message;
    assert.ok(asked.startsWith('Delete the suite test_CartridgeShape?'), asked);
    assert.ok(done.lost.some((c) => c.includes('CartridgeShape/hasCartridge/MaxCountConstraintComponent')),
      done.lost.join(', '));
    assert.ok(!fs.existsSync(path.join(EXAMPLES, 'test_CartridgeShape')));
    await until(async () => {
      const tests = await row(api.trees.model,
        (raw) => raw.kind === 'group' && raw.label === 'Tests', 'Tests');
      const suites = await api.trees.model.getChildren(tests);
      return !suites.some((n) => (n.raw.term || n.raw.label) === 'test_CartridgeShape');
    }, 'the suite gone from the view');
  });
});
