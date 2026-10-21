/*
 * The package health page: is this package in good shape, and what needs
 * attention first. Test results, model violations, untested constraints,
 * broken references and the cache, side by side, then one list ordered by
 * severity where every item opens the thing it is about.
 *
 * Computed by the SDK (`semforge/health`) and only rendered here;
 * `renderHealthPage` is pure and escapes everything it shows.
 */

const crypto = require('crypto');
const vscode = require('vscode');

const { showLocation } = require('./reveal');
const { escape } = require('./typepage');

const SEVERITY_CLASS = { error: 'bad', warning: 'warn', note: '' };

function tile(value, label, tone, title) {
  return `<div class="tile ${tone || ''}"${title ? ` title="${escape(title)}"` : ''}>` +
    `<span class="n">${escape(value)}</span><span class="s">${escape(label)}</span></div>`;
}

function action(item) {
  if (item.case) {
    return `<button data-case="${escape(item.case)}">Open case</button>`;
  }
  if (item.type) {
    return `<button data-type="${escape(item.type)}">Open ${escape(item.type)}</button>`;
  }
  if (item.at) {
    return `<button data-open="${escape(item.at)}">Open</button>`;
  }
  return '';
}

function renderHealthPage(page, options) {
  const nonce = (options && options.nonce) || '';
  const csp = `default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';`;
  const t = page.tiles || {};
  const items = page.attention || [];
  const counts = page.counts || {};
  const tiles = [
    tile(`${t.casesPassing} / ${t.cases}`, 'test cases pass',
      t.cases === 0 ? 'warn' : t.casesPassing === t.cases ? 'good' : 'bad',
      t.cases === 0 ? 'No test case is declared: nothing proves a constraint can fire.' : ''),
    tile(t.modelViolations, t.modelViolations === 1 ? 'violation in the model'
      : 'violations in the model', t.modelViolations ? 'warn' : 'good',
    t.modelConstraints ? `from ${t.modelConstraints} constraint(s)` : ''),
    tile(t.evaluated, 'constraints evaluated'),
    tile(t.neverFired, `never fired, in ${t.neverFiredShapes} shape(s)`,
      t.neverFired ? 'warn' : 'good',
      'A constraint no example makes fire looks exactly like one that holds.'),
    tile(t.brokenReferences, 'broken references', t.brokenReferences ? 'bad' : 'good'),
    tile(t.cacheViews ? (t.cacheCurrent === t.cacheViews ? 'current' : `${t.cacheCurrent} / ${t.cacheViews}`)
      : 'empty', 'cache', t.cacheViews && t.cacheCurrent === t.cacheViews ? 'good' : '')
  ].join('');

  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(page.name)}</title>
