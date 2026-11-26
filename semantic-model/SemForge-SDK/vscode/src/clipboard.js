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
 * Copy an entity, or it and its children, and paste it into a test case: where
 * one is, not by its name from a list. Children are what a relationship made
 * from a HasChild reference leads to; the server knows by its shape. What is
 * copied is taken then, so the original may change or go; what is pasted is a
 * copy.
 */

const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const some = (ids) => (ids.length === 1 ? ids[0] : `${ids.length} entities`);
const listed = (ids) => ids.slice(0, 8).join('\n') + (ids.length > 8 ? `\n… and ${ids.length - 8} more` : '');

/** What a copy left out, or is not sure of, as a status bar says it. */
function notes(held, subtree) {
  const said = [];
  if (subtree && held.copied.length === 1 && !held.missing.length) {
    said.push('it has no children: it points at nothing by a HasChild reference');
  }
  if (held.assumed.length) {
    said.push(`${held.assumed.length} of them by the data, no shape declares the relationship`);
  }
  if (held.missing.length) {
    said.push(`${held.missing.length} child${held.missing.length === 1 ? ' is' : 'ren are'} written nowhere`);
  }
  if (held.left.length) {
    said.push(`${held.left.length} other${held.left.length === 1 ? '' : 's'} pointed at, not copied`);
  }
  if (held.repeated.length) {
    said.push(`${some(held.repeated)} defined more than once, the first copied`);
  }
  return said;
}

/** What a paste says about its copy: what was left out of it. */
function leftOut(held) {
  return [
    ...(held.missing.length ? [`${some(held.missing)} written nowhere`] : []),
    ...(held.left.length ? [`${some(held.left)} pointed at, not copied`] : []),
    ...(held.repeated.length ? [`${some(held.repeated)} defined more than once, the first copied`] : [])];
}

/** The file behind links, as one name for it. On Windows a name is the same
 * in any case: Python and Node may spell the drive letter differently. */
function real(file) {
  let found = file;
  try {
    found = fs.realpathSync.native(file);
  } catch (error) {
    // not on disk: as it is named
  }
  return process.platform === 'win32' ? found.toLowerCase() : found;
}

class Clipboard {
  constructor(clientHolder, onDone) {
    Object.assign(this, { clientHolder, onDone, held: undefined, last: Promise.resolve(), queue: Promise.resolve() });
  }

  /** Take a copy of the entity of a row (or a card), with `subtree` of
   *  its children and theirs, and hold it to be pasted. What was held before
   *  goes when this starts: a copy that fails must not paste the one before. */
  copy(node, subtree) {
    this.held = undefined;
    vscode.commands.executeCommand('setContext', 'semforge.canPaste', false);
    const taken = this.take(node, subtree);
    // A paste waits for the copy that was under way when it was asked for.
    this.last = taken.catch(() => undefined);
    return this.hold(taken, this.last, subtree);
  }

  async hold(taken, turn, subtree) {
    const held = await taken;
    if (!held || this.last !== turn) {
      return held;                     // failed, or another copy has started since
    }
    this.held = held;
    await vscode.commands.executeCommand('setContext', 'semforge.canPaste', true);
    const said = notes(held, subtree);
    const below = held.copied.length - 1;
    vscode.window.setStatusBarMessage(`SemForge: ${held.entity}${below ? ` and ${below} below it` : ''} copied` +
      `${said.length ? ` (${said.join('; ')})` : ''} — paste in a test case`, 8000);
    return held;
  }

  async take(node, subtree) {
    const raw = (node && node.raw) || {};
    const client = this.clientHolder.client;
    if (raw.kind !== 'entity' || !raw.entity || !client) {
      vscode.window.showInformationMessage('SemForge: Copy works on an entity.');
      return undefined;
    }
    const done = await client.sendRequest('semforge/copyEntities', { uri: node.packageUri, entity: raw.entity,
      file: raw.file || undefined, subtree: Boolean(subtree) });
    if (!done.ok) {
      vscode.window.showErrorMessage(`SemForge: ${done.error}`);
      return undefined;
    }
    const held = { packageUri: node.packageUri, entity: raw.entity, content: done.content };
    for (const ids of ['copied', 'missing', 'left', 'assumed', 'repeated']) {
      held[ids] = done[ids] || [];
    }
    return held;
  }

