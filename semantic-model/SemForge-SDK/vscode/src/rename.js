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

/*
 * Rename… for a shape, a test case and a suite.
 *
 * A shape's name is written in more places than its declaration -- other
 * shapes' `sh:node`, a SPARQL body, every assert naming one of its
 * constraints, the digest of every residue it is part of -- so the SDK plans
 * the rename and this file says the plan before anything is written. A case
 * is its file and a suite its folder: those are moves, with the entries that
 * point at them following.
 *
 * Editors showing a moved file are closed and the file reopened where it went;
 * the SPARQL workbench of a renamed shape is closed (its query document is
 * named by the shape).
 */

const path = require('path');
const vscode = require('vscode');

const REFRESH_VIEWS = ['semforge.refreshShapes', 'semforge.refreshTree',
  'semforge.refreshModel'];

const NAME = /^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)*$/;

function validName(text) {
  return NAME.test(String(text || '').trim()) ? undefined
    : 'a letter or "_" first, then letters, digits, "_", "-" and "." (not at the end)';
}

function refreshViews() {
  for (const command of REFRESH_VIEWS) {
    vscode.commands.executeCommand(command);
  }
}

async function ask(client, method, params) {
  const answer = await client.sendRequest(method, params);
  if (!answer.ok) {
    vscode.window.showErrorMessage(`SemForge: ${answer.error}`);
    return undefined;
  }
  return answer;
}

/** Tabs showing a file at or under `where`, closed; the files they showed. */
async function closeTabs(where, scheme) {
  const groups = vscode.window.tabGroups;
  if (!groups) {
    return [];
  }
  const tabs = groups.all.flatMap((g) => g.tabs).filter((t) => t.input && t.input.uri &&
    (scheme ? t.input.uri.scheme === scheme && t.input.uri.path === where
      : t.input.uri.scheme === 'file' && (t.input.uri.fsPath === where ||
        t.input.uri.fsPath.startsWith(where + path.sep))));
  const files = tabs.map((t) => t.input.uri.fsPath);
  if (tabs.length) {
    await groups.close(tabs);
  }
  return files;
}

async function reopen(files, from, to) {
  for (const file of files) {
    const moved = to + file.slice(from.length);
    await vscode.window.showTextDocument(vscode.Uri.file(moved), { preview: false });
  }
}

/** What renaming says before it writes. */
function planned(plan) {
  const lines = [];
  for (const file of plan.files) {
    lines.push(`${path.basename(file.file)}: ${file.references} reference(s)` +
      (file.inQueries ? `, ${file.inQueries} of them in a SPARQL query` : ''));
  }
  const asserts = plan.asserts.reduce((sum, a) => sum + a.count, 0);
  if (asserts) {
    lines.push(`${asserts} assert(s) in ${plan.asserts.length} test case(s) name it: renamed with it.`);
  }
  if (plan.residues.length) {
    lines.push(`${plan.residues.length} case(s) pin a residue: each that holds now is pinned ` +
      'again, since a rename changes no verdict.');
  }
  return lines.join('\n');
}

