/*
 * The SPARQL workbench: one SPARQL query of a shape, the data it runs over,
 * and what it returns -- to develop a SPARQL constraint (or rule) against the
 * very graph validation hands it.
 *
 * The query is edited in a real editor beside the page: a document
 * `semforge-sparql:/<Shape>.rq`, read from and saved into the shape's
 * literal in shacl.ttl by the file system provider below, with the language
 * server's completion, diagnostics, hover, formatting and quick fixes. The
 * page runs what the editor holds: Apply (Ctrl+Enter in the editor) the way
 * validation does -- once per focus node, $this bound -- Inspect
 * (Ctrl+Shift+Enter, or the toggle on the result), Snapshot. Revert is the
 * editor's Revert, Save is its Save (Ctrl+S), which refuses if the literal
 * changed underneath; both show only while the editor has unsaved changes,
 * the rest waits behind ⋯.
 *
 * `renderSparqlBench` is a pure function from the `semforge/sparqlBench`
 * payload; results arrive later by postMessage, so a run never resets the
 * editor.
 */

const crypto = require('crypto');
const vscode = require('vscode');

const { showLocation } = require('./reveal');
const { escape } = require('./typepage');

const REFRESH_VIEWS = ['semforge.refreshTree', 'semforge.refreshShapes',
  'semforge.refreshModel', 'semforge.refreshKnowledge'];

function chip(text, tone, title) {
  return `<span class="chip ${tone || ''}"${title ? ` title="${escape(title)}"` : ''}>` +
    `${escape(text)}</span>`;
}

