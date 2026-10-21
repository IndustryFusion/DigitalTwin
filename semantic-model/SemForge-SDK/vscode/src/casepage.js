/*
 * The test case page: what one case claims, whether the claims hold, and the
 * data it uses -- entity cards instead of a nine-level tree, every violation
 * on the attribute it is about.
 *
 * Computed by the SDK (`semforge/casePage`, which runs the case exactly as
 * `semforge test` does) and only rendered here. `renderCasePage` is pure, so
 * it is tested without a window; everything shown is escaped, and script and
 * style run only with the per-render nonce.
 */

const crypto = require('crypto');
const vscode = require('vscode');

const { showLocation } = require('./reveal');
const { escape } = require('./typepage');

function chip(text, tone, title) {
  return `<span class="chip ${tone || ''}"${title ? ` title="${escape(title)}"` : ''}>` +
    `${escape(text)}</span>`;
}

function open(text, file, line, title) {
  return file
    ? `<a href="#" data-open="${escape(`${file}:${line || 1}`)}"` +
      `${title ? ` title="${escape(title)}"` : ''}>${escape(text)}</a>`
    : escape(text);
}

function problem(violation) {
  return `<div class="problem" title="${escape(violation.detail || '')}">` +
    `${escape(violation.text)} <span class="dim">· ${escape(violation.shape)}</span></div>`;
}

/**
 * An entity's attributes, sub-attributes nested. `at` addresses the row for
 * the editing messages ("file.card.row.row"); a value the data lets be edited
 * is a link, and every row with a Tests-tree row behind it has a ⋯.
 */
function attributeRows(rows, file, depth, at) {
  // Only the latest observation of each datasetId is shown -- the one that is
  // validated; the earlier ones fold under it behind "+N earlier", so a
  // series does not crowd the card. A series is (attribute, datasetId).
  const seriesOf = (row) => `${row.term}|${row.dataset || '@none'}`;
  const earlier = {};
  rows.forEach((row, index) => {
    if (row.superseded) {
      (earlier[seriesOf(row)] = earlier[seriesOf(row)] || []).push(index);
    }
  });
  const series = (row) => `${at === undefined ? 'x' : at}-${Object.keys(earlier).indexOf(seriesOf(row))}`;
  const one = (row, index) => {
    const here = at === undefined ? undefined : `${at}.${index}`;
    const editable = here !== undefined && row.node && row.node.editable;
    const value = editable
      ? `<a href="#" class="act" data-edit="${here}" title="Change the value">` +
        `${escape(row.value) || '<span class="dim">(none)</span>'}</a>`
      : escape(row.value);
    // When it was observed: a click opens the date-and-time picker. An
    // instance without one counts as now, as on the platform.
    const time = here !== undefined && row.stamp && row.kind
      ? ` <a href="#" class="stamp" data-stamp="${here}"` +
        ` data-current="${escape(row.observedAt)}" data-latest="${escape(row.latestAt || '')}"` +
        ` title="${row.observedAt ? `observedAt ${escape(row.observedAt)} — click to change`
          : 'No observedAt: it counts as now. Click to give it a time'}">` +
        `${row.observedAt ? escape(row.observedAt.replace('T', ' ').replace(/\.000Z$|Z$/, ' UTC'))
          : '◷'}</a>` : '';
    const older = !row.superseded && earlier[seriesOf(row)] ? earlier[seriesOf(row)].length : 0;
    const superseded = older
      ? ` <a href="#" class="history" data-history="${series(row)}" title="${older} earlier ` +
        'observation(s) of this instance. Only the latest is validated; click to show them.">' +
        `+${older} earlier</a>` : '';
    const menu = here !== undefined && (row.node || row.attributeNode)
      ? ` <button class="mini" data-rowmenu="${here}" title="More: sub-attribute, observation, ` +
        'the rule">⋯</button>' : '';
    return `<div class="attr${depth ? ` depth${Math.min(depth, 4)}` : ''}` +
      `${row.superseded ? ' superseded' : ''}">` +
      `<span class="name">${open(row.display || row.name, file, row.line, row.term)}</span>` +
      `<span class="value">${value}` +
      `${row.unitText ? ` <span class="unit" title="unitCode ${escape(row.unitCode)}">${escape(row.unitText)}</span>` : ''}` +
      `${row.instances > 1 && !(row.dataset && row.dataset !== '@none') ? ' <span class="dim">· default</span>' : ''}` +
      `${time}${superseded}${menu}</span>` +
      `${row.violations.map(problem).join('')}</div>` +
      attributeRows(row.children || [], file, depth + 1, here);
  };
  // Each current row, then -- folded -- the earlier observations of its series.
  return rows.map((row, index) => {
    if (row.superseded) {
      return '';
    }
    const before = earlier[seriesOf(row)] || [];
    return one(row, index) + (before.length
      ? `<div class="older" data-series="${series(row)}">` +
        before.map((position) => one(rows[position], position)).join('') + '</div>'
      : '');
  }).join('');
}

