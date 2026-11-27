//
// Copyright (c) 2026 IndustryFusion Foundation
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//    http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

/**
 * Remove an entity from the file it is written in, where one is: its row or its
 * card. Asked first, with what refers to it; nothing but the entity is removed.
 */

const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const listed = (ids) => ids.slice(0, 8).join('\n') + (ids.length > 8 ? `\n… and ${ids.length - 8} more` : '');

/** The file behind links, as one name for it -- on Windows in any case. Both
 *  sides go through this: the server's name for it may be spelled otherwise. */
function real(file) {
  let found = file;
  try {
    found = fs.realpathSync.native(file);
  } catch (error) {
    // not on disk: as it is named
  }
  return process.platform === 'win32' ? found.toLowerCase() : found;
}

/** Has the file, whatever it is opened as, edits that are not saved? */
function unsaved(plan) {
  const file = real(plan.file);
  const open = (vscode.workspace.textDocuments || []).some((d) => d.isDirty && d.uri.fsPath &&
    real(d.uri.fsPath) === file);
  if (open) {
    vscode.window.showErrorMessage(`SemForge: ${path.basename(plan.file)} has unsaved edits. Save or discard ` +
      'them, then remove.');
  }
  return open;
}

/** What the question says below itself. */
function consequences(plan) {
  const file = path.basename(plan.file);
  const shared = plan.cases.length > (plan.model ? 0 : 1);
  return [
    `It goes from ${file}, with all its attributes${plan.model ? '. That is the main model' : ''}.`,
    plan.empty ? 'No entity is left in the file.' : '',
    plan.remains ? 'The file defines it once more: that definition stays.' : '',
    shared ? `${plan.cases.length === 1 ? 'A case uses' : `${plan.cases.length} cases use`} this file and ` +
      `${plan.cases.length === 1 ? 'changes' : 'change'}:\n${listed(plan.cases)}` : '',
    plan.pointing.length ? `Still pointing at it in this file:\n${listed(plan.pointing)}` : '',
    plan.asserts.length ? `Asserting something on it, which stays as it is:\n${listed(plan.asserts)}` : '',
    plan.unread ? `What points at it is not known: ${plan.unread}` : ''
  ].filter(Boolean).join('\n\n');
}

/** Remove what a row -- or `raw` of a card -- stands for. `onDone` when the
 *  file is, or may be, another than what is shown. */
async function removeEntity(clientHolder, node, onDone) {
  const raw = (node && node.raw) || {};
  const client = clientHolder.client;
  if (raw.kind !== 'entity' || !raw.entity || !client) {
    vscode.window.showInformationMessage('SemForge: Remove entity works on an entity of a file.');
    return undefined;
  }
  const params = { uri: node.packageUri, entity: raw.entity, file: raw.file || undefined,
    position: raw.position, digest: raw.digest };
  const ask = async (more) => {
    let answer;
    try {
      answer = await client.sendRequest('semforge/removeEntity', Object.assign({}, params, more));
    } catch (error) {
      answer = { ok: false, error: error.message || String(error) };
    }
    if (!answer || !answer.ok) {
      vscode.window.showErrorMessage(`SemForge: ${(answer && answer.error) || 'no answer from the server'}`);
      onDone();                        // shown anew, it can be asked again
      return undefined;
    }
    return answer;
  };
  const plan = await ask({ check: true });
  if (!plan || unsaved(plan)) {
    return undefined;
  }
  const answer = await vscode.window.showWarningMessage(`Remove ${raw.entity}?`,
    { modal: true, detail: consequences(plan) }, 'Remove');
  if (answer !== 'Remove' || unsaved(plan)) {        // edited while it was asked
    return undefined;
  }
  const done = await ask({ plan: plan.plan });
  if (done) {
    onDone();
    vscode.window.setStatusBarMessage(`SemForge: ${raw.entity} removed from ${path.basename(done.file)}`, 5000);
  }
  return done;
}

