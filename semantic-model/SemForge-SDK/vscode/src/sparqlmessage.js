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
 * The message of a SPARQL constraint, edited on the workbench page: a text
 * field, the variables the query selects as chips, a preview filled from a
 * row of the last run, and what the server says is wrong in it.
 *
 * `fillPieces` and `messageClient` run in the page: they are put into its
 * script as they are written here (`toString`), so they use nothing but their
 * arguments and the document.
 */

const { escape } = require('./typepage');

const MESSAGE_CSS = `
  .message { margin: 2px 0 6px; }
  .message .text { margin-right: 8px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .message button { padding: 0 8px; }
  #messageeditor { margin: 6px 0; padding: 8px 10px; border-radius: 3px;
                   border: 1px solid var(--vscode-panel-border, rgba(128,128,128,.35)); }
  #messageeditor textarea { width: 100%; box-sizing: border-box; font: inherit; resize: vertical;
                   padding: 4px 6px; color: var(--vscode-input-foreground);
                   background: var(--vscode-input-background);
                   border: 1px solid var(--vscode-input-border, rgba(128,128,128,.35)); }
  #messageeditor .bar { margin-top: 6px; }
  #messagevars button { font-family: var(--vscode-editor-font-family); border-radius: 999px; }
  #messagevars button.other { opacity: .4; }
  #messagevars button.first { border-color: var(--vscode-focusBorder, #0078d4); }
  #messagepreview { margin-top: 6px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .unfilled { color: var(--vscode-editorWarning-foreground, #cca700); text-decoration: underline dotted; }
`;

/** The parts of a message filled from a row: [{text, unfilled}] -- the same
 *  rule as semforge/sparql/message.py `fill`. */
function fillPieces(template, row) {
  const pieces = [];
  const pattern = /\{([?$])([\p{L}\p{N}_]+)\}/gu;
  let from = 0;
  for (const match of String(template || '').matchAll(pattern)) {
    if (match.index > from) {
      pieces.push({ text: template.slice(from, match.index), unfilled: false });
    }
    const known = Object.prototype.hasOwnProperty.call(row || {}, match[2]);
    pieces.push({ text: known ? String(row[match[2]]) : match[0], unfilled: !known });
    from = match.index + match[0].length;
  }
  if (from < String(template || '').length) {
    pieces.push({ text: template.slice(from), unfilled: false });
  }
  return pieces;
}

/** The message's part of the page, under its head. '' for a rule. */
function renderMessageBox(page) {
  const holder = page.holder;
  if (holder.kind !== 'constraint') {
    return '';
  }
  const text = holder.message
    ? `<span class="text" title="sh:message — {?var} is filled from each row">“${escape(holder.message)}”</span>`
    : '<span class="text dim">no sh:message</span>';
  const edit = holder.messageLocked
    ? `<a tabindex="0" role="link" data-open="${escape(`${holder.file}:${holder.line}`)}">Show in .ttl</a>` +
      `<div class="warning">${escape(holder.messageLocked)}</div>`
    : `<button id="messageedit" title="sh:message: what a violation means">${holder.message
      ? 'Edit message' : '+ Message'}</button>`;
  return `<div class="message"><div id="messageview">${text}${edit}</div>
<div id="messageeditor" hidden>
  <textarea id="messagetext" rows="2" spellcheck="true" aria-label="The message of a violation"></textarea>
  <div class="bar" id="messagevars"></div>
  <div id="messagepreview"></div>
  <div id="messagechanged" class="warning" hidden></div>
  <div class="bar"><button class="primary" id="messagesave">Save message</button>
    <button id="messagecancel">Cancel</button>
    <span class="dim">Enter saves · Shift+Enter: a new line · Esc cancels</span></div>
</div>
<div id="messagewarnings"></div></div>`;
}

/** The message editor's own script. Returns {ran, received}: what the page
 *  hands it of a run and of the extension's messages. */