async function renameShape(clientHolder, session, node, bench, preset) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  const shape = node && node.raw && node.raw.shape;
  if (!client || !packageUri || !shape) {
    vscode.window.showWarningMessage('SemForge: Rename… works on a shape.');
    return undefined;
  }
  const old = shape.split(/[/#]/).pop();
  // F2 in the .ttl already asked for the name in its own box.
  const name = preset !== undefined ? preset : await vscode.window.showInputBox({
    title: `Rename ${old}`, value: old, valueSelection: [0, old.length],
    prompt: 'Its new name, in the same namespace; its random part (-3f9a1c2e) stays. Every reference, assert and residue follows.',
    validateInput: (text) => text.trim() === old ? 'that is its name' : validName(text)
  });
  if (!name || name.trim() === old) {
    return undefined;
  }
  const invalid = validName(name);
  if (invalid) {
    vscode.window.showErrorMessage(`SemForge: ${name.trim()} is not a shape name: ${invalid}`);
    return undefined;
  }
  const plan = await ask(client, 'semforge/renameShapePlan',
    { uri: packageUri, shape, name: name.trim() });
  if (!plan) {
    return undefined;
  }
  const buttons = ['Rename'];
  if (plan.suite && plan.suite.free) {
    buttons.unshift(`Rename it and ${plan.suite.from}`);
  }
  const detail = planned(plan) + (plan.suite ? '\n\n' + (plan.suite.free
    ? `The suite folder ${plan.suite.from} can be renamed to ${plan.suite.to} too.`
    : `${plan.suite.to} already exists, so ${plan.suite.from} keeps its name.`) : '');
  const answer = await vscode.window.showWarningMessage(
    `Rename ${plan.name} to ${plan.newCurie}?`, { modal: true, detail }, ...buttons);
  if (!answer) {
    return undefined;
  }
  // The workbench's query document is named by the shape: it goes.
  if (bench && bench.current && bench.current.shape === shape && bench.panel) {
    if (bench.uri) {
      await bench.close(bench.uri);
    }
    bench.panel.dispose();
  }
  const suite = answer !== 'Rename';
  const done = await ask(client, 'semforge/renameShape',
    { uri: packageUri, shape, name: name.trim(), suite });
  if (!done) {
    return undefined;
  }
  refreshViews();
  await vscode.commands.executeCommand('semforge.openShapePage',
    { raw: { shape: done.newIri }, packageUri });
  vscode.window.showInformationMessage(`SemForge: ${done.oldName} is now ${done.newName}` +
    (done.asserts ? `, with ${done.asserts} assert(s)` : '') +
    (done.repinned.length ? `; ${done.repinned.length} residue(s) pinned again` : '') +
    (done.suiteMoved ? `; its suite is ${done.suiteMoved}` : '') + '.');
  return done;
}

async function renameCase(clientHolder, session, node) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  const file = node && node.raw && node.raw.file;
  if (!client || !packageUri || !file) {
    vscode.window.showWarningMessage('SemForge: Rename… works on a test case.');
    return undefined;
  }
  const old = path.basename(file).replace(/\.jsonld$/, '');
  const name = await vscode.window.showInputBox({
    title: `Rename the case ${old}`, value: old, valueSelection: [0, old.length],
    prompt: 'Its new file name (.jsonld is kept). Its expectations entry follows.',
    validateInput: (text) => text.trim().replace(/\.jsonld$/, '') === old ? 'that is its name'
      : validName(text.trim().replace(/\.jsonld$/, ''))
  });
  if (!name) {
    return undefined;
  }
  const open = await closeTabs(file);
  const done = await ask(client, 'semforge/renameCase',
    { uri: packageUri, case: file, name: name.trim() });
  if (!done) {
    await reopen(open, file, file);
    return undefined;
  }
  await reopen(open, file, done.file);
  refreshViews();
  await vscode.commands.executeCommand('semforge.openCasePage',
    { raw: { kind: 'example', file: done.file }, packageUri });
  return done;
}

async function renameSuite(clientHolder, session, node) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  const raw = node && node.raw;
  const folder = raw && (raw.term || raw.label);
  if (!client || !packageUri || !raw || raw.kind !== 'suite' || !folder) {
    vscode.window.showWarningMessage('SemForge: Rename… works on a suite.');
    return undefined;
  }
  const old = folder.split('/').pop();
  const name = await vscode.window.showInputBox({
    title: `Rename the suite ${old}`, value: old, valueSelection: [0, old.length],
    prompt: 'Its new folder name. Nothing inside it changes.',
    validateInput: (text) => text.trim() === old ? 'that is its name' : validName(text)
  });
  if (!name) {
    return undefined;
  }
  const done = await ask(client, 'semforge/renameSuite',
    { uri: packageUri, suite: folder, name: name.trim() });
  if (!done) {
    return undefined;
  }
  // Editors of files in the folder now show a path that is gone.
  await reopen(await closeTabs(done.source), done.source, done.folder);
  refreshViews();
  return done;
}

