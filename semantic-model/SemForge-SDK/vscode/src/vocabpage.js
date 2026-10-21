/*
 * The vocabulary page: one value list -- MachineState, Wasteclass -- and its
 * care.
 *
 * A vocabulary value is used in the data, in SPARQL queries, in the shapes and
 * in the knowledge itself, so the page lists every value with where it is
 * used, and the constraints that draw their values from the class. Managing
 * it happens here: + Value, a click on the label, and each value's ⋯ --
 * Label…, Open in .ttl, Delete… (which shows the uses first and refuses
 * quietly to break them).
 *
 * `renderVocabularyPage` is a pure function from the payload
 * `semforge/vocabularyPage` returns; everything shown is escaped, and script
 * and style run only with the per-render nonce.
 */

const crypto = require('crypto');
const vscode = require('vscode');
const { pickVocabularyNamespace, NAME, CLASS_NAME } = require('./namespacepick');

const { showLocation } = require('./reveal');
const { escape } = require('./typepage');

const REFRESH_VIEWS = ['semforge.refreshKnowledge', 'semforge.refreshTree',
  'semforge.refreshShapes'];

function chip(text, tone, title) {
  return `<span class="chip ${tone || ''}"${title ? ` title="${escape(title)}"` : ''}>` +
    `${escape(text)}</span>`;
}

function openable(text, at, title) {
  return at
    ? `<a href="#" data-open="${escape(at)}"${title ? ` title="${escape(title)}"` : ''}>${escape(text)}</a>`
    : escape(text);
}

function usedChips(uses) {
  if (!uses.total) {
    return chip('unused', 'warn', 'No data, shape, query or knowledge statement names it.');
  }
  const where = uses.places.map((p) =>
    `${p.kind}: ${p.file}:${p.line}${p.owner ? ` (${p.owner})` : ''}`).join('\n');
  return [['data', 'in data'], ['queries', 'in queries'], ['shapes', 'in shapes'],
    ['knowledge', 'in knowledge']]
    .filter(([key]) => uses[key])
    .map(([key, words]) => chip(`${uses[key]} ${words}`, key === 'data' ? 'ok' : '', where))
    .join(' ');
}

/** A value's properties as a reader says them: valid for Filter. */
function propertyText(p) {
  const value = p.link ? `<a href="#" data-vocab="${escape(p.link)}">${escape(p.shortValue || p.value)}</a>`
    : p.type ? `<a href="#" data-type="${escape(p.type)}" title="Open the type page">` +
      `${escape(p.shortValue || p.value)}</a>`
      : escape(p.shortValue || p.value);
  return `<div title="${escape(`${p.property} ${p.value}`)}"><span class="dim">` +
    `${escape(p.name || p.property)}</span> ${value}</div>`;
}

function valueRows(values, focus) {
  // The values in use first: an unused one is a question, kept for last.
  const order = values.map((row, index) => ({ row, index }))
    .sort((x, y) => (x.row.uses.total ? 0 : 1) - (y.row.uses.total ? 0 : 1));
  return order.map(({ row, index }) => {
    const focused = focus && row.iri === focus;
    if (row.builtin) {
      // SHACL declares these, not the package: shown, used, not edited.
      return `<tr${focused ? ' class="focus" id="focus"' : ''}>` +
        `<td><span class="mono" title="${escape(row.iri)}">${escape(row.term || row.name)}</span></td>` +
        `<td>${escape(row.label)}</td>` +
        `<td>${chip('SHACL', '', 'Declared by SHACL itself; every package has it')} ` +
        `<span class="dim">${escape(row.note || '')}</span></td>` +
        // Not naming one of SHACL's levels is no gap: violation is what every
        // constraint that names none already has.
        `<td>${row.uses.total ? usedChips(row.uses) : `<span class="dim">${
          /#Violation$/.test(row.iri) ? 'the default of every constraint that names none'
            : 'not named yet'}</span>`}</td><td></td></tr>`;
    }
    return `<tr${focused ? ' class="focus" id="focus"' : ''}>` +
      `<td>${openable(row.name, row.definedAt, row.iri)}</td>` +
      `<td><a href="#" class="act" data-action="label" data-row="${index}" ` +
      `title="Change the label">${row.label ? escape(row.label) : '<span class="dim">add…</span>'}</a></td>` +
      `<td>${row.properties.map(propertyText).join('')}</td>` +
      `<td>${usedChips(row.uses)}</td>` +
      `<td class="acts"><button data-action="rowMenu" data-row="${index}" ` +
      'title="Label…, Open in .ttl, Delete…">⋯</button></td></tr>';
  }).join('');
}

