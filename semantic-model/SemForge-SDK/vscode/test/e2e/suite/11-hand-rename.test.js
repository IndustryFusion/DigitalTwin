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

// A shape renamed by typing in shacl.ttl, in a real VS Code: the save is
// noticed and what still names the old shape is carried along; an assert
// left behind gets a quick fix that names what it meant; and F2 on a shape's
// name runs Rename… itself. Every rename is undone at the end of its test.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, semforge, row, until, answering, read,
  restoreShapeName } = require('./helpers');

const EXAMPLES = path.join(WORKSPACE, 'examples');
const SHACL = path.join(WORKSPACE, 'shacl.ttl');

async function summary(api) {
  return until(async () => {
    const raw = (await row(api.trees.model,
      (r) => r.kind === 'group' && r.label === 'Tests', 'Tests')).raw;
    return raw.detail && `${raw.detail} ${raw.severity || ''}`;
  }, 'the Tests summary');
}

/** Rename by typing: every `iffBaseShacl:<from> ` in the open editor, then save. */
async function typeRename(from, to) {
  const doc = await vscode.workspace.openTextDocument(SHACL);
  await vscode.window.showTextDocument(doc, { preview: false });
  const edit = new vscode.WorkspaceEdit();
  const text = doc.getText();
  const needle = `iffBaseShacl:${from} `;
  for (let at = text.indexOf(needle); at >= 0; at = text.indexOf(needle, at + 1)) {
    edit.replace(doc.uri, new vscode.Range(doc.positionAt(at), doc.positionAt(at + needle.length)),
      `iffBaseShacl:${to} `);
  }
  await vscode.workspace.applyEdit(edit);
  await doc.save();
  return doc;
}

// Undone by hand: Rename… would keep a random part, the suites after expect
// the corpus as it was.
const renameBack = restoreShapeName;

describe('A shape renamed by typing', () => {
  it('is noticed on save, and its asserts and suite are carried along', async () => {
    const api = await semforge();
    const before = await summary(api);
    const session = answering([{ kind: 'message', button: 'Update them and rename test_CartridgeShape' }]);
    try {
      await typeRename('CartridgeShape', 'CartridgeCheckShape');
      await until(() => fs.existsSync(path.join(EXAMPLES, 'test_CartridgeCheckShape')),
        'the offer to be taken and the suite renamed');
    } finally {
      session.restore();
    }
    assert.ok(session.asked[0].offered.message.includes(
      'CartridgeShape is gone and CartridgeCheckShape says exactly what it said. Renamed?'));
    assert.ok(read('examples/test_CartridgeCheckShape/bad/expectations.yaml')
      .includes('iffBaseShacl:CartridgeCheckShape/hasCartridge/MaxCountConstraintComponent'));
    assert.strictEqual(await until(async () => {
      const now = await summary(api);
      return now === before && now;
    }, 'the cases to test as before'), before);
    await renameBack(api, 'CartridgeCheckShape', 'CartridgeShape', true);
  });

  it('leaves a stale assert whose quick fix names what it meant', async () => {
    const api = await semforge();
    const session = answering([{ kind: 'message' }]);          // dismissed
    try {
      await typeRename('WorkpieceShape', 'WorkpieceCheckShape');
      await until(() => session.asked.length, 'the offer');
    } finally {
      session.restore();
    }
    const yaml = vscode.Uri.file(path.join(EXAMPLES, 'test_WorkpieceShape', 'bad', 'expectations.yaml'));
    await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(yaml),
      { preview: false });
    const stale = await until(() => vscode.languages.getDiagnostics(yaml)
      .find((d) => String(d.code && (d.code.value || d.code)) === 'stale-assert'), 'the stale assert');
    const actions = await until(async () => {
      const found = await vscode.commands.executeCommand('vscode.executeCodeActionProvider',
        yaml, stale.range);
      return found && found.length && found;
    }, 'its quick fixes');
    const fix = actions.find((a) => a.title.startsWith('Rename the assert to'));
    assert.ok(fix, actions.map((a) => a.title).join(' | '));
    assert.strictEqual(fix.title,
      'Rename the assert to iffBaseShacl:WorkpieceCheckShape/hasHeight/MaxInclusiveConstraintComponent');
    await vscode.commands.executeCommand(fix.command.command, ...fix.command.arguments);
    await until(() => read('examples/test_WorkpieceShape/bad/expectations.yaml')
      .includes('iffBaseShacl:WorkpieceCheckShape/hasHeight'), 'the assert renamed');
    await until(() => !vscode.languages.getDiagnostics(yaml)
      .some((d) => String(d.code && (d.code.value || d.code)) === 'stale-assert'), 'the error to go');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    await renameBack(api, 'WorkpieceCheckShape', 'WorkpieceShape', false);
  });

  it('F2 on a shape\'s name runs Rename…', async () => {
    const api = await semforge();
    const doc = await vscode.workspace.openTextDocument(SHACL);
    await vscode.window.showTextDocument(doc, { preview: false });
    const line = doc.getText().split('\n').findIndex((l) => l.startsWith('iffBaseShacl:WorkpieceShape a'));
    const position = new vscode.Position(line, 'iffBaseShacl:Work'.length);
    const prepared = await vscode.commands.executeCommand('vscode.prepareRename', doc.uri, position);
    assert.strictEqual(prepared.placeholder, 'WorkpieceShape');
    const session = answering([{ kind: 'warning', button: 'Rename it and test_WorkpieceShape' }]);
    try {
      await vscode.commands.executeCommand('vscode.executeDocumentRenameProvider', doc.uri,
        position, 'WorkpieceF2Shape');
    } finally {
      session.restore();
    }
    // Rename… named it with a random part: WorkpieceF2Shape-3f9a1c2e.
    const renamed = read('shacl.ttl').match(/iffBaseShacl:(WorkpieceF2Shape-[0-9a-f]{8}) a/);
    assert.ok(renamed, 'renamed, with its random part');
    const name = renamed[1];
    assert.ok(fs.existsSync(path.join(EXAMPLES, `test_${name}`)), 'its suite went along');
    assert.ok(read(`examples/test_${name}/bad/expectations.yaml`)
      .includes(`iffBaseShacl:${name}/hasHeight`));
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    await renameBack(api, name, 'WorkpieceShape', true);
  });
});
