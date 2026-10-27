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
 * The entity type page: one webview in the editor area showing everything
 * about one type -- its place in the hierarchy, every attribute it must or may
 * carry (inherited ones and sub-attributes included), the rules that judge it,
 * the cases that exercise it and what is wrong with it in the model.
 *
 * Read-only, and computed by the SDK: `semforge/typePage` returns one JSON
 * payload and this file only renders it. The page decides nothing a tree
 * could disagree with.
 *
 * `renderTypePage` is a pure function from payload to HTML so it can be
 * tested without a window. Everything shown is escaped; script and style run
 * only with the per-render nonce under a strict Content-Security-Policy.
 */

const crypto = require('crypto');
const vscode = require('vscode');

const { showLocation } = require('./reveal');
const { pickValue } = require('./attribute');

const REFRESH_VIEWS = ['semforge.refreshTree', 'semforge.refreshKnowledge',
  'semforge.refreshModel'];

function escape(value) {
  return String(value === undefined || value === null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const TESTED_CLASS = {
  'both ways': 'ok', 'fires only': 'warn', 'never fired': 'warn', untested: '', evaluating: 'dim'
};

function chip(text, tone, title) {
  return `<span class="chip ${tone || ''}" title="${escape(title || text)}">` +
    `${escape(text)}</span>`;
}

/** A camelCase name that may break between its words, and only there:
 *  "hasPowerLossDueToInternalLeakage" fits a narrow column as "hasPowerLoss…
 *  / DueToInternal… / Leakage", not cut mid-word. */
function breakable(text) {
  return escape(text).replace(/([a-z0-9])([A-Z])/g, '$1<wbr>$2');
}

function action(name, index, text, title) {
  return `<a tabindex="0" role="link" class="act" data-action="${name}" data-row="${index}"` +
    `${title ? ` title="${escape(title)}"` : ''}>${escape(text)}</a>`;
}

/**
 * Which attribute row a tree click meant. The Constraints tree knows the path
 * (its deepest row on the page is the longest prefix: a full-mode constraint
 * row sits below its attribute); the Knowledge tree knows only the attribute.
 */
function focusIndex(attributes, focus) {
  if (!focus) {
    return -1;
  }
  let best = -1;
  let length = 0;
  const wanted = focus.path || [];
  attributes.forEach((row, index) => {
    const path = row.path || [];
    if (path.length > length && path.length <= wanted.length &&
        path.every((step, at) => step === wanted[at])) {
      best = index;
      length = path.length;
    }
  });
  if (best < 0 && focus.attribute) {
    best = attributes.findIndex((row) => row.attribute === focus.attribute);
  }
  // By name, as the data spells it: a case page knows `hasState` /
  // `hasXXXWorkpiece`, not the shapes' prefixes. The deepest row whose path
  // the names begin with.
  if (best < 0 && (focus.names || []).length) {
    const local = (term) => String(term).split(/[/#:]/).pop();
    attributes.forEach((row, index) => {
      const path = (row.path || []).map(local);
      if (path.length > length && path.length <= focus.names.length &&
          path.every((step, at) => step === local(focus.names[at]))) {
        best = index;
        length = path.length;
      }
    });
  }
  return best;
}

/** Where an attribute row comes from, as its group says it. */
function origin(row) {
  if (row.contributions) {
    return { key: 'several', html: 'Constrained by several shapes <span class="dim">· all apply</span>' };
  }
  const where = shapeLink(row.shapeName, row.shape);
  if (row.via || row.condition) {
    return { key: `via|${row.shape}|${row.condition || ''}`,
      html: `${where} <span class="cond">· ${escape(row.condition || 'by another target')}</span>` };
  }
  if (row.inherited) {
    return { key: `from|${row.inheritedFrom}|${row.shape}`,
      html: `From ${escape(row.inheritedFrom)} <span class="dim">·</span> ${where}` };
  }
  return { key: `own|${row.shape}`, html: `Own <span class="dim">·</span> ${where}` };
}

/** How an attribute stands, worst news first: what violates it in the model,
 *  then how well the test cases prove it -- which also starts a new test. */
/** How serious its results are when it fires: the level's label, or
 *  SHACL's default -- dimmed, since nobody said it. */
function severityText(row) {
  return row.severityDeclared ? escape(row.severity || '')
    : '<span class="dim">violation (default)</span>';
}

/** How well the test cases prove an attribute's constraints -- and the way
 *  to a new test. What the model's data does is not this column's: it is
 *  marked beside the attribute's name. */
function coverageText(row) {
  return row.tested && row.tested !== 'untested'
    ? chip(row.tested, TESTED_CLASS[row.tested],
      row.tested === 'never fired'
        ? 'No example makes this attribute\'s constraints fire. A constraint ' +
          'that cannot fire looks exactly like one that is satisfied.' : '')
    : '<span class="dim">untested</span>';
}

function attributeRows(attributes, focused, options) {
  // The shape page shows one shape's rows: a group saying where they are
  // declared would say the same name over every row.
  const grouped = !(options && options.shapeColumn === false);
  let group;
  return attributes.map((row, index) => {
    let head = '';
    if (grouped && !row.depth) {
      const from = origin(row);
      if (from.key !== group) {
        group = from.key;
        head = `<tr class="group"><td colspan="7">${from.html}</td></tr>`;
      }
    }
    const classes = [row.inherited ? 'inh' : '', row.violations.length ? 'flag' : '',
      index === focused ? 'focus' : ''].filter(Boolean).join(' ');
    // A class, not a style attribute: the page's CSP admits only its own
    // nonce'd stylesheet, so an inline style would be silently dropped.
    const indent = row.depth ? ` class="depth${Math.min(row.depth, 4)}"` : '';
    const verbatim = (row.verbatim.length
      ? `<div class="verbatim">${row.verbatim.map(escape).join('<br>')}</div>` : '') +
      (row.expression ? expressionTree(row.expression) : '');
    // The table says what holds; a click on the row opens the attribute
    // editor beside the page (attributepanel.js) -- one place to change it.
    return head + `<tr class="${classes} pick" data-action="attribute" data-row="${index}"` +
      ` title="${escape(`${row.term || row.label} — click to edit`)}"${index === focused ? ' id="focus"' : ''}>` +
      `<td${indent}>${breakable(row.label)}` +
      `${row.violations.length ? ` <a tabindex="0" role="link" class="violates" data-model="" title="${escape(
        `Violated in the main-model by:\n${row.violations.join('\n')}\n\nClick: open the main-model`)}">✗ ${row.violations.length}</a>`
        : ''}</td>` +
      // Every kind the value may take: `Property or ListProperty` for a value
      // that may be a scalar or a list (an OPC UA Variable's ValueRank).
      `<td class="kinds">${(row.kinds || [row.kind]).map((k) => `<span class="kind">${escape(k)}</span>`)
        .join(' <span class="dim">or</span> ')}</td>` +
      `<td>${escape(row.presence)}</td>` +
      // The value wraps: "one of PortDirectionEnum, or a list of them (possibly
      // empty)" kept on one line pushed the coverage column -- "New test…" --
      // and the actions off the right of the page.
      `<td class="value"><span title="${escape(row.valueLocked || '')}">${escape(row.value)}</span>` +
      `${verbatim}` +
      `${(row.notes || []).map((n) => `<div>${chip(n, 'bad')}</div>`).join('')}</td>` +
      `<td class="sev">${severityText(row)}</td>` +
      `<td class="coverage">${coverageText(row)}</td>` +
      `<td class="acts">${actions(row, index)}</td></tr>` +
      (row.contributions && grouped
        ? contributionRows(row, index, row.depth || 0) : '');
  }).join('');
}

function actions(row, index, contrib) {
  const at = `data-row="${index}"${contrib === undefined ? '' : ` data-contrib="${contrib}"`}`;
  if (row.via) {
    // A shape that reaches the type by another target: edited there.
    return `<button data-shape="${escape(row.shape)}" title="Edit it on its shape page">` +
      'Open shape</button>';
  }
  if (row.inherited && !row.contributions) {
    return `<a tabindex="0" role="link" class="act" data-action="override" ${at} title="Declare a stricter ` +
      'constraint on this type\'s own shape">override…</a>';
  }
  return `<button data-action="menu" ${at} title="More actions">⋯</button>`;
}

/** Beneath an attribute several shapes constrain: what each one says, and
 *  which of it the others already outdo. All of them apply (SHACL
 *  conjoins); the row above is what holds when they do. */
function contributionRows(row, index, depth) {
  const indent = `depth${Math.min(depth + 1, 4)}`;
  return row.contributions.map((c, j) => {
    const weaker = (c.noEffect || []).length
      ? ' ' + c.noEffect.map((n) => chip(`${n}: no effect`, '', 'Another shape on this ' +
        'attribute says something stricter, so this part never decides anything.')).join(' ')
      : '';
    // The shape's name goes where every row says where it is declared; the
    // attribute column stays empty -- these lines are about the same one.
    return `<tr class="contrib pick" data-action="attribute" data-row="${index}" data-contrib="${j}">` +
      `<td class="${indent}">↳ ${shapeLink(c.shapeName, c.shape)}` +
      `${c.inheritedFrom ? ` <span class="dim">· from ${escape(c.inheritedFrom)}</span>` : ''}` +
      `${c.condition ? ` <span class="cond">· ${escape(c.condition)}</span>` : ''}</td>` +
      '<td></td>' +
      `<td>${escape(c.presence)}</td><td>${escape(c.value)}${weaker}</td>` +
      `<td>${severityText(c)}</td>` +
      '<td></td>' +
      `<td class="acts">${actions(c, index, j)}</td></tr>`;
  }).join('');
}

/** A shape's name, opening its page: the shape is where the constraint lives. */
function shapeLink(name, iri) {
  const short = String(name || '').split(':').pop();
  return iri
    ? `<a tabindex="0" role="link" class="mono" data-shape="${escape(iri)}" title="${escape(name)}">${escape(short)}</a>`
    : `<span class="mono">${escape(short)}</span>`;
}

function ruleOrigin(rule) {
  if (rule.via || rule.condition) {
    return `<span class="cond">${escape(rule.condition || 'by another target')}</span>`;
  }
  return rule.inherited ? `From ${escape(rule.inheritedFrom)}` : 'Own';
}

function ruleRows(rules) {
  const groups = new Set(rules.map(ruleOrigin));
  let group;
  return rules.map((rule, index) => {
    const from = ruleOrigin(rule);
    const head = groups.size > 1 && from !== group
      ? `<div class="group">${from}</div>` : '';
    group = from;
    return head + `<div class="rule">` +
      `<span class="kind" title="${rule.kind === 'rule' ? 'A SPARQL rule: it derives data'
        : 'A SPARQL constraint: every row it returns is a violation'}">${rule.kind === 'rule'
        ? 'rule' : 'SPARQL'}</span>` +
      `<span class="what">${rule.text ? escape(rule.text)
        : `<span class="dim">(no message)</span>`} <span class="dim">·</span> ` +
      `${shapeLink(rule.shapeName, rule.shape)}</span>` +
      `<span>${rule.tested ? chip(rule.tested, TESTED_CLASS[rule.tested]) : ''}</span>` +
      `<span class="acts"><button data-bench="${escape(rule.shape)}" data-benchkind="${escape(rule.kind)}" ` +
      'title="Edit and run its query in the SPARQL workbench">Open</button>' +
      `<button data-action="ruleMenu" data-row="${index}" title="More">⋯</button></span></div>`;
  }).join('');
}

/** Who has this type: the model's entities, then the test cases. */
function instanceRows(page) {
  const model = (page.instances || []).map((i) => i.violations === null ? `<div class="inst">` +
    '<span class="dim">…</span>' +
    `<a tabindex="0" role="link" class="mono" data-model="${escape(i.id)}" title="Open it in the main-model">${escape(i.id)}</a>` +
    `<span class="dim">main-model${i.type !== page.label ? ` · ${escape(i.type)}` : ''}</span>` +
    '<span class="dim">evaluating…</span></div>' : `<div class="inst">` +
    `<span class="${i.violations.length ? 'bad-text' : 'ok-text'}">${i.violations.length ? '✗' : '✓'}</span>` +
    `<a tabindex="0" role="link" class="mono" data-model="${escape(i.id)}" title="Open it in the main-model">${escape(i.id)}</a>` +
    `<span class="dim">main-model${i.type !== page.label ? ` · ${escape(i.type)}` : ''}</span>` +
    `<span>${i.violations.length ? `<a tabindex="0" role="link" data-model="${escape(i.id)}">` + i.violations.map((v) =>
      chip(v.split('/').slice(1).join(' · ').replace('ConstraintComponent', ''), 'bad', v)).join(' ') +
      '</a>' : '<span class="dim">valid</span>'}</span></div>`).join('');
  const cases = (page.exercisedBy || []).map((c) => `<div class="inst">` +
    (c.passed === null ? '<span class="dim">…</span>'
      : `<span class="${c.passed ? 'ok-text' : 'bad-text'}">${c.passed ? '✓' : '✗'}</span>`) +
    `<a tabindex="0" role="link" data-case="${escape(c.file)}" title="${escape(c.description || '')}">` +
    `${escape(c.case.split('/').slice(-3).join(' / '))}</a>` +
    `<span class="dim">${escape(c.expect)}</span>` +
    `<span>${c.passed ? '<span class="dim">passes</span>' : chip('FAILS', 'bad')}</span></div>`).join('');
  return (model || '<p class="empty">No entity of this type in the main-model.</p>') +
    (cases || '<p class="empty">No test case has an entity of this type: nothing proves ' +
      'its constraints can fire.</p>');
}

/**
 * Where the validation is: the page is answered at once, and what the
 * validator concludes follows (editor/verdicts.py). Empty when it is current.
 */
/**
 * A value that is an expression (sh:or, sh:and, sh:xone, sh:not), as a small
 * tree under the value: the root's own conditions first, then each part.
 */
function expressionTree(root) {
  const parts = [];
  function walk(node, depth, own) {
    const pad = depth ? ` class="expr-d${Math.min(depth, 4)}"` : '';
    if (node.kind === 'op') {
      parts.push(`<div${pad}>${escape(node.words)}:</div>`);
      node.children.forEach((child) => walk(child, depth + 1, false));
    } else if (node.kind === 'leaf') {
      if (!(own && !node.conditions.length)) {
        parts.push(`<div${pad}>${own ? 'always: ' : ''}${escape(node.words)}</div>`);
      }
    } else {
      parts.push(`<div${pad} class="mono" title="kept as written">${escape(node.words)}</div>`);
    }
  }
  root.children.forEach((child, index) => walk(child, 0, index === 0));
  return `<div class="verbatim expr">${parts.join('')}</div>`;
}

function verdictNote(verdicts) {
  if (verdicts.state === 'evaluating') {
    // The strip runs along the top of the page: the note alone, small and dim,
    // was easy to miss, and a validation can take seconds.
    return `<span class="vstrip" aria-hidden="true"></span>` +
      `<span class="dim" title="The package is being validated in the background; this page ` +
      `updates when it is done">⟳ ${verdicts.stale ? 'showing the last results, re-evaluating…'
        : 'evaluating…'}</span>`;
  }
  if (verdicts.state === 'failed') {
    return `<span class="bad-text" title="${escape(verdicts.error || '')}">validation failed` +
      `${verdicts.stale ? ' (showing the last results)' : ''}</span>`;
  }
  return '';
}

function renderTypePage(page, options) {
  const nonce = (options && options.nonce) || '';
  const csp = `default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';`;
  const summary = page.summary || {};
  const crumbs = (page.crumbs || []).map((name) =>
    `<a tabindex="0" role="link" data-type="${escape(name)}">${escape(name)}</a> › `).join('');
  const attributes = page.attributes || [];
  const rules = page.rules || [];
  const subtypes = page.subtypes || [];
  const also = page.alsoCheckedBy || [];
  const verdicts = page.verdicts || { state: 'ready' };
  const status = [
    verdictNote(verdicts),
    summary.instances && summary.instancesViolating === null
      ? `<span class="dim">${summary.instances} in the main-model</span>`
      : summary.instances
      ? (summary.instancesViolating
        ? `<span class="bad-text">${summary.instancesViolating} of ${summary.instances} in the main-model violate</span>`
        : `<span class="ok-text">${summary.instances} in the main-model, all valid</span>`)
      : '<span class="dim">none in the main-model</span>',
    summary.cases
      ? (summary.casesFailing ? `<span class="bad-text">${summary.casesFailing} of ${summary.cases} ` +
        'case(s) failing</span>' : `${summary.cases} case(s), all pass`)
      : '<span class="warn-text">no test case uses it</span>',
    summary.neverFired ? `<span class="warn-text" title="Constraints or rules that no example ` +
      `makes fire">${summary.neverFired} never fired</span>` : ''
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
  .crumbs, .dim { color: var(--vscode-descriptionForeground); }
  .cond { color: var(--vscode-descriptionForeground); font-style: italic; }
  .crumbs { font-size: 0.9em; }
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
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { font-size: 0.86em; padding: 0 8px; border-radius: 999px; white-space: nowrap;
          display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis;
          vertical-align: bottom; box-sizing: border-box;
          border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  .chip.ok { color: var(--vscode-testing-iconPassed, #388a34); border-color: currentColor; }
  .chip.bad { color: var(--vscode-errorForeground, #f14c4c); border-color: currentColor; }
  .chip.warn { color: var(--vscode-editorWarning-foreground, #cca700); border-color: currentColor; }
  button { font: inherit; color: var(--vscode-button-secondaryForeground, inherit);
           background: var(--vscode-button-secondaryBackground, transparent);
           border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35));
           padding: 2px 10px; border-radius: 2px; cursor: pointer; }
  button:hover { background: var(--vscode-button-secondaryHoverBackground, transparent); }
  .table { overflow-x: auto; border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  table { border-collapse: collapse; width: 100%; }
  th { text-align: left; font-size: 0.78em; letter-spacing: .06em; text-transform: uppercase;
       color: var(--vscode-descriptionForeground); font-weight: 600; padding: 7px 12px;
       background: var(--vscode-sideBar-background, transparent); }
  td { padding: 5px 12px; border-top: 1px solid var(--vscode-panel-border, rgba(128,128,128,.25));
       white-space: nowrap; vertical-align: top; }
  td.coverage { white-space: normal; }
  tr.pick { cursor: pointer; }
  td.value { white-space: normal; min-width: 12em; overflow-wrap: anywhere; }
  td.kinds { white-space: normal; min-width: 7em; }
  /* The table fits the page: a long OPC UA attribute name, a severity with
     "(default)", wrap where they must -- the coverage column with "New
     test…" and the actions stay on screen. */
  tr td:first-child { white-space: normal; overflow-wrap: break-word; }
  td.coverage .act { white-space: nowrap; }
  td.sev, td.sev .severity { white-space: normal; }
  .severity { font-size: 0.86em; color: var(--vscode-descriptionForeground); white-space: nowrap; }
  .violates { color: var(--vscode-errorForeground, #f14c4c); font-size: 0.9em; }
  tr:hover td { background: var(--vscode-list-hoverBackground); }
  tr.inh td { color: var(--vscode-descriptionForeground); }
  tr.group td { font-size: 0.86em; color: var(--vscode-descriptionForeground); padding-top: 9px;
                background: var(--vscode-sideBar-background, rgba(128,128,128,.05)); }
  tr.contrib td { color: var(--vscode-descriptionForeground); font-size: 0.94em; border-top: 0;
                  padding-top: 2px; padding-bottom: 2px; }
  tr.flag td:first-child { box-shadow: inset 3px 0 0 var(--vscode-errorForeground, #f14c4c); }
  tr.focus td { background: var(--vscode-editor-selectionHighlightBackground, rgba(128,128,128,.2)); }
  tr.focus td:first-child { box-shadow: inset 3px 0 0 var(--vscode-focusBorder, #0078d4); }
  td.depth1 { padding-left: 30px; } td.depth2 { padding-left: 48px; }
  td.depth3 { padding-left: 66px; } td.depth4 { padding-left: 84px; }
  .kind { font-size: 0.8em; padding: 0 6px; border-radius: 3px;
          background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); }
  .mono, .verbatim { font-family: var(--vscode-editor-font-family); font-size: 0.92em; }
  .verbatim { color: var(--vscode-descriptionForeground); white-space: normal; margin-top: 2px; }
  .expr { font-family: var(--vscode-font-family); }
  .expr-d1 { padding-left: 14px; } .expr-d2 { padding-left: 28px; }
  .expr-d3 { padding-left: 42px; } .expr-d4 { padding-left: 56px; }
  .rule { display: grid; grid-template-columns: auto 1fr auto auto; gap: 10px; align-items: baseline;
          padding: 6px 8px; border-bottom: 1px solid var(--vscode-panel-border, rgba(128,128,128,.2)); }
  .rule .acts { display: flex; gap: 4px; }
  .rule .acts button, td.acts button { padding: 0 8px; }
  div.group { font-size: 0.86em; color: var(--vscode-descriptionForeground); margin: 8px 0 0; }
  .inst > * { min-width: 0; overflow-wrap: anywhere; }
  .inst { display: grid; grid-template-columns: 1.2em minmax(12em, 2fr) minmax(0, auto) minmax(0, 3fr);
          gap: 10px;
          align-items: baseline; padding: 3px 0; }
  .empty { color: var(--vscode-descriptionForeground); font-style: italic; margin: 4px 0; }
  a.act { color: inherit; border-bottom: 1px dashed var(--vscode-descriptionForeground); }
  a.act:hover, a.act:focus-visible { color: var(--vscode-textLink-foreground); text-decoration: none; }
  td.acts { text-align: right; }
  /* The row's actions -- ⋯ with "New test…" first -- stay at the right edge
     while a narrow panel scrolls the table sideways. */
  td.acts, tr > th:last-child { position: sticky; right: 0;
                                background: var(--vscode-editor-background, Canvas);
                                box-shadow: inset 1px 0 0 var(--vscode-panel-border, rgba(128,128,128,.25)); }
  tr:hover td.acts { background: var(--vscode-list-hoverBackground); }
  button.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground);
                   border-color: var(--vscode-button-background); }
  button.primary:hover { background: var(--vscode-button-hoverBackground); }
  details.fold { margin-top: 18px; }
  details.fold > summary { cursor: pointer; font-size: 0.78em; font-weight: 600; letter-spacing: .08em;
                           text-transform: uppercase; color: var(--vscode-descriptionForeground); }
  details.fold .rule { grid-template-columns: auto 1fr auto; }
${BUSY_CSS}</style></head><body>
<div class="crumbs">${crumbs}<b>${escape(page.label)}</b> · <span class="mono">${escape(page.term)}</span>${
  subtypes.length ? ` <span class="sep">·</span> subtypes: ${subtypes.map((name) =>
    `<a tabindex="0" role="link" data-type="${escape(name)}">${escape(name)}</a>`).join(', ')}` : ''}</div>
<div class="head"><h1>Entity type: ${escape(page.label)}</h1>
  <div class="acts"><button class="primary" data-action="addAttribute" title="${page.ownShape
    ? `Add an attribute to ${escape(page.ownShapeName)}`
    : `${escape(page.label)} has no shape of its own yet: one is created for it first`}">+ Attribute</button>
  <button data-action="pageMenu" title="New subtype…, the shape in .ttl, Refresh">⋯</button></div></div>
<p class="status">${status}</p>

<div class="sechead"><h2>Attributes</h2></div>
${attributes.length ? `<div class="table"><table>
<thead><tr><th>Attribute</th><th>Kind</th><th>Presence</th><th>Value</th><th title="How serious its results are when it fires (sh:severity)">Severity</th><th title="How well the test cases prove its constraints: both ways, fires only, never fired">Test coverage</th><th></th></tr></thead>
<tbody>${attributeRows(attributes, focusIndex(attributes, options && options.focus))}</tbody></table></div>`
    : '<p class="empty">No shape constrains an attribute of this type.</p>'}

<div class="sechead"><h2 title="SPARQL constraints and rules read the entity as a whole, not one attribute">Rules</h2>
  ${page.ownShape ? '<button data-action="addSparql" title="A SPARQL constraint on the whole entity, written in the workbench">+ SPARQL constraint</button>' : ''}</div>
${rules.length ? ruleRows(rules)
    : '<p class="empty">No SPARQL constraint or rule applies to this type.</p>'}

<div class="sechead"><h2>Instances</h2></div>
${instanceRows(page)}

${also.length ? `<details class="fold"><summary>Shapes that apply under a condition (${also.length})</summary>
<p class="dim">They do not target ${escape(page.label)} by class; their constraints are in the
tables above, under their condition.</p>
${also.map((a) => `<div class="rule"><span class="kind">shape</span>` +
    `<span class="what">${shapeLink(a.shapeName, a.shape)} <span class="cond">· ${escape(a.condition || a.target)}</span></span>` +
    `${a.reached ? chip(`reaches ${a.reached}`) : chip('none in the data yet')}</div>`).join('')}</details>` : ''}

<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
${BUSY_SCRIPT}
  const focused = document.getElementById('focus');
  if (focused) { focused.scrollIntoView({ block: 'center' }); }
  document.addEventListener('click', (event) => {
    const target = event.target.closest('[data-open],[data-type],[data-shape],[data-case],[data-model],[data-refresh],[data-action],[data-bench]');
    if (!target) { return; }
    event.preventDefault();
    if (target.dataset.action) {
      vscode.postMessage({ command: target.dataset.action,
                           row: target.dataset.row === undefined ? -1 : Number(target.dataset.row),
                           contrib: target.dataset.contrib === undefined ? undefined
                             : Number(target.dataset.contrib) });
    }
    else if (target.dataset.bench) {
      vscode.postMessage({ command: 'bench', shape: target.dataset.bench, kind: target.dataset.benchkind });
    }
    else if (target.dataset.open) { vscode.postMessage({ command: 'open', at: target.dataset.open }); }
    else if (target.dataset.type) { vscode.postMessage({ command: 'type', name: target.dataset.type }); }
    else if (target.dataset.shape) { vscode.postMessage({ command: 'shape', name: target.dataset.shape }); }
    else if (target.dataset.case) { vscode.postMessage({ command: 'case', file: target.dataset.case }); }
    else if (target.dataset.model !== undefined) { vscode.postMessage({ command: 'model', entity: target.dataset.model }); }
    else { vscode.postMessage({ command: 'refresh' }); }
  });
</script>
</body></html>`;
}

/**
 * "Loading …" in a panel while the server answers -- but only after 150 ms,
 * so a quick answer does not flicker, and only when the panel is switching to
 * something else: a refresh of what is on screen keeps it (and its scroll).
 * Returns the function that cancels it.
 */
function showLoading(panel, what, switching) {
  if (!panel || !switching) {
    return () => {};
  }
  const timer = setTimeout(() => {
    try {
      panel.webview.html = `<!DOCTYPE html><html><head><meta charset="utf-8">` +
        `<meta http-equiv="Content-Security-Policy" content="default-src 'none';"></head>` +
        `<body style="font-family:var(--vscode-font-family);color:var(--vscode-descriptionForeground);` +
        `padding:20px"><p>⟳ Loading ${escape(what)}…</p></body></html>`;
    } catch (error) {
      // Closed within the 150 ms: there is nothing left to say it to.
    }
  }, 150);
  return () => clearTimeout(timer);
}

/**
 * "⟳ updating…" on what a click changes, from the click until the extension
 * is done with it (it then says `idle`, or redraws the page). An edit takes a
 * moment -- the file is written, the package read again -- and a page that
 * shows nothing meanwhile looks frozen. Navigation is not marked: only what
 * writes (field actions, menus, Assert it, + Attribute …).
 */
// VS Code's webview host scrolls the page to its top on a click of any
// link to "#", whatever the page's own handler prevented (handleInnerClick
// in the webview's pre/index.html): a jump down the page was undone by the
// link that asked for it. So a page's links have no href -- role=link,
// tabindex 0 -- and Enter clicks them, as it did.
const LINK_CSS = 'a[role="link"] { cursor: pointer; }';
const LINK_SCRIPT = `
  document.addEventListener('keydown', function (event) {
    const link = event.key === 'Enter' && event.target.closest &&
      event.target.closest('a[role="link"]');
    if (link) { event.preventDefault(); link.click(); }
  });
`;

const BUSY_SCRIPT = LINK_SCRIPT + `
  const BUSY_TARGETS = '[data-action],[data-edit],[data-assert],[data-dropassert],' +
    '[data-retarget],[data-rowmenu],[data-addattr],[data-addentity],[data-pagemenu],[data-newcase]';
  function markBusy(node) {
    const holder = node.closest('tr, .attr, .claim, .card, .rule, .case, .file, h1') || node;
    if (holder.classList.contains('busy')) { return; }
    holder.classList.add('busy');
    const note = document.createElement('span');
    note.className = 'updating';
    note.textContent = '⟳ updating…';
    (holder.matches('tr') ? (holder.lastElementChild || holder) : holder).append(note);
  }
  function clearBusy() {
    document.querySelectorAll('.busy').forEach(function (n) { n.classList.remove('busy'); });
    document.querySelectorAll('.updating').forEach(function (n) { n.remove(); });
  }
  document.addEventListener('click', function (event) {
    const target = event.target.closest(BUSY_TARGETS);
    if (target) { markBusy(target); }
  }, true);
  window.addEventListener('message', function (event) {
    if (event.data && event.data.command === 'idle') { clearBusy(); }
  });
`;

const BUSY_CSS = LINK_CSS + `
  .busy { opacity: 0.55; transition: opacity 0.15s; }
  .updating { color: var(--vscode-textLink-foreground, #3794ff); font-size: 0.86em; margin-left: 8px;
              white-space: nowrap; opacity: 1; }
  .busy .updating { opacity: 1; }
  .vstrip { position: fixed; top: 0; left: 0; right: 0; height: 2px; overflow: hidden; z-index: 10; }
  .vstrip::after { content: ''; position: absolute; top: 0; bottom: 0; width: 30%;
                   background: var(--vscode-progressBar-background, #0e70c0);
                   animation: vstrip 1.2s ease-in-out infinite; }
  @keyframes vstrip { from { left: -30%; } to { left: 100%; } }
`;

function renderMessage(title, message) {
  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none';">
<title>${escape(title)}</title></head>
<body style="font-family:var(--vscode-font-family);color:var(--vscode-foreground);padding:20px">
<p>${escape(message)}</p></body></html>`;
}

/** One reusable panel, like the Settings editor: clicking another type
 *  replaces the page rather than opening another tab. */
class TypePages {
  constructor(clientHolder, session) {
    this.clientHolder = clientHolder;
    this.session = session;
    this.panel = undefined;
    this.current = undefined;          // { packageUri, entityType }
  }

  /**
   * `focus` marks one attribute row ({path} from the Constraints tree,
   * {attribute} from the Knowledge tree). `preserveFocus` leaves the keyboard
   * where it was: a click in a tree opens the page beside the reader's
   * browsing, and the next arrow key should move in the tree, not the page.
   * `edit` also opens the attribute editor on the marked row: an attribute
   * just added is shown where it is changed, not in the .ttl.
   */
  async show(packageUri, entityType, focus, preserveFocus, edit) {
    const client = this.clientHolder.client;
    if (!client || !packageUri || !entityType) {
      vscode.window.showWarningMessage(
        'SemForge: no package is open, or the language server is not running.');
      return;
    }
    const same = this.panel && this.current && this.current.packageUri === packageUri &&
      this.current.entityType === entityType &&
      JSON.stringify(this.current.focus) === JSON.stringify(focus);
    this.current = { packageUri, entityType, focus };
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        'semforgeTypePage', 'Entity type',
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
    }
    if (!same) {                       // clicked again: already showing it
      await this.render();
    }
    if (edit && this.page) {
      const rows = this.page.attributes || [];
      const index = focusIndex(rows, focus);
      if (index >= 0) {
        await require('./attributepanel').openAttribute(this, rows[index], index);
      }
    }
  }

  async render() {
    this.editing = false;      // a redraw closes any editor the page had open
    if (!this.panel || !this.current) {
      return;
    }
    const { packageUri, entityType } = this.current;
    const target = `${packageUri}#${entityType}`;
    const loaded = showLoading(this.panel, entityType.split(/[/#:]/).pop(), this.shown !== target);
    let page;
    try {
      page = await this.clientHolder.client.sendRequest('semforge/typePage',
        { uri: packageUri, entityType });
    } catch (error) {
      page = { ok: false, error: error.message || String(error) };
    }
    loaded();
    this.shown = target;
    if (!this.panel) {
      return;                          // closed while the server answered
    }
    if (!page.ok) {
      this.panel.title = 'Entity type';
      this.panel.webview.html = renderMessage('Entity type', `SemForge: ${page.error}`);
      return;
    }
    this.page = page;
    this.panel.title = `Entity type: ${page.label}`;
    this.panel.webview.html = renderTypePage(page,
      { nonce: crypto.randomBytes(16).toString('base64'), focus: this.current.focus });
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
    if (message.command === 'attribute') {
      // A click on a row: the attribute editor on it, the whole row -- which
      // shape a change goes to is asked when one is made.
      const row = this.page && this.page.attributes ? this.page.attributes[message.row] : undefined;
      if (row) {
        const part = message.contrib !== undefined && row.contributions
          ? row.contributions[message.contrib] : row;
        await require('./attributepanel').openAttribute(this, part, message.row, message.contrib);
      }
      return;
    }
    const edit = EDITS[message.command];
    if (edit) {
      let row = this.page && this.page.attributes
        ? this.page.attributes[message.row] : undefined;
      if (row && row.contributions) {
        row = message.contrib !== undefined ? row.contributions[message.contrib]
          : message.command === 'test' ? row : await whichShape(row, message.command);
        if (!row) {
          return;
        }
      }
      const changed = await edit(this, row);
      if (changed) {
        await this.render();
        for (const command of REFRESH_VIEWS) {
          vscode.commands.executeCommand(command);
        }
      }
      return;
    }
    if (message.command === 'pageMenu') {
      // What is used now and then, kept off the page: one ⋯.
      const page = this.page;
      const items = [{ label: '$(type-hierarchy-sub) New subtype…', message: { command: 'newSubtype', row: -1 } }];
      if (page.shapeAt) {
        items.push({ label: '$(go-to-file) Open the shape in .ttl', message: { command: 'open', at: page.shapeAt } });
      }
      if (!page.ownShape) {
        items.push({ label: '$(new-file) Create its shape', description: 'e.g. for a SPARQL rule',
          message: { command: 'createShape', row: -1 } });
      }
      items.push({ label: '$(refresh) Refresh', message: { command: 'refresh' } });
      const picked = await vscode.window.showQuickPick(items, { title: page.label });
      if (picked) {
        await this.receive(picked.message);
      }
      return;
    }
    if (message.command === 'ruleMenu') {
      const rule = (this.page.rules || [])[message.row];
      if (!rule) {
        return;
      }
      const picked = await vscode.window.showQuickPick([
        { label: '$(beaker) Open in SPARQL workbench', message: { command: 'bench', shape: rule.shape, kind: rule.kind } },
        { label: '$(symbol-interface) Open its shape page', message: { command: 'shape', name: rule.shape } },
        { label: '$(go-to-file) Open in .ttl', message: { command: 'open', at: rule.definedAt } }
      ].filter((item) => item.message.at !== ''), { title: rule.text || rule.shapeName });
      if (picked) {
        await this.receive(picked.message);
      }
      return;
    }
    if (message.command === 'addSparql' && this.page.ownShape) {
      await vscode.commands.executeCommand('semforge.addSparqlConstraint',
        { raw: { shape: this.page.ownShape }, packageUri: this.current.packageUri });
      return;
    }
    if (message.command === 'case' && message.file) {
      await vscode.commands.executeCommand('semforge.openCasePage',
        { raw: { kind: 'example', file: message.file }, packageUri: this.current.packageUri });
      return;
    }
    // The model has a page too -- Main -- scrolled to the entity named.
    if (message.command === 'model') {
      await vscode.commands.executeCommand('semforge.openModelPage',
        { packageUri: this.current.packageUri }, { focus: message.entity || undefined });
      return;
    }
    if (message.command === 'bench' && message.shape) {
      await vscode.commands.executeCommand('semforge.openSparqlBench',
        { raw: { shape: message.shape }, packageUri: this.current.packageUri },
        { kind: message.kind });
    } else if (message.command === 'open' && message.at) {
      await showLocation(message.at, true);
    } else if (message.command === 'shape' && message.name) {
      await vscode.commands.executeCommand('semforge.openShapePage',
        { raw: { shape: message.name }, packageUri: this.current.packageUri });
    } else if (message.command === 'type' && message.name) {
      await this.show(this.current.packageUri, message.name);
    } else if (message.command === 'refresh') {
      await this.render();
    }
  }

  /** After a save the page may be stale; the cache makes this cheap. */
  refresh() {
    if (this.panel && this.panel.visible) {
      this.render();
    }
  }

}

// --- editing: each answers one click, and says whether anything changed --------------

async function request(pages, method, params) {
  const result = await pages.clientHolder.client.sendRequest(method,
    Object.assign({ uri: pages.current.packageUri }, params));
  if (!result.ok) {
    vscode.window.showErrorMessage(`SemForge: ${result.error}`);
    return false;
  }
  return result;
}

/** A whole number typed into a box, or undefined when cancelled. */
async function askCount(title, prompt, value, least) {
  const typed = await vscode.window.showInputBox({
    title, prompt, value: value === undefined ? '' : String(value),
    validateInput: (text) => {
      if (!/^\d+$/.test(text.trim())) {
        return 'a whole number, 0 or more';
      }
      return least !== undefined && Number(text) < least
        ? `at least ${least}: fewer than the minimum can never be satisfied` : undefined;
    }
  });
  return typed === undefined ? undefined : Number(typed.trim());
}

/**
 * How many instances the attribute must have -- distinct datasetIds, which is
 * what sh:minCount / sh:maxCount count. Optional and Required change only the
 * minimum (Required keeps one already above 1); the others set both.
 */
async function editPresence(pages, row) {
  if (!row) {
    return false;
  }
  const own = (name) => {
    const found = (row.parameters || []).find((p) => p.layer === 'attribute' && p.parameter === name);
    return found && /^\d+$/.test(String(found.value)) ? Number(found.value) : undefined;
  };
  const least = own('sh:minCount') || 0;
  const most = own('sh:maxCount');
  const items = [
    { label: 'Optional', description: 'sh:minCount 0', value: { presence: 'optional' } },
    { label: 'Required', description: least > 1 ? `at least one — keeps sh:minCount ${least}`
      : 'at least one: sh:minCount 1', value: { presence: 'required' } },
    { label: 'Exactly one', description: 'sh:minCount 1 · sh:maxCount 1',
      value: { counts: { min: 1, max: 1 } } },
    { label: 'Exactly…', description: 'n instances, each its own datasetId', ask: 'exactly' },
    { label: 'At least…', description: 'n or more; no maximum', ask: 'atLeast' },
    { label: 'Between…', description: 'a minimum and a maximum', ask: 'between' },
    { label: 'Any number', description: 'sh:minCount 0, no sh:maxCount',
      value: { counts: { min: 0, max: null } } }
  ];
  for (const item of items) {
    if (item.label.toLowerCase() === String(row.presence).split(' · ')[0] ||
        (item.label === 'Exactly one' && row.presence === 'required · one')) {
      item.description = `${item.description} — now`;
    }
  }
  const picked = await vscode.window.showQuickPick(items, {
    title: `${row.label}: how many on every ${pages.page.subject || pages.page.label}? Now ${row.presence}`,
    placeHolder: 'Instances are datasetIds: one attribute name, several values'
  });
  if (!picked) {
    return false;
  }
  let change = picked.value;
  if (picked.ask === 'exactly') {
    const count = await askCount(`${row.label}: exactly how many?`, 'Instances, each its own datasetId',
      least || 2);
    change = count === undefined ? undefined : { counts: { min: count, max: count } };
  } else if (picked.ask === 'atLeast') {
    const count = await askCount(`${row.label}: at least how many?`, 'No maximum', least || 2);
    change = count === undefined ? undefined : { counts: { min: count, max: null } };
  } else if (picked.ask === 'between') {
    const low = await askCount(`${row.label}: at least how many?`, 'The minimum', least);
    const high = low === undefined ? undefined
      : await askCount(`${row.label}: at most how many?`, `The maximum — ${low} or more`,
        most !== undefined && most >= low ? most : Math.max(low, 1), low);
    change = high === undefined ? undefined : { counts: { min: low, max: high } };
  }
  if (!change) {
    return false;
  }
  return Boolean(await request(pages, 'semforge/editAttribute',
    Object.assign({ shape: row.shape, path: row.path }, change)));
}

function describeParameter(parameter) {
  return { label: `${parameter.parameter} ${parameter.value}`,
    description: parameter.layer === 'value' ? 'on the value' : 'on the attribute',
    parameter };
}

// Every constraint the editor writes, in words, with where it goes and what
// its value is. A count goes on the attribute (how many instances) or on the
// value; everything else only on the value.
const CONSTRAINTS = [
  { parameter: 'sh:minInclusive', words: 'at least (≥)', kind: 'number' },
  { parameter: 'sh:maxInclusive', words: 'at most (≤)', kind: 'number' },
  { parameter: 'sh:minExclusive', words: 'more than (>)', kind: 'number' },
  { parameter: 'sh:maxExclusive', words: 'less than (<)', kind: 'number' },
  { parameter: 'sh:datatype', words: 'the value\'s datatype', kind: 'choice' },
  { parameter: 'sh:class', words: 'the value is one of a class', kind: 'choice' },
  { parameter: 'sh:nodeKind', words: 'IRI, literal or blank node', kind: 'choice' },
  { parameter: 'sh:minLength', words: 'text at least this long', kind: 'integer' },
  { parameter: 'sh:maxLength', words: 'text at most this long', kind: 'integer' },
  { parameter: 'sh:pattern', words: 'text matching a regular expression', kind: 'text' },
  { parameter: 'sh:in', words: 'the value is one of a list', kind: 'list' },
  { parameter: 'sh:minCount', words: 'at least this many instances', kind: 'integer',
    layer: 'attribute' },
  { parameter: 'sh:maxCount', words: 'at most this many instances', kind: 'integer',
    layer: 'attribute' }
];

const KIND_PROMPT = {
  number: ['A number, e.g. 0 or 12.5', (t) => (/^[-+]?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(t.trim())
    ? undefined : 'a number')],
  integer: ['A whole number, 0 or more', (t) => (/^\d+$/.test(t.trim()) ? undefined
    : 'a whole number')],
  text: ['A regular expression, e.g. ^[A-Z]{2}[0-9]+$', (t) => (t ? undefined : 'required')]
};

/**
 * An sh:in list. Where the value is drawn from a vocabulary class
 * (sh:class MachineState), its values are offered to tick -- the current
 * ones ticked; otherwise the items are typed, separated by commas: numbers,
 * "quoted text", prefixed names. Returns a list, a text, or undefined.
 */
async function askList(pages, row, current) {
  const cls = row.parameters.find((p) => p.layer === 'value' && p.parameter === 'sh:class');
  if (cls) {
    let page;
    try {
      page = await pages.clientHolder.client.sendRequest('semforge/vocabularyPage',
        { uri: pages.current.packageUri, cls: cls.value });
    } catch (error) {
      page = undefined;
    }
    if (page && page.ok && page.values.length) {
      const short = (term) => String(term).split(':').pop();
      const ticked = new Set((current || []).map(short));
      const picked = await vscode.window.showQuickPick(page.values.map((v) => ({
        label: v.name, description: v.label, value: v.term, picked: ticked.has(v.name) })),
      { title: `${row.label} · sh:in: which ${page.label} values are allowed?`,
        canPickMany: true });
      if (!picked) {
        return undefined;
      }
      if (!picked.length) {
        vscode.window.showWarningMessage('SemForge: an empty list admits no value; ' +
          'remove sh:in instead.');
        return undefined;
      }
      return picked.map((item) => item.value);
    }
  }
  const value = await vscode.window.showInputBox({
    title: `${row.label} · sh:in: the value is one of`,
    value: (current || []).join(', '),
    prompt: 'Separated by commas: numbers, "quoted text", prefixed names (ex:ON)',
    validateInput: (t) => (t.trim() ? undefined : 'at least one value; or remove sh:in') });
  return value === undefined ? undefined : value.trim();
}

async function askValue(pages, row, spec, current) {
  if (spec.kind === 'list') {
    return askList(pages, row, current);
  }
  if (spec.kind === 'choice') {
    const slot = row.kind === 'Relationship' ? 'ngsild:hasObject' : 'ngsild:hasValue';
    let offered = [];
    try {
      const answer = await pages.clientHolder.client.sendRequest('semforge/choices', {
        uri: pages.current.packageUri, path: row.path.concat([slot]),
        parameter: spec.parameter });
      offered = answer.choices || [];
    } catch (error) {
      offered = [];
    }
    const items = offered.map((c) => ({ label: c.label || c.value, description: c.detail,
      value: c.value }));
    // On top: the list may be hundreds of OPC UA classes long.
    const picked = await require('./picks').pickWithActions(
      [{ label: '$(edit) Enter a different value…', value: undefined }], items,
      { title: `${row.label} · ${spec.parameter}`, heading: 'Offered', matchOnDescription: true });
    if (!picked) {
      return undefined;
    }
    if (picked.value !== undefined) {
      return picked.value;
    }
  }
  const [prompt, validate] = KIND_PROMPT[spec.kind] ||
    ['A prefixed name, e.g. xsd:double', (t) => (t.trim() ? undefined : 'required')];
  const value = await vscode.window.showInputBox({
    title: `${row.label} · ${spec.parameter}: ${spec.words}`,
    value: current, prompt, validateInput: validate });
  return value === undefined ? undefined : value.trim();
}

async function editParameter(pages, row) {
  const have = row.parameters.map((p) => ({
    label: `${p.parameter} ${p.value}`,
    description: p.layer === 'value' ? 'on the value' : 'on the attribute',
    detail: 'change it, or remove it', existing: p }));
  const present = new Set(row.parameters.map((p) => `${p.layer}:${p.parameter}`));
  if (row.inList) {
    // A list is structure, not a plain parameter: listed here item by item.
    have.push({ label: `sh:in ${row.inList.value}`, description: 'on the value',
      detail: 'edit the list, or remove it',
      existing: { parameter: 'sh:in', value: row.inList.value, path: row.inList.path,
        layer: 'value', items: row.inList.items } });
    present.add('value:sh:in');
  }
  const add = [];
  for (const spec of CONSTRAINTS) {
    const layers = spec.layer === 'attribute' ? ['attribute', 'value'] : ['value'];
    for (const layer of layers) {
      if (!present.has(`${layer}:${spec.parameter}`)) {
        add.push({ label: `$(add) ${spec.parameter}`,
          description: `${spec.words}${layer === 'attribute' ? '' : ' · on the value'}`,
          spec, layer });
      }
    }
  }
  const picked = await vscode.window.showQuickPick([
    { label: 'On this attribute', kind: vscode.QuickPickItemKind.Separator },
    ...have,
    { label: 'Add a constraint', kind: vscode.QuickPickItemKind.Separator },
    ...add
  ], { title: `${row.label}: which constraint?`, matchOnDescription: true });
  if (!picked) {
    return false;
  }
  if (picked.existing) {
    const parameter = picked.existing;
    const spec = CONSTRAINTS.find((c) => c.parameter === parameter.parameter) ||
      { parameter: parameter.parameter, words: '', kind: 'term' };
    const how = await vscode.window.showQuickPick([
      { label: parameter.items ? '$(edit) Edit the list…' : '$(edit) Change the value…',
        action: 'change' },
      { label: `$(trash) Remove ${parameter.parameter}`, action: 'remove' }
    ], { title: `${row.label} · ${parameter.parameter} ${parameter.value}` });
    if (!how) {
      return false;
    }
    if (how.action === 'remove') {
      return Boolean(await request(pages, 'semforge/setConstraint', {
        shape: row.shape, path: parameter.path, parameter: parameter.parameter,
        remove: true }));
    }
    if (parameter.items) {
      // Written anew in place: the list as a whole is the value.
      const items = await askList(pages, row, parameter.items);
      if (items === undefined) {
        return false;
      }
      return Boolean(await request(pages, 'semforge/setConstraint', {
        shape: row.shape, path: row.path, parameter: 'sh:in', value: items,
        add: true, layer: 'value' }));
    }
    const value = await askValue(pages, row, spec, parameter.value);
    if (value === undefined || value === parameter.value) {
      return false;
    }
    return Boolean(await request(pages, 'semforge/setConstraint', {
      shape: row.shape, path: parameter.path, parameter: parameter.parameter, value }));
  }
  const value = await askValue(pages, row, picked.spec, picked.spec.kind === 'list' ? [] : '');
  if (value === undefined || value === '') {
    return false;
  }
  const done = await request(pages, 'semforge/setConstraint', {
    shape: row.shape, path: row.path, parameter: picked.spec.parameter, value,
    add: true, layer: picked.layer });
  if (done && done.note) {
    vscode.window.showWarningMessage(`SemForge: ${done.note}`);
  }
  return Boolean(done);
}

/** The attribute editor on `row`: the page's own row, or one shape's part
 *  of a row several shapes constrain. */
function openEditor(pages, row) {
  const rows = (pages.page && pages.page.attributes) || [];
  let index = rows.indexOf(row);
  let contrib;
  if (index < 0) {
    index = rows.findIndex((r) => (r.contributions || []).includes(row));
    contrib = index < 0 ? undefined : rows[index].contributions.indexOf(row);
  }
  return require('./attributepanel').openAttribute(pages, row, index, contrib);
}

async function rowMenu(pages, row) {
  if (!row) {
    return false;
  }
  const shapeName = row.shapeName.split(':').pop();
  const choices = [
    { label: '$(beaker) New test…', description: 'valid, or one of its constraints firing',
      run: newTest },
    // Everything about the constraint -- presence, value, severity, unit --
    // is changed in the attribute editor beside the page.
    { label: '$(edit) Edit…', description: 'presence, value, severity, unit — in the attribute editor',
      run: async () => openEditor(pages, row) },
    { label: '$(add) Add a sub-attribute…', description: `nested inside ${row.label}`,
      run: async () => {
        await vscode.commands.executeCommand('semforge.addAttributeConstraint', {
          raw: { kind: 'attribute', shape: row.shape, path: row.path,
            label: row.term, inheritedFrom: '' },
          packageUri: pages.current.packageUri });
        return true;
      } },
    { label: `$(remove) Remove from ${shapeName}…`,
      description: 'the attribute stays declared', run: removeFromShape },
    { label: '$(trash) Delete the attribute everywhere…',
      description: 'shows every dependent first',
      run: async () => {
        await vscode.commands.executeCommand('semforge.deleteAttribute', {
          raw: { iri: row.attribute }, packageUri: pages.current.packageUri });
        return true;
      } },
    { label: `$(merge) Merge ${shapeName} into…`,
      description: 'another shape selecting the same nodes; nothing checked changes',
      run: async () => Boolean(await vscode.commands.executeCommand('semforge.mergeShape', {
        raw: { shape: row.shape }, packageUri: pages.current.packageUri })) },
    { label: '$(go-to-file) Open in .ttl',
      run: async () => { await showLocation(row.definedAt, true); return false; } }
  ];
  const picked = await vscode.window.showQuickPick(choices, { title: row.label });
  return picked ? picked.run(pages, row) : false;
}

/** An attribute several shapes constrain is changed in ONE of them: which?
 *  Only this type's own shapes can be edited here; an inherited one is
 *  tightened with Override, and a conditional one on its shape page. */
async function whichShape(row, command) {
  const own = row.contributions.filter((c) => !c.inherited);
  const candidates = command === 'override'
    ? row.contributions.filter((c) => c.inherited && !c.via) : own;
  if (!candidates.length) {
    vscode.window.showInformationMessage(
      `SemForge: ${row.label} is constrained here by shapes this type does not own; ` +
        'open one of them to change it.');
    return undefined;
  }
  if (candidates.length === 1) {
    return candidates[0];
  }
  const picked = await vscode.window.showQuickPick(candidates.map((c) => ({
    label: c.shapeName.split(':').pop(), description: `${c.presence} · ${c.value}`,
    detail: (c.noEffect || []).length ? `no effect here: ${c.noEffect.join(', ')}` : undefined,
    contribution: c })),
  { title: `${row.label} is constrained by ${row.contributions.length} shapes: change which?` });
  return picked && picked.contribution;
}

/** The type has no shape of its own: write one targeting it. The type page
 *  re-renders after it, now with + Attribute. */
async function createShape(pages) {
  const made = await vscode.commands.executeCommand('semforge.newShape', {
    raw: { kind: 'type', targetClass: pages.page.iri, label: pages.page.label },
    packageUri: pages.current.packageUri }, { stay: true });
  return Boolean(made);
}

/** New subtype…: the shared command, with this type as the parent. The page
 *  itself does not change -- a subtype is not part of its parent's page. */
async function newSubtype(pages) {
  await vscode.commands.executeCommand('semforge.newSubtype', {
    raw: { targetClass: pages.page.iri }, packageUri: pages.current.packageUri });
  return false;
}

/** A test for this attribute: the shared command, aimed at this row. */
async function newTest(pages, row) {
  if (!row) {
    return false;
  }
  // On a type page the type is the page's; on a shape page it is the class
  // the shape targets -- and a shape targeting no class has no type to test.
  const type = 'testType' in pages.page ? pages.page.testType : pages.page.iri;
  if (!type) {
    vscode.window.showInformationMessage(
      `SemForge: ${pages.page.label} targets no entity type, so a test cannot pick ` +
        'an entity for it here. Open the attribute on the type page of an entity it reaches.');
    return false;
  }
  return vscode.commands.executeCommand('semforge.newAttributeTest', {
    raw: { kind: 'attribute', label: row.label, path: row.path, typeClass: type },
    packageUri: pages.current.packageUri });
}

async function removeFromShape(pages, row) {
  const shapeName = row.shapeName.split(':').pop();
  const answer = await vscode.window.showWarningMessage(
    `Remove ${row.label} from ${shapeName}?`,
    { modal: true, detail: `Its property shape — every constraint on it, and ` +
      `any sub-attribute nested in it — is taken out of ${shapeName}. The ` +
      'attribute stays declared in the knowledge, and stays constrained wherever ' +
      'else it is. The data is not touched.' },
    'Remove');
  if (answer !== 'Remove') {
    return false;
  }
  return Boolean(await request(pages, 'semforge/removeProperty',
    { shape: row.shape, path: row.path }));
}

async function override(pages, row) {
  if (!row) {
    return false;
  }
  if (!pages.page.ownShape) {
    vscode.window.showInformationMessage(
      `SemForge: ${pages.page.label} has no shape of its own to declare it on.`);
    return false;
  }
  const picked = await vscode.window.showQuickPick(row.parameters.map(describeParameter),
    { title: `${row.label}: which inherited constraint to tighten on ${pages.page.label}?` });
  if (!picked) {
    return false;
  }
  const { parameter } = picked;
  const value = await vscode.window.showInputBox({
    title: `${parameter.parameter} on ${pages.page.label}`, value: parameter.value,
    prompt: `Inherited from ${row.inheritedFrom}: ${parameter.value}. SHACL conjoins, ` +
      'so this can only make the constraint stricter.'
  });
  if (value === undefined) {
    return false;
  }
  const send = (force) => pages.clientHolder.client.sendRequest('semforge/override', {
    uri: pages.current.packageUri, targetShape: pages.page.ownShape,
    path: parameter.path, parameter: parameter.parameter,
    inheritedValue: parameter.value, value, force });
  let result = await send(false);
  if (!result.ok && (result.effect === 'weaker' || result.effect === 'same')) {
    const choice = await vscode.window.showWarningMessage(
      `${parameter.parameter} ${parameter.value} → ${value} is ${result.effect}. ${result.error}`,
      { modal: true }, 'Add it anyway');
    if (choice !== 'Add it anyway') {
      return false;
    }
    result = await send(true);
  }
  if (!result.ok) {
    vscode.window.showErrorMessage(`SemForge: ${result.error}`);
    return false;
  }
  return true;
}

async function addAttribute(pages) {
  return addAttributeToType(pages.current.packageUri, {
    iri: pages.page.iri, label: pages.page.label,
    shapes: pages.page.ownShape
      ? [{ shape: pages.page.ownShape, label: pages.page.ownShapeName }] : [] });
}

/**
 * + Attribute on a type: the attribute goes into one of the type's OWN shapes.
 * A type with none yet -- a new subtype, judged only by what it inherits --
 * gets one first (its name is asked, prefilled), so adding an attribute never
 * stops at "create a shape first".
 */
async function addAttributeToType(packageUri, type) {
  let target = type.shapes[0];
  if (type.shapes.length > 1) {
    const picked = await vscode.window.showQuickPick(
      type.shapes.map((s) => ({ label: s.label, shape: s })),
      { title: `+ Attribute on ${type.label}: into which of its shapes?` });
    if (!picked) {
      return false;
    }
    target = picked.shape;
  }
  if (!target) {
    const made = await vscode.commands.executeCommand('semforge.newShape', {
      raw: { kind: 'type', targetClass: type.iri, label: type.label }, packageUri },
    { stay: true, quiet: true });
    if (!made) {
      return false;
    }
    target = { shape: made.iri, label: made.name };
  }
  await vscode.commands.executeCommand('semforge.addAttributeConstraint', {
    raw: { kind: 'shape', shape: target.shape, label: target.label, inheritedFrom: '' },
    packageUri });
  return true;
}

/** The Severity cell: SHACL's levels and the package's, in the same picker
 *  as ⋯ → Severity…. */
async function editSeverity(pages, row) {
  if (!row) {
    return false;
  }
  const current = `${row.severity || 'violation'}${row.severityDeclared ? '' : ' (default)'}`;
  return Boolean(await require('./severity').chooseSeverity(
    pages.clientHolder.client, pages.current.packageUri,
    { shape: row.shape, path: row.path, label: row.label, current }));
}

const EDITS = { presence: editPresence, menu: rowMenu, test: newTest,
  severity: editSeverity, createShape, newSubtype, override, addAttribute,
  // What the attribute editor asks of the page (attributepanel.js).
  unit: async (pages, row) => Boolean(await require('./units').editUnits(
    pages.clientHolder.client, pages.current.packageUri, row)),
  params: editParameter };

/** The entity type a tree row stands for, whichever tree it is in. */
function typeOf(node) {
  const raw = node && node.raw;
  if (!raw) {
    return undefined;
  }
  return raw.targetClass || raw.typeClass || (raw.kind === 'class' && raw.iri) ||
    raw.entityType || raw.iri || undefined;
}

/** The attribute row a tree row points at on its type's page, if any. */
function focusOf(node) {
  const raw = node && node.raw;
  if (!raw || raw.kind === 'type' || raw.kind === 'class' || raw.kind === 'carrier') {
    return undefined;
  }
  const path = Array.isArray(raw.path) && raw.path.length ? raw.path : undefined;
  const attribute = raw.kind === 'attribute' && raw.iri ? raw.iri : undefined;
  // From a case page or a new attribute: the attribute by its names.
  const names = Array.isArray(raw.focusNames) && raw.focusNames.length ? raw.focusNames : undefined;
  return path || attribute || names ? { path, attribute, names } : undefined;
}

async function pickType(client, packageUri) {
  const answer = await client.sendRequest('semforge/entityTypes', { uri: packageUri });
  const picked = await vscode.window.showQuickPick(
    (answer.types || []).map((t) => ({ label: t.label, description: t.term, iri: t.iri })),
    { title: 'Open the page of an entity type', matchOnDescription: true });
  return picked ? picked.iri : undefined;
}

function register(context, clientHolder, session) {
  const pages = new TypePages(clientHolder, session);
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.openTypePage', async (node, options) => {
      const client = clientHolder.client;
      const packageUri = (node && node.packageUri) || session.uri;
      if (!client || !packageUri) {
        vscode.window.showWarningMessage(
          'SemForge: no package is open, or the language server is not running.');
        return;
      }
      const entityType = node && node.raw ? typeOf(node) : await pickType(client, packageUri);
      if (entityType) {
        await pages.show(packageUri, entityType, focusOf(node),
          !!(options && options.preserveFocus), !!(options && options.edit));
      }
    }),
    // + Attribute on a type row in the Entity Types & Constraints view: its own shapes are the
    // children not marked inherited.
    vscode.commands.registerCommand('semforge.addTypeAttribute', async (node) => {
      const raw = node && node.raw;
      const packageUri = (node && node.packageUri) || session.uri;
      if (!raw || !packageUri || !clientHolder.client) {
        return false;
      }
      const shapes = (raw.children || [])
        .filter((c) => c.kind === 'shape' && !c.inheritedFrom && c.shape)
        .map((c) => ({ shape: c.shape, label: c.label }));
      const changed = await addAttributeToType(packageUri,
        { iri: typeOf(node), label: raw.label, shapes });
      if (changed) {
        for (const command of REFRESH_VIEWS) {
          vscode.commands.executeCommand(command);
        }
        pages.refresh();
      }
      return changed;
    }),
    vscode.workspace.onDidSaveTextDocument(() => pages.refresh())
  );
  if (clientHolder.onVerdicts) {
    context.subscriptions.push(clientHolder.onVerdicts((notice) => pages.verdictsArrived(notice)));
  }
  return pages;
}

module.exports = { register, renderTypePage, verdictNote, showLoading, BUSY_SCRIPT, BUSY_CSS,
  LINK_CSS, LINK_SCRIPT, TypePages, typeOf, focusOf, focusIndex, escape,
  attributeRows, EDITS };