<style nonce="${nonce}">
  body { font-family: var(--vscode-font-family); font-size: var(--vscode-font-size);
         color: var(--vscode-foreground); background: var(--vscode-editor-background);
         padding: 16px 22px 40px; line-height: 1.45; }
  .dim { color: var(--vscode-descriptionForeground); }
  .head { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: baseline;
          justify-content: space-between; }
  h1 { font-size: 1.5em; font-weight: 600; margin: 0; }
  h2 { font-size: 0.78em; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
       color: var(--vscode-descriptionForeground); margin: 24px 0 8px; }
  .bar { display: flex; gap: 8px; }
  button { font: inherit; color: var(--vscode-button-secondaryForeground, inherit);
           background: var(--vscode-button-secondaryBackground, transparent);
           border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35));
           padding: 2px 10px; border-radius: 2px; cursor: pointer; white-space: nowrap; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
           gap: 10px; margin-top: 14px; }
  .tile { border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); border-radius: 4px;
          padding: 10px 12px; display: grid; gap: 2px; }
  .tile .n { font-size: 1.7em; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.15; }
  .tile .s { font-size: 0.9em; color: var(--vscode-descriptionForeground); }
  .tile.good .n { color: var(--vscode-testing-iconPassed, #388a34); }
  .tile.warn .n { color: var(--vscode-editorWarning-foreground, #cca700); }
  .tile.bad .n { color: var(--vscode-errorForeground, #f14c4c); }
  .items { display: grid; gap: 6px; }
  .item { display: grid; grid-template-columns: 5.5em 6.5em 1fr auto; gap: 10px; align-items: baseline;
          padding: 6px 10px; border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .chip { font-size: 0.82em; padding: 1px 8px; border-radius: 999px; text-align: center;
          border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .chip.bad { color: var(--vscode-errorForeground, #f14c4c); border-color: currentColor; }
  .chip.warn { color: var(--vscode-editorWarning-foreground, #cca700); border-color: currentColor; }
  .area { color: var(--vscode-descriptionForeground); font-size: 0.9em; }
  .what { min-width: 0; overflow-wrap: anywhere; }
  .empty { color: var(--vscode-testing-iconPassed, #388a34); }
  @media (max-width: 640px) { .item { grid-template-columns: 1fr; } }
</style></head><body>
<div class="head">
  <div><h1>${escape(page.name)}</h1><div class="dim">${escape(page.path)}</div></div>
  <div class="bar"><button data-rescan="1">Rescan</button><button data-refresh="1">Refresh</button></div>
</div>
<div class="tiles">${tiles}</div>

<h2>Needs attention${items.length ? ` · ${counts.error || 0} error(s), ${counts.warning || 0} warning(s), ` +
    `${counts.note || 0} note(s)` : ''}</h2>
${items.length ? `<div class="items">${items.map((item) => `<div class="item">` +
    `<span class="chip ${SEVERITY_CLASS[item.severity] || ''}">${escape(item.severity)}</span>` +
    `<span class="area">${escape(item.area)}</span>` +
    `<span class="what">${escape(item.text)}</span>${action(item)}</div>`).join('')}</div>`
    : '<p class="empty">Nothing needs attention: every case passes, every reference resolves, ' +
      'and every constraint has an example that makes it fire.</p>'}

<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  document.addEventListener('click', (event) => {
    const target = event.target.closest('button');
    if (!target) { return; }
    const d = target.dataset;
    if (d.open) { vscode.postMessage({ command: 'open', at: d.open }); }
    else if (d.case) { vscode.postMessage({ command: 'case', file: d.case }); }
    else if (d.type) { vscode.postMessage({ command: 'type', name: d.type }); }
    else if (d.rescan) { vscode.postMessage({ command: 'rescan' }); }
    else { vscode.postMessage({ command: 'refresh' }); }
  });
</script>
</body></html>`;
}

class HealthPage {
  constructor(clientHolder, session) {
    this.clientHolder = clientHolder;
    this.session = session;
    this.panel = undefined;
    this.packageUri = undefined;
  }

  async show(packageUri) {
    if (!this.clientHolder.client || !packageUri) {
      vscode.window.showWarningMessage(
        'SemForge: no package is open, or the language server is not running.');
      return;
    }
    this.packageUri = packageUri;
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        'semforgeHealthPage', 'Package health', vscode.ViewColumn.Active,
        { enableScripts: true, localResourceRoots: [] });
      this.panel.onDidDispose(() => { this.panel = undefined; });
      this.panel.webview.onDidReceiveMessage((message) => this.receive(message));
    } else {
      this.panel.reveal(undefined, false);
    }
    await this.render();
  }

  async render() {
    if (!this.panel || !this.packageUri) {
      return;
    }
    let page;
    try {
      page = await this.clientHolder.client.sendRequest('semforge/health',
        { uri: this.packageUri });
    } catch (error) {
      page = { ok: false, error: error.message || String(error) };
    }
    if (!this.panel) {
      return;
    }
    if (!page.ok) {
      this.panel.webview.html = `<!DOCTYPE html><html><head><meta charset="utf-8">` +
        `<meta http-equiv="Content-Security-Policy" content="default-src 'none';"></head>` +
        `<body style="font-family:var(--vscode-font-family);color:var(--vscode-foreground);` +
        `padding:20px"><p>SemForge: ${escape(page.error)}</p></body></html>`;
      return;
    }
    this.panel.title = `${page.name} · health`;
    this.panel.webview.html = renderHealthPage(page,
      { nonce: crypto.randomBytes(16).toString('base64') });
  }

  async receive(message) {
    if (!message || !this.packageUri) {
      return;
    }
    const node = (raw) => ({ raw, packageUri: this.packageUri });
    if (message.command === 'open' && message.at) {
      await showLocation(message.at, true);
    } else if (message.command === 'case' && message.file) {
      await vscode.commands.executeCommand('semforge.openCasePage',
        node({ kind: 'example', label: message.file.split('/').pop(), file: message.file }));
    } else if (message.command === 'type' && message.name) {
      await vscode.commands.executeCommand('semforge.openTypePage',
        node({ targetClass: message.name }));
    } else if (message.command === 'rescan') {
      await vscode.commands.executeCommand('semforge.rescan', { packageUri: this.packageUri });
      await this.render();
    } else if (message.command === 'refresh') {
      await this.render();
    }
  }

  refresh() {
    if (this.panel && this.panel.visible) {
      this.render();
    }
  }
}

function register(context, clientHolder, session) {
  const page = new HealthPage(clientHolder, session);
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.openHealthPage', async (node) => {
      await page.show((node && node.packageUri) || session.uri);
    }),
    vscode.workspace.onDidSaveTextDocument(() => page.refresh())
  );
  return page;
}

module.exports = { register, renderHealthPage, HealthPage };
