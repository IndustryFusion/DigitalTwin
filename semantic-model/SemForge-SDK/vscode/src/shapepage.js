/*
 * The shape page: what one shape checks, and what it reaches.
 *
 * A shape is not tied to an entity type. It targets nodes -- by class, by
 * named node, by the subjects or objects of a predicate, by a SPARQL query --
 * or nothing, being reached from another shape through sh:node. The type
 * page reads constraints by type; this page is the shape's own: its target in
 * words, its attributes and rules (the same rows the type page shows), the
 * nodes it reaches in the model, the types those are, and the cases that make
 * it fire.
 *
 * Its attributes are edited as on the type page -- the same rows, the same
 * actions (presence, value, ⋯, New test…, + Attribute) -- written into this
 * shape. `renderShapePage` is a pure function from the payload
 * `semforge/shapePage` returns; everything shown is escaped, and script and
 * style run only with the per-render nonce.
 */

const crypto = require('crypto');
const vscode = require('vscode');

const { showLocation } = require('./reveal');
const { escape, attributeRows: typeRows, EDITS } = require('./typepage');
const { pickTarget } = require('./shapes');

function chip(text, tone, title) {
  return `<span class="chip ${tone || ''}"${title ? ` title="${escape(title)}"` : ''}>` +
    `${escape(text)}</span>`;
}

function shapeLink(name, iri) {
  return `<a href="#" data-shape="${escape(iri)}">${escape(name)}</a>`;
}

/** The type page's rows, actions and all: a shape's attributes are edited
 *  here the same way, written into this shape. */
function attributeRows(attributes) {
  return typeRows(attributes, -1, { shapeColumn: false });
}

const NEW_CASE_TIP = 'Writes a bad case asserting this shape fires, copied from a ' +
  'scene where it holds. It fails until you edit its data so the rule is broken: ' +
  'it cannot pass by accident.';

