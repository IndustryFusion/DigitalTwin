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
const { escape, verdictNote, showLoading, BUSY_SCRIPT, BUSY_CSS } = require('./typepage');

function chip(text, tone, title) {
  return `<span class="chip ${tone || ''}" title="${escape(title || text)}">` +
    `${escape(text)}</span>`;
}

/** An attribute's name: a click shows it on its type's page, where its
 *  constraints, verdicts and editor are. Its line in the .jsonld is in ⋯. */
function attributeName(text, type, names, term) {
  return type
    ? `<a tabindex="0" role="link" data-type="${escape(type)}" data-names="${escape(JSON.stringify(names))}"` +
      ` title="${escape(`${term} — show it on the ${type} page`)}">${escape(text)}</a>`
    : `<span title="${escape(term)}">${escape(text)}</span>`;
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
function attributeRows(rows, file, depth, at, type, chain) {
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
      ? `<a tabindex="0" role="link" class="act" data-edit="${here}" title="Change the value">` +
        `${escape(row.value) || '<span class="dim">(none)</span>'}</a>`
      : escape(row.value);
    // When it was observed: a click opens the date-and-time picker. An
    // instance without one counts as now, as on the platform.
    const time = here !== undefined && row.stamp && row.kind
      ? ` <a tabindex="0" role="link" class="stamp" data-stamp="${here}"` +
        ` data-current="${escape(row.observedAt)}" data-latest="${escape(row.latestAt || '')}"` +
        ` title="${row.observedAt ? `observedAt ${escape(row.observedAt)} — click to change`
          : 'No observedAt: it counts as now. Click to give it a time'}">` +
        `${row.observedAt ? escape(row.observedAt.replace('T', ' ').replace(/\.000Z$|Z$/, ' UTC'))
          : '◷'}</a>` : '';
    const older = !row.superseded && earlier[seriesOf(row)] ? earlier[seriesOf(row)].length : 0;
    const superseded = older
      ? ` <a tabindex="0" role="link" class="history" data-history="${series(row)}" title="${older} earlier ` +
        'observation(s) of this instance. Only the latest is validated; click to show them.">' +
        `+${older} earlier</a>` : '';
    const menu = here !== undefined
      ? ` <button class="mini" data-rowmenu="${here}" title="More: sub-attribute, observation, ` +
        'the rule, Open in .jsonld">⋯</button>' : '';
    const rel = row.kind === 'Relationship' && row.value && !row.superseded
      ? ` data-rel="${escape(row.value)}" data-relname="${escape(row.name)}"` : '';
    const address = here !== undefined ? ` data-at="${here}"` : '';
    return `<div class="attr${depth ? ` depth${Math.min(depth, 4)}` : ''}` +
      `${row.superseded ? ' superseded' : ''}${row.violations.length ? ' violates' : ''}"` +
      `${rel}${address} data-name="${escape(row.name)}">` +
      `<span class="name">${attributeName(row.display || row.name, type,
        (chain || []).concat(row.name), row.term)}</span>` +
      `<span class="value">${value}` +
      `${row.unitText ? ` <span class="unit" title="unitCode ${escape(row.unitCode)}">${escape(row.unitText)}</span>` : ''}` +
      `${row.instances > 1 && !(row.dataset && row.dataset !== '@none') ? ' <span class="dim">· default</span>' : ''}` +
      `${time}${superseded}${menu}</span>` +
      `${row.violations.map(problem).join('')}</div>` +
      attributeRows(row.children || [], file, depth + 1, here, type,
        (chain || []).concat(row.name));
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
  const names = (entity.attributes || []).map((row) => row.name).join('|');
  return `<div class="card${bad ? ' bad' : ''}${focused ? ' focus" id="focus' : ''}"` +
    ` data-card="${at === undefined ? '' : at}" data-id="${escape(entity.id || '')}"` +
    // What the filter reads. Not data-type: that is what a click opens the
    // type page for, and the whole card carrying it made a click anywhere on
    // it -- on a relationship to another type, too -- open this card's type.
    ` data-ftype="${escape(entity.type || '')}" data-attrs="${escape(names)}">` +
    `<div class="title"><span class="mono">${escape(entity.id || '(no id)')}</span>` +
    `${entity.type ? ` <a tabindex="0" role="link" class="dim" data-type="${escape(entity.type)}"` +
      ` title="Open the ${escape(entity.type)} page">· ${escape(entity.type)}</a>` : ''}` +
    `<span class="acts">${add}</span></div>` +
    `${entity.error ? `<div class="problem">${escape(entity.error)}</div>` : ''}` +
    `${entity.violations.map(problem).join('')}` +
    `${attributeRows(entity.attributes, entity.file, 0, at, entity.type, []) ||
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
    : claim.holds === null ? chip('evaluating…', 'dim', 'The package is being validated')
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

/**
 * Every entity of the page with its relationships -- what the entity graph is
 * drawn from. A relationship nested in a sub-attribute counts too, named by
 * its path (hasState.hasXXXWorkpiece). Targets are matched by id as written.
 */
function entityIndex(files) {
  const out = [];
  const relationships = (rows, prefix, into) => (rows || []).forEach((row) => {
    const name = prefix ? `${prefix}.${row.name}` : row.name;
    if (row.kind === 'Relationship' && row.value && !row.superseded) {
      into.push({ name, target: row.value });
    }
    relationships(row.children, name, into);
  });
  files.forEach((file, f) => file.cards.forEach((card, j) => {
    const rels = [];
    relationships(card.attributes, '', rels);
    out.push({ id: card.id || '', type: card.type || '', card: `${f}.${j}`, rels,
      bad: !!(card.violations.length || anyViolation(card.attributes)) });
  }));
  return out;
}

/** Every violation on the page, in card order: where it is (`at`, a row's
 *  address or its card's), on what, what is wrong, which shape says so. */
function violationsOf(files) {
  const out = [];
  const rows = (card, list, prefix) => (list || []).forEach((row, r) => {
    const at = `${prefix}.${r}`;
    row.violations.forEach((v) => out.push({ at, entity: card.id, attribute: row.name,
      text: v.text, shape: v.shape }));
    rows(card, row.children, at);
  });
  files.forEach((file, f) => file.cards.forEach((card, c) => {
    card.violations.forEach((v) => out.push({ at: `${f}.${c}`, entity: card.id, attribute: '',
      text: v.text, shape: v.shape }));
    rows(card, card.attributes, `${f}.${c}`);
  }));
  return out;
}

/** The list at the top: the way to each violation, not just their count.
 *  On the Main page, where each is also a problem on its line, the way to
 *  VS Code's Problems panel too -- nothing said what or where it was. */
function violationList(found, model) {
  if (!found.length) {
    return '';
  }
  return `<h2 id="violations">Violations <span class="dim">· ${found.length}</span></h2>
${model ? '<p class="dim">Click one to go to it. Each is also listed in VS Code\u2019s ' +
    '<b>Problems</b> panel (Ctrl+Shift+M, or the warning count in the status bar), on its line ' +
    'in the .jsonld: F8 steps from one to the next. ' +
    '<a tabindex="0" role="link" data-problems="1">Open the Problems panel</a></p>' : ''}
<ul class="vlist">${found.map((v) => `<li data-jump="${v.at}" title="Click: go to it">` +
    `<a tabindex="0" role="link">${escape(v.entity || '(no id)')}${v.attribute ? ` · ${escape(v.attribute)}` : ''}</a> ` +
    `${escape(v.text)} <span class="dim">· ${escape(v.shape)}</span></li>`).join('')}</ul>`;
}

/** Cards | Graph, and the filter -- closed until asked for. */
function entityBar(entities) {
  const types = [...new Set(entities.map((e) => e.type).filter(Boolean))].sort();
  const attrs = [...new Set(entities.flatMap((e) => e.attrs || []))].sort();
  const options = (list) => list.map((v) => `<option value="${escape(v)}">${escape(v)}</option>`).join('');
  return `<div class="entitybar">
  <span class="views"><button class="mini on" data-view="cards" title="Every entity as a card">Cards</button><button class="mini" data-view="graph" title="From the entities nothing points at, along their relationships">Graph</button></span>
  <details class="filter" id="filter"><summary>Filter</summary>
    <label>Type <select id="ftype"><option value="">any</option>${options(types)}</select></label>
    <label>Has attribute <select id="fattr"><option value="">any</option>${options(attrs)}</select></label>
    <label>Id contains <input id="fid" type="search" spellcheck="false"></label>
    <label><input id="fbad" type="checkbox"> only what violates</label>
    <button class="mini" data-clearfilter="1">Clear</button>
  </details>
  <span class="dim" id="fcount"></span>
</div>
<div class="graph" id="graph" hidden></div>`;
}

function renderCasePage(page, options) {
  const entities = entityIndex(page.files || []).map((e, i) => Object.assign(e, {
    attrs: (((page.files || []).flatMap((f) => f.cards))[i].attributes || []).map((r) => r.name)
  }));
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
          display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis;
          vertical-align: bottom; box-sizing: border-box;
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
          padding: 10px 12px; display: grid; gap: 4px; align-content: start;
          min-width: 0; overflow-wrap: anywhere; }
  .card.bad { border-color: var(--vscode-errorForeground, #f14c4c); }
  .card.focus { box-shadow: 0 0 0 2px var(--vscode-focusBorder, #0078d4);
                background: var(--vscode-editor-selectionHighlightBackground, transparent); }
  .attr.depth1 { padding-left: 16px; } .attr.depth2 { padding-left: 32px; }
  .attr.depth3 { padding-left: 48px; } .attr.depth4 { padding-left: 64px; }
  .card .title { font-weight: 600; margin-bottom: 4px; }
  /* A name takes what it needs; the value keeps at least 6em; only a name
     longer than what is left wraps. */
  .attr { display: grid; grid-template-columns: minmax(6em, max-content) minmax(6em, 1fr);
          gap: 2px 12px; }
  .attr > * { min-width: 0; }
  /* A name breaks only when it cannot fit at all: "anywhere" would make its
     smallest width one letter, and the grid would break short names too. */
  .attr > .name { overflow-wrap: break-word; }
  .attr .value { font-family: var(--vscode-editor-font-family); font-size: 0.92em;
                 overflow-wrap: anywhere; }
  button.mini { padding: 0 6px; font-size: 0.86em; margin-left: 4px; }
  .card .title { display: flex; flex-wrap: wrap; gap: 4px; align-items: baseline; }
  .card .title > * { min-width: 0; }
  .card .title .acts, .file .head .acts { margin-left: auto; }
  .problem { grid-column: 1 / -1; color: var(--vscode-errorForeground, #f14c4c);
             border-left: 2px solid currentColor; padding-left: 8px; font-size: 0.92em; }
  .entitybar { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: baseline; margin: 0 0 10px; }
  .views button { margin-left: 0; border-radius: 0; }
  .views button.on { background: var(--vscode-button-background, #0e639c);
                     color: var(--vscode-button-foreground, #fff); }
  .filter summary { cursor: pointer; color: var(--vscode-textLink-foreground); }
  .filter[open] { flex-basis: 100%; display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: baseline; }
  .filter[open] summary { flex-basis: 100%; }
  .filter label { display: inline-flex; gap: 6px; align-items: baseline; }
  .filter select, .filter input { font: inherit; color: var(--vscode-input-foreground);
       background: var(--vscode-input-background); border: 1px solid var(--vscode-input-border, transparent);
       padding: 1px 4px; max-width: 22em; }
  .card[hidden], #cardview[hidden], .graph[hidden] { display: none; }
  .graph .roots { margin-bottom: 6px; }
  .gid { font-family: var(--vscode-editor-font-family); font-size: 0.88em;
         color: var(--vscode-descriptionForeground); margin-left: 6px; }
  .gtype { font-weight: 600; }
  .tcard { margin: 6px 0; border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35));
           border-radius: 4px; }
  .tcard.bad { border-color: var(--vscode-errorForeground, #f14c4c); }
  .tcard > summary { padding: 4px 10px; cursor: pointer; overflow-wrap: anywhere; }
  .tcard > summary .acts { display: inline-flex; margin-left: 8px; }
  .tcard.bad > summary .gtype, .badmark { color: var(--vscode-errorForeground, #f14c4c); }
  .badmark { margin-left: 6px; }
  .tcard > .card { border: none; padding: 2px 10px 8px; }
  .via { color: var(--vscode-descriptionForeground); font-size: 0.9em; margin-right: 6px; }
  .nested { margin: 2px 0 6px 4px; padding-left: 10px;
            border-left: 2px solid var(--vscode-textLink-foreground, #3794ff); }
  .reltoggle { display: inline-block; width: 1.1em; text-decoration: none; }
  .reltoggle.missing { color: var(--vscode-descriptionForeground); cursor: default; }
  .tref { font-style: italic; }
  .trail { position: sticky; top: 0; z-index: 2; padding: 4px 0 6px; margin-bottom: 4px;
           background: var(--vscode-editor-background); overflow-wrap: anywhere; font-size: 0.92em;
           border-bottom: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .trail .sep { color: var(--vscode-descriptionForeground); }
  .flash { outline: 2px solid var(--vscode-focusBorder, #0078d4); outline-offset: 2px;
           background: var(--vscode-editor-findMatchHighlightBackground, rgba(234,92,0,.33)); }
  .vlist { margin: 4px 0 12px; padding-left: 18px; }
  .chiplink { text-decoration: none; }
  .vlist li { margin: 2px 0; cursor: pointer; padding: 1px 4px; border-radius: 3px; }
  .vlist li:hover { background: var(--vscode-list-hoverBackground, rgba(128,128,128,.15)); }
  .vlist a { color: var(--vscode-errorForeground, #f14c4c); }
  .attr.violates > .name { color: var(--vscode-errorForeground, #f14c4c); }
  .attr.violates > .name::before { content: '✗ '; }
${BUSY_CSS}</style></head><body data-page="${escape(page.file || page.case || '')}"` +
    `${options && options.only ? ' data-only="1"' : ''}` +
    `${options && options.attribute ? ` data-focusattr="${escape(options.attribute)}"` : ''}>
<div class="crumbs">${crumbs}</div>
<h1>${page.kind === 'model' ? 'Entities' : 'Test case'}: ${escape(page.name)}</h1>
${page.description ? `<p class="lede">${escape(page.description)}</p>` : ''}
${verdictNote(page.verdicts || { state: 'ready' })
    ? `<p class="lede">${verdictNote(page.verdicts)}</p>` : ''}
${model ? `<div class="chips">
  ${chip(`${(page.summary || {}).entities || 0} entities`)}
  ${(page.summary || {}).violations === null ? ''
    : (page.summary || {}).violations
    ? `<a tabindex="0" role="link" class="chiplink" data-jumplist="1" title="Show them">` +
      chip(`${page.summary.violations} violation(s)`, 'warn',
        'Click: the list of them, below. The model declares nothing and cannot fail: ' +
        'these are information.') + '</a>'
    : chip('all valid', 'ok')}
</div>` : `<div class="chips">
  ${chip(`expects ${page.expect}`)}
  ${page.passed === null ? '' : page.passed ? chip('passes', 'ok') : chip('fails', 'bad')}
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

${violationList(violationsOf(files), model)}
<h2>${model ? 'Entities' : 'Data'}</h2>
${entityBar(entities)}
<script type="application/json" id="entities">${JSON.stringify(entities).replace(/</g, '\\u003c')}</script>
<div id="cardview">
${files.map((file, f) => `<div class="file"><div class="head">
  ${chip(file.role === 'case' ? 'this case' : file.role === 'model' ? 'model' : 'included')}
  <span class="mono">${escape(file.relative)}</span>
  ${file.sharedBy.length ? `<span class="dim" title="${escape(file.sharedBy.join('\n'))}">· shared with ` +
    `${file.sharedBy.length} other case(s) — an edit here changes them too</span>` : ''}
  <span class="acts"><button class="mini" data-addentity="${f}" title="Add an entity to this file">` +
  `+ Entity</button><button class="mini" data-open="${escape(file.path)}:1" ` +
  `title="Open ${escape(file.relative)} in the editor">Open .jsonld</button></span>
</div><div class="cards">${file.cards.map((c, j) => card(c, mark(c), `${f}.${j}`)).join('')}</div></div>`).join('')}
</div>

<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
${BUSY_SCRIPT}
  const focused = document.getElementById('focus');
  if (focused) { focused.scrollIntoView({ block: 'center' }); }

  // --- Cards | Graph, and the filter. Kept per page across refreshes. -------
  const ENTITIES = JSON.parse((document.getElementById('entities') || {}).textContent || '[]');
  const byId = new Map(ENTITIES.map(function (e) { return [e.id, e]; }));
  const pageKey = (document.body && document.body.dataset.page) || '';
  const saved = (vscode.getState() || {})[pageKey] || {};
  const ui = { view: saved.view || 'cards', type: saved.type || '', attr: saved.attr || '',
               id: saved.id || '', open: !!saved.open,
               bad: !!saved.bad,
               tree: saved.tree || { roots: {}, rels: {} }, scroll: saved.scroll || 0 };
  // Opened from a violation count: only what violates.
  const opened = (document.body && document.body.dataset) || {};
  if (opened.only) { ui.bad = true; ui.open = true; }
  const ftype = document.getElementById('ftype');
  const fattr = document.getElementById('fattr');
  const fid = document.getElementById('fid');
  const fbad = document.getElementById('fbad');
  const filterBox = document.getElementById('filter');
  const graph = document.getElementById('graph');
  const cardview = document.getElementById('cardview');
  function remember() {
    const all = vscode.getState() || {};
    all[pageKey] = ui;
    vscode.setState(all);
  }
  function filtering() { return !!(ui.type || ui.attr || ui.id || ui.bad); }
  function matches(e) {
    if (ui.bad && !e.bad) { return false; }
    if (ui.type && e.type !== ui.type) { return false; }
    if (ui.attr && (e.attrs || []).indexOf(ui.attr) < 0) { return false; }
    if (ui.id && e.id.toLowerCase().indexOf(ui.id.toLowerCase()) < 0) { return false; }
    return true;
  }
  function applyFilter() {
    let shown = 0;
    document.querySelectorAll('.card[data-card]').forEach(function (card) {
      const ok = matches({ id: card.dataset.id || '', type: card.dataset.ftype || '',
                           attrs: (card.dataset.attrs || '').split('|'),
                           bad: card.classList.contains('bad') });
      card.hidden = !ok;
      if (ok) { shown += 1; }
    });
    document.getElementById('fcount').textContent = filtering()
      ? shown + ' of ' + ENTITIES.length + ' shown' : '';
    if (ui.view === 'graph') { drawGraph(); }
  }
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined) { node.textContent = text; }
    return node;
  }
  // The roots: what nothing points at -- or, while filtering, what matches.
  // A cycle nothing points into (a pump and its port naming each other) has
  // no such entity: the first of it, in page order, is entered instead, until
  // every entity can be reached from some root.
  function roots() {
    if (filtering()) { return { free: ENTITIES.filter(matches), cyclic: [] }; }
    const pointed = new Set();
    ENTITIES.forEach(function (e) { e.rels.forEach(function (r) { pointed.add(r.target); }); });
    const free = ENTITIES.filter(function (e) { return !pointed.has(e.id); });
    const reached = new Set();
    function reach(e) {
      const todo = [e];
      while (todo.length) {
        const next = todo.pop();
        if (reached.has(next.id)) { continue; }
        reached.add(next.id);
        next.rels.forEach(function (r) { if (byId.has(r.target)) { todo.push(byId.get(r.target)); } });
      }
    }
    free.forEach(reach);
    const cyclic = [];
    ENTITIES.forEach(function (e) {
      if (!reached.has(e.id)) { cyclic.push(e); reach(e); }
    });
    return { free: free, cyclic: cyclic };
  }
  function shortId(id) {
    return id.length > 42 ? id.slice(0, 14) + '…' + id.slice(-20) : id;
  }

  // --- The entity graph: a tree of cards. ------------------------------------
  // Each entity is its own card, copied from the cards view: the same rows,
  // links and edits (a row is addressed by its card, so a copy edits the
  // original). A relationship row opens the card it points at right under it.
  // An entity is open in full once; asked for again, it is a line that jumps
  // to it -- which is also where a cycle ends.
  const shown = new Map();
  function present(node) { return !!node && document.body.contains(node); }
  // A type, as a link to its page -- the page of THIS type, whatever card or
  // row it stands on.
  function typeLink(type, cls) {
    if (!type) { return el('span', cls, '(no type)'); }
    const link = el('a', cls, type);
    link.tabIndex = 0;
    link.setAttribute('role', 'link');
    link.title = 'Open the ' + type + ' page';
    link.dataset.type = type;
    return link;
  }
  function header(e, via) {
    const summary = el('summary', 'thead');
    summary.title = e.id;
    if (via) { summary.append(el('span', 'via', via + ' →')); }
    summary.append(typeLink(e.type, 'gtype'));
    summary.append(el('span', 'gid', shortId(e.id)));
    if (e.bad) { summary.append(el('span', 'badmark', '✗')); }
    return summary;
  }
  function treeCard(e, via, key) {
    const d = el('details', 'tcard' + (e.bad ? ' bad' : ''));
    d.dataset.id = e.id;
    d.dataset.via = via || '';
    d.dataset.key = key;
    d.append(header(e, via));
    return d;
  }
  function relKey(card, row) {
    return card.dataset.id + '|' + row.dataset.relname + '|' + row.dataset.rel;
  }
  // The body is built when the card is first opened -- it must be on the page
  // already, so that "is it shown?" sees everything above it.
  function fill(d) {
    if (d.filled) { return; }
    d.filled = true;
    const e = byId.get(d.dataset.id);
    const source = cardview.querySelector('.card[data-card="' + e.card + '"]');
    const body = source ? source.cloneNode(true) : el('div', 'dim', '(no card)');
    body.removeAttribute('id');
    body.hidden = false;
    body.classList.remove('focus');
    const title = body.querySelector('.title');
    if (title) {
      const acts = title.querySelector('.acts');
      title.remove();
      if (acts) { d.querySelector('summary').append(acts); }
    }
    body.querySelectorAll('.attr[data-rel]').forEach(function (row) {
      const target = byId.get(row.dataset.rel);
      const toggle = el('a', 'reltoggle' + (target ? '' : ' missing'), target ? '▸' : '·');
      toggle.tabIndex = 0;
    toggle.setAttribute('role', 'link');
      toggle.title = target ? 'Open its ' + (target.type || 'entity') + ' here'
        : row.dataset.rel + ' is not on this page';
      if (target) { toggle.dataset.reltoggle = '1'; }
      (row.querySelector('.name') || row).prepend(toggle);
      // The card it points at opens right here: its type and a short id say
      // enough on the row (the whole id stays on hover).
      const value = row.querySelector('.value');
      const idNode = value && Array.from(value.querySelectorAll('a')).concat(Array.from(value.childNodes))
        .find(function (n) { return n.textContent.trim() === row.dataset.rel; });
      if (idNode) {
        // The target's type opens the TARGET's type page; the id stays what
        // it was (a link to where the entity is written, or text).
        let idHolder = idNode;
        if (idNode.nodeType === 3) {
          idHolder = el('span', '', '');
          idNode.replaceWith(idHolder);
        }
        idHolder.textContent = shortId(row.dataset.rel);
        idHolder.title = row.dataset.rel;
        if (target && target.type) {
          idHolder.before(typeLink(target.type, 'dim'), document.createTextNode(' '));
        }
      }
    });
    d.append(body);
    shown.set(e.id, d);
    body.querySelectorAll('.attr[data-rel]').forEach(function (row) {
      if (ui.tree.rels[relKey(d, row)] && byId.has(row.dataset.rel)) { openRel(row, false); }
    });
  }
  function release(node) {
    [node].concat(Array.from(node.querySelectorAll('.tcard'))).forEach(function (c) {
      if (shown.get(c.dataset.id) === c) { shown.delete(c.dataset.id); }
    });
  }
  function openRel(row, record) {
    const card = row.closest('.tcard');
    const toggle = row.querySelector('.reltoggle');
    const next = row.nextElementSibling;
    const key = relKey(card, row);
    if (next && next.classList.contains('nested')) {
      release(next);
      next.remove();
      delete ui.tree.rels[key];
      toggle.textContent = '▸';
      remember();
      return;
    }
    const target = byId.get(row.dataset.rel);
    const holder = el('div', 'nested');
    row.after(holder);
    toggle.textContent = '▾';
    ui.tree.rels[key] = true;
    const existing = shown.get(target.id);
    if (present(existing)) {
      const ref = el('a', 'tref', '↩ ' + (target.type || '') + ' ' + shortId(target.id) +
        ' is open elsewhere on this page — go there');
      ref.tabIndex = 0;
    ref.setAttribute('role', 'link');
      ref.title = target.id;
      ref.dataset.goto = target.id;
      holder.append(ref);
    } else {
      const child = treeCard(target, row.dataset.relname, key);
      holder.append(child);
      child.open = true;
      fill(child);
    }
    if (record !== false) { remember(); }
  }
  function goTo(id) {
    const card = shown.get(id);
    if (!present(card)) { return; }
    let up = card;
    while (up) { up.open = true; up = up.parentElement ? up.parentElement.closest('.tcard') : null; }
    flash(card.querySelector('summary'));
  }
  function drawGraph() {
    graph.textContent = '';
    shown.clear();
    const trail = el('div', 'trail');
    trail.id = 'trail';
    trail.hidden = true;
    graph.append(trail);
    const found = roots();
    const count = found.free.length;
    graph.append(el('div', 'roots dim', filtering()
      ? count + ' matching entit' + (count === 1 ? 'y' : 'ies') + ' as roots'
      : count + ' root(s): the entities nothing points at' + (found.cyclic.length
        ? ' · ' + found.cyclic.length + ' more where a cycle has no way in' : '')));
    const all = found.free.concat(found.cyclic);
    all.forEach(function (e) {
      const d = treeCard(e, '', 'root|' + e.id);
      graph.append(d);
      const wanted = ui.tree.roots[e.id];
      if (wanted === undefined ? all.length <= 3 : wanted) {
        d.open = true;
        fill(d);
      }
    });
    if (ui.scroll) { window.scrollTo(0, ui.scroll); }
    follow();
  }
  // The path to the card at the top of the view, kept in sight.
  function follow() {
    const trail = document.getElementById('trail');
    if (!trail || graph.hidden) { return; }
    // Hidden, the trail measures nothing: what has scrolled past the top counts.
    const limit = (trail.hidden ? 0 : trail.getBoundingClientRect().bottom) + 6;
    let current = null;
    graph.querySelectorAll('.tcard').forEach(function (c) {
      if (c.offsetParent !== null && c.querySelector('summary').getBoundingClientRect().top <= limit) {
        current = c;
      }
    });
    trail.textContent = '';
    trail.hidden = !current;
    if (!current) { return; }
    const chain = [];
    for (let c = current; c; c = c.parentElement ? c.parentElement.closest('.tcard') : null) {
      chain.unshift(c);
    }
    chain.forEach(function (c, i) {
      if (i) { trail.append(el('span', 'sep', ' › ' + c.dataset.via + ' › ')); }
      const e = byId.get(c.dataset.id) || { id: c.dataset.id };
      const crumb = el('a', 'crumb', e.type || shortId(e.id));
      crumb.tabIndex = 0;
    crumb.setAttribute('role', 'link');
      crumb.title = e.id;
      crumb.dataset.goto = e.id;
      trail.append(crumb);
    });
  }
  let pending = false;
  window.addEventListener('scroll', function () {
    if (pending || ui.view !== 'graph') { return; }
    pending = true;
    requestAnimationFrame(function () {
      pending = false;
      follow();
      ui.scroll = window.scrollY;
      remember();
    });
  });
  function setView(view) {
    ui.view = view === 'graph' ? 'graph' : 'cards';
    remember();
    cardview.hidden = ui.view !== 'cards';
    graph.hidden = ui.view !== 'graph';
    document.querySelectorAll('[data-view]').forEach(function (b) {
      b.classList.toggle('on', b.dataset.view === ui.view);
    });
    if (ui.view === 'graph') { drawGraph(); }
  }
  // A violation in the list: its row (or, for a missing attribute, its
  // card) -- in the cards, whatever the filter or the view hid.
  function jumpTo(at) {
    const node = document.querySelector('.attr[data-at="' + at + '"]') ||
      document.querySelector('.card[data-card="' + at + '"]');
    if (!node) { return; }
    const card = node.closest('.card');
    if (card && card.hidden) {
      ui.type = ''; ui.attr = ''; ui.id = ''; ui.bad = false;
      ftype.value = ''; fattr.value = ''; fid.value = ''; fbad.checked = false;
      remember();
      applyFilter();
    }
    if (ui.view !== 'cards') { setView('cards'); }
    flash(node);
    report(node, card ? card.dataset.id : '', node.dataset.name || '', 'list');
  }
  // Where a jump ended, said to the extension: the SemForge output shows it,
  // and the e2e tests read it.
  function report(node, entity, attribute, from) {
    setTimeout(function () {
      const box = node.getBoundingClientRect();
      vscode.postMessage({ command: 'landed', from: from, entity: entity, attribute: attribute,
        inView: box.height > 0 && box.top >= 0 && box.bottom <= window.innerHeight,
        top: Math.round(box.top), height: window.innerHeight, scrollY: Math.round(window.scrollY),
        page: document.documentElement.scrollHeight });
    }, 1100);
  }
  function flash(node) {
    node.scrollIntoView({ block: 'center' });
    node.classList.add('flash');
    setTimeout(function () { node.classList.remove('flash'); }, 3000);
  }
  if (filterBox && graph && cardview) {
    ftype.value = ui.type;
    fattr.value = ui.attr;
    fid.value = ui.id;
    filterBox.open = ui.open;
    ftype.addEventListener('change', function () { ui.type = ftype.value; remember(); applyFilter(); });
    fattr.addEventListener('change', function () { ui.attr = fattr.value; remember(); applyFilter(); });
    fid.addEventListener('input', function () { ui.id = fid.value; remember(); applyFilter(); });
    fbad.checked = ui.bad;
    fbad.addEventListener('change', function () { ui.bad = fbad.checked; remember(); applyFilter(); });
    filterBox.addEventListener('toggle', function () { ui.open = filterBox.open; remember(); });
    graph.addEventListener('toggle', function (event) {
      const card = event.target;
      if (!card.classList || !card.classList.contains('tcard')) { return; }
      if (card.open) { fill(card); }
      if (card.dataset.key.indexOf('root|') === 0) {
        ui.tree.roots[card.dataset.id] = card.open;
        remember();
      }
      follow();
    }, true);
    setView(ui.view);
    applyFilter();
    land();
    // Clicked again from the tree, the page already open: the same jump.
    window.addEventListener('message', function (event) {
      if (event.data && event.data.command === 'land') { land(); }
    });
  }
  // Opened at an entity -- or at its attribute, from a violation: there,
  // AFTER the filter and the view are what they will be. Scrolled before,
  // the cards a remembered filter hid afterwards moved it out of sight, and
  // in the graph it was a card in the hidden list.
  function land() {
    if (!focused) { return; }
    const wanted = opened.focusattr;
    const row = wanted && Array.from(focused.querySelectorAll('.attr[data-name]'))
      .find(function (r) { return r.dataset.name === wanted; });
    if (focused.hidden) {
      ui.type = ''; ui.attr = ''; ui.id = ''; ui.bad = false;
      ftype.value = ''; fattr.value = ''; fid.value = ''; fbad.checked = false;
      remember();
      applyFilter();
    }
    if (ui.view !== 'cards') { setView('cards'); }
    const node = row || focused;
    flash(node);
    report(node, focused.dataset.id, wanted || '', 'open');
  }
  // observedAt: a date-and-time picker beside the time, in UTC, to the
  // millisecond; Now, Just after the latest of its datasetId, Remove.
  const utc = (iso) => (iso || new Date().toISOString()).replace(/Z$/, '').slice(0, 23);
  // The picker is a panel of its own UNDER the row, across the card: the row
  // stays as it is, and the controls run left to right.
  function stampEditor(link) {
    const row = link.closest('.attr') || link;
    const open = row.nextElementSibling;
    if (open && open.classList.contains('stampedit')) {
      open.remove();
      vscode.postMessage({ command: 'editing', open: false });
      return;
    }
    const box = document.createElement('div');
    // Said to the extension, so results arriving meanwhile wait for it.
    const close = () => { box.remove(); vscode.postMessage({ command: 'editing', open: false }); };
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
      close();
      markBusy(row);
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
      if (event.key === 'Escape') { event.preventDefault(); close(); }
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
    button('×', 'Close (Esc)', close);
    row.after(box);
    vscode.postMessage({ command: 'editing', open: true });
    input.focus();
  }
  document.addEventListener('click', (event) => {
    const view = event.target.closest('[data-view]');
    if (view) { event.preventDefault(); setView(view.dataset.view); return; }
    const reltoggle = event.target.closest('[data-reltoggle]');
    if (reltoggle) { event.preventDefault(); event.stopPropagation(); openRel(reltoggle.closest('.attr')); return; }
    if (event.target.closest('[data-jumplist]')) {
      event.preventDefault();
      const list = document.getElementById('violations');
      if (list) { flash(list); }
      return;
    }
    if (event.target.closest('[data-problems]')) {
      event.preventDefault();
      vscode.postMessage({ command: 'problems' });
      return;
    }
    const jump = event.target.closest('[data-jump]');
    if (jump) { event.preventDefault(); jumpTo(jump.dataset.jump); return; }
    const goto = event.target.closest('[data-goto]');
    if (goto) { event.preventDefault(); goTo(goto.dataset.goto); return; }
    if (event.target.closest('[data-clearfilter]')) {
      event.preventDefault();
      ui.type = ''; ui.attr = ''; ui.id = ''; ui.bad = false;
      ftype.value = ''; fattr.value = ''; fid.value = ''; fbad.checked = false;
      remember();
      applyFilter();
      return;
    }
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
    else if (target.dataset.type) {
      vscode.postMessage({ command: 'type', name: target.dataset.type,
        names: target.dataset.names ? JSON.parse(target.dataset.names) : undefined });
    }
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
  async show(packageUri, caseFile, focus, preserveFocus, extra) {
    const more = extra || {};
    if (!this.clientHolder.client || !packageUri || (!caseFile && caseFile !== MODEL)) {
      vscode.window.showWarningMessage(
        'SemForge: no package is open, or the language server is not running.');
      return;
    }
    const same = this.panel && this.current && this.current.packageUri === packageUri &&
      this.current.caseFile === caseFile && this.current.focus === focus &&
      this.current.attribute === more.attribute && this.current.only === more.only;
    if (focus || more.only) {
      this.trace(`open ${caseFile === MODEL ? 'Main' : caseFile} at ${focus || '-'}` +
        `${more.attribute ? ` · ${more.attribute}` : ''}${more.only ? ' (only what violates)' : ''}` +
        `${same ? ' -- already shown, jump again' : ''}`);
    }
    this.current = { packageUri, caseFile, focus, attribute: more.attribute, only: more.only };
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        'semforgeCasePage', 'Test case',
        { viewColumn: vscode.ViewColumn.Active, preserveFocus: !!preserveFocus },
        { enableScripts: true, localResourceRoots: [] });
      this.panel.onDidDispose(() => { this.panel = undefined; });
      this.panel.onDidChangeViewState(() => {
        if (this.panel && this.panel.visible && this.staleWhileHidden) {
          this.staleWhileHidden = false;
          this.refreshPending = true;
          this.flushRefresh();
        }
      });
      this.panel.webview.onDidReceiveMessage((message) => this.receive(message));
    } else {
      this.panel.reveal(undefined, !!preserveFocus);
      if (same) {
        // Clicked again: already showing it, but maybe scrolled away.
        this.panel.webview.postMessage({ command: 'land' });
        return;
      }
    }
    await this.render();
  }

  async render() {
    this.editing = false;      // a redraw closes any editor the page had open
    if (!this.panel || !this.current) {
      return;
    }
    const target = `${this.current.packageUri}#${this.current.caseFile}`;
    const loaded = showLoading(this.panel, this.current.caseFile === MODEL ? 'the main-model'
      : String(this.current.caseFile).split('/').pop(), this.shown !== target);
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
    loaded();
    this.shown = target;
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
      ? 'Entities: Main' : `Test case: ${page.name.replace(/\.jsonld$/, '')}`;
    this.panel.webview.html = renderCasePage(page,
      { nonce: crypto.randomBytes(16).toString('base64'), focus: this.current.focus,
        attribute: this.current.attribute, only: this.current.only });
    if (this.current.focus && !this.panel.webview.html.includes('id="focus"')) {
      this.trace(`no card on the page is ${this.current.focus}`);
    }
  }

  /** A line in the SemForge output: where a jump went, for when it went wrong. */
  trace(line) {
    const client = this.clientHolder.client;
    const channel = client && client.outputChannel;
    if (channel) {
      channel.appendLine(`[${new Date().toISOString().slice(11, 23)} page] ${line}`);
    }
  }

  /**
   * Every message from the page, one edit at a time as far as refreshing goes:
   * results that arrive while an edit is under way -- a picker of the
   * extension's, or the page's own editor (`editing`) -- wait for it to end,
   * so the page is never redrawn under someone's hands.
   */
  async receive(message) {
    if (message && message.command === 'editing') {
      this.editing = !!message.open;
      this.flushRefresh();
      return;
    }
    if (message && message.command === 'landed') {
      this.landed = message;           // where a jump ended: read by the e2e tests
      this.trace(`${message.from === 'list' ? 'list click' : 'opened'} -> ${message.entity}` +
        `${message.attribute ? ` · ${message.attribute}` : ''}: ` +
        `${message.inView ? 'in view' : 'NOT in view'} (top ${message.top} of ${message.height}, ` +
        `scrolled ${message.scrollY} of ${message.page})`);
      return;
    }
    this.busy = (this.busy || 0) + 1;
    try {
      await this.handle(message);
    } finally {
      this.busy -= 1;
      if (this.panel && !this.busy) {
        try {
          this.panel.webview.postMessage({ command: 'idle' });
        } catch (error) {
          // Closed meanwhile: nothing left to tell.
        }
      }
      this.flushRefresh();
    }
  }

  /**
   * A validation run finished. A page waiting for it asks again -- and so
   * does one showing an older version's verdicts: an edit made on another
   * page writes the file with no editor save, and a type page that had its
   * verdicts kept showing them. Hidden, it asks when it is shown again.
   */
  verdictsArrived(notice) {
    const shown = this.page && this.page.verdicts;
    if (!shown || !this.panel) {
      return;
    }
    if (notice && notice.root && this.page.root && notice.root !== this.page.root) {
      return;                          // another package's run
    }
    if (shown.state === 'ready' && !(notice && notice.state === 'ready')) {
      return;
    }
    if (!this.panel.visible) {
      this.staleWhileHidden = true;
      return;
    }
    this.refreshPending = true;
    this.flushRefresh();
  }

  flushRefresh() {
    if (this.refreshPending && !this.busy && !this.editing) {
      this.refreshPending = false;
      this.refresh();
    }
  }

  async handle(message) {
    if (!message || !this.current) {
      return;
    }
    if (message.command === 'assert') {
      await this.assert(message.index);
    } else if (message.command === 'open' && message.at) {
      await showLocation(message.at, true);
    } else if (message.command === 'problems') {
      await vscode.commands.executeCommand('workbench.actions.view.problems');
    } else if (message.command === 'type' && message.name) {
      // An attribute's name: its type's page, the attribute marked.
      await vscode.commands.executeCommand('semforge.openTypePage',
        { raw: { targetClass: message.name, focusNames: message.names },
          packageUri: this.current.packageUri });
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
   * Editing from the page goes through the Entities & Test Cases view's own commands, given
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
        items.push({ label: '$(symbol-ruler) Show its rule', description: 'on the type page',
          run: () => run('semforge.goToShape', row.node) },
        { label: '$(go-to-file) Open its rule in .ttl',
          run: () => run('semforge.goToShapeSource', row.node) });
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
      // From options, or from the node when a quick fix (one argument) or a
      // violation count sends it: the entity, its attribute, only what violates.
      const given = Object.assign({}, node || {}, options || {});
      await pages.show(packageUri, MODEL, given.focus, !!given.preserveFocus,
        { attribute: given.attribute || undefined, only: !!given.only });
    }),
    vscode.workspace.onDidSaveTextDocument(() => pages.refresh())
  );
  if (clientHolder.onVerdicts) {
    context.subscriptions.push(clientHolder.onVerdicts((notice) => pages.verdictsArrived(notice)));
  }
  return pages;
}

module.exports = { register, renderCasePage, CasePages };
