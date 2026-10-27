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
 * The package page: what the package IS, its settings and what it is made of.
 *
 * The Package view's rows, read as a page: each setting with what it decides
 * and an Edit… button, the namespace table with + Namespace and Remove, the
 * contents counted. A click on a row of the view opens this page with the
 * row marked -- semforge.yaml is the "Open semforge.yaml" button, not the
 * place a click lands. Every change runs the view's own command
 * (semforge.editSetting, addNamespace, removeNamespace), which keeps the
 * file's comments.
 */

const crypto = require('crypto');
const vscode = require('vscode');

const { showLocation } = require('./reveal');
const { escape } = require('./typepage');

const TONE = { error: 'bad', warning: 'warn' };

/** Every row of the payload, numbered in page order: the page posts the
 *  number, the extension finds the row again. */
function numbered(roots) {
  const rows = [];
  const walk = (row, depth) => {
    rows.push({ row, depth, index: rows.length });
    (row.children || []).forEach((child) => walk(child, depth + 1));
  };
  (roots || []).forEach((root) => walk(root, 0));
  return rows;
}

/** Which row a focus names: a setting by its key, anything else by its label. */
function focusIndex(rows, focus) {
  if (!focus) {
    return -1;
  }
  return rows.findIndex(({ row }) => (focus.key && row.key === focus.key) ||
    (!focus.key && focus.label && row.label === focus.label));
}

function chip(text, tone, title) {
  return `<span class="chip ${tone || ''}"${title ? ` title="${escape(title)}"` : ''}>` +
    `${escape(text)}</span>`;
}

function actions(row, index) {
  const out = [];
  if (row.kind === 'setting' && row.editable) {
    out.push(`<button data-act="edit" data-row="${index}" title="Change it in semforge.yaml, ` +
      'its comment kept">Edit…</button>');
  }
  if (row.kind === 'namespaces') {
    out.push(`<button data-act="addNamespace" data-row="${index}" ` +
      'title="Agree a name for a namespace, for the whole package">+ Namespace</button>');
  }
  if (row.kind === 'namespaceEntry') {
    out.push(`<button data-act="removeNamespace" data-row="${index}">Remove</button>`);
  }
  if (row.kind === 'cache') {
    out.push('<button data-act="rescan">Rescan</button>');
  }
  return out.join('');
}

function rowHtml(row, index, depth, focused) {
  const tone = TONE[row.severity];
  return `<tr class="${index === focused ? 'focus' : ''} depth${Math.min(depth, 3)}"` +
    `${index === focused ? ' id="focus"' : ''}>` +
    `<td class="label">${escape(row.label)}</td>` +
    `<td class="value">${row.value ? `<span class="mono">${escape(row.value)}</span>` : ''}` +
    `${tone ? ` ${chip(row.severity, tone)}` : ''}</td>` +
    // What it decides: the row's own note, else the setting's documentation.
    `<td class="detail">${escape(row.detail || row.doc || '')}</td>` +
    `<td class="acts">${actions(row, index)}</td></tr>`;
}

/** One top-level row as a heading, everything under it as its table; a
 *  row with nothing under it (the cache) is its own one-row table. */
function section(root, rows, focused) {
  const start = rows.find(({ row }) => row === root).index;
  const body = rows.filter(({ row }) => contains(root, row));
  const own = actions(root, start);
  return `<h2>${escape(root.label)}${root.detail ? ` <span class="dim">· ${escape(root.detail)}</span>` : ''}` +
    `${own && body.length ? ` <span class="acts">${own}</span>` : ''}</h2>` +
    `<table><tbody>${body.length
      ? body.map(({ row, depth, index }) => rowHtml(row, index, depth - 1, focused)).join('')
      : rowHtml(root, start, 0, focused)}</tbody></table>`;
}

function contains(parent, row) {
  return (parent.children || []).some((child) => child === row || contains(child, row));
}

function renderPackagePage(payload, options) {
  const nonce = (options && options.nonce) || '';
  const csp = `default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';`;
  const rows = numbered(payload.roots);
  const focused = focusIndex(rows, options && options.focus);
  const roots = payload.roots || [];
  const name = (roots.find((r) => r.kind === 'project') || {}).detail || '';
  const manifest = payload.manifest;
  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(name)}</title>