/** A reference a subtree takes with it, as a line: whose, which attribute, which instance. */
function reference(d) {
  const short = (key) => String(key).split(/[/#:]/).filter(Boolean).pop() || String(key);
  const attribute = (d.path || []).map(short).join(' › ');
  return `${d.entity} · ${attribute}${d.datasetId ? ` (${String(d.datasetId).split(/[/#]/).pop()})` : ''}`;
}

/** What the question of Remove with subtree… says below itself. */
function subtreeConsequences(plan, entity) {
  const file = path.basename(plan.file);
  const others = plan.removed.filter((id) => id !== entity);
  const shared = plan.cases.length > (plan.model ? 0 : 1);
  return [
    `They go from ${file}, with all their attributes${plan.model ? '. That is the main model' : ''}.`,
    others.length ? `In its subtree:\n${listed(others)}` : 'It has no children in this file.',
    plan.assumed.length ? `Children by the data only (no shape declares the reference):\n${listed(plan.assumed)}` : '',
    plan.dropped.length ? `References to them that go too:\n${listed(plan.dropped.map(reference))}` : '',
    plan.elsewhere.length ? `In its subtree, written in another file, and kept:\n${listed(plan.elsewhere)}` : '',
    plan.shared.length ? `Children another entity still points at, and kept:\n${listed(plan.shared)}` : '',
    plan.missing.length ? `Children written in no file, so not removed:\n${listed(plan.missing)}` : '',
    plan.unread ? `Some ids could not be read with their context and are compared as written: ${plan.unread}` : '',
    plan.empty ? 'No entity is left in the file.' : '',
    shared ? `${plan.cases.length === 1 ? 'A case uses' : `${plan.cases.length} cases use`} this file and ` +
      `${plan.cases.length === 1 ? 'changes' : 'change'}:\n${listed(plan.cases)}` : '',
    plan.asserts.length ? `Asserting something on them, which stays as it is:\n${listed(plan.asserts)}` : ''
  ].filter(Boolean).join('\n\n');
}

/** Remove a row's entity with the subtree Copy with subtree copies. */
async function removeSubtree(clientHolder, node, onDone) {
  const raw = (node && node.raw) || {};
  const client = clientHolder.client;
  if (raw.kind !== 'entity' || !raw.entity || !client) {
    vscode.window.showInformationMessage('SemForge: Remove with subtree works on an entity of a file.');
    return undefined;
  }
  const params = { uri: node.packageUri, entity: raw.entity, file: raw.file || undefined,
    digest: raw.digest, subtree: true };
  const ask = async (more) => {
    let answer;
    try {
      answer = await client.sendRequest('semforge/removeEntity', Object.assign({}, params, more));
    } catch (error) {
      answer = { ok: false, error: error.message || String(error) };
    }
    if (!answer || !answer.ok) {
      vscode.window.showErrorMessage(`SemForge: ${(answer && answer.error) || 'no answer from the server'}`);
      onDone();
      return undefined;
    }
    return answer;
  };
  const plan = await ask({ check: true });
  if (!plan || unsaved(plan)) {
    return undefined;
  }
  const count = plan.removed.length;
  const answer = await vscode.window.showWarningMessage(
    `Remove ${raw.entity} with its subtree (${count} entit${count === 1 ? 'y' : 'ies'})?`,
    { modal: true, detail: subtreeConsequences(plan, raw.entity) }, 'Remove');
  if (answer !== 'Remove' || unsaved(plan)) {
    return undefined;
  }
  const done = await ask({ plan: plan.plan });
  if (done) {
    onDone();
    vscode.window.setStatusBarMessage(`SemForge: ${raw.entity} removed with its subtree (${done.removed.length}) ` +
      `from ${path.basename(done.file)}`, 5000);
  }
  return done;
}

module.exports = { removeEntity, removeSubtree };