function messageClient(state, vscode, kept, esc, pieces) {
  const at = (id) => document.getElementById(id);
  const field = at('messagetext');
  const open = at('messageedit');
  let known = (state.messageCheck || {}).variables || [];
  let warnings = (state.messageCheck || {}).warnings || [];
  let row;                 // a violating row of the last run, and whose it is
  let node = '';
  let timer;
  let saving = false;

  function keep() {
    kept.message = { shape: state.shape, index: state.index, text: field.value,
      expected: at('messageeditor').dataset.expected };
    vscode.setState(kept);
  }
  function forget() {
    delete kept.message;
    vscode.setState(kept);
  }
  function warn() {
    at('messagewarnings').innerHTML = warnings.map((w) =>
      '<div class="warning">' + esc(w) + '</div>').join('');
  }
  /** The `{?pre` the cursor stands in: [from, pre], or undefined. */
  function typing() {
    const before = field.value.slice(0, field.selectionStart);
    const found = /\{[?$]([\p{L}\p{N}_]*)$/u.exec(before);
    return found ? [found.index, found[1]] : undefined;
  }
  function chips() {
    const now = typing();
    const fits = now ? known.filter((name) => name.startsWith(now[1])) : [];
    at('messagevars').innerHTML = '<span class="dim">Insert</span>' + (known.length
      ? known.map((name) => '<button type="button" data-var="' + esc(name) + '" class="' +
        (!now ? '' : name === fits[0] ? 'first' : fits.includes(name) ? '' : 'other') +
        '" title="Insert {?' + esc(name) + '}">' + esc(name === 'this' ? '$this' : '?' + name) +
        '</button>').join('') +
        (fits.length ? '<span class="dim">Tab inserts ' + esc('{?' + fits[0] + '}') + '</span>' : '')
      : '<span class="dim">the query selects nothing that can be read</span>');
    return fits;
  }
  function preview() {
    const shown = pieces(field.value, row).map((p) => p.unfilled
      ? '<span class="unfilled" title="stays as text: the row has no such value">' + esc(p.text) +
        '</span>' : esc(p.text)).join('');
    at('messagepreview').innerHTML = (row
      ? '<span class="dim">Preview · ' + esc(node) + ':</span> '
      : '<span class="dim">Preview · no row of this run violates: choose a case under Run over ' +
        'that does, to see the variables filled:</span> ') + shown;
  }
  function refresh() {
    chips();
    preview();
    clearTimeout(timer);
    timer = setTimeout(() =>
      vscode.postMessage({ command: 'checkMessage', message: field.value }), 250);
  }
  function edited() {
    at('messagechanged').hidden = true;
    keep();
    refresh();
  }
  function insert(name) {
    const now = typing();
    const from = now ? now[0] : field.selectionStart;
    let to = field.selectionEnd;
    const rest = now ? /^[\p{L}\p{N}_]*\}/u.exec(field.value.slice(to)) : null;
    if (rest) { to += rest[0].length; }
    field.setRangeText('{?' + name + '}', from, to, 'end');
    field.focus();
    edited();
  }
  function edit(text, expected) {
    at('messageview').hidden = true;
    at('messageeditor').hidden = false;
    at('messageeditor').dataset.expected = expected;
    field.value = text;
    if (expected !== state.message) {
      at('messagechanged').textContent = 'The message changed in the file meanwhile: “' +
        state.message + '”. Cancel to see it.';
      at('messagechanged').hidden = false;
    }
    refresh();
    field.focus();
    field.setSelectionRange(text.length, text.length);
  }
  function close() {
    clearTimeout(timer);
    forget();
    at('messageview').hidden = false;
    at('messageeditor').hidden = true;
    warnings = (state.messageCheck || {}).warnings || [];
    warn();
  }
  function save() {
    const expected = at('messageeditor').dataset.expected;
    if (saving) { return; }
    if (field.value === state.message && expected === state.message) {
      close();
      return;
    }
    saving = true;
    clearTimeout(timer);
    at('messagesave').disabled = true;
    forget();                // saved, the page is drawn anew: nothing to restore
    vscode.postMessage({ command: 'saveMessage', message: field.value, expected });
  }

  if (open) {
    open.addEventListener('click', () => edit(state.message, state.message));
    at('messagecancel').addEventListener('click', close);
    at('messagesave').addEventListener('click', save);
    field.addEventListener('input', edited);
    for (const event of ['click', 'keyup']) {
      field.addEventListener(event, chips);
    }
    field.addEventListener('keydown', (event) => {
      if (event.isComposing) { return; }
      const fits = event.key === 'Tab' && !event.shiftKey ? chips() : [];
      if (fits.length) {
        event.preventDefault();
        insert(fits[0]);
      } else if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        save();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        close();
        open.focus();
      }
    });
    at('messagevars').addEventListener('click', (event) => {
      const chosen = event.target.closest('[data-var]');
      if (chosen) { insert(chosen.dataset.var); }
    });
    // A draft outlives a redraw of the page (a save elsewhere).
    const draft = kept.message;
    if (draft && draft.shape === state.shape && draft.index === state.index) {
      edit(draft.text, draft.expected);
    } else if (state.editMessage) {
      edit(state.message, state.message);
    }
  }
  if (at('messagewarnings')) { warn(); }

  return {
    ran(result) {
      if (!at('messagewarnings')) { return; }
      const hit = result.ok && result.kind !== 'rule'
        ? (result.focus || []).find((f) => f.rows && f.rows.length) : undefined;
      row = hit && hit.rows[0];
      node = hit ? hit.node : '';
      if (result.message) {
        state.messageCheck = result.message;
        known = result.message.variables || known;
      }
      if (at('messageeditor').hidden) {
        warnings = (state.messageCheck || {}).warnings || [];
        warn();
      } else {
        refresh();
      }
    },
    received(message) {
      if (message.type === 'messageCheck' && !at('messageeditor').hidden &&
          message.message === field.value) {
        known = message.variables || known;
        warnings = message.warnings || [];
        warn();
        chips();
      } else if (message.type === 'messageError') {
        saving = false;
        at('messagesave').disabled = false;
        keep();
        if (message.text) {
          warnings = [message.text];
          warn();
        }
      }
    }
  };
}

module.exports = { MESSAGE_CSS, fillPieces, messageClient, renderMessageBox };
