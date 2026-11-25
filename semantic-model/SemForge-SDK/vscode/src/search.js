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
 * Search…: the views show only what fits, while one types.
 *
 * VS Code's own search finds lines and opens files, and from there no way led
 * back. Here every view -- entities and test cases, types, shapes, knowledge --
 * keeps only the rows that fit and what they are under, with the count on
 * top; a click opens the page, as always. The search stays until it is
 * cleared (the ✕ on a view, or an empty search). And from a file, Open in
 * SemForge goes to the page of what the cursor is on.
 */

const vscode = require('vscode');

let text = '';
let round = 0;                   // a new search draws its rows afresh
let refresh = () => {};
const counts = {};

/** What a view's request carries. */
function params(request) {
  return text ? Object.assign({}, request, { search: text }) : request;
}

/** A view's message while searching: how much fits. `other` is its own. */
function message(view, result, other) {
  if (!text) {
    return other;
  }
  if (result.search === undefined && !result.error) {
    // A language server that does not know the search: the rows are all of them.
    return 'Search: this language server does not filter the views. Restart it (SemForge: Restart Language Server).';
  }
  if (result.search !== text) {
    return other;                  // the answer to what was typed before: the next one counts
  }
  counts[view] = result.matches || 0;
  const said = counts[view] ? `Search “${text}”: ${counts[view]} found.`
    : `Search “${text}”: nothing here.`;
  return other ? `${said} ${other}` : said;
}

/** A row of a search: open down to what fits. VS Code remembers by id
 *  whether a row was open, so the rows of each search have their own. */
function decorate(item, raw) {
  if (text && raw.searchId !== undefined) {
    item.id = `search:${round}:${raw.searchId}`;
    if (item.collapsibleState !== vscode.TreeItemCollapsibleState.None) {
      item.collapsibleState = raw.expand ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.Collapsed;
    }
  }
  return item;
}

/** The rows under a row, the hidden ones too: what an edit goes by. */
function all(raw) {
  return raw.all || raw.children || [];
}

function current() {
  return text;
}

async function set(value) {
  const next = String(value || '').trim();
  if (next === text) {
    return;
  }
  text = next;
  round += 1;
  Object.keys(counts).forEach((key) => delete counts[key]);
  await vscode.commands.executeCommand('setContext', 'semforge.searching', !!text);
  refresh();
}

const NAMES = { model: 'Entities & Test Cases', constraints: 'Constraints by Type',
  shapes: 'SHACL Shapes as Written', knowledge: 'Knowledge (Ontology)' };

/** Ask, filtering as one types. Enter keeps it, Escape puts back what was. */
function ask() {
  const before = text;
  return new Promise((resolve) => {
    const box = vscode.window.createInputBox();
    box.title = 'Search this model';
    box.placeholder = 'A type, attribute, entity, value, constraint… — every word must fit';
    box.prompt = 'The views show only what fits. Enter keeps it; empty shows everything.';
    box.value = before;
    let timer;
    let kept = false;
    box.onDidChangeValue((value) => {
      clearTimeout(timer);
      timer = setTimeout(() => set(value), 300);
    });
    box.onDidAccept(async () => {
      clearTimeout(timer);
      kept = true;
      await set(box.value);
      box.hide();
    });
    box.onDidHide(async () => {
      clearTimeout(timer);
      if (!kept) {
        await set(before);
      }
      box.dispose();
      resolve(text);
    });
    box.show();
  });
}

/** The page of what the cursor is on, in a file of a package. */
async function openHere(clientHolder) {
  const editor = vscode.window.activeTextEditor;
  const client = clientHolder.client;
  if (!editor || !client) {
    vscode.window.showWarningMessage('SemForge: open a file of a package first.');
    return undefined;
  }
  const uri = editor.document.uri.toString();
  const at = editor.selection.active;
  const range = editor.document.getWordRangeAtPosition(at, /[A-Za-z_][\w.:-]*/);
  const found = await client.sendRequest('semforge/pageAt', { uri, line: at.line + 1,
    token: range ? editor.document.getText(range) : '',
    text: editor.document.isDirty ? editor.document.getText() : undefined });
  if (!found.ok) {
    vscode.window.showErrorMessage(`SemForge: ${found.error}`);
    return undefined;
  }
  const run = (command, raw, options) =>
    vscode.commands.executeCommand(command, { raw, packageUri: uri }, options);
  if (found.page === 'shape') {
    await run('semforge.openShapePage', { shape: found.shape });
  } else if (found.page === 'type') {
    await run('semforge.openTypePage', { targetClass: found.targetClass, focusNames: found.focusNames });
  } else if (found.page === 'vocabulary') {
    await run('semforge.openVocabularyPage', { kind: 'class', iri: found.cls }, { focus: found.focus || undefined });
  } else if (found.page === 'case') {
    await run('semforge.openCasePage', { kind: 'example', file: found.file }, { focus: found.focus || undefined });
  } else if (found.page === 'model') {
    await vscode.commands.executeCommand('semforge.openModelPage', { packageUri: uri },
      { focus: found.focus || undefined });
  } else if (found.text) {
    // Nothing here has a page of its own: where it shows up, instead.
    await vscode.commands.executeCommand('semforge.showDetails');
    await set(found.text);
  } else {
    vscode.window.showInformationMessage('SemForge: nothing on this line has a page.');
  }
  return found;
}

function register(context, clientHolder, refreshAll) {
  refresh = refreshAll;
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.search', async () => {
      // All four views: what fits may be in the details column only.
      await vscode.commands.executeCommand('semforge.showDetails');
      const kept = await ask();
      if (kept) {
        const said = Object.keys(NAMES).filter((view) => counts[view])
          .map((view) => `${NAMES[view]} ${counts[view]}`).join(' · ');
        vscode.window.setStatusBarMessage(`SemForge: “${kept}” — ${said || 'searching…'}`, 8000);
      }
      return kept;
    }),
    vscode.commands.registerCommand('semforge.clearSearch', () => set('')),
    vscode.commands.registerCommand('semforge.openHere', () => openHere(clientHolder)));
}

module.exports = { register, params, message, decorate, all, current, set };