/** sh:severity as a reader says it: base:severityCritical -> critical. */
function severityText(severity) {
  const local = String(severity || '').split(/[/#:]/).pop();
  return local.replace(/^severity/i, '').toLowerCase();
}

const SEVERITY_TIP = 'SHACL severity: how serious a result of this constraint is WHEN it ' +
  'fires -- violation (the data does not conform; the default), warning (reported, the data ' +
  'still conforms) or info. It does not say whether it fires.';

/** The severity as a label, not a verdict: neutral, and "(default)" when the
 *  shape never said -- a red "violation" chip read as something failing. */
function severityLabel(severity, declared) {
  const text = severityText(severity) || 'violation';
  return `<span class="severity" title="${escape(SEVERITY_TIP)}">severity: ${escape(text)}` +
    `${declared ? '' : ' <span class="dim">(default)</span>'}</span>`;
}

function renderSparqlBench(page, options) {
  const nonce = (options && options.nonce) || '';
  const csp = `default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';`;
  const holder = page.holder;
  const rule = holder.kind === 'rule';
  const tabs = page.holders.length > 1
    ? `<div class="tabs">${page.holders.map((h) =>
      `<button class="tab${h.index === holder.index ? ' on' : ''}" data-holder="${h.index}" ` +
      `title="line ${h.line}">${escape(h.kind)} ${h.index + 1}${h.message
        ? ` · ${escape(h.message.slice(0, 40))}` : ''}</button>`).join('')}</div>` : '';
  const sources = page.sources.map((s) => `<option value="${escape(s.id)}"` +
    `${s.id === page.source ? ' selected' : ''}>${escape(s.label)}` +
    `${s.expect ? ` (${escape(s.expect)})` : ''}</option>`).join('');
  const state = { kind: holder.kind, message: holder.message,
    dirty: !!(options && options.dirty),
    snapshots: (options && options.snapshots) || [] };
  const file = (options && options.file) || `${page.label}.rq`;
  const selects = page.selector;
  const severity = severityText(holder.severity);
  const focus = page.focus.length;

  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(page.label)} · SPARQL</title>
<style nonce="${nonce}">
  body { font-family: var(--vscode-font-family); font-size: var(--vscode-font-size);
         color: var(--vscode-foreground); background: var(--vscode-editor-background);
         padding: 14px 20px 40px; line-height: 1.45; }
  a { color: var(--vscode-textLink-foreground); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .dim { color: var(--vscode-descriptionForeground); }
  .severity { font-size: 0.86em; color: var(--vscode-descriptionForeground); white-space: nowrap; }
  .crumbs { font-size: 0.9em; }
  .head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  h1 { font-size: 1.4em; font-weight: 600; margin: 2px 0; }
  .head .right { margin-left: auto; }
  .message { margin: 0 0 6px; }
  h2 { font-size: 0.78em; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
       color: var(--vscode-descriptionForeground); margin: 0; flex: 1 1 auto; }
  .sechead { display: flex; align-items: baseline; gap: 10px; margin: 18px 0 6px; padding-bottom: 4px;
             border-bottom: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .bar, .tabs { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .toolbar { margin: 10px 0 4px; padding: 8px 10px; border-radius: 3px;
             background: var(--vscode-sideBar-background, rgba(128,128,128,.06)); }
  .sechead .status { font-size: 0.9em; }
  .chip { font-size: 0.86em; padding: 1px 8px; border-radius: 999px; white-space: nowrap;
          border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .chip.ok { color: var(--vscode-testing-iconPassed, #388a34); border-color: currentColor; }
  .chip.bad { color: var(--vscode-errorForeground, #f14c4c); border-color: currentColor; }
  .chip.warn { color: var(--vscode-editorWarning-foreground, #cca700); border-color: currentColor; }
  button { font: inherit; color: var(--vscode-button-secondaryForeground, inherit);
           background: var(--vscode-button-secondaryBackground, transparent);
           border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35));
           padding: 3px 12px; border-radius: 2px; cursor: pointer; }
  button.primary { color: var(--vscode-button-foreground); background: var(--vscode-button-background);
                   border-color: var(--vscode-button-background); }
  .tab.on { border-color: var(--vscode-focusBorder, #0078d4); }
  select { font: inherit; color: var(--vscode-dropdown-foreground); padding: 2px 4px; max-width: 22em;
           background: var(--vscode-dropdown-background); border: 1px solid var(--vscode-dropdown-border); }
  label.toggle { font-size: 0.92em; color: var(--vscode-descriptionForeground); cursor: pointer; }
  pre { font-family: var(--vscode-editor-font-family); font-size: 0.9em; margin: 4px 0 0;
        padding: 8px; overflow: auto; max-height: 28em;
        background: var(--vscode-textCodeBlock-background, rgba(128,128,128,.1)); }
  table { border-collapse: collapse; width: 100%; font-size: 0.92em; }
  th, td { text-align: left; padding: 3px 8px; vertical-align: top;
           border-bottom: 1px solid var(--vscode-panel-border, rgba(128,128,128,.25)); }
  td { font-family: var(--vscode-editor-font-family); overflow-wrap: anywhere; }
  .problem { color: var(--vscode-errorForeground, #f14c4c); white-space: pre-wrap;
             border-left: 2px solid currentColor; padding-left: 8px; }
  .warning { color: var(--vscode-editorWarning-foreground, #cca700);
             border-left: 2px solid currentColor; padding-left: 8px; margin: 2px 0; }
  details.fold { margin: 6px 0; border-top: 1px solid var(--vscode-panel-border, rgba(128,128,128,.25));
                 padding-top: 6px; }
  details.fold > summary { cursor: pointer; font-size: 0.78em; font-weight: 600; letter-spacing: .08em;
                           text-transform: uppercase; color: var(--vscode-descriptionForeground); }
  details.fold > summary .dim { text-transform: none; letter-spacing: 0; font-weight: normal; }
  details.inner > summary { cursor: pointer; color: var(--vscode-descriptionForeground); }
  .fold > :not(summary) { margin-left: 14px; }
  tr.dropped td { opacity: .55; }
  td.yes { color: var(--vscode-testing-iconPassed, #388a34); }
  td.no { color: var(--vscode-errorForeground, #f14c4c); }
  td.err { color: var(--vscode-editorWarning-foreground, #cca700); }
  .snap { display: flex; gap: 8px; align-items: baseline; padding: 2px 0; }
  .snap .name { font-weight: 600; }
  h3 { font-size: 1em; margin: 12px 0 4px; }
  kbd { font-family: var(--vscode-editor-font-family); font-size: 0.9em; padding: 0 4px;
        border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); border-radius: 3px; }
  .keys div { margin: 2px 0; }
</style></head><body>
<div class="dim crumbs">SPARQL workbench · <a href="#" data-shape="1">${escape(page.shapeName)}</a></div>
<div class="head">
  <h1>${escape(page.label)}</h1>
  <span class="dim">${escape(holder.kind)}</span>
  ${rule ? '' : severityLabel(holder.severity, !!severity)}
  <span class="right"><span class="chip warn" id="dirty"${state.dirty ? '' : ' hidden'}
    title="The editor holds changes not in shacl.ttl">● unsaved</span></span>
</div>
${holder.message ? `<p class="message" title="sh:message — {?var} is filled from each row">` +
  `“${escape(holder.message)}”</p>` : ''}
${tabs}

<div class="bar toolbar">
  <label for="source">Run over</label>
  <select id="source" title="The data validation would see for this case">${sources}</select>
  <span class="dim" title="${escape(page.focus.join('\n'))}">${focus} focus node${focus === 1 ? '' : 's'}</span>
  <button class="primary" id="apply" title="Run the query in the editor (Ctrl+Enter)">▶ Apply</button>
  <button id="save" title="Write it into shacl.ttl (Ctrl+S)">Save</button>
  <button id="cancel" title="Back to the query shacl.ttl holds">Revert</button>
  <button id="snapshot" title="Keep this text to come back to — this session only">Snapshot</button>
  <button id="more" title="Edit in ${escape(file)}, show in shacl.ttl, Remove…">⋯</button>
</div>
<div id="warnings"></div>

<div class="sechead"><h2>Result</h2>
  <span class="status dim" id="status"></span>
  <label class="toggle" title="Every variable of every row, and which FILTER part dropped a row (Ctrl+Shift+Enter) — the query is not changed">
    <input type="checkbox" id="inspect"> show every row and the FILTER checks</label></div>
<div id="result" class="dim">${rule ? 'Apply shows the triples the rule constructs.'
    : 'Apply shows which focus nodes violate, and what the saved query says.'}</div>
<div id="inspected"></div>

<details class="fold" id="fold-snapshots"${state.snapshots.length ? '' : ' hidden'}>
  <summary>Snapshots <span class="dim" id="snapcount"></span></summary><div id="snapshots"></div></details>
${selects ? `<details class="fold" id="fold-selects"><summary>What it selects <span class="dim">· ${
  selects.binds ? `$this = ${selects.count} node(s)` : 'runs once, unbound'}</span></summary>
<div class="selects"><b>Selects</b> <span>${selects.binds
    ? `$this = each of ${escape(selects.text)} → ${selects.count} node(s), bound before the query runs`
    : `the query never mentions $this: it runs once, unbound (${escape(selects.text)})`}</span></div>
<details class="inner"><summary>Show as SPARQL — what the engine adds</summary><pre>${
  escape(selects.sparql)}</pre></details></details>` : ''}
<details class="fold" id="fold-data"><summary>What it runs over <span class="dim">· ${
  page.data.triples} instance triple(s)${page.data.derivedTriples
  ? `, ${page.data.derivedTriples} derived` : ''}</span></summary>
<p class="dim">${escape(page.stats.graph)} · ${page.data.triples} instance triple(s), ${
  page.data.derivedTriples} of them derived by rules, and ${page.stats.knowledge} knowledge
  triple(s) not shown.</p>
<details class="inner" open><summary>Instance data (Turtle)</summary><pre id="data">${escape(page.data.turtle)}</pre></details>
${page.data.derivedTriples ? `<details class="inner"><summary>Derived by rules (${page.data.derivedTriples})</summary>` +
  `<pre>${escape(page.data.derived)}</pre></details>` : ''}</details>
<details class="fold" id="fold-keys"><summary>Shortcuts <span class="dim">· in
  <a href="#" data-editor="1" title="Show the query's editor">${escape(file)}</a></span></summary>
<div class="dim keys">
  <div><kbd>Ctrl+Space</kbd> completes · <kbd>Shift+Alt+F</kbd> formats</div>
  <div><kbd>Ctrl+Enter</kbd> applies · <kbd>Ctrl+Shift+Enter</kbd> inspects</div>
  <div><kbd>Ctrl+S</kbd> saves into shacl.ttl</div></div></details>

<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  const state = ${JSON.stringify(state).replace(/</g, '\\u003c')};
  const apply = document.getElementById('apply');
  const cancel = document.getElementById('cancel');
  const save = document.getElementById('save');
  const status = document.getElementById('status');
  const inspect = document.getElementById('inspect');
  const esc = (text) => String(text == null ? '' : text).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

  // Folds and the Inspect toggle are remembered while the page is open,
  // and forgotten with it.
  const kept = vscode.getState() || { open: {}, inspect: false };
  for (const fold of document.querySelectorAll('details.fold')) {
    if (kept.open[fold.id] !== undefined) { fold.open = kept.open[fold.id]; }
    fold.addEventListener('toggle', () => { kept.open[fold.id] = fold.open; vscode.setState(kept); });
  }
  inspect.checked = !!kept.inspect;

  // The query lives in its editor; the page asks the extension to act on it.
  function dirty(on) {
    state.dirty = on;
    document.getElementById('dirty').hidden = !on;
    cancel.hidden = !on;
    save.hidden = !on;
  }
  function run() {
    status.textContent = 'running…';
    vscode.postMessage({ command: 'run' });
    if (inspect.checked) { vscode.postMessage({ command: 'inspect' }); }
  }
  apply.addEventListener('click', run);
  inspect.addEventListener('change', () => {
    kept.inspect = inspect.checked;
    vscode.setState(kept);
    if (inspect.checked) {
      status.textContent = 'inspecting…';
      vscode.postMessage({ command: 'inspect' });
    } else {
      document.getElementById('inspected').innerHTML = '';
    }
  });
  document.getElementById('snapshot').addEventListener('click', () =>
    vscode.postMessage({ command: 'snapshot' }));
  document.getElementById('more').addEventListener('click', () =>
    vscode.postMessage({ command: 'menu' }));
  cancel.addEventListener('click', () => vscode.postMessage({ command: 'cancel' }));
  save.addEventListener('click', () => vscode.postMessage({ command: 'save' }));
  document.getElementById('source').addEventListener('change', (event) =>
    vscode.postMessage({ command: 'source', source: event.target.value }));
  document.addEventListener('click', (event) => {
    const snap = event.target.closest('[data-load],[data-drop]');
    if (snap) {
      event.preventDefault();
      if (snap.dataset.drop) {
        vscode.postMessage({ command: 'deleteSnapshot', id: Number(snap.dataset.drop) });
      } else {
        vscode.postMessage({ command: 'loadSnapshot', id: snap.dataset.load });
      }
      return;
    }
    const target = event.target.closest('[data-open],[data-shape],[data-holder],[data-editor]');
    if (!target) { return; }
    event.preventDefault();
    if (target.dataset.open) { vscode.postMessage({ command: 'open', at: target.dataset.open }); }
    else if (target.dataset.shape) { vscode.postMessage({ command: 'shape' }); }
    else if (target.dataset.editor) { vscode.postMessage({ command: 'editor' }); }
    else { vscode.postMessage({ command: 'holder', index: Number(target.dataset.holder) }); }
  });

  function table(columns, rows) {
    return '<table><thead><tr>' + columns.map((c) => '<th>?' + esc(c) + '</th>').join('') +
      '</tr></thead><tbody>' + rows.map((row) => '<tr>' + columns.map((c) =>
        '<td>' + esc(row[c]) + '</td>').join('') + '</tr>').join('') + '</tbody></table>';
  }
  function show(result) {
    const out = document.getElementById('result');
    document.getElementById('warnings').innerHTML = (result.warnings || []).map((w) =>
      '<div class="warning">' + esc(w) + '</div>').join('');
    out.classList.remove('dim');
    if (!result.ok) {
      status.textContent = 'not run';
      out.innerHTML = '<div class="problem">' + esc(result.error) + '</div>';
      return;
    }
    status.textContent = 'ran in ' + result.ms + ' ms over ' + result.focusCount + ' focus node(s)';
    if (result.kind === 'rule') {
      const made = (result.focus || []).map((f) => esc(f.node) + ': ' + f.triples).join(' · ');
      out.innerHTML = '<p>' + (result.triples ? result.triples + ' triple(s) constructed'
        : 'Constructs nothing: the WHERE matched for no focus node.') + '</p>' +
        '<p class="dim">' + made + '</p>' +
        (result.triples ? '<pre>' + esc(result.constructed) + '</pre>' : '');
      return;
    }
    const violating = result.violating || [];
    let summary = '<p>' + (violating.length
      ? '<span class="chip bad">' + violating.length + ' violating</span> ' + esc(violating.join(', '))
      : '<span class="chip ok">no violation</span> every focus node conforms') + '</p>';
    if (result.saved) {
      const before = result.saved.violating || [];
      const added = violating.filter((n) => !before.includes(n));
      const gone = before.filter((n) => !violating.includes(n));
      summary += '<p class="dim">The saved query: ' + (before.length
        ? before.length + ' violating (' + esc(before.join(', ')) + ')' : 'no violation') +
        (added.length ? ' · now also ' + esc(added.join(', ')) : '') +
        (gone.length ? ' · no longer ' + esc(gone.join(', ')) : '') + '</p>';
    }
    const rows = (result.focus || []).filter((f) => f.rows.length).map((f) =>
      '<h3>' + esc(f.node) + '</h3>' + (f.messages || []).filter(Boolean).map((m) =>
        '<div class="warning">' + esc(m) + '</div>').join('') +
      table(result.columns || [], f.rows)).join('');
    // With the toggle on, the inspected rows below say it all, and more.
    out.innerHTML = summary + (inspect.checked ? '' : rows);
  }
  function snapshots() {
    const list = state.snapshots;
    const fold = document.getElementById('fold-snapshots');
    fold.hidden = !list.length;
    document.getElementById('snapcount').textContent = list.length ? '· ' + list.length +
      ', this session only' : '';
    document.getElementById('snapshots').innerHTML = !list.length ? '' :
      '<div class="snap"><span class="name">Saved in shacl.ttl</span>' +
      '<a href="#" data-load="saved">Load</a></div>' +
      list.map((s) => '<div class="snap"><span class="name">' + esc(s.name) + '</span>' +
        '<span class="dim">' + esc(s.verdict) + ' · ' + esc(s.at) + '</span>' +
        '<a href="#" data-load="' + s.id + '">Load</a>' +
        '<a href="#" data-drop="' + s.id + '">Delete</a></div>').join('');
  }
  function mark(held) {
    return held === true ? '<td class="yes">✓</td>' : held === false ? '<td class="no">✗</td>'
      : '<td class="err" title="an error: FILTER counts it as false">⚠</td>';
  }
  function inspected(result) {
    const out = document.getElementById('inspected');
    if (!inspect.checked) {
      // Asked from the editor's key: the toggle follows.
      inspect.checked = true;
      kept.inspect = true;
      vscode.setState(kept);
    }
    if (!result.ok) {
      out.innerHTML = '<div class="problem">' + esc(result.error) + '</div>';
      return;
    }
    status.textContent = 'inspected in ' + result.ms + ' ms';
    const filters = result.filters || [];
    const legend = filters.map((f, i) => '<div><b>F' + (i + 1) + '</b> <code>' + esc(f) +
      '</code></div>').join('');
    const head = '<tr>' + result.columns.map((c) => '<th>?' + esc(c) + '</th>').join('') +
      filters.map((f, i) => '<th title="' + esc(f) + '">F' + (i + 1) + '</th>').join('') +
      '<th></th></tr>';
    const blocks = (result.focus || []).map((f) => {
      const rows = f.rows.map((r) => '<tr class="' + (r.kept ? 'kept' : 'dropped') + '">' +
        result.columns.map((c) => '<td>' + esc(r.values[c] || '') + '</td>').join('') +
        r.checks.map(mark).join('') + '<td>' + (r.kept ? (result.kind === 'rule'
          ? 'constructs' : 'violation') : 'dropped') + '</td></tr>').join('');
      return '<h3>' + esc(f.node) + ' <span class="dim">· ' + f.total + ' row(s) from the WHERE, ' +
        f.kept + ' kept' + (f.total > f.rows.length ? ', first ' + f.rows.length + ' shown' : '') +
        '</span></h3>' + (f.total ? '<table><thead>' + head + '</thead><tbody>' + rows +
        '</tbody></table>' : '<p class="dim">The pattern matches nothing for this node: ' +
        'no FILTER is reached.</p>');
    }).join('');
    out.innerHTML = (result.notes || []).map((n) =>
      '<div class="warning">' + esc(n) + '</div>').join('') +
      (legend ? '<div class="dim">' + legend + '</div>' : '<p class="dim">No outer FILTER: every ' +
        'row of the WHERE is kept.</p>') + blocks;
  }
  window.addEventListener('message', (event) => {
    const message = event.data || {};
    if (message.type === 'result') { show(message.result); }
    else if (message.type === 'inspect') { inspected(message.result); }
    else if (message.type === 'snapshots') { state.snapshots = message.list; snapshots(); }
    else if (message.type === 'saved') {
      dirty(false);
      status.textContent = 'saved to ' + message.where;
    } else if (message.type === 'dirty') { dirty(message.dirty); }
    else if (message.type === 'error') { status.textContent = message.text; }
  });
  dirty(state.dirty);
  snapshots();
  run();
</script>
</body></html>`;
}

function renderMessage(text) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="default-src 'none';"></head>` +
    `<body><p>${escape(text)}</p></body></html>`;
}

// --- query documents: semforge-sparql:/<Shape>.rq ------------------------------------------

const SCHEME = 'semforge-sparql';

/** Which query a document is: package, shape, which of its queries, kind. */
function reference(uri) {
  return JSON.parse(Buffer.from(uri.query, 'base64url').toString('utf-8'));
}

function queryUri(packageUri, shape, holder, label) {
  const name = `${label}${holder.index ? `-${holder.index + 1}` : ''}.rq`;
  const ref = { p: packageUri, s: shape, h: holder.index, k: holder.kind };
  return vscode.Uri.from({ scheme: SCHEME, path: `/${name}`,
    query: Buffer.from(JSON.stringify(ref), 'utf-8').toString('base64url') });
}

/**
 * The file system behind query documents: reading one is reading the
 * shape's literal from shacl.ttl, writing one is the workbench's Save --
 * refused, as a failed save, if the literal changed since it was read.
 */
class QueryFiles {
  constructor(clientHolder) {
    this.clientHolder = clientHolder;
    this.saved = new Map();          // uri -> the text shacl.ttl holds
    this.mtime = new Map();
    this.listeners = [];
    this.emitter = new vscode.EventEmitter();
    this.onDidChangeFile = this.emitter.event;
  }

  async client() {
    for (let waited = 0; !this.clientHolder.client && waited < 30000; waited += 200) {
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    if (!this.clientHolder.client) {
      throw vscode.FileSystemError.Unavailable('the SemForge language server is not running');
    }
    return this.clientHolder.client;
  }

  watch() {
    return new vscode.Disposable(() => {});
  }

  stat(uri) {
    const text = this.saved.get(uri.toString()) || '';
    return { type: vscode.FileType.File, ctime: 0, mtime: this.mtime.get(uri.toString()) || 1,
      size: Buffer.byteLength(text, 'utf-8') };
  }

  async readFile(uri) {
    const ref = reference(uri);
    const client = await this.client();
    const got = await client.sendRequest('semforge/sparqlQuery',
      { uri: ref.p, shape: ref.s, holder: ref.h });
    if (!got.ok) {
      throw vscode.FileSystemError.FileNotFound(`SemForge: ${got.error}`);
    }
    this.saved.set(uri.toString(), got.query);
    return Buffer.from(got.query, 'utf-8');
  }

  async writeFile(uri, content) {
    const ref = reference(uri);
    const text = Buffer.from(content).toString('utf-8');
    const client = await this.client();
    const result = await client.sendRequest('semforge/sparqlSave', { uri: ref.p, shape: ref.s,
      index: ref.h, query: text, expected: this.saved.get(uri.toString()) });
    if (!result.ok) {
      throw vscode.FileSystemError.NoPermissions(`SemForge: ${result.error}`);
    }
    this.saved.set(uri.toString(), text);
    this.mtime.set(uri.toString(), Date.now());
    this.emitter.fire([{ type: vscode.FileChangeType.Changed, uri }]);
    for (const listener of this.listeners) {
      listener(uri, text, result);
    }
  }

  readDirectory() { return []; }

  createDirectory() { throw vscode.FileSystemError.NoPermissions('queries are not folders'); }

  delete() { throw vscode.FileSystemError.NoPermissions('remove a query from its workbench'); }

  rename() { throw vscode.FileSystemError.NoPermissions('a query is named by its shape'); }
}

class SparqlBench {
  constructor(clientHolder, files) {
    this.clientHolder = clientHolder;
    this.files = files;
    this.panel = undefined;
    this.current = undefined;
    this.page = undefined;
    this.uri = undefined;            // the query document the page acts on
    // Snapshots: texts kept to come back to, per query, for this session only.
    // Nothing is written anywhere: closing VS Code keeps the saved query alone.
    this.snapshots = new Map();
    this.nextSnapshot = 1;
    files.listeners.push((uri, text, result) => this.saved(uri, text, result));
  }

  snapshotKey() {
    return this.current && this.page
      ? `${this.current.packageUri}|${this.current.shape}|${this.page.holder.index}` : '';
  }

  snapshotList() {
    return this.snapshots.get(this.snapshotKey()) || [];
  }

  document() {
    return this.uri && vscode.workspace.textDocuments.find((d) =>
      d.uri.toString() === this.uri.toString());
  }

  /** What the editor holds now -- the query every button acts on. */
  text() {
    const doc = this.document();
    return doc ? doc.getText() : this.page.holder.query;
  }

  get dirty() {
    const doc = this.document();
    return !!(doc && doc.isDirty);
  }

  /** `options`: {index, query, kind, source, preserveFocus}. */
  async show(packageUri, shape, options) {
    if (!this.clientHolder.client || !packageUri || !shape) {
      vscode.window.showWarningMessage(
        'SemForge: no package is open, or the language server is not running.');
      return;
    }
    const wanted = Object.assign({}, options || {});
    this.current = { packageUri, shape, index: wanted.index, query: wanted.query,
      kind: wanted.kind,
      source: wanted.source || (this.current && this.current.shape === shape
        ? this.current.source : '@main') };
    const page = await this.load();
    if (!page) {
      return;
    }
    this.uri = queryUri(packageUri, shape, page.holder, page.label);
    const doc = await vscode.workspace.openTextDocument(this.uri);
    await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.One,
      preview: false, preserveFocus: !!wanted.preserveFocus });
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel('semforgeSparqlBench', 'SPARQL',
        { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
        { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [] });
      this.panel.onDidDispose(() => { this.panel = undefined; });
      this.panel.webview.onDidReceiveMessage((message) => this.receive(message));
    } else {
      this.panel.reveal(undefined, true);
    }
    this.draw();
  }

  async request(method, params) {
    try {
      return await this.clientHolder.client.sendRequest(method,
        Object.assign({ uri: this.current.packageUri, shape: this.current.shape }, params));
    } catch (error) {
      return { ok: false, error: error.message || String(error) };
    }
  }

  /** The page's payload for the current query and data. */
  async load() {
    const page = await this.request('semforge/sparqlBench', {
      index: this.current.index, query: this.current.query, kind: this.current.kind,
      source: this.current.source });
    if (!page.ok) {
      if (this.panel) {
        this.panel.title = 'SPARQL';
        this.panel.webview.html = renderMessage(`SemForge: ${page.error}`);
      } else {
        vscode.window.showErrorMessage(`SemForge: ${page.error}`);
      }
      return undefined;
    }
    this.page = page;
    this.current.index = page.holder.index;
    this.current.query = page.holder.query;
    return page;
  }

  draw() {
    if (!this.panel || !this.page) {
      return;
    }
    this.panel.title = `${this.page.label} · SPARQL`;
    this.panel.webview.html = renderSparqlBench(this.page, {
      nonce: crypto.randomBytes(16).toString('base64'), snapshots: this.snapshotList(),
      dirty: this.dirty, file: this.uri ? this.uri.path.slice(1) : undefined });
  }

  async render() {
    if (this.current && (await this.load())) {
      this.draw();
    }
  }

  /** Put text into the query's editor -- a snapshot, an edit from a test. */
  async replaceText(text) {
    const doc = this.document() || await vscode.workspace.openTextDocument(this.uri);
    const edit = new vscode.WorkspaceEdit();
    edit.replace(doc.uri, new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length)),
      text);
    await vscode.workspace.applyEdit(edit);
    return doc;
  }

  async snapshot(query) {
    const list = this.snapshotList();
    const name = await vscode.window.showInputBox({
      title: 'Snapshot', value: `Snapshot ${list.length + 1}`,
      prompt: 'Kept for this session, to come back to — closing VS Code forgets it. ' +
        'Only Save writes shacl.ttl.'
    });
    if (name === undefined) {
      return undefined;
    }
    const ran = await this.request('semforge/sparqlRun', { index: this.page.holder.index,
      source: this.current.source, query });
    const where = (this.page.sources.find((s) => s.id === this.current.source) || {}).label ||
      this.current.source;
    const verdict = !ran.ok ? 'does not run'
      : ran.kind === 'rule' ? `${ran.triples} triple(s) on ${where}`
        : `${ran.violating.length} violating on ${where}`;
    const entry = { id: this.nextSnapshot++, name: name || `Snapshot ${list.length + 1}`,
      query, verdict, at: new Date().toLocaleTimeString() };
    this.snapshots.set(this.snapshotKey(), list.concat([entry]));
    this.post({ type: 'snapshots', list: this.snapshotList() });
    return entry;
  }

  deleteSnapshot(id) {
    this.snapshots.set(this.snapshotKey(), this.snapshotList().filter((s) => s.id !== id));
    this.post({ type: 'snapshots', list: this.snapshotList() });
  }

  async receive(message) {
    if (!message || !this.current || !this.page) {
      return undefined;
    }
    const query = typeof message.query === 'string' ? message.query : this.text();
    if (message.command === 'run') {
      const result = await this.request('semforge/sparqlRun', { index: this.page.holder.index,
        source: this.current.source, query });
      this.post({ type: 'result', result });
      return result;
    } else if (message.command === 'inspect') {
      const result = await this.request('semforge/sparqlInspect', {
        index: this.page.holder.index, source: this.current.source, query });
      this.post({ type: 'inspect', result });
      return result;
    } else if (message.command === 'snapshot') {
      return this.snapshot(query);
    } else if (message.command === 'deleteSnapshot') {
      this.deleteSnapshot(message.id);
    } else if (message.command === 'loadSnapshot') {
      const chosen = message.id === 'saved' ? { query: this.files.saved.get(this.uri.toString()) ||
        this.page.holder.query } : this.snapshotList().find((s) => String(s.id) === String(message.id));
      if (chosen) {
        await this.replaceText(chosen.query);
        return this.receive({ command: 'run' });
      }
    } else if (message.command === 'save') {
      return this.save(message.query);
    } else if (message.command === 'cancel') {
      return this.cancel();
    } else if (message.command === 'remove') {
      return this.remove();
    } else if (message.command === 'source') {
      this.current.source = message.source;
      await this.render();
    } else if (message.command === 'holder') {
      await this.show(this.current.packageUri, this.current.shape,
        { index: message.index, source: this.current.source });
    } else if (message.command === 'menu') {
      // What is used now and then: one ⋯.
      const holder = this.page.holder;
      const doc = this.document();
      const items = [
        { label: '$(edit) Show the query\'s editor', message: { command: 'editor' } },
        { label: '$(go-to-file) Show it in shacl.ttl', message: { command: 'open',
          at: `${holder.file}:${holder.line}` } },
        { label: '$(type-hierarchy) Open the shape page', message: { command: 'shape' } }];
      if (doc && doc.isDirty) {
        items.unshift({ label: '$(save) Save into shacl.ttl', description: 'Ctrl+S',
          message: { command: 'save' } },
        { label: '$(discard) Revert to the saved query', message: { command: 'cancel' } });
      }
      if (holder.kind === 'constraint') {
        items.push({ label: '$(warning) Severity…',
          description: `${holder.severityLabel || 'violation'}${holder.severity ? '' : ' (default)'}`,
          message: { command: 'severity' } });
      }
      items.push({ label: `$(trash) Remove this ${holder.kind}…`, message: { command: 'remove' } });
      const picked = await vscode.window.showQuickPick(items, { title: this.page.label });
      if (picked) {
        return this.receive(picked.message);
      }
    } else if (message.command === 'severity') {
      const holder = this.page.holder;
      if (await require('./severity').chooseSeverity(this.clientHolder.client,
        this.current.packageUri, { shape: this.current.shape, holder: holder.index,
          label: holder.message || 'this constraint',
          current: `${holder.severityLabel || 'violation'}${holder.severity ? '' : ' (default)'}` })) {
        await this.render();
      }
    } else if (message.command === 'editor') {
      const doc = this.document() || await vscode.workspace.openTextDocument(this.uri);
      await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.One,
        preview: false });
    } else if (message.command === 'open' && message.at) {
      await showLocation(message.at, true);
    } else if (message.command === 'shape') {
      await vscode.commands.executeCommand('semforge.openShapePage',
        { raw: { shape: this.current.shape }, packageUri: this.current.packageUri });
    }
    return undefined;
  }

  /** The editor's Save; with `query`, that text is put in first. */
  async save(query) {
    const doc = typeof query === 'string' ? await this.replaceText(query)
      : this.document() || await vscode.workspace.openTextDocument(this.uri);
    this.lastSave = undefined;
    let ok = false;
    try {
      ok = await doc.save();
    } catch (error) {
      this.lastSave = { ok: false, error: error.message || String(error) };
    }
    if (!ok && !this.lastSave) {
      this.lastSave = { ok: false, error: 'not saved' };
    }
    if (!this.lastSave.ok) {
      this.post({ type: 'error', text: 'not saved' });
    }
    return this.lastSave;
  }

  /** The editor's Revert: back to what shacl.ttl holds. */
  async cancel() {
    const doc = this.document();
    if (!doc || !doc.isDirty) {
      return false;
    }
    await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.One,
      preview: false });
    await vscode.commands.executeCommand('workbench.action.files.revert');
    this.post({ type: 'dirty', dirty: false });
    await this.receive({ command: 'run' });
    return true;
  }

  /** The file system wrote a query into shacl.ttl. */
  saved(uri, text, result) {
    this.lastSave = Object.assign({ ok: true }, result);
    if (!this.uri || uri.toString() !== this.uri.toString() || !this.page) {
      return;
    }
    this.page.holder.query = text;
    this.current.query = text;
    this.post({ type: 'saved', query: text, where: `shacl.ttl:${result.line}` });
    for (const command of REFRESH_VIEWS) {
      vscode.commands.executeCommand(command);
    }
    vscode.window.setStatusBarMessage(
      `SemForge: the query of ${this.page.label} saved — validation re-runs`, 5000);
  }

  /** Remove the open query; the page then shows the shape's next one, or closes. */
  async remove() {
    const doc = this.document();
    const done = await removeQuery(this.clientHolder, this.current.packageUri,
      this.current.shape, this.page.holder, this.page.label, !!(doc && doc.isDirty));
    if (!done) {
      return undefined;
    }
    await this.close(this.uri);
    this.current.query = undefined;
    this.current.index = 0;
    const next = await this.request('semforge/sparqlBench', { index: 0,
      source: this.current.source });
    if (!next.ok) {
      if (this.panel) {
        this.panel.dispose();          // that was the shape's last query
      }
    } else {
      await this.show(this.current.packageUri, this.current.shape,
        { index: 0, source: this.current.source });
    }
    return done;
  }

  /** Close a query's editor without asking to save: its query is gone. */
  async close(uri) {
    const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
    if (doc && doc.isDirty) {
      await vscode.window.showTextDocument(doc, { preview: false });
      await vscode.commands.executeCommand('workbench.action.files.revert');
    }
    const tabs = vscode.window.tabGroups ? vscode.window.tabGroups.all.flatMap((g) => g.tabs)
      .filter((t) => t.input && t.input.uri && t.input.uri.toString() === uri.toString()) : [];
    if (tabs.length) {
      await vscode.window.tabGroups.close(tabs);
    }
  }

  post(message) {
    if (this.panel) {
      this.panel.webview.postMessage(message);
    }
  }

  /** The editor changed: say so on the page. */
  changed(document) {
    if (this.uri && document.uri.toString() === this.uri.toString()) {
      this.post({ type: 'dirty', dirty: document.isDirty });
    }
  }

  /** A save elsewhere: the data may have changed; the editor is left alone. */
  refresh(document) {
    if (document && document.uri.scheme === SCHEME) {
      return;
    }
    if (this.panel && this.panel.visible) {
      this.render();
    }
  }
}

/**
 * Remove one SPARQL constraint or rule, after saying what goes with it: the
 * test cases that assert it (asserts name the shape's SPARQL constraints
 * together, so they only lose their meaning with its LAST one), and unsaved
 * edits in the workbench. Returns the server's answer, or undefined.
 */
async function removeQuery(clientHolder, packageUri, shape, holder, label, dirty) {
  const client = clientHolder.client;
  const which = { uri: packageUri, shape, query: holder.query, kind: holder.kind };
  const plan = await client.sendRequest('semforge/sparqlRemovalPlan', which);
  if (!plan.ok) {
    vscode.window.showErrorMessage(`SemForge: ${plan.error}`);
    return undefined;
  }
  const what = holder.kind === 'rule' ? 'SPARQL rule'
    : `SPARQL constraint${holder.message ? ` "${holder.message}"` : ''}`;
  const lines = [];
  const cases = plan.asserts.map((a) => `  ${a.case}${a.resource ? ` (on ${a.resource})` : ''}`);
  let buttons = ['Remove'];
  if (plan.asserts.length && plan.last) {
    lines.push(`${plan.asserts.length} test case assert(s) name it, and no other SPARQL ` +
      'constraint of this shape is left to satisfy them:', ...cases,
    'Removing them too keeps those cases meaningful; keeping them makes them fail.');
    buttons = ['Remove it and its asserts', 'Remove it only'];
  } else if (plan.asserts.length) {
    lines.push(`${plan.asserts.length} test case assert(s) name this shape's SPARQL ` +
      `constraints; ${plan.others} other(s) remain, so the asserts are kept:`, ...cases);
  }
  if (dirty) {
    lines.push('Its unsaved edits in the workbench go with it.');
  }
  lines.push(`Written at shacl.ttl:${plan.holder.line}.`);
  const answer = await vscode.window.showWarningMessage(
    `Remove the ${what} from ${label}?`, { modal: true, detail: lines.join('\n') }, ...buttons);
  if (!answer) {
    return undefined;
  }
  const done = await client.sendRequest('semforge/sparqlRemove', Object.assign(which,
    { expected: holder.query, dropAsserts: answer === 'Remove it and its asserts' }));
  if (!done.ok) {
    vscode.window.showErrorMessage(`SemForge: ${done.error}`);
    return undefined;
  }
  for (const command of REFRESH_VIEWS) {
    vscode.commands.executeCommand(command);
  }
  vscode.window.setStatusBarMessage(`SemForge: the ${what} removed from ${label}` +
    (done.asserts ? `, with ${done.asserts} assert(s)` : ''), 6000);
  return done;
}

/** + SPARQL constraint: ask what a violation means, write a skeleton, open it. */
async function addConstraint(bench, clientHolder, packageUri, shape, label) {
  const message = await vscode.window.showInputBox({
    title: `New SPARQL constraint on ${label}`,
    prompt: 'Its sh:message: what a violation means, e.g. "Cutter running without a filter". ' +
      '{?var} is filled from the query\'s row.',
    validateInput: (text) => (text && text.trim() ? undefined : 'a message is required')
  });
  if (!message) {
    return undefined;
  }
  const made = await clientHolder.client.sendRequest('semforge/addSparqlConstraint',
    { uri: packageUri, shape, message });
  if (!made.ok) {
    vscode.window.showErrorMessage(`SemForge: ${made.error}`);
    return undefined;
  }
  for (const command of REFRESH_VIEWS) {
    vscode.commands.executeCommand(command);
  }
  await bench.show(packageUri, shape, { index: made.index });
  vscode.window.showInformationMessage(
    'SemForge: a SPARQL constraint that fires on nothing yet — write its condition, Apply ' +
      'to see what it finds, Save when it says what you mean.');
  return made;
}

/** The workbench of the query document in the active editor, opened if needed. */
async function forActiveQuery(bench) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.uri.scheme !== SCHEME) {
    return false;
  }
  const uri = editor.document.uri;
  if (!bench.uri || bench.uri.toString() !== uri.toString() || !bench.panel) {
    const ref = reference(uri);
    await bench.show(ref.p, ref.s, { index: ref.h, preserveFocus: true });
  }
  return true;
}

function register(context, clientHolder, session) {
  const files = new QueryFiles(clientHolder);
  const bench = new SparqlBench(clientHolder, files);
  const target = (node) => ({
    packageUri: (node && node.packageUri) || session.uri,
    shape: node && node.raw && (node.raw.shape || node.raw.iri)
  });
  context.subscriptions.push(
    vscode.workspace.registerFileSystemProvider(SCHEME, files, { isCaseSensitive: true }),
    vscode.commands.registerCommand('semforge.sparqlApply', async () =>
      (await forActiveQuery(bench)) && bench.receive({ command: 'run' })),
    vscode.commands.registerCommand('semforge.sparqlInspect', async () =>
      (await forActiveQuery(bench)) && bench.receive({ command: 'inspect' })),
    vscode.workspace.onDidChangeTextDocument((event) => bench.changed(event.document)),
    // The quick fix for "shacl2flink would read this attribute as a plain
    // triple": an optional property shape nesting its payload, on the shape
    // of the type that carries it -- created first when the type has none.
    vscode.commands.registerCommand('semforge.nestForFlink', async (args) => {
      const client = clientHolder.client;
      if (!client || !args) {
        return undefined;
      }
      const request = (shape) => client.sendRequest('semforge/addAttributeConstraint', {
        uri: args.packageUri, shape: shape || null, entityType: shape ? null : args.entityType,
        attribute: args.attribute, required: false });
      let made = await request();
      if (!made.ok && /no shape targets/.test(made.error || '')) {
        const label = args.entityType.split(/[/#]/).pop();
        const shape = await vscode.commands.executeCommand('semforge.newShape', {
          raw: { kind: 'type', targetClass: args.entityType, label },
          packageUri: args.packageUri }, { stay: true, quiet: true });
        if (!shape) {
          return undefined;
        }
        made = await request(shape.iri);
      }
      if (!made.ok) {
        vscode.window.showErrorMessage(`SemForge: ${made.error}`);
        return undefined;
      }
      for (const command of REFRESH_VIEWS) {
        vscode.commands.executeCommand(command);
      }
      vscode.window.setStatusBarMessage(
        `SemForge: ${args.attribute.split(/[/#]/).pop()} is now an NGSI-LD attribute to ` +
          'shacl2flink too (an optional property shape)', 6000);
      return made;
    }),
    vscode.commands.registerCommand('semforge.openSparqlBench', async (node, options) => {
      const { packageUri, shape } = target(node);
      if (!shape) {
        vscode.window.showInformationMessage('SemForge: open the workbench from a shape.');
        return;
      }
      await bench.show(packageUri, shape, options);
    }),
    vscode.commands.registerCommand('semforge.addSparqlConstraint', async (node) => {
      const { packageUri, shape } = target(node);
      if (!shape || !clientHolder.client) {
        return undefined;
      }
      return addConstraint(bench, clientHolder, packageUri, shape,
        (node.raw.label || shape.split(/[/#]/).pop()));
    }),
    // From the shape page: which query is said by its text.
    vscode.commands.registerCommand('semforge.removeSparqlQuery', async (node, holder) => {
      const { packageUri, shape } = target(node);
      if (!shape || !holder || !clientHolder.client) {
        return undefined;
      }
      const label = node.raw.label || shape.split(/[/#]/).pop();
      const open = bench.panel && bench.current && bench.current.shape === shape &&
        bench.page && bench.page.holder.query.trim() === String(holder.query).trim();
      if (open) {
        bench.panel.reveal();
        return bench.remove();
      }
      return removeQuery(clientHolder, packageUri, shape, holder, label, false);
    }),
    vscode.workspace.onDidSaveTextDocument((document) => {
      bench.changed(document);
      bench.refresh(document);
    })
  );
  return bench;
}

module.exports = { register, renderSparqlBench, SparqlBench, QueryFiles, queryUri, reference,
  SCHEME };
