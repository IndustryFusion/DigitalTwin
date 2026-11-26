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
 * Moving the editor to a node's location.
 *
 * Shared by both trees so selection behaves the same in each: the Examples tree
 * had no such wiring at all, which is why selecting an entity moved nothing.
 */

const vscode = require('vscode');

/** `file:line` -> { file, line }, tolerating a Windows drive letter. */
function splitLocation(at) {
  const split = (at || '').lastIndexOf(':');
  if (split < 0) {
    return undefined;
  }
  const line = parseInt(at.slice(split + 1), 10);
  if (Number.isNaN(line)) {
    return undefined;
  }
  return { file: at.slice(0, split), line: Math.max(line - 1, 0) };
}

/** Put the cursor on a file:line. Keeps focus in the tree unless asked. */
async function showLocation(at, focus) {
  const where = splitLocation(at);
  if (!where) {
    return;
  }
  const document = await vscode.workspace.openTextDocument(where.file);
  const editor = await vscode.window.showTextDocument(document, {
    preserveFocus: !focus,
    preview: true
  });
  const position = new vscode.Position(where.line, 0);
  editor.selection = new vscode.Selection(position, position);
  editor.revealRange(
    new vscode.Range(position, position),
    vscode.TextEditorRevealType.InCenter
  );
}

/**
 * How much the trees show: 'summary' (one row per attribute, said in the type
 * page's words) or 'full' (every SHACL parameter, editable in place).
 */
function treeDetail() {
  const value = vscode.workspace.getConfiguration('semforge').get('trees.detail');
  return value === 'full' ? 'full' : 'summary';
}

/** What a click on a tree row opens: its page, or its place in the source. */
function treeClick() {
  const value = vscode.workspace.getConfiguration('semforge').get('trees.click');
  return value === 'source' ? 'source' : 'page';
}

// Status is the icon's COLOUR, never a different icon: a row keeps the shape
// that says what it is, and the description says in words what is wrong.
const TONES = {
  error: 'list.errorForeground',
  violation: 'list.errorForeground',
  warning: 'list.warningForeground',
  ok: 'testing.iconPassed',
  inherited: 'disabledForeground'
};

function icon(name, tone) {
  const colour = TONES[tone];
  return colour
    ? new vscode.ThemeIcon(name, new vscode.ThemeColor(colour))
    : new vscode.ThemeIcon(name);
}

/**
 * What a row of a view does when it is clicked -- EVERY time it is clicked.
 *
 * A view's selection changes only when another row is chosen: a click on the
 * row already selected -- "Main · 2 violation(s)", clicked again after the
 * page was closed -- did nothing at all. So each row also carries a command
 * that runs `handler` on a click, and the selection still runs it for the
 * keyboard. A click that also changes the selection would run it twice; the
 * second, for the same row within moments, is skipped.
 */
function rowClicks(view, provider, command, handler) {
  let last = { node: undefined, at: 0 };
  const once = async (node) => {
    if (!node) {
      return;
    }
    const now = Date.now();
    if (last.node === node && now - last.at < 600) {
      return;
    }
    last = { node, at: now };
    await handler({ selection: [node] });
  };
  const original = provider.getTreeItem.bind(provider);
  provider.getTreeItem = (node) => {
    const attach = (item) => {
      if (item && !item.command) {
        item.command = { command, title: 'Open', arguments: [node] };
      }
      return item;
    };
    const item = original(node);
    return item && typeof item.then === 'function' ? item.then(attach) : attach(item);
  };
  const registered = vscode.commands.registerCommand(command, once);
  const selected = view.onDidChangeSelection((event) =>
    once(event && event.selection && event.selection[0]));
  return { dispose: () => { registered.dispose(); selected.dispose(); } };
}

const html = (text) => String(text).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
  .replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** What VS Code hands a page's right-click commands: an attribute, read from
 *  where the click was and everything around it. */
function contextAttribute(said) {
  return ` data-vscode-context="${html(JSON.stringify(said))}"`;
}

/**
 * What an entity's id on a page carries: Reveal in graph view, on a right
 * click (package.json, webview/context) and on the button beside it. `file`:
 * the test case that holds the entity, none for the main model.
 */
function revealContext(id, file) {
  return contextAttribute(Object.assign({ webviewSection: 'semforgeEntity', entity: id },
    file ? { case: file } : {}));
}

function revealButton(id, file) {
  return `<button type="button" class="reveal" data-reveal="${html(id)}"${file ? ` data-revealcase="${html(file)}"` : ''}` +
    ` title="Reveal in graph view" aria-label="Reveal ${html(id)} in graph view">⌖</button>`;
}

const REVEAL_CSS = `
  button.reveal { font: inherit; line-height: 1; border: 0; background: none; padding: 0 3px; cursor: pointer;
                  color: var(--vscode-textLink-foreground); }
  button.reveal:hover { color: var(--vscode-textLink-activeForeground, var(--vscode-textLink-foreground)); }
  button.reveal:focus-visible { outline: 1px solid var(--vscode-focusBorder, #0078d4); }
`;

module.exports = { splitLocation, showLocation, treeDetail, treeClick, icon, rowClicks,
  contextAttribute, revealContext, revealButton, REVEAL_CSS };