/**
 * The server saw a shape vanish from the .ttl as one saying exactly the same
 * appeared: a rename typed into the file, which carried nothing along. Offer
 * to update what still names the old shape -- its asserts, residues pinned
 * under the old name, and its test_<Shape> suite.
 */
async function offerFollow(clientHolder, notice) {
  const what = [];
  if (notice.asserts) {
    what.push(`${notice.asserts} assert(s) still name ${notice.name}`);
  }
  if (notice.suite) {
    what.push(`its suite is still ${notice.suite.from}`);
  }
  const buttons = ['Update them'];
  if (notice.suite && notice.suite.free) {
    buttons.unshift(`Update them and rename ${notice.suite.from}`);
  }
  const answer = await vscode.window.showInformationMessage(
    `SemForge: ${notice.oldName} is gone and ${notice.newName} says exactly what it said. ` +
      `Renamed? ${what.join('; ')}.`, ...buttons);
  if (!answer || !clientHolder.client) {
    return undefined;
  }
  const done = await ask(clientHolder.client, 'semforge/followRename', {
    uri: notice.uri, shape: notice.shape, newIri: notice.newIri,
    suite: answer !== 'Update them' });
  if (!done) {
    return undefined;
  }
  refreshViews();
  vscode.window.setStatusBarMessage(`SemForge: ${notice.newName} — ` +
    `${done.asserts} assert(s) updated` +
    (done.repinned.length ? `, ${done.repinned.length} residue(s) pinned again` : '') +
    (done.suiteMoved ? `, suite now ${done.suiteMoved}` : ''), 6000);
  return done;
}

/** The node shape whose name is under the cursor, or an Error saying why not. */
async function shapeAt(clientHolder, document, position) {
  if (!clientHolder.client) {
    throw new Error('SemForge: the language server is not running.');
  }
  const at = await clientHolder.client.sendRequest('semforge/shapeAt', {
    uri: document.uri.toString(), line: position.line, character: position.character });
  if (!at.ok) {
    throw new Error(`SemForge: ${at.error}`);
  }
  return at;
}

/**
 * F2 on a shape's name in a .ttl runs Rename…, not a text replace: a shape's
 * name is also in asserts, residues and its suite's folder, which no edit of
 * this file reaches. The rename writes the files itself and the edit VS Code
 * gets back is empty -- the changed files reload from disk.
 */
const RENAME_PROVIDER = (clientHolder, session, bench) => ({
  async prepareRename(document, position) {
    const at = await shapeAt(clientHolder, document, position);
    return { placeholder: at.placeholder,
      range: new vscode.Range(at.range.start.line, at.range.start.character,
        at.range.end.line, at.range.end.character) };
  },
  async provideRenameEdits(document, position, newName) {
    const at = await shapeAt(clientHolder, document, position);
    if (document.isDirty) {
      await document.save();       // the rename reads and writes the file on disk
    }
    await renameShape(clientHolder, session,
      { raw: { shape: at.shape }, packageUri: document.uri.toString() }, bench, newName);
    return new vscode.WorkspaceEdit();
  }
});

function register(context, clientHolder, session, bench) {
  if (vscode.languages && vscode.languages.registerRenameProvider) {
    context.subscriptions.push(vscode.languages.registerRenameProvider(
      [{ scheme: 'file', language: 'turtle' }, { scheme: 'file', pattern: '**/*.ttl' }],
      RENAME_PROVIDER(clientHolder, session, bench)));
  }
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.renameShape',
      (node) => renameShape(clientHolder, session, node, bench)),
    vscode.commands.registerCommand('semforge.renameTestCase',
      (node) => renameCase(clientHolder, session, node)),
    vscode.commands.registerCommand('semforge.renameSuite',
      (node) => renameSuite(clientHolder, session, node))
  );
}

module.exports = { register, renameShape, renameCase, renameSuite, validName, offerFollow,
  RENAME_PROVIDER, closeTabs, refreshViews };