function renderVocabularyPage(page, options) {
  const nonce = (options && options.nonce) || '';
  const focus = options && options.focus;
  const csp = `default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';`;
  const summary = page.summary || {};
  const values = page.values || [];
  const drawn = page.constrainedBy || [];
  const relations = page.relations || [];
  const subclasses = page.subclasses || [];
  const parents = page.parents || [];
  const drawer = (d) => `<a href="#" data-shape="${escape(d.shape)}" class="mono">` +
    `${escape(d.shapeName.split(':').pop())}</a>${d.attribute ? ` › ${escape(d.attribute)}` : ''}` +
    ` <span class="dim">(${escape(d.how)})</span>`;
  const status = [
    `${summary.values} value${summary.values === 1 ? '' : 's'}`,
    summary.unused ? `<span class="warn-text" title="Named nowhere: no data, shape, query or ` +
      `knowledge statement uses them.">${summary.unused} unused</span>` : '',
    drawn.length === 1 ? `drawn from by ${drawer(drawn[0])}`
      : drawn.length ? `drawn from by ${drawn.length} constraints`
        : '<span class="warn-text" title="No sh:class or sh:in names this class or its values, so ' +
          'nothing checks that an attribute holds one of them.">no constraint draws from it</span>'
  ].filter(Boolean).join(' · ');

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
  .crumbs { font-size: 0.9em; }
  .empty { font-style: italic; margin: 4px 0; }
  .head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .head h1 { font-size: 1.5em; font-weight: 600; margin: 2px 0; flex: 1 1 auto; }
  .head .acts { display: flex; gap: 6px; }
  .status { margin: 2px 0 6px; }
  .comment { margin: 2px 0 6px; color: var(--vscode-descriptionForeground); }
  .warn-text { color: var(--vscode-editorWarning-foreground, #cca700); }
  .sechead { display: flex; align-items: baseline; gap: 10px; margin: 22px 0 6px;
             border-bottom: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35));
             padding-bottom: 4px; }
  .sechead h2 { font-size: 0.78em; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
                color: var(--vscode-descriptionForeground); margin: 0; flex: 1 1 auto; }
  .mono { font-family: var(--vscode-editor-font-family); font-size: 0.92em; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { font-size: 0.86em; padding: 0 8px; border-radius: 999px; white-space: nowrap;
          border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .chip.ok { color: var(--vscode-testing-iconPassed, #388a34); border-color: currentColor; }
  .chip.bad { color: var(--vscode-errorForeground, #f14c4c); border-color: currentColor; }
  .chip.warn { color: var(--vscode-editorWarning-foreground, #cca700); border-color: currentColor; }
  button { font: inherit; color: var(--vscode-button-secondaryForeground, inherit);
           background: var(--vscode-button-secondaryBackground, transparent);
           border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35));
           padding: 2px 10px; border-radius: 2px; cursor: pointer; }
  button.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground);
                   border-color: var(--vscode-button-background); }
  .table { overflow-x: auto; border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  table { border-collapse: collapse; width: 100%; }
  th { text-align: left; font-size: 0.78em; letter-spacing: .06em; text-transform: uppercase;
       color: var(--vscode-descriptionForeground); font-weight: 600; padding: 7px 12px;
       background: var(--vscode-sideBar-background, transparent); }
  td { padding: 5px 12px; border-top: 1px solid var(--vscode-panel-border, rgba(128,128,128,.25));
       vertical-align: top; }
  tr:hover td { background: var(--vscode-list-hoverBackground); }
  tr.focus td { background: var(--vscode-editor-selectionHighlightBackground, rgba(128,128,128,.2)); }
  tr.focus td:first-child { box-shadow: inset 3px 0 0 var(--vscode-focusBorder, #0078d4); }
  td.acts { text-align: right; white-space: nowrap; }
  td.acts button { padding: 0 8px; }
  a.act { color: inherit; border-bottom: 1px dashed var(--vscode-descriptionForeground); }
  details.fold { margin-top: 18px; }
  details.fold > summary { cursor: pointer; font-size: 0.78em; font-weight: 600; letter-spacing: .08em;
                           text-transform: uppercase; color: var(--vscode-descriptionForeground); }
  details.fold ul { margin: 6px 0 0; padding-left: 1.2em; display: grid; gap: 4px; }
</style></head><body>
<div class="crumbs">Vocabulary${parents.map((p) => ' › ' + (p.page
    ? `<a href="#" data-vocab="${escape(p.iri)}">${escape(p.label)}</a>` : escape(p.label))).join('')}` +
  ` › <span class="mono">${escape(page.term)}</span></div>
<div class="head"><h1>${escape(page.label)}</h1>
  <div class="acts"><button class="primary" data-action="addValue">+ Value</button>
  <button data-action="pageMenu" title="Open in .ttl, Refresh">⋯</button></div></div>
${page.comment && page.comment !== page.label ? `<p class="comment">${escape(page.comment)}</p>` : ''}
<p class="status">${status}</p>

<div class="sechead"><h2>Values</h2></div>
${values.length ? `<div class="table"><table>
<thead><tr><th>Value</th><th>Label</th><th>Properties</th><th>Used</th><th></th></tr></thead>
<tbody>${valueRows(values, focus)}</tbody></table></div>`
    : '<p class="empty">No values yet. + Value adds the first.</p>'}

${drawn.length > 1 ? `<details class="fold" open><summary>Drawn from by (${drawn.length})</summary>` +
  `<ul>${drawn.map((d) => `<li>${drawer(d)}</li>`).join('')}</ul></details>` : ''}
${relations.length ? `<details class="fold"><summary>Properties of its values (${relations.length})</summary>` +
  `<ul>${relations.map((r) => `<li>${openable(r.name, r.definedAt)} <span class="dim">· ` +
    `${escape(r.domain || '(no domain declared)')} → ${escape(r.range || '(no range declared)')}` +
    '</span></li>').join('')}</ul></details>` : ''}
${subclasses.length ? `<details class="fold"><summary>Subclasses (${subclasses.length})</summary>` +
  `<div class="chips">${subclasses.map((c) => c.page
    ? `<a href="#" data-vocab="${escape(c.iri)}">${chip(c.label)}</a>` : chip(c.label)).join('')}</div></details>` : ''}

<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  const focused = document.getElementById('focus');
  if (focused) { focused.scrollIntoView({ block: 'center' }); }
  document.addEventListener('click', (event) => {
    const target = event.target.closest('[data-open],[data-vocab],[data-type],[data-shape],[data-action],[data-refresh]');
    if (!target) { return; }
    event.preventDefault();
    if (target.dataset.action) {
      vscode.postMessage({ command: target.dataset.action,
                           row: target.dataset.row === undefined ? -1 : Number(target.dataset.row) });
    }
    else if (target.dataset.open) { vscode.postMessage({ command: 'open', at: target.dataset.open }); }
    else if (target.dataset.vocab) { vscode.postMessage({ command: 'vocab', cls: target.dataset.vocab }); }
    else if (target.dataset.type) { vscode.postMessage({ command: 'type', iri: target.dataset.type }); }
    else if (target.dataset.shape) { vscode.postMessage({ command: 'shape', name: target.dataset.shape }); }
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

/** One reused panel, like the type and shape pages. */
class VocabularyPages {
  constructor(clientHolder) {
    this.clientHolder = clientHolder;
    this.panel = undefined;
    this.current = undefined;
  }

  async show(packageUri, cls, focus, preserveFocus) {
    if (!this.clientHolder.client || !packageUri || !cls) {
      vscode.window.showWarningMessage(
        'SemForge: no package is open, or the language server is not running.');
      return;
    }
    const same = this.panel && this.current && this.current.packageUri === packageUri &&
      this.current.cls === cls && this.current.focus === focus;
    this.current = { packageUri, cls, focus };
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        'semforgeVocabularyPage', 'Vocabulary',
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
      page = await this.clientHolder.client.sendRequest('semforge/vocabularyPage',
        { uri: this.current.packageUri, cls: this.current.cls });
    } catch (error) {
      page = { ok: false, error: error.message || String(error) };
    }
    if (!this.panel) {
      return;
    }
    if (!page.ok) {
      this.panel.title = 'Vocabulary';
      this.panel.webview.html = renderMessage(`SemForge: ${page.error}`);
      return;
    }
    this.page = page;
    this.panel.title = `${page.label} · vocabulary`;
    this.panel.webview.html = renderVocabularyPage(page,
      { nonce: crypto.randomBytes(16).toString('base64'), focus: this.current.focus });
  }

  async receive(message) {
    if (!message || !this.current) {
      return;
    }
    const { packageUri } = this.current;
    const row = this.page && this.page.values ? this.page.values[message.row] : undefined;
    if (message.command === 'open' && message.at) {
      await showLocation(message.at, true);
    } else if (message.command === 'vocab' && message.cls) {
      await this.show(packageUri, message.cls);
    } else if (message.command === 'shape' && message.name) {
      await vscode.commands.executeCommand('semforge.openShapePage',
        { raw: { shape: message.name }, packageUri });
    } else if (message.command === 'type' && message.iri) {
      await vscode.commands.executeCommand('semforge.openTypePage',
        { raw: { kind: 'type', targetClass: message.iri }, packageUri });
    } else if (message.command === 'pageMenu') {
      const items = [];
      if (this.page.severity) {
        items.push({ label: `$(type-hierarchy-sub) New severity class derived from ${this.page.label}…`,
          description: 'its own levels, a kind of sh:Severity', message: { command: 'deriveSeverity' } });
      }
      if (this.page.definedAt) {
        items.push({ label: '$(go-to-file) Open in .ttl', message: { command: 'open', at: this.page.definedAt } });
      }
      items.push({ label: '$(refresh) Refresh', message: { command: 'refresh' } });
      const picked = await vscode.window.showQuickPick(items, { title: this.page.label });
      if (picked) {
        await this.receive(picked.message);
      }
    } else if (message.command === 'deriveSeverity' && this.page.severity) {
      const name = await vscode.window.showInputBox({
        title: `New severity class, derived from ${this.page.term}`,
        prompt: 'Its name, e.g. AlarmLevel — a capital first; prefix:AlarmLevel chooses its namespace',
        validateInput: (text) => (CLASS_NAME.test(text.trim()) ? undefined
          : 'a capital first, then letters, digits, "_" and "-"')
      });
      if (!name) {
        return;
      }
      const namespace = await pickVocabularyNamespace(this.clientHolder.client, packageUri,
        name.trim(), this.page.iri);
      if (namespace === undefined) {
        return;
      }
      const made = await this.clientHolder.client.sendRequest('semforge/addSeverityClass',
        { uri: packageUri, name: name.trim(), parent: this.page.term, namespace: namespace || null });
      if (!made.ok) {
        vscode.window.showErrorMessage(`SemForge: ${made.error}`);
        return;
      }
      for (const command of REFRESH_VIEWS) {
        vscode.commands.executeCommand(command);
      }
      await this.show(packageUri, made.iri);
    } else if (message.command === 'rowMenu' && row) {
      const items = [{ label: '$(edit) Label…', message: { command: 'label', row: message.row } }];
      if (row.definedAt) {
        items.push({ label: '$(go-to-file) Open in .ttl', message: { command: 'open', at: row.definedAt } });
      }
      items.push({ label: '$(trash) Delete…', description: row.uses.total
        ? `used in ${row.uses.total} place(s)` : 'unused',
      message: { command: 'delete', row: message.row } });
      const picked = await vscode.window.showQuickPick(items, { title: row.name });
      if (picked) {
        await this.receive(picked.message);
      }
    } else if (message.command === 'addValue') {
      await this.changed(await this.addValue());
    } else if (message.command === 'label' && row) {
      await this.changed(await this.editLabel(row));
    } else if (message.command === 'delete' && row) {
      await this.changed(await this.deleteValue(row));
    } else if (message.command === 'refresh') {
      await this.render();
    }
  }

  async changed(result) {
    if (!result) {
      return;
    }
    if (!result.ok) {
      vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      return;
    }
    if (result.iri) {
      this.current.focus = result.iri;
    }
    await this.render();
    for (const command of REFRESH_VIEWS) {
      vscode.commands.executeCommand(command);
    }
  }

  async addValue() {
    const page = this.page;
    const name = await vscode.window.showInputBox({
      title: `New value of ${page.label}`,
      prompt: 'Its name — or prefix:name to choose its namespace',
      validateInput: (text) => NAME.test(text.trim())
        ? undefined : 'letters, digits, "_", "-" and ".", starting with a letter'
    });
    if (!name) {
      return undefined;
    }
    const namespace = await pickVocabularyNamespace(this.clientHolder.client,
      this.current.packageUri, name.trim(), page.iri);
    if (namespace === undefined) {
      return undefined;
    }
    const label = await vscode.window.showInputBox({
      title: `${name.trim()}: label (optional)`,
      prompt: 'What a person reads, e.g. "ON". Leave empty for none.'
    });
    if (label === undefined) {
      return undefined;
    }
    return this.clientHolder.client.sendRequest('semforge/addVocabularyValue',
      { uri: this.current.packageUri, cls: page.iri, name: name.trim(), label: label.trim(),
        namespace: namespace || null });
  }

  async editLabel(row) {
    const label = await vscode.window.showInputBox({
      title: `${row.name}: label`, value: row.label,
      prompt: 'Empty removes the label.'
    });
    if (label === undefined || label === row.label) {
      return undefined;
    }
    return this.clientHolder.client.sendRequest('semforge/setValueLabel',
      { uri: this.current.packageUri, value: row.iri, label: label.trim() });
  }

  async deleteValue(row) {
    const uses = row.uses;
    let force = false;
    if (uses.total) {
      const where = uses.places.slice(0, 8).map((p) =>
        `${p.kind}: ${p.file}:${p.line}${p.owner ? ` (${p.owner})` : ''}`).join('\n');
      const answer = await vscode.window.showWarningMessage(
        `${row.name} is used in ${uses.total} place(s). Deleting the declaration ` +
          'leaves each of them naming an undeclared value.',
        { modal: true, detail: where + (uses.places.length > 8 ? '\n…' : '') },
        'Delete anyway');
      if (answer !== 'Delete anyway') {
        return undefined;
      }
      force = true;
    } else {
      const answer = await vscode.window.showWarningMessage(
        `Delete ${row.name}? Nothing uses it.`, { modal: true }, 'Delete');
      if (answer !== 'Delete') {
        return undefined;
      }
    }
    return this.clientHolder.client.sendRequest('semforge/removeVocabularyValue',
      { uri: this.current.packageUri, value: row.iri, force });
  }

  refresh() {
    if (this.panel && this.panel.visible) {
      this.render();
    }
  }
}

async function pickClass(client, packageUri, title, extra) {
  const answer = await client.sendRequest('semforge/vocabularyClasses', { uri: packageUri });
  const items = (extra || []).concat((answer.classes || []).map((c) =>
    ({ label: c.label, description: c.term, iri: c.iri })));
  const picked = await vscode.window.showQuickPick(items, { title, matchOnDescription: true });
  return picked;
}

function register(context, clientHolder, session) {
  const pages = new VocabularyPages(clientHolder);
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.openVocabularyPage', async (node, options) => {
      const client = clientHolder.client;
      const packageUri = (node && node.packageUri) || session.uri;
      if (!client || !packageUri) {
        vscode.window.showWarningMessage(
          'SemForge: no package is open, or the language server is not running.');
        return;
      }
      let cls = options && options.cls;
      if (!cls && node && node.raw) {
        cls = node.raw.kind === 'class' ? node.raw.iri : node.raw.cls;
      }
      if (!cls) {
        const picked = await pickClass(client, packageUri, 'Open a vocabulary class');
        cls = picked && picked.iri;
      }
      if (cls) {
        await pages.show(packageUri, cls, options && options.focus,
          !!(options && options.preserveFocus));
      }
    }),

    vscode.commands.registerCommand('semforge.newVocabularyClass', async (node) => {
      const client = clientHolder.client;
      const packageUri = (node && node.packageUri) || session.uri;
      if (!client || !packageUri) {
        vscode.window.showWarningMessage(
          'SemForge: no package is open, or the language server is not running.');
        return;
      }
      const parent = await pickClass(client, packageUri,
        'New vocabulary class: under which class?',
        [{ label: '(none)', description: 'a class of its own', iri: '' }]);
      if (!parent) {
        return;
      }
      const name = await vscode.window.showInputBox({
        title: 'New vocabulary class',
        prompt: (parent.iri ? `Its name; it goes under ${parent.label}` : 'Its name') +
          ' — or prefix:Name to choose its namespace',
        validateInput: (text) => NAME.test(text.trim())
          ? undefined : 'letters, digits, "_", "-" and ".", starting with a letter'
      });
      if (!name) {
        return;
      }
      const namespace = await pickVocabularyNamespace(client, packageUri, name.trim(),
        parent.iri || '');
      if (namespace === undefined) {
        return;
      }
      const made = await client.sendRequest('semforge/addVocabularyClass',
        { uri: packageUri, name: name.trim(), parent: parent.iri || null,
          namespace: namespace || null });
      if (!made.ok) {
        vscode.window.showErrorMessage(`SemForge: ${made.error}`);
        return;
      }
      for (const command of REFRESH_VIEWS) {
        vscode.commands.executeCommand(command);
      }
      await pages.show(packageUri, made.iri);
    }),
    vscode.workspace.onDidSaveTextDocument(() => pages.refresh())
  );
  return pages;
}

module.exports = { register, renderVocabularyPage, VocabularyPages };