function anyViolation(rows) {
  return (rows || []).some((row) => row.violations.length || anyViolation(row.children));
}

function card(entity, focused, at) {
  const bad = entity.violations.length || anyViolation(entity.attributes);
  const add = entity.node && at !== undefined
    ? `<button class="mini" data-addattr="${at}" title="Add an attribute to ${escape(entity.id)}">` +
      '+ Attribute</button>' : '';
  return `<div class="card${bad ? ' bad' : ''}${focused ? ' focus" id="focus' : ''}">` +
    `<div class="title">${open(entity.id || '(no id)', entity.file, entity.line)}` +
    `${entity.type ? ` <a href="#" class="dim" data-type="${escape(entity.type)}"` +
      ` title="Open the ${escape(entity.type)} page">· ${escape(entity.type)}</a>` : ''}` +
    `<span class="acts">${add}</span></div>` +
    `${entity.error ? `<div class="problem">${escape(entity.error)}</div>` : ''}` +
    `${entity.violations.map(problem).join('')}` +
    `${attributeRows(entity.attributes, entity.file, 0, at) ||
      '<div class="dim">no attributes</div>'}</div>`;
}

const ASSERT_TIP = 'Assert it if the case MEANS this: it then fails the day this stops ' +
  'firing. If it fired only because the data is incomplete, fix the data instead, ' +
  'so the case fails for exactly one reason.';

function claimRow(claim, unasserted, index, at) {
  const explained = claim.explained || {};
  const where = claim.resource ? ` on <span class="mono">${escape(claim.resource)}</span>` : '';
  const status = unasserted ? chip('also fired', 'warn',
    'Not asserted. Either a second problem this case found, or a sign the data ' +
    'is not what the case means it to be.')
    : claim.stale ? chip('names no shape', 'bad', 'No shape declares this constraint: the ' +
      'shape was renamed or removed. It can never fire.')
    : claim.holds ? chip('holds', 'ok') : chip('does not hold', 'bad');
  const parts = claim.constraint.split('/');
  const actions = unasserted
    ? `<span class="acts"><button data-assert="${index}" title="${escape(ASSERT_TIP)}">` +
      'Assert it</button>' +
      (at ? `<button data-open="${escape(at)}">Open in .jsonld</button>` : '') + '</span>'
    : claim.stale
    ? '<span class="acts">' + (claim.suggest
      ? `<button class="primary" data-retarget="${index}" title="Renamed? ${escape(claim.suggest)} ` +
        `declares the same constraint and fires here">Rename to ` +
        `${escape(claim.suggest.split('/')[0].split(':').pop())}</button>` : '') +
      `<button data-dropassert="${index}" title="Remove this assert from the case">Remove</button></span>`
    : '';
  return `<div class="claim${unasserted ? ' extra' : ''}">${status}<span class="what">` +
    `${escape(explained.text || parts.slice(1).join(' · ').replace('ConstraintComponent', ''))}` +
    `${where} <span class="dim">· ${escape(parts[0].split(':').pop())}</span></span>` +
    `${actions}</div>`;
}

function renderCasePage(page, options) {
  const nonce = (options && options.nonce) || '';
  const csp = `default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';`;
  const claims = page.claims || [];
  const unasserted = page.unasserted || [];
  const files = page.files || [];
  const model = page.kind === 'model';
  const crumbs = (page.case || '').split('/').slice(0, -1).map(escape).join(' › ');
  // The entity a tree click named: its first card is marked and scrolled to.
  let pending = options && options.focus;
  const mark = (c) => {
    if (pending && c.id === pending) {
      pending = undefined;
      return true;
    }
    return false;
  };
  // Where each entity is written, so "Open in .jsonld" lands on it.
  const located = {};
  files.forEach((file) => file.cards.forEach((c) => {
    if (c.id && !located[c.id]) { located[c.id] = `${c.file}:${c.line}`; }
  }));

  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escape(page.name)}</title>