/** sh:severity as a reader says it: base:severityCritical -> critical. */
function severityText(severity) {
  const local = String(severity || '').split(/[/#:]/).pop();
  return local.replace(/^severity/i, '').toLowerCase() || '';
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

/** How well the cases prove this shape: both ways, only one, or not at all. */
function provenChip(cases) {
  const fires = cases.filter((c) => c.fired).length;
  const holds = cases.length - fires;
  if (!cases.length) {
    return chip('no case reaches it', 'warn', 'Nothing proves it can fire.');
  }
  if (!fires) {
    return chip('never fired', 'warn', 'No test case makes it fire: a check that cannot fire ' +
      'looks exactly like one that holds.');
  }
  return holds ? chip('tested both ways', 'ok', `fires in ${fires} case(s), holds in ${holds}`)
    : chip(`fires in ${fires}`, 'ok', 'No case where it holds');
}

/** A SPARQL constraint or rule: what it says, how proven, its query folded. */
function checkRows(checks, cases) {
  return checks.map((c, i) => `<div class="check">` +
    `<span class="kind" title="${c.kind === 'rule' ? 'A SPARQL rule: it derives data'
      : 'A SPARQL constraint: every row it returns is a violation'}">${c.kind === 'rule'
      ? 'rule' : 'SPARQL'}</span>` +
    `<span class="what">${escape(c.message || (c.kind === 'rule'
      ? 'Derives data' : '(no sh:message)'))}</span>` +
    `<span class="tags">${c.kind === 'constraint'
      ? severityLabel(c.severity, c.severityDeclared !== false) : ''}` +
    `${c.kind === 'constraint' ? provenChip(cases) : ''}</span>` +
    `<span class="acts">${c.query ? `<button data-action="bench" data-row="${i}" ` +
      'title="Edit and run it in the SPARQL workbench">Open</button>' : ''}` +
    `<button data-action="checkMenu" data-row="${i}" title="More">⋯</button></span>` +
    (c.query ? `<details class="query"><summary>query</summary>` +
      `<pre>${escape(c.query.trim())}</pre></details>` : '') +
    '</div>').join('');
}

/** What the shape applies to, in one line; its targets edited in a fold. */
function appliesTo(page) {
  const targets = page.targets || [];
  const users = page.usedBy || [];
  const reach = page.reach || { nodes: [], more: 0 };
  const said = targets.length ? targets.map((t) => escape(t.text)).join('; ')
    : users.length ? `no target of its own — what ${users.map((u) =>
      shapeLink(u.name, u.iri)).join(', ')} reach through <span class="mono">sh:node</span>`
      : '<span class="warn-text">nothing: no target, and no shape uses it</span>';
  const nodes = reach.nodes.map((n) => `<span class="node${n.violations.length ? ' bad' : ''}" ` +
    `title="${escape(n.violations.length ? n.violations.join('\n') : 'valid')}">` +
    `<span class="mono">${escape(n.id)}</span> ${n.violations.length
      ? `✗ ${n.violations.length}` : '✓'}</span>`).join('') +
    (reach.more ? `<span class="dim">… and ${reach.more} more</span>` : '');
  const editable = targets.map((t, index) => `<div class="target">` +
    `<span class="mono">${escape({ class: 'sh:targetClass', node: 'sh:targetNode',
      subjectsOf: 'sh:targetSubjectsOf', objectsOf: 'sh:targetObjectsOf', sparql: 'sh:target',
      implicit: 'implicit' }[t.kind] || t.kind)}</span><span>${escape(t.text)}` +
    (t.kind === 'sparql' && t.value ? `<pre class="query-inline">${escape(t.value.trim())}</pre>`
      : '') + '</span>' +
    (['class', 'node', 'subjectsOf', 'objectsOf'].includes(t.kind)
      ? `<button data-action="removeTarget" data-row="${index}" ` +
        'title="Take this target off the shape">Remove</button>' : '<span></span>') +
    '</div>').join('');
  const types = (page.types || []).filter((t) => t.page).map((t) =>
    `<a href="#" data-type="${escape(t.iri)}" title="Open the ${escape(t.label)} type page">` +
    `${escape(t.label)}</a>`).join(', ');
  return `<p class="line" title="The node selector: which nodes the checks run on">${said}` +
    `${types ? ` <span class="dim">· type</span> ${types}` : ''}</p>` +
    (nodes ? `<div class="nodes" title="In the main-model">${nodes}</div>`
      : '<p class="empty">Nothing in the main-model is one of them.</p>') +
    `<details class="fold"><summary>Edit targets</summary>${editable}` +
    '<div class="bar"><button data-action="addTarget">+ Target</button></div></details>';
}

/** The cases that reach the shape: one row each, the ones it fires in first. */
function testedBy(page, cases) {
  const rows = cases.slice().sort((a, b) => (b.fired ? 1 : 0) - (a.fired ? 1 : 0))
    .map((c) => `<div class="case">` +
      chip(c.fired ? 'fires' : 'holds', c.fired ? 'ok' : '',
        c.fired ? `reports it ${c.fired}× here` : 'evaluated here, conforming') +
      `<a href="#" data-case="${escape(c.file)}" title="${escape(c.description || '')}">` +
      `${escape(c.case.split('/').slice(-3).join(' / '))}</a>` +
      `<span class="dim">${c.firedOn && c.firedOn.length
        ? `on ${escape(c.firedOn.join(', '))}` : ''}</span>` +
      (c.passed ? '<span class="dim">passes</span>' : chip('FAILS', 'bad')) + '</div>').join('');
  return rows || '<p class="empty">No test case reaches it: nothing proves it can fire.</p>';
}

function renderShapePage(page, options) {
  const nonce = (options && options.nonce) || '';
  const csp = `default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';`;
  const summary = page.summary || {};
  const attributes = page.attributes || [];
  const checks = page.checks || [];
  const cases = page.exercisedBy || [];
  const status = [
    summary.violations
      ? `<span class="bad-text">${summary.violations} violation(s) in the main-model</span>`
      : summary.reached ? `<span class="ok-text">${summary.reached} in the main-model, all valid</span>`
        : '<span class="dim">reaches nothing in the main-model</span>',
    summary.cases
      ? (summary.casesFailing ? `<span class="bad-text">${summary.casesFailing} of ` +
        `${summary.cases} case(s) failing</span>` : `${summary.cases} case(s), all pass`)
      : '<span class="warn-text">no test case reaches it</span>',
    summary.neverFired ? '<span class="warn-text" title="No test case makes it report anything">' +
      'never fired</span>' : ''
  ].filter(Boolean).join(' · ');
  // The one thing most visits are for: a SPARQL shape is developed in the
  // workbench, an attribute shape grows by attributes.
  const primary = checks.some((c) => c.query) && !attributes.length
    ? `<button class="primary" data-action="bench" data-row="${checks.findIndex((c) => c.query)}" ` +
      'title="Edit and run its query over a case\'s data">Open in workbench</button>'
    : page.ownShape ? '<button class="primary" data-action="addAttribute">+ Attribute</button>' : '';
  const anything = attributes.length || checks.length;

  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(page.label)}</title>
<style nonce="${nonce}">
  body { font-family: var(--vscode-font-family); font-size: var(--vscode-font-size);
         color: var(--vscode-foreground); background: var(--vscode-editor-background);
         padding: 14px 22px 40px; line-height: 1.45; max-width: 1100px; }
  a { color: var(--vscode-textLink-foreground); text-decoration: none; }
  a:hover, a:focus-visible { text-decoration: underline; }
  .crumbs, .dim, .empty { color: var(--vscode-descriptionForeground); }
  .severity { font-size: 0.86em; color: var(--vscode-descriptionForeground); white-space: nowrap; }
  .crumbs { font-size: 0.9em; }
  .empty { font-style: italic; margin: 4px 0; }
  .head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .head h1 { font-size: 1.5em; font-weight: 600; margin: 2px 0; flex: 1 1 auto; }
  .head .acts { display: flex; gap: 6px; }
  .status { margin: 2px 0 6px; }
  .ok-text { color: var(--vscode-testing-iconPassed, #388a34); }
  .bad-text { color: var(--vscode-errorForeground, #f14c4c); }
  .warn-text { color: var(--vscode-editorWarning-foreground, #cca700); }
  .sechead { display: flex; align-items: baseline; gap: 10px; margin: 22px 0 6px;
             border-bottom: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35));
             padding-bottom: 4px; }
  .sechead h2 { font-size: 0.78em; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
                color: var(--vscode-descriptionForeground); margin: 0; flex: 1 1 auto; }
  .chip { font-size: 0.84em; padding: 0 8px; border-radius: 999px; white-space: nowrap;
          border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .chip.ok { color: var(--vscode-testing-iconPassed, #388a34); border-color: currentColor; }
  .chip.bad { color: var(--vscode-errorForeground, #f14c4c); border-color: currentColor; }
  .chip.warn { color: var(--vscode-editorWarning-foreground, #cca700); border-color: currentColor; }
  .bar { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
  button { font: inherit; color: var(--vscode-button-secondaryForeground, inherit);
           background: var(--vscode-button-secondaryBackground, transparent);
           border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35));
           padding: 2px 10px; border-radius: 2px; cursor: pointer; }
  button.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground);
                   border-color: var(--vscode-button-background); }
  .check { display: grid; grid-template-columns: auto 1fr auto auto; gap: 4px 10px;
           align-items: baseline; padding: 6px 8px;
           border-bottom: 1px solid var(--vscode-panel-border, rgba(128,128,128,.2)); }
  .check .tags { display: flex; gap: 6px; }
  .check .acts { display: flex; gap: 4px; }
  .check .acts button { padding: 0 8px; }
  .check details { grid-column: 2 / -1; }
  .kind { font-size: 0.8em; padding: 0 6px; border-radius: 3px;
          background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); }
  details summary { cursor: pointer; color: var(--vscode-descriptionForeground); font-size: 0.92em; }
  .mono, pre { font-family: var(--vscode-editor-font-family); font-size: 0.92em; }
  pre { white-space: pre-wrap; overflow-wrap: anywhere; margin: 6px 0 0; padding: 8px 10px;
        background: var(--vscode-textCodeBlock-background, rgba(128,128,128,.1)); }
  .verbatim { color: var(--vscode-descriptionForeground); white-space: normal; margin-top: 2px;
              font-family: var(--vscode-editor-font-family); font-size: 0.92em; }
  .line { margin: 4px 0; }
  .nodes { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 4px 0; }
  .node.bad { color: var(--vscode-errorForeground, #f14c4c); }
  .fold { margin-top: 6px; }
  .target { display: grid; grid-template-columns: auto 1fr auto; gap: 10px; align-items: baseline;
            padding: 4px 0; }
  .case { display: grid; grid-template-columns: auto auto 1fr auto; gap: 10px; align-items: baseline;
          padding: 4px 0; }
  .table { overflow-x: auto; margin-top: 6px;
           border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  table { border-collapse: collapse; width: 100%; }
  th { text-align: left; font-size: 0.78em; letter-spacing: .06em; text-transform: uppercase;
       color: var(--vscode-descriptionForeground); font-weight: 600; padding: 6px 12px; }
  td { padding: 5px 12px; border-top: 1px solid var(--vscode-panel-border, rgba(128,128,128,.25));
       white-space: nowrap; vertical-align: top; }
  td.coverage { white-space: normal; }
  .violates { color: var(--vscode-errorForeground, #f14c4c); font-size: 0.9em; }
  tr.flag td:first-child { box-shadow: inset 3px 0 0 var(--vscode-errorForeground, #f14c4c); }
  tr:hover td { background: var(--vscode-list-hoverBackground); }
  a.act { color: inherit; border-bottom: 1px dashed var(--vscode-descriptionForeground); }
  a.act:hover, a.act:focus-visible { color: var(--vscode-textLink-foreground); text-decoration: none; }
  td.acts { text-align: right; }
  td.acts button { padding: 0 8px; }
  td.depth1 { padding-left: 30px; } td.depth2 { padding-left: 48px; }
  td.depth3 { padding-left: 66px; } td.depth4 { padding-left: 84px; }
</style></head><body>
<div class="crumbs">Shapes › <span class="mono">${escape(page.name)}</span></div>
<div class="head"><h1>${escape(page.label)}</h1>
  <div class="acts">${primary}<button data-action="pageMenu" title="Open in .ttl, the type page, + Target, Rename…, Merge into…, Delete…, Refresh">⋯</button></div></div>
<p class="status">${status}</p>

<div class="sechead"><h2>Checks</h2>
  <button data-action="addCheck" title="An attribute, or a SPARQL constraint on the whole node">+ Add check ▾</button></div>
${checkRows(checks, cases)}
${attributes.length ? `<div class="table"><table>
<thead><tr><th>Attribute</th><th>Kind</th><th>Presence</th><th>Value</th><th title="How serious its results are when it fires (sh:severity)">Severity</th><th title="How well the test cases prove its constraints: both ways, fires only, never fired">Test coverage</th><th></th></tr></thead>
<tbody>${attributeRows(attributes)}</tbody></table></div>` : ''}
${anything ? '' : '<p class="empty">No checks yet.</p>'}

<div class="sechead"><h2>Applies to</h2></div>
${appliesTo(page)}

<div class="sechead"><h2>Tested by</h2>
  ${page.canNewCase && !cases.some((c) => c.fired)
    ? `<button data-newcase="1" title="${escape(NEW_CASE_TIP)}">+ New case</button>` : ''}</div>
${testedBy(page, cases)}

<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  document.addEventListener('click', (event) => {
    const target = event.target.closest('[data-open],[data-type],[data-shape],[data-case],[data-model],[data-newcase],[data-action],[data-refresh]');
    if (!target) { return; }
    event.preventDefault();
    if (target.dataset.action) {
      vscode.postMessage({ command: target.dataset.action,
                           row: target.dataset.row === undefined ? -1 : Number(target.dataset.row) });
    }
    else if (target.dataset.open) { vscode.postMessage({ command: 'open', at: target.dataset.open }); }
    else if (target.dataset.type) { vscode.postMessage({ command: 'type', name: target.dataset.type }); }
    else if (target.dataset.shape) { vscode.postMessage({ command: 'shape', name: target.dataset.shape }); }
    else if (target.dataset.case) { vscode.postMessage({ command: 'case', file: target.dataset.case }); }
    else if (target.dataset.model !== undefined) { vscode.postMessage({ command: 'model', entity: target.dataset.model }); }
    else if (target.dataset.newcase) { vscode.postMessage({ command: 'newCase' }); }
    else { vscode.postMessage({ command: 'refresh' }); }
  });
</script>
</body></html>`;
}

function renderMessage(message) {
  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';"></head>
<body><p>${escape(message)}</p></body></html>`;
}

/** One reused panel, like the type page. */
class ShapePages {
  constructor(clientHolder) {
    this.clientHolder = clientHolder;
    this.panel = undefined;
    this.current = undefined;
  }

  async show(packageUri, shape, preserveFocus) {
    if (!this.clientHolder.client || !packageUri || !shape) {
      vscode.window.showWarningMessage(
        'SemForge: no package is open, or the language server is not running.');
      return;
    }
    const same = this.panel && this.current && this.current.packageUri === packageUri &&
      this.current.shape === shape;
    this.current = { packageUri, shape };
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        'semforgeShapePage', 'Shape',
        { viewColumn: vscode.ViewColumn.Active, preserveFocus: !!preserveFocus },
        { enableScripts: true, localResourceRoots: [] });
      this.panel.onDidDispose(() => { this.panel = undefined; });
      this.panel.webview.onDidReceiveMessage((message) => this.receive(message));
    } else {
      this.panel.reveal(undefined, !!preserveFocus);
      if (same) {
        return;
      }
    }
    await this.render();
  }

  async render() {
    if (!this.panel || !this.current) {
      return;
    }
    let page;
    try {
      page = await this.clientHolder.client.sendRequest('semforge/shapePage',
        { uri: this.current.packageUri, shape: this.current.shape });
    } catch (error) {
      page = { ok: false, error: error.message || String(error) };
    }
    if (!this.panel) {
      return;
    }
    if (!page.ok) {
      this.panel.title = 'Shape';
      this.panel.webview.html = renderMessage(`SemForge: ${page.error}`);
      return;
    }
    this.page = page;
    this.panel.title = `${page.label} · shape`;
    this.panel.webview.html = renderShapePage(page,
      { nonce: crypto.randomBytes(16).toString('base64') });
  }

  async receive(message) {
    if (!message || !this.current) {
      return;
    }
    const packageUri = this.current.packageUri;
    const edit = EDITS[message.command];
    if (edit) {
      // The type page's own edits: they write into `page.ownShape`, which
      // here is this shape.
      const row = this.page && this.page.attributes
        ? this.page.attributes[message.row] : undefined;
      if (await edit(this, row)) {
        await this.render();
        for (const command of ['semforge.refreshTree', 'semforge.refreshShapes',
          'semforge.refreshKnowledge', 'semforge.refreshModel']) {
          vscode.commands.executeCommand(command);
        }
      }
    } else if (message.command === 'pageMenu') {
      // What is used now and then, kept off the page: one ⋯.
      const page = this.page;
      const items = [];
      if (page.definedAt) {
        items.push({ label: '$(go-to-file) Open in .ttl', message: { command: 'open', at: page.definedAt } });
      }
      for (const t of (page.types || []).filter((type) => type.page)) {
        items.push({ label: `$(symbol-class) Open the ${t.label} type page`,
          message: { command: 'type', name: t.iri } });
      }
      items.push(
        { label: '$(add) + Target', message: { command: 'addTarget', row: -1 } },
        { label: '$(edit) Rename…', message: { command: 'rename' } },
        { label: '$(git-merge) Merge into…', message: { command: 'merge' } },
        { label: '$(trash) Delete…', message: { command: 'delete' } },
        { label: '$(refresh) Refresh', message: { command: 'refresh' } });
      const picked = await vscode.window.showQuickPick(items, { title: page.label });
      if (picked) {
        await this.receive(picked.message);
      }
    } else if (message.command === 'addCheck') {
      const items = [];
      if (this.page.ownShape) {
        items.push({ label: '$(symbol-field) Attribute', description: 'a constraint on one attribute',
          message: { command: 'addAttribute', row: -1 } });
      }
      items.push({ label: '$(beaker) SPARQL constraint',
        description: 'reads the node as a whole; written in the workbench',
        message: { command: 'addSparql' } });
      const picked = await vscode.window.showQuickPick(items, { title: 'Add a check' });
      if (picked) {
        await this.receive(picked.message);
      }
    } else if (message.command === 'checkMenu') {
      const check = (this.page.checks || [])[message.row];
      if (!check) {
        return;
      }
      const items = [
        { label: '$(beaker) Open in SPARQL workbench', message: { command: 'bench', row: message.row } }];
      if (check.kind === 'constraint') {
        items.push({ label: '$(warning) Severity…',
          description: `${check.severity}${check.severityDeclared === false ? ' (default)' : ''}`,
          message: { command: 'checkSeverity', row: message.row } });
      }
      items.push({ label: '$(trash) Remove…', message: { command: 'removeSparql', row: message.row } });
      const picked = await vscode.window.showQuickPick(items, { title: check.message || check.kind });
      if (picked) {
        await this.receive(picked.message);
      }
    } else if (message.command === 'checkSeverity') {
      const check = (this.page.checks || [])[message.row];
      if (check && await require('./severity').chooseSeverity(this.clientHolder.client, packageUri,
        { shape: this.current.shape, query: check.query, label: check.message || 'this check',
          current: `${check.severity}${check.severityDeclared === false ? ' (default)' : ''}` })) {
        await this.render();
      }
    } else if (message.command === 'bench') {
      const check = (this.page.checks || [])[message.row];
      if (check) {
        await vscode.commands.executeCommand('semforge.openSparqlBench',
          { raw: { shape: this.page.iri }, packageUri },
          { query: check.query, kind: check.kind });
      }
    } else if (message.command === 'removeSparql') {
      const check = (this.page.checks || [])[message.row];
      if (check && await vscode.commands.executeCommand('semforge.removeSparqlQuery',
        { raw: { shape: this.page.iri, label: this.page.label }, packageUri },
        { query: check.query, kind: check.kind, message: check.message })) {
        await this.render();
      }
    } else if (message.command === 'addSparql') {
      if (await vscode.commands.executeCommand('semforge.addSparqlConstraint',
        { raw: { shape: this.page.iri, label: this.page.label }, packageUri })) {
        this.render();
      }
    } else if (message.command === 'open' && message.at) {
      await showLocation(message.at, true);
    } else if (message.command === 'type' && message.name) {
      await vscode.commands.executeCommand('semforge.openTypePage',
        { raw: { targetClass: message.name }, packageUri });
    } else if (message.command === 'shape' && message.name) {
      await this.show(packageUri, message.name);
    } else if (message.command === 'case' && message.file) {
      await vscode.commands.executeCommand('semforge.openCasePage',
        { raw: { kind: 'example', file: message.file }, packageUri });
    } else if (message.command === 'model') {
      // "✗ N" on an attribute row: what violates it is in the model -- Main.
      await vscode.commands.executeCommand('semforge.openModelPage', { packageUri },
        { focus: message.entity || undefined });
    } else if (message.command === 'delete') {
      // On success this page closes: its shape is gone.
      await vscode.commands.executeCommand('semforge.deleteShape',
        { raw: { shape: this.current.shape }, packageUri });
    } else if (message.command === 'rename') {
      // On success the renamed shape's page replaces this one.
      await vscode.commands.executeCommand('semforge.renameShape',
        { raw: { shape: this.current.shape }, packageUri });
    } else if (message.command === 'merge') {
      // On success the merged-into shape's page replaces this one.
      await vscode.commands.executeCommand('semforge.mergeShape',
        { raw: { shape: this.page.iri }, packageUri: this.current.packageUri });
    } else if (message.command === 'addTarget' || message.command === 'removeTarget') {
      if (await this.editTarget(message)) {
        await this.render();
        for (const command of ['semforge.refreshShapes', 'semforge.refreshTree']) {
          vscode.commands.executeCommand(command);
        }
      }
    } else if (message.command === 'newCase') {
      await this.newCase();
    } else if (message.command === 'refresh') {
      await this.render();
    }
  }

  /** + Target and Remove: the node selector, edited in place. */
  async editTarget(message) {
    const page = this.page;
    const client = this.clientHolder.client;
    const { packageUri } = this.current;
    let result;
    if (message.command === 'addTarget') {
      const chosen = await pickTarget(client, packageUri,
        `${page.label}: select what else?`);
      if (!chosen) {
        return false;
      }
      result = await client.sendRequest('semforge/addTarget', { uri: packageUri,
        shape: page.iri, targetKind: chosen.kind, target: chosen.target });
    } else {
      const target = (page.targets || [])[message.row];
      if (!target) {
        return false;
      }
      const last = page.targets.length === 1;
      const answer = await vscode.window.showWarningMessage(
        `Take "${target.text}" off ${page.label}?`,
        { modal: true, detail: last
          ? 'It is the only target: the shape will then run only where another shape ' +
            'reaches it through sh:node.'
          : 'The shape keeps its other targets and its constraints.' },
        'Remove');
      if (answer !== 'Remove') {
        return false;
      }
      result = await client.sendRequest('semforge/removeTarget', { uri: packageUri,
        shape: page.iri, targetKind: target.kind, value: target.value });
    }
    if (!result.ok) {
      vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      return false;
    }
    if (result.note) {
      vscode.window.showWarningMessage(`SemForge: ${result.note}`);
    }
    return true;
  }

  /** Write a bad case asserting this shape fires, then open it to edit. */
  async newCase() {
    const page = this.page;
    const name = await vscode.window.showInputBox({
      title: `New case: make ${page.label} fire`,
      prompt: 'A name for the case file (letters, digits, dashes)',
      value: 'fires',
      validateInput: (text) => (/[A-Za-z0-9]/.test(text) ? undefined : 'a name is required')
    });
    if (!name) {
      return;
    }
    const { packageUri } = this.current;
    const made = await this.clientHolder.client.sendRequest('semforge/newCase',
      { uri: packageUri, shape: page.iri, name });
    if (!made.ok) {
      vscode.window.showErrorMessage(`SemForge: ${made.error}`);
      return;
    }
    await this.render();
    vscode.commands.executeCommand('semforge.refreshModel');
    await vscode.commands.executeCommand('semforge.openCasePage',
      { raw: { kind: 'example', file: made.file }, packageUri });
    const open = await vscode.window.showInformationMessage(
      `SemForge: ${made.case} started from ${made.source}. It fails until its ` +
        `data makes ${page.label} fire on ${made.resource}.`, 'Open .jsonld');
    if (open) {
      await showLocation(`${made.file}:1`, true);
    }
  }

  refresh() {
    if (this.panel && this.panel.visible) {
      this.render();
    }
  }
}

async function pickShape(client, packageUri) {
  const answer = await client.sendRequest('semforge/shapes', { uri: packageUri });
  const picked = await vscode.window.showQuickPick(
    (answer.roots || []).map((r) => ({ label: r.label, description: r.detail, shape: r.shape })),
    { title: 'Open the page of a shape', matchOnDescription: true });
  return picked ? picked.shape : undefined;
}

function register(context, clientHolder, session) {
  const pages = new ShapePages(clientHolder);
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.openShapePage', async (node, options) => {
      const client = clientHolder.client;
      const packageUri = (node && node.packageUri) || session.uri;
      if (!client || !packageUri) {
        vscode.window.showWarningMessage(
          'SemForge: no package is open, or the language server is not running.');
        return;
      }
      const shape = node && node.raw ? node.raw.shape : await pickShape(client, packageUri);
      if (shape) {
        await pages.show(packageUri, shape, !!(options && options.preserveFocus));
      }
    }),
    vscode.workspace.onDidSaveTextDocument(() => pages.refresh())
  );
  return pages;
}

module.exports = { register, renderShapePage, ShapePages };