  /** Paste what is held -- or `held` -- into a case, given by its file. */
  paste(packageUri, caseFile, held) {
    // One after the other, each with what was copied when it was asked for.
    const what = held ? Promise.resolve(held) : this.last;
    const done = this.queue.then(async () => this.write(packageUri, caseFile, await what));
    this.queue = done.catch(() => undefined);
    return done;
  }

  /** Has the case's file, whatever it is opened as, edits that are not saved? */
  unsaved(plan) {
    const file = real(plan.real || plan.file);
    const open = (vscode.workspace.textDocuments || []).some((d) => d.isDirty && d.uri.fsPath &&
      real(d.uri.fsPath) === file);
    if (open) {
      vscode.window.showErrorMessage(`SemForge: ${path.basename(plan.file)} has unsaved edits. Save or discard ` +
        'them, then paste.');
    }
    return open;
  }

  async write(packageUri, caseFile, what) {
    const client = this.clientHolder.client;
    if (!what) {
      vscode.window.showInformationMessage('SemForge: nothing to paste. Copy an entity first: right-click it, ' +
        'Copy entity or Copy with subtree.');
      return undefined;
    }
    if (!caseFile || !client) {
      vscode.window.showInformationMessage('SemForge: Paste works in a test case.');
      return undefined;
    }
    const params = { uri: packageUri, case: caseFile, content: what.content };
    const plan = await client.sendRequest('semforge/pasteEntities', Object.assign({ check: true }, params));
    if (!plan.ok) {
      vscode.window.showErrorMessage(`SemForge: ${plan.error}`);
      return undefined;
    }
    if (this.unsaved(plan)) {
      return undefined;
    }
    const replace = plan.present.length ? await this.askToReplace(plan) : false;
    if (replace === undefined) {
      return undefined;
    }
    if (!plan.pasted.length && !replace) {
      vscode.window.showInformationMessage(`SemForge: nothing pasted into ${plan.case}: ` + [
        ...(plan.same.length ? [`it has ${some(plan.same)} just like that already`] : []),
        ...(plan.included.length
          ? [`${some(plan.included)} in a file it includes, and changed there`] : []),
        ...leftOut(what)
      ].join('; ') + '.');
      return undefined;
    }
    if (plan.shared.length && !(await this.askShared(plan))) {
      return undefined;
    }
    if (this.unsaved(plan)) {          // edited while the question was open
      return undefined;
    }
    const done = await client.sendRequest('semforge/pasteEntities',
      Object.assign({ replace, plan: plan.plan }, params));
    if (!done.ok) {
      vscode.window.showErrorMessage(`SemForge: ${done.error}`);
      return undefined;
    }
    this.onDone();
    const kept = [
      ...(done.included.length ? [`${some(done.included)} left, in a file it includes`] : []),
      ...(done.present.length && !replace ? [`${some(done.present)} left as it has`] : []),
      ...(done.same.length ? [`${some(done.same)} there already`] : []),
      ...leftOut(what)];
    vscode.window.setStatusBarMessage(`SemForge: ${some(done.pasted)} pasted into ${done.case}` +
      (kept.length ? ` (${kept.join('; ')})` : ''), 8000);
    return done;
  }

  /** true, false for only what the case has not, undefined to do nothing. */
  async askToReplace(plan) {
    const fresh = plan.pasted.length;
    const spelled = plan.spelled || {};
    const only = `Paste only the other ${fresh}`;
    const answer = await vscode.window.showWarningMessage(
      `${path.basename(plan.file)} has ${some(plan.present)} already, with other values.`,
      { modal: true, detail: `${listed(plan.present.map((id) => id + (spelled[id] ? ` (${spelled[id]} there)` : '')))}` +
        '\n\nReplaced, the values in the case are lost' +
        `${Object.keys(spelled).length ? ', and the id is spelled as copied' : ''}.` },
      'Replace', ...(fresh ? [only] : []));
    return answer === 'Replace' ? true : answer === only ? false : undefined;
  }

  async askShared(plan) {
    const cases = plan.shared.length === 1 ? 'another case includes' : `${plan.shared.length} other cases include`;
    return (await vscode.window.showWarningMessage(
      `Pasting into ${path.basename(plan.file)} changes what ${cases}.`,
      { modal: true, detail: listed(plan.shared) }, 'Paste anyway')) === 'Paste anyway';
  }
}

module.exports = { Clipboard };
