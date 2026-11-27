/*
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

'use strict';

/**
 * Undo, Redo and History… over the package's own git history
 * (package/history.py on the server): every SemForge change is a commit, a
 * change made outside SemForge is committed before any step, and a step back
 * is itself undone by Redo -- so nothing is ever lost, and nothing is asked.
 *
 * Reachable where the work is: Ctrl+Z / Ctrl+Shift+Z in SemForge's views, the
 * ↶ ↷ buttons on Entities & Test Cases, the "↶ Undo" item in the status bar
 * (its tooltip says what it takes back), and the command palette.
 */

const path = require('path');
const vscode = require('vscode');
const { refreshViews } = require('./rename');

function short(title) {
  return String(title || '').replace(/^SemForge: /, '');
}

function ago(iso) {
  const seconds = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (!Number.isFinite(seconds)) {
    return '';
  }
  if (seconds < 90) {
    return 'just now';
  }
  if (seconds < 5400) {
    return `${Math.round(seconds / 60)} min ago`;
  }
  if (seconds < 129600) {
    return `${Math.round(seconds / 3600)} h ago`;
  }
  return `${Math.round(seconds / 86400)} d ago`;
}

/** Package files with unsaved edits: a step would change the files under them. */
function unsaved(root) {
  return vscode.workspace.textDocuments.filter((d) => d.isDirty && d.uri.scheme === 'file' &&
    root && (d.uri.fsPath === root || d.uri.fsPath.startsWith(root + path.sep)));
}

function register(context, clientHolder, session) {
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 1);
  item.command = 'semforge.undo';
  context.subscriptions.push(item);
  let state = { mode: 'none' };
  let asking = 0;

  async function refresh() {
    const client = clientHolder.client;
    const uri = session.uri;
    if (!client || !uri) {
      item.hide();
      return state;
    }
    const mine = ++asking;
    let answer;
    try {
      answer = await client.sendRequest('semforge/history', { uri });
    } catch (error) {
      answer = { ok: false };
    }
    if (mine !== asking) {
      return state;                     // a newer answer is on its way
    }
    state = answer && answer.ok ? answer : { mode: 'none' };
    await vscode.commands.executeCommand('setContext', 'semforge.canUndo', !!state.undo);
    await vscode.commands.executeCommand('setContext', 'semforge.canRedo', !!state.redo);
    if (state.mode !== 'own') {
      item.hide();
      return state;
    }
    item.text = '$(discard) Undo';
    item.tooltip = (state.undo ? `Undo: ${short(state.undo)}` : 'Nothing to undo') +
      (state.redo ? `\nRedo: ${short(state.redo)}` : '') +
      '\n\nCtrl+Z / Ctrl+Shift+Z in SemForge views · History… in the command palette';
    item.show();
    return state;
  }

  let soon;
  function refreshSoon() {
    clearTimeout(soon);
    soon = setTimeout(() => refresh(), 400);
  }

  async function step(method, params, said) {
    const client = clientHolder.client;
    const uri = session.uri;
    if (!client || !uri) {
      vscode.window.showInformationMessage('SemForge: no package is open.');
      return undefined;
    }
    // The package's root comes with its history state, asked for anew and for
    // this package -- not taken from a refresh still on its way, which may be
    // the previous package's.
    let now;
    try {
      now = await client.sendRequest('semforge/history', { uri });
    } catch (error) {
      now = {};
    }
    const dirty = unsaved((now && now.root) || session.directory || '');
    if (dirty.length) {
      vscode.window.showWarningMessage('SemForge: save or discard the unsaved edits first — ' +
        `undo changes the files under them: ${dirty.map((d) => path.basename(d.uri.fsPath)).join(', ')}`);
      return undefined;
    }
    const done = await client.sendRequest(method, Object.assign({ uri }, params));
    if (!done.ok) {
      vscode.window[done.refused ? 'showInformationMessage' : 'showErrorMessage'](
        `SemForge: ${done.error}`);
      await refresh();
      return done;
    }
    refreshViews();
    await refresh();
    vscode.window.setStatusBarMessage(`SemForge: ${said(done)}`, 6000);
    return done;
  }

  const undo = () => step('semforge/undo', {}, (done) =>
    `undone — ${short(done.undone)}${state.redo ? ' (Redo: Ctrl+Shift+Z)' : ''}`);
  const redo = () => step('semforge/redo', {}, (done) => `redone — ${short(done.redone)}`);

  async function history() {
    const now = await refresh();
    if (now.mode !== 'own' && now.reason) {
      // Why there is none: marked, turned off, a repository SemForge did not
      // start, linked files, no git -- the server says which.
      vscode.window.showInformationMessage(`SemForge: ${now.reason}.`);
      return undefined;
    }
    if (now.mode !== 'own' || !now.log || !now.log.length) {
      vscode.window.showInformationMessage('SemForge: this package has no history yet.');
      return undefined;
    }
    const items = now.log.map((entry, index) => ({
      label: `${index === 0 ? '$(circle-filled)' : '$(circle-outline)'} ${short(entry.title)}`,
      description: [ago(entry.date), ...(entry.tags || [])].filter(Boolean).join(' · '),
      detail: index === 0 ? 'now' : `back to here: ${index} step${index === 1 ? '' : 's'} undone (Redo brings them back)`,
      entry, index
    }));
    const picked = await vscode.window.showQuickPick(items,
      { title: 'SemForge: History — go back to…', matchOnDescription: true });
    if (!picked || picked.index === 0) {
      return undefined;
    }
    return step('semforge/backTo', { sha: picked.entry.sha }, (done) =>
      `back to “${short(done.now)}” — ${done.undone.length} step(s) undone`);
  }

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.undo', undo),
    vscode.commands.registerCommand('semforge.redo', redo),
    vscode.commands.registerCommand('semforge.history', history),
    session.onDidChange(() => refresh()),
    vscode.workspace.onDidSaveTextDocument(() => refreshSoon()),
    // Verdicts come in bursts: one history request after the burst, not one each.
    ...(clientHolder.onVerdicts ? [clientHolder.onVerdicts(() => refreshSoon())] : []),
    { dispose: () => clearTimeout(soon) });
  refresh();
  return { refresh, undo, redo, history, state: () => state };
}

module.exports = { register, short, ago };