<style nonce="${nonce}">
  body { font-family: var(--vscode-font-family); font-size: var(--vscode-font-size);
         color: var(--vscode-foreground); background: var(--vscode-editor-background);
         padding: 16px 22px 40px; line-height: 1.45; }
  a { color: var(--vscode-textLink-foreground); text-decoration: none; }
  a:hover, a:focus-visible { text-decoration: underline; }
  .dim, .crumbs { color: var(--vscode-descriptionForeground); }
  .unit { color: var(--vscode-descriptionForeground); margin-left: 0.15em; }
  .stamp { color: var(--vscode-descriptionForeground); font-size: 0.88em; margin-left: 0.4em; }
  .attr.superseded > .name, .attr.superseded > .value > .act,
  .attr.superseded > .value > .unit { opacity: 0.6; }
  .history { font-size: 0.82em; margin-left: 0.4em; padding: 0 5px; border-radius: 8px;
             color: var(--vscode-descriptionForeground);
             border: 1px solid var(--vscode-widget-border, rgba(128, 128, 128, 0.35)); }
  .history.open { color: var(--vscode-foreground); }
  .older { display: none; }
  .older.open { display: grid; gap: 4px; padding-left: 10px;
                border-left: 2px solid var(--vscode-widget-border, rgba(128, 128, 128, 0.35)); }
  .stampedit { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px;
               margin: 2px 0 6px; padding: 6px 8px; border-radius: 4px;
               border: 1px solid var(--vscode-widget-border, rgba(128, 128, 128, 0.35));
               background: var(--vscode-editorWidget-background, transparent); }
  .stampedit .zone { color: var(--vscode-descriptionForeground); font-size: 0.86em; }
  .stampedit input { font-family: var(--vscode-editor-font-family); font-size: 0.92em;
                     color: var(--vscode-input-foreground); background: var(--vscode-input-background);
                     border: 1px solid var(--vscode-input-border, transparent); padding: 1px 4px; }
  .stampedit button.mini { margin-left: 0; white-space: nowrap; }
  .crumbs { font-size: 0.92em; }
  .mono { font-family: var(--vscode-editor-font-family); font-size: 0.92em; }
  h1 { font-size: 1.5em; font-weight: 600; margin: 4px 0 4px; }
  .lede { margin: 0 0 10px; max-width: 80ch; }
  h2 { font-size: 0.78em; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
       color: var(--vscode-descriptionForeground); margin: 24px 0 8px; }
  .chips, .bar { display: flex; flex-wrap: wrap; gap: 6px; }
  .bar { margin-top: 10px; gap: 8px; }
  .chip { font-size: 0.86em; padding: 1px 8px; border-radius: 999px; white-space: nowrap;
          border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .chip.ok { color: var(--vscode-testing-iconPassed, #388a34); border-color: currentColor; }
  .chip.bad { color: var(--vscode-errorForeground, #f14c4c); border-color: currentColor; }
  .chip.warn { color: var(--vscode-editorWarning-foreground, #cca700); border-color: currentColor; }
  button { font: inherit; color: var(--vscode-button-secondaryForeground, inherit);
           background: var(--vscode-button-secondaryBackground, transparent);
           border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35));
           padding: 3px 10px; border-radius: 2px; cursor: pointer; }
  .claims { display: grid; gap: 6px; }
  .claim.extra { grid-template-columns: auto 1fr auto; }
  .acts { display: flex; gap: 6px; }
  .claim { display: grid; grid-template-columns: auto 1fr; gap: 10px; align-items: baseline;
           padding: 6px 10px; border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .failures { margin: 8px 0 0; padding-left: 1.2em; color: var(--vscode-errorForeground, #f14c4c); }
  .file { margin-top: 18px; }
  .file .head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; margin-bottom: 8px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
  .card { border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); border-radius: 4px;
          padding: 10px 12px; display: grid; gap: 4px; align-content: start; }
  .card.bad { border-color: var(--vscode-errorForeground, #f14c4c); }
  .card.focus { box-shadow: 0 0 0 2px var(--vscode-focusBorder, #0078d4);
                background: var(--vscode-editor-selectionHighlightBackground, transparent); }
  .attr.depth1 { padding-left: 16px; } .attr.depth2 { padding-left: 32px; }
  .attr.depth3 { padding-left: 48px; } .attr.depth4 { padding-left: 64px; }
  .card .title { font-weight: 600; margin-bottom: 4px; }
  .attr { display: grid; grid-template-columns: minmax(7em, auto) 1fr; gap: 2px 12px; }
  .attr .value { font-family: var(--vscode-editor-font-family); font-size: 0.92em;
                 overflow-wrap: anywhere; }
  button.mini { padding: 0 6px; font-size: 0.86em; margin-left: 4px; }
  .card .title { display: flex; flex-wrap: wrap; gap: 4px; align-items: baseline; }
  .card .title .acts, .file .head .acts { margin-left: auto; }
  .problem { grid-column: 1 / -1; color: var(--vscode-errorForeground, #f14c4c);
             border-left: 2px solid currentColor; padding-left: 8px; font-size: 0.92em; }
</style></head><body>
<div class="crumbs">${crumbs}</div>
<h1>${escape(page.name)}</h1>
${page.description ? `<p class="lede">${escape(page.description)}</p>` : ''}
${model ? `<div class="chips">
  ${chip(`${(page.summary || {}).entities || 0} entities`)}
  ${(page.summary || {}).violations
    ? chip(`${page.summary.violations} violation(s)`, 'warn',
      'The model declares nothing and cannot fail: these are information.')
    : chip('all valid', 'ok')}
</div>` : `<div class="chips">
  ${chip(`expects ${page.expect}`)}
  ${page.passed ? chip('passes', 'ok') : chip('fails', 'bad')}
  ${page.residuePinned ? chip('residue pinned', '', 'Everything else that fires is pinned by digest') : ''}
  ${chip(`${(page.summary || {}).entities || 0} entities`)}
</div>`}
${(page.failures || []).length
    ? `<ul class="failures">${page.failures.map((f) => `<li>${escape(f)}</li>`).join('')}</ul>` : ''}
<div class="bar">
  ${model ? `<button data-open="${escape(page.file)}:1">Open the model file</button>
  <button data-refresh="1">Refresh</button>`
    : '<button data-pagemenu="1" title="Open the case file, its expectations, Clone…, Rename…, Delete…, Refresh">⋯</button>'}
</div>

${model ? '' : `<h2>Claims</h2>
${claims.length || unasserted.length
    ? `<div class="claims">${claims.map((c, i) => claimRow(c, false, i)).join('')}` +
      `${unasserted.map((c, i) => claimRow(c, true, i, located[c.resource])).join('')}</div>`
    : `<p class="dim">This case asserts nothing${page.expect === 'valid'
      ? ' beyond being valid.' : '. A bad case that asserts nothing is an unfinished test.'}</p>`}`}

<h2>${model ? 'Entities' : 'Data'}</h2>
${files.map((file, f) => `<div class="file"><div class="head">
  ${chip(file.role === 'case' ? 'this case' : file.role === 'model' ? 'model' : 'included')}
  ${open(file.relative, file.path, 1)}
  ${file.sharedBy.length ? `<span class="dim" title="${escape(file.sharedBy.join('\n'))}">· shared with ` +
    `${file.sharedBy.length} other case(s) — an edit here changes them too</span>` : ''}
  <span class="acts"><button class="mini" data-addentity="${f}" title="Add an entity to this file">` +
  `+ Entity</button></span>
</div><div class="cards">${file.cards.map((c, j) => card(c, mark(c), `${f}.${j}`)).join('')}</div></div>`).join('')}

<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  const focused = document.getElementById('focus');
  if (focused) { focused.scrollIntoView({ block: 'center' }); }
  // observedAt: a date-and-time picker beside the time, in UTC, to the
  // millisecond; Now, Just after the latest of its datasetId, Remove.
  const utc = (iso) => (iso || new Date().toISOString()).replace(/Z$/, '').slice(0, 23);
  // The picker is a panel of its own UNDER the row, across the card: the row
  // stays as it is, and the controls run left to right.
  function stampEditor(link) {
    const row = link.closest('.attr') || link;
    const open = row.nextElementSibling;
    if (open && open.classList.contains('stampedit')) { open.remove(); return; }
    const box = document.createElement('div');
    box.className = 'stampedit';
    const zone = document.createElement('span');
    zone.className = 'zone';
    zone.textContent = 'observedAt (UTC)';
    const input = document.createElement('input');
    input.type = 'datetime-local';
    input.step = '0.001';
    input.value = utc(link.dataset.current);
    input.title = 'Enter writes it, Esc closes';
    box.append(zone, input);
    const send = (value) => {
      vscode.postMessage({ command: 'stamp', at: link.dataset.stamp, value });
      box.remove();
    };
    const button = (label, title, act) => {
      const b = document.createElement('button');
      b.className = 'mini';
      b.textContent = label;
      b.title = title;
      b.addEventListener('click', (event) => { event.preventDefault(); event.stopPropagation(); act(); });
      box.append(b);
    };
    const set = () => {
      const value = input.value.length === 16 ? input.value + ':00.000'
        : input.value.length === 19 ? input.value + '.000' : input.value;
      if (value) { send(value + 'Z'); }
    };
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') { event.preventDefault(); set(); }
      if (event.key === 'Escape') { event.preventDefault(); box.remove(); }
    });
    button('Set', 'Write this time as its observedAt (Enter)', set);
    button('Now', 'The time it is now', () => send(new Date().toISOString()));
    if (link.dataset.latest) {
      button('Just after the latest', 'One millisecond after the latest of its datasetId',
        () => send(new Date(Date.parse(link.dataset.latest) + 1).toISOString()));
    }
    if (link.dataset.current) {
      button('Remove', 'No observedAt: it then counts as now, as on the platform', () => send(''));
    }
    button('×', 'Close (Esc)', () => box.remove());
    row.after(box);
    input.focus();
  }
  document.addEventListener('click', (event) => {
    const history = event.target.closest('[data-history]');
    if (history) {
      event.preventDefault();
      document.querySelectorAll('.older').forEach(function (older) {
        if (older.dataset.series === history.dataset.history) { older.classList.toggle('open'); }
      });
      history.classList.toggle('open');
      return;
    }
    const stamp = event.target.closest('[data-stamp]');
    if (stamp) { event.preventDefault(); stampEditor(stamp); return; }
    if (event.target.closest('.stampedit')) { return; }
    const target = event.target.closest('[data-open],[data-type],[data-refresh],[data-assert],' +
      '[data-edit],[data-rowmenu],[data-addattr],[data-addentity],[data-pagemenu],' +
      '[data-retarget],[data-dropassert]');
    if (!target) { return; }
    event.preventDefault();
    const d = target.dataset;
    if (d.pagemenu) { vscode.postMessage({ command: 'pageMenu' }); }
    else if (d.retarget !== undefined) { vscode.postMessage({ command: 'retargetAssert', index: Number(d.retarget) }); }
    else if (d.dropassert !== undefined) { vscode.postMessage({ command: 'removeAssert', index: Number(d.dropassert) }); }
    else if (d.edit) { vscode.postMessage({ command: 'edit', at: d.edit }); }
    else if (d.rowmenu) { vscode.postMessage({ command: 'rowMenu', at: d.rowmenu }); }
    else if (d.addattr) { vscode.postMessage({ command: 'addAttribute', at: d.addattr }); }
    else if (d.addentity !== undefined) { vscode.postMessage({ command: 'addEntity', at: d.addentity }); }
    else if (target.dataset.assert !== undefined) {
      vscode.postMessage({ command: 'assert', index: Number(target.dataset.assert) });
    }
    else if (target.dataset.open) { vscode.postMessage({ command: 'open', at: target.dataset.open }); }
    else if (target.dataset.type) { vscode.postMessage({ command: 'type', name: target.dataset.type }); }
    else { vscode.postMessage({ command: 'refresh' }); }
  });
</script>
</body></html>`;
}

// The model's own data has no case file; this stands in for one.
const MODEL = '@model';

class CasePages {
  constructor(clientHolder) {
    this.clientHolder = clientHolder;
    this.panel = undefined;
    this.current = undefined;
  }

  /** `focus` is an entity id to mark; `preserveFocus` keeps the keyboard in
   *  the tree the click came from. */
  async show(packageUri, caseFile, focus, preserveFocus) {
    if (!this.clientHolder.client || !packageUri || (!caseFile && caseFile !== MODEL)) {
      vscode.window.showWarningMessage(
        'SemForge: no package is open, or the language server is not running.');
      return;
    }
    const same = this.panel && this.current && this.current.packageUri === packageUri &&
      this.current.caseFile === caseFile && this.current.focus === focus;
    this.current = { packageUri, caseFile, focus };
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        'semforgeCasePage', 'Test case',
        { viewColumn: vscode.ViewColumn.Active, preserveFocus: !!preserveFocus },
        { enableScripts: true, localResourceRoots: [] });
      this.panel.onDidDispose(() => { this.panel = undefined; });
      this.panel.webview.onDidReceiveMessage((message) => this.receive(message));
    } else {
      this.panel.reveal(undefined, !!preserveFocus);
      if (same) {
        return;                        // clicked again: already showing it
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
      page = this.current.caseFile === MODEL
        ? await this.clientHolder.client.sendRequest('semforge/modelPage',
          { uri: this.current.packageUri })
        : await this.clientHolder.client.sendRequest('semforge/casePage',
          { uri: this.current.packageUri, case: this.current.caseFile });
    } catch (error) {
      page = { ok: false, error: error.message || String(error) };
    }
    if (!this.panel) {
      return;
    }
    if (!page.ok) {
      this.panel.title = 'Test case';
      this.panel.webview.html = `<!DOCTYPE html><html><head><meta charset="utf-8">` +
        `<meta http-equiv="Content-Security-Policy" content="default-src 'none';"></head>` +
        `<body style="font-family:var(--vscode-font-family);color:var(--vscode-foreground);` +
        `padding:20px"><p>SemForge: ${escape(page.error)}</p></body></html>`;
      return;
    }
    this.page = page;
    this.panel.title = page.kind === 'model'
      ? 'Main · instances' : `${page.name.replace(/\.jsonld$/, '')} · test case`;
    this.panel.webview.html = renderCasePage(page,
      { nonce: crypto.randomBytes(16).toString('base64'), focus: this.current.focus });
  }

  async receive(message) {
    if (!message || !this.current) {
      return;
    }
    if (message.command === 'assert') {
      await this.assert(message.index);
    } else if (message.command === 'open' && message.at) {
      await showLocation(message.at, true);
    } else if (message.command === 'type' && message.name) {
      await vscode.commands.executeCommand('semforge.openTypePage',
        { raw: { targetClass: message.name }, packageUri: this.current.packageUri });
    } else if (message.command === 'refresh') {
      await this.render();
    } else if (['retargetAssert', 'removeAssert'].includes(message.command) && this.page) {
      // An assert naming a shape that is gone: point it at the one it meant,
      // or take it out.
      const claim = (this.page.claims || [])[message.index];
      if (!claim || !claim.stale) {
        return;
      }
      const retarget = message.command === 'retargetAssert';
      const result = await this.clientHolder.client.sendRequest('semforge/removeUse', {
        uri: this.current.packageUri, kind: retarget ? 'retarget' : 'assert',
        file: this.page.expectations, case: claim.entry, index: claim.index,
        constraint: claim.suggest });
      if (!result.ok) {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
        return;
      }
      if (result.note) {
        vscode.window.showWarningMessage(`SemForge: ${result.note}`);
      }
      await this.render();
      vscode.commands.executeCommand('semforge.refreshModel');
    } else if (message.command === 'pageMenu' && this.page) {
      const page = this.page;
      const items = [{ label: '$(go-to-file) Open the case file', message: { command: 'open', at: `${page.file}:1` } }];
      if (page.expectations) {
        items.push({ label: '$(list-unordered) Open its expectations',
          message: { command: 'open', at: `${page.expectations}:1` } });
      }
      items.push({ label: '$(copy) Clone…', description: 'valid ↔ invalid, or the same',
        message: { command: 'clone' } },
      { label: '$(edit) Rename…', message: { command: 'rename' } },
      { label: '$(trash) Delete…', message: { command: 'delete' } },
        { label: '$(refresh) Refresh', message: { command: 'refresh' } });
      const picked = await vscode.window.showQuickPick(items, { title: page.name });
      if (picked) {
        await this.receive(picked.message);
      }
    } else if (message.command === 'delete' && this.page) {
      // On success this page closes: its case is gone.
      await vscode.commands.executeCommand('semforge.deleteTestCase',
        { raw: { kind: 'example', file: this.page.file }, packageUri: this.current.packageUri });
    } else if (message.command === 'clone' && this.page) {
      // On success the clone's page replaces this one.
      await vscode.commands.executeCommand('semforge.cloneTestCase',
        { raw: { kind: 'example', file: this.page.file, expect: this.page.expect },
          packageUri: this.current.packageUri });
    } else if (message.command === 'rename' && this.page) {
      // On success the case page reopens on the renamed file.
      await vscode.commands.executeCommand('semforge.renameTestCase',
        { raw: { kind: 'example', file: this.page.file }, packageUri: this.current.packageUri });
    } else if (['edit', 'rowMenu', 'addAttribute', 'addEntity', 'stamp'].includes(message.command)) {
      await this.edit(message.command, `${message.at}`, message.value);
    }
  }

  /** The row, card or file a page address ("file.card.row.row…") names. */
  locate(at) {
    const [f, c, ...rows] = at.split('.').map(Number);
    const file = ((this.page && this.page.files) || [])[f];
    const card = file && c !== undefined && !Number.isNaN(c) ? file.cards[c] : undefined;
    let row;
    let list = card ? card.attributes : [];
    for (const index of rows) {
      row = (list || [])[index];
      list = row ? row.children : [];
    }
    return { file, card, row };
  }

  /**
   * Editing from the page goes through the Instances view's own commands, given
   * the tree row the server attached -- so the page asks the same questions
   * (the shape's allowed values, a known attribute) and writes the same way.
   * Afterwards the case re-runs and the page shows what the change did.
   */
  async edit(command, at, value) {
    const { file, card, row } = this.locate(at);
    const packageUri = this.current.packageUri;
    const run = (name, raw) => vscode.commands.executeCommand(name, { raw, packageUri });
    if (command === 'addEntity' && file) {
      await run('semforge.addEntity', { kind: 'example', file: file.path });
    } else if (command === 'addAttribute' && card && card.node) {
      // What the entity already has, by datasetId: an attribute it has is
      // added again as another instance, or -- same datasetId -- as another
      // observation at a time of its own, so the dialog must know.
      const has = {};
      for (const attribute of card.attributes || []) {
        (has[attribute.term] = has[attribute.term] || new Set()).add(attribute.dataset || '@none');
      }
      const children = Object.entries(has).map(([term, datasets]) => ({
        kind: 'attribute', attributePath: [term], datasets: [...datasets] }));
      await run('semforge.addAttribute', Object.assign({}, card.node, { children }));
    } else if (command === 'edit' && row && row.node) {
      await run('semforge.editValue', row.node);
    } else if (command === 'stamp' && row && row.stamp && card) {
      // From the page's picker: its value, or '' to remove it.
      await vscode.commands.executeCommand('semforge.setObservedAt', {
        packageUri, entity: card.id, file: card.file || (file && file.path),
        attributePath: row.stamp.attributePath, index: row.stamp.index,
        observedAt: value || '' });
    } else if (command === 'rowMenu' && row) {
      const items = [];
      if (row.node && row.node.editable) {
        items.push({ label: '$(edit) Edit value', run: () => run('semforge.editValue', row.node) });
      }
      if (row.attributeNode) {
        items.push(
          { label: '$(add) Add sub-attribute',
            run: () => run('semforge.addSubAttribute', row.attributeNode) },
          { label: '$(history) Add observation',
            run: () => run('semforge.addObservation', row.attributeNode) },
          // Another datasetId: what sh:minCount / sh:maxCount count.
          { label: '$(layers) Add instance…', description: 'another datasetId',
            run: () => run('semforge.addInstance', row.node && row.node.kind === 'dataset'
              ? row.node : row.attributeNode) });
      }
      const instance = row.node && row.node.kind === 'dataset' ? row.node
        : row.attributeNode && row.attributeNode.datasetId ? row.attributeNode : null;
      // Its unit (unitCode): a Property's, set on this instance and every
      // observation of it.
      if (instance && row.kind !== 'Relationship') {
        items.push({ label: '$(symbol-ruler) Unit…',
          description: row.unitCode ? `${row.unitCode}${row.unitText && row.unitText !== row.unitCode
            ? ` (${row.unitText})` : ''}` : 'none',
          run: () => run('semforge.setUnitCode', Object.assign({}, instance,
            { current: row.unitCode, entityType: instance.entityType || (card && card.type) })) });
      }
      if (instance) {
        items.push({ label: '$(symbol-key) Change datasetId…',
          description: instance.datasetId === '@none' ? 'default' : instance.datasetId,
          run: () => run('semforge.setDatasetId', instance) });
      }
      if (row.node) {
        items.push({ label: '$(symbol-ruler) Go to the SHACL rule',
          run: () => run('semforge.goToShape', row.node) });
      }
      items.push({ label: '$(go-to-file) Open in .jsonld',
        run: () => showLocation(`${card ? card.file : file.path}:${row.line || 1}`, true) });
      // Taking it out: just this instance -- its datasetId -- when the row
      // is one of several, and the whole attribute only when asked for by
      // name. A removal that took every instance of hasHeight when one was
      // meant is the mistake this guards against.
      if (row.node && row.node.kind === 'dataset') {
        items.push({ label: `$(trash) Remove ${row.display || row.name}`,
          description: 'this instance only',
          run: () => run('semforge.removeCaseValue', row.node) });
      }
      if (row.attributeNode) {
        items.push({ label: `$(trash) Remove ${row.name}…`,
          description: row.instances > 1 ? `all ${row.instances} instances, from this entity`
            : 'from this entity',
          run: () => run('semforge.removeCaseValue', row.attributeNode) });
      }
      const picked = await vscode.window.showQuickPick(items,
        { title: `${row.name} on ${card ? card.id : ''}` });
      if (!picked) {
        return;
      }
      await picked.run();
    } else {
      return;
    }
    await this.render();
  }

  /** "Assert it": the firing becomes a claim, written into the case's
   *  expectations.yaml, and the page re-renders with it under holds. */
  async assert(index) {
    const firing = this.page && (this.page.unasserted || [])[index];
    if (!firing) {
      return;
    }
    const result = await this.clientHolder.client.sendRequest('semforge/addAssert', {
      uri: this.current.packageUri, case: this.page.case,
      constraint: firing.constraint, resource: firing.resource });
    if (!result.ok) {
      vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      return;
    }
    vscode.window.setStatusBarMessage(
      `SemForge: ${this.page.name} now asserts ` +
        `${firing.constraint.split('/').slice(1, 2).join('')} on ${firing.resource}`, 5000);
    if (result.note) {
      vscode.window.showWarningMessage(`SemForge: ${result.note}`);
    }
    await this.render();
    vscode.commands.executeCommand('semforge.refreshModel');
  }

  refresh() {
    if (this.panel && this.panel.visible) {
      this.render();
    }
  }
}

/** Every declared case, from the Model tree's payload, for the palette. */
async function pickCase(client, packageUri) {
  const answer = await client.sendRequest('semforge/model', { uri: packageUri, detail: 'summary' });
  const cases = [];
  const walk = (nodes) => (nodes || []).forEach((node) => {
    if (node.kind === 'example' && node.file) {
      cases.push({ label: node.label, description: node.detail, file: node.file });
    }
    walk(node.children);
  });
  walk(answer.roots);
  if (!cases.length) {
    vscode.window.showInformationMessage(
      'SemForge: this package declares no test cases. Cases live in an ' +
        'expectations.yaml under examples/.');
    return undefined;
  }
  const picked = await vscode.window.showQuickPick(cases,
    { title: 'Open the page of a test case', matchOnDescription: true });
  return picked ? picked.file : undefined;
}

function register(context, clientHolder, session) {
  const pages = new CasePages(clientHolder);
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.openCasePage', async (node, options) => {
      const client = clientHolder.client;
      const packageUri = (node && node.packageUri) || session.uri;
      if (!client || !packageUri) {
        vscode.window.showWarningMessage(
          'SemForge: no package is open, or the language server is not running.');
        return;
      }
      if (node && node.raw && !node.raw.file) {
        // The model scratchpad sits in the same tree as the cases but is not
        // one: it has no claims to check, so it gets the Main page.
        await pages.show(packageUri, MODEL, options && options.focus,
          !!(options && options.preserveFocus));
        return;
      }
      const caseFile = node && node.raw ? node.raw.file : await pickCase(client, packageUri);
      if (caseFile) {
        await pages.show(packageUri, caseFile, options && options.focus,
          !!(options && options.preserveFocus));
      }
    }),
    vscode.commands.registerCommand('semforge.openModelPage', async (node, options) => {
      const packageUri = (node && node.packageUri) || session.uri;
      await pages.show(packageUri, MODEL, options && options.focus,
        !!(options && options.preserveFocus));
    }),
    vscode.workspace.onDidSaveTextDocument(() => pages.refresh())
  );
  return pages;
}

module.exports = { register, renderCasePage, CasePages };