<style nonce="${nonce}">
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); padding: 12px 20px; }
  h1 { font-size: 1.3em; margin: 0 0 4px; }
  h2 { font-size: 1.05em; margin: 18px 0 6px; }
  .dim { color: var(--vscode-descriptionForeground); font-weight: normal; }
  .mono { font-family: var(--vscode-editor-font-family); font-size: 0.92em; overflow-wrap: anywhere; }
  .bar { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0 4px; }
  table { border-collapse: collapse; width: 100%; table-layout: fixed; }
  td { padding: 4px 8px; vertical-align: top; border-bottom: 1px solid var(--vscode-panel-border, rgba(128,128,128,.2)); }
  td.label { width: 22%; } td.value { width: 30%; } td.acts { width: 16%; text-align: right; }
  td.detail { color: var(--vscode-descriptionForeground); }
  tr.depth1 td.label { padding-left: 22px; } tr.depth2 td.label { padding-left: 36px; }
  tr.depth3 td.label { padding-left: 50px; }
  tr.focus td { background: var(--vscode-editor-selectionHighlightBackground, rgba(128,128,128,.2)); }
  tr.focus td:first-child { box-shadow: inset 3px 0 0 var(--vscode-focusBorder, #0078d4); }
  .chip { border-radius: 10px; padding: 0 7px; font-size: 0.85em; background: var(--vscode-badge-background);
          color: var(--vscode-badge-foreground); }
  .chip.bad { background: var(--vscode-inputValidation-errorBackground, #5a1d1d); }
  .chip.warn { background: var(--vscode-inputValidation-warningBackground, #5a4a1d); }
  button { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground);
           border: none; padding: 3px 10px; border-radius: 3px; cursor: pointer; margin-left: 4px; }
  button:hover { background: var(--vscode-button-secondaryHoverBackground); }
</style></head><body>
<h1>Package: ${escape(name)}</h1>
<div class="dim mono">${escape(payload.root || '')}</div>
<div class="bar">
  <button data-act="health" title="Cases, violations, untested constraints">Health</button>
  ${manifest ? `<button data-open="${escape(manifest)}:1">Open semforge.yaml</button>` : ''}
  <button data-act="refresh">Refresh</button>
</div>
${roots.map((root) => section(root, rows, focused)).join('')}
<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  const focused = document.getElementById('focus');
  if (focused) { focused.scrollIntoView({ block: 'center' }); }
  document.addEventListener('click', (event) => {
    const target = event.target.closest('button');
    if (!target) { return; }
    const d = target.dataset;
    if (d.open) { vscode.postMessage({ command: 'open', at: d.open }); return; }
    vscode.postMessage({ command: d.act, row: d.row === undefined ? undefined : Number(d.row) });
  });
</script>
</body></html>`;
}

class PackagePage {
  constructor(clientHolder, session) {
    this.clientHolder = clientHolder;
    this.session = session;
    this.panel = undefined;
    this.packageUri = undefined;
    this.focus = undefined;
    this.payload = undefined;
  }

  /** `focus` marks one row: {key} for a setting, {label} for anything else. */
  async show(packageUri, focus, preserveFocus) {
    if (!this.clientHolder.client || !packageUri) {
      vscode.window.showWarningMessage(
        'SemForge: no package is open, or the language server is not running.');
      return;
    }
    this.packageUri = packageUri;
    this.focus = focus;
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        'semforgePackagePage', 'Package', { viewColumn: vscode.ViewColumn.Active,
          preserveFocus: !!preserveFocus },
        { enableScripts: true, localResourceRoots: [] });
      this.panel.onDidDispose(() => { this.panel = undefined; });
      this.panel.webview.onDidReceiveMessage((message) => this.receive(message));
    } else {
      this.panel.reveal(undefined, !!preserveFocus);
    }
    await this.render();
  }

  async render() {
    if (!this.panel || !this.packageUri) {
      return;
    }
    let payload;
    try {
      payload = await this.clientHolder.client.sendRequest('semforge/project',
        { uri: this.packageUri });
    } catch (error) {
      payload = { roots: [], error: error.message || String(error) };
    }
    if (!this.panel) {
      return;
    }
    if (payload.error && !(payload.roots || []).length) {
      this.panel.webview.html = `<!DOCTYPE html><html><head><meta charset="utf-8">` +
        `<meta http-equiv="Content-Security-Policy" content="default-src 'none';"></head>` +
        `<body style="font-family:var(--vscode-font-family);color:var(--vscode-foreground);` +
        `padding:20px"><p>SemForge: ${escape(payload.error)}</p></body></html>`;
      return;
    }
    // The manifest's own row says where semforge.yaml is, when there is one.
    const manifest = numbered(payload.roots).map(({ row }) => row)
      .find((row) => row.label === 'manifest' && row.definedAt);
    this.payload = Object.assign({}, payload,
      { manifest: manifest ? manifest.definedAt.replace(/:\d+$/, '') : '' });
    const name = ((payload.roots || []).find((r) => r.kind === 'project') || {}).detail;
    this.panel.title = name ? `Package: ${name}` : 'Package';
    this.panel.webview.html = renderPackagePage(this.payload,
      { nonce: crypto.randomBytes(16).toString('base64'), focus: this.focus });
  }

  async receive(message) {
    if (!message || !this.packageUri) {
      return;
    }
    const rows = this.payload ? numbered(this.payload.roots) : [];
    const row = message.row === undefined ? undefined : (rows[message.row] || {}).row;
    const node = (raw) => ({ raw, packageUri: this.packageUri });
    if (message.command === 'open' && message.at) {
      await showLocation(message.at, true);
      return;
    }
    if (message.command === 'health') {
      await vscode.commands.executeCommand('semforge.openHealthPage', node({ kind: 'health' }));
      return;
    }
    const run = { edit: 'semforge.editSetting', addNamespace: 'semforge.addNamespace',
      removeNamespace: 'semforge.removeNamespace', rescan: 'semforge.rescan' }[message.command];
    if (run) {
      // The view's own command, on the view's own row: the same questions,
      // the same write. The page then shows what it wrote.
      if (row) {
        this.focus = row.key ? { key: row.key } : { label: row.label };
      }
      await vscode.commands.executeCommand(run, node(row || {}));
    }
    await this.render();
  }

  refresh() {
    if (this.panel && this.panel.visible) {
      this.render();
    }
  }
}

function register(context, clientHolder, session) {
  const page = new PackagePage(clientHolder, session);
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.openPackagePage', async (node, options) => {
      const raw = node && node.raw;
      const focus = raw && (raw.key ? { key: raw.key } : raw.label ? { label: raw.label } : undefined);
      await page.show((node && node.packageUri) || session.uri, focus,
        !!(options && options.preserveFocus));
    }),
    vscode.workspace.onDidSaveTextDocument(() => page.refresh())
  );
  return page;
}

module.exports = { register, renderPackagePage, PackagePage, numbered, focusIndex };
