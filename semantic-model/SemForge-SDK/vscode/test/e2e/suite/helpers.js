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

// What every end-to-end test needs: the running extension, its server, the
// rows of its trees, and a way to answer the questions it asks.

const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const WORKSPACE = process.env.SEMFORGE_E2E_WORKSPACE;
const PACKAGE_URI = vscode.Uri.file(path.join(WORKSPACE, 'shacl.ttl')).toString();
// The OPC UA pump slice, copied beside the workspace (run.js).
const OPCUA = process.env.SEMFORGE_E2E_OPCUA;
const OPCUA_URI = OPCUA ? vscode.Uri.file(path.join(OPCUA, 'shacl.ttl')).toString() : undefined;

async function until(check, what, timeout = 45000) {
  const started = Date.now();
  let last;
  while (Date.now() - started < timeout) {
    try {
      const value = await check();
      if (value) {
        return value;
      }
    } catch (error) {
      last = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`timed out waiting for ${what}${last ? `: ${last.message}` : ''}`);
}

let cached;
/** The activated extension's handle, once its language server answers. */
async function semforge() {
  if (cached) {
    return cached;
  }
  const extension = vscode.extensions.getExtension('industryfusion.semforge');
  const api = await extension.activate();
  await until(async () => {
    const client = api.clientHolder.client;
    return client && (await client.sendRequest('semforge/methods', {})).methods;
  }, 'the language server');
  await until(() => api.session.uri, 'the package to be found');
  // The suites drive every tree, so the details column is open for them.
  await vscode.commands.executeCommand('semforge.showDetails');
  // Every click a suite makes on a page waits until the page has settled
  // after what came before (#1197): a picker opened while it settled could
  // close by itself on a slow machine.
  for (const [name, page] of Object.entries(api.pages)) {
    if (name !== 'attribute') {
      settledFirst(page, name);
    }
  }
  const current = Object.getOwnPropertyDescriptor(api.pages, 'attribute');
  if (current && current.get) {
    Object.defineProperty(api.pages, 'attribute', { configurable: true,
      get: () => settledFirst(current.get.call(api.pages), 'attribute') });
  }
  cached = api;
  return api;
}

function request(api, method, params) {
  return api.clientHolder.client.sendRequest(method, Object.assign({ uri: PACKAGE_URI }, params));
}

/** Every row of a tree, depth-first, each with its parent chain resolved. */
async function rows(provider, depth = 6) {
  const out = [];
  const walk = async (parent, level) => {
    if (level > depth) {
      return;
    }
    for (const child of (await provider.getChildren(parent)) || []) {
      out.push(child);
      await walk(child, level + 1);
    }
  };
  await walk(undefined, 0);
  return out;
}

async function row(provider, predicate, what) {
  return until(async () => (await rows(provider)).find((node) => predicate(node.raw)),
    what || 'a tree row');
}

/**
 * Answer the questions the extension asks -- input boxes, quick picks, the
 * quick pick it drives itself, information messages -- the way a person
 * would, by label. `answers` is consumed in order. The extension and these
 * tests share one `vscode` module object, so replacing its window functions
 * is what the extension calls.
 */
function answering(answers) {
  const window = vscode.window;
  const saved = {};
  const queue = answers.slice();
  const asked = [];
  // `also`: other kinds that answer the same question -- a list picker drawn
  // with createQuickPick only to highlight its default is still a pick.
  const next = (kind, offered, also) => {
    asked.push({ kind, offered });
    const answer = queue.shift();
    if (answer && answer.kind && answer.kind !== kind && !(also || []).includes(answer.kind)) {
      throw new Error(`asked a ${kind}, the test expected a ${answer.kind}: ${JSON.stringify(offered)}`);
    }
    return answer;
  };
  const by = (items, answer) => (answer.choose
    ? answer.choose(items.filter((item) => item.kind !== vscode.QuickPickItemKind.Separator))
    : items.find((item) => item.label === answer.label ||
      (answer.labelStarts && String(item.label).startsWith(answer.labelStarts))));

  const replace = (name, fn) => {
    saved[name] = window[name];
    window[name] = fn;
  };
  replace('showInputBox', async (options) => {
    const answer = next('input', (options || {}).title);
    return answer ? answer.value : undefined;
  });
  replace('showQuickPick', async (items) => {
    const resolved = await items;
    const answer = next('pick', resolved.map((i) => i.label));
    return answer ? by(resolved, answer) : undefined;
  });
  replace('showInformationMessage', async (message, ...rest) => {
    const buttons = rest.filter((item) => typeof item === 'string');
    if (!buttons.length) {
      return undefined;                 // a plain notice asks nothing
    }
    const answer = next('message', { message, buttons });
    return answer ? answer.button : undefined;
  });
  // A modal question ("unsaved edits — discard them?"): a test VS Code
  // refuses to show one, so it is answered here when the test expects it.
  replace('showWarningMessage', async (message, ...rest) => {
    const buttons = rest.filter((item) => typeof item === 'string');
    if (!buttons.length || !queue.length || queue[0].kind !== 'warning') {
      return saved.showWarningMessage(message, ...rest);
    }
    const answer = next('warning', { message, buttons });
    return answer.button;
  });
  replace('createQuickPick', () => {
    const real = saved.createQuickPick();
    // Accepting is a person pressing Enter on THEIR item; the workbench's
    // accept command takes whichever row is highlighted, which is the first.
    // So the item is made the selection and the extension's own accept
    // handlers run with it.
    const accepted = [];
    const subscribe = real.onDidAccept.bind(real);
    real.onDidAccept = (handler, thisArg, disposables) => {
      accepted.push(thisArg ? handler.bind(thisArg) : handler);
      return subscribe(handler, thisArg, disposables);
    };
    // When the picker was closed, and by whom: said in `asked` if it was
    // before the answer was given (the workbench closes one that loses focus).
    let closed;
    let closing = false;
    real.onDidHide(() => {
      closed = closed || (closing ? 'by the answer' : `by the workbench at ${Date.now() - opened} ms`);
    });
    let opened = Date.now();
    let selection = [];
    Object.defineProperty(real, 'selectedItems', {
      configurable: true, get: () => selection, set: (items) => { selection = items; } });
    const shown = real.show.bind(real);
    real.show = () => {
      shown();
      opened = Date.now();
      const answer = next('quickPick', real.items.map((i) => i.label), ['pick']);
      const record = asked[asked.length - 1];
      // `enter: true` is a person pressing Enter on what the picker itself
      // highlights -- its default, which need not be the first row.
      const highlighted = (real.activeItems || [])[0];
      setTimeout(() => {
        if (!answer) {
          real.hide();
          return;
        }
        if (answer.type !== undefined) {
          real.value = answer.type;     // fires onDidChangeValue
        }
        // What was typed may bring the row to pick only when the picker has
        // answered it (a server request): waited for, as a person waits for
        // the list to show it -- a fixed pause missed it on a slow machine.
        const pick = (tries) => {
          const chosen = answer.enter ? highlighted : by(real.items, answer);
          if (!chosen && tries > 0) {
            setTimeout(() => pick(tries - 1), 100);
            return;
          }
          if (closed) {
            record.closed = closed;        // before the answer: said, for the test's message
          }
          if (!chosen) {
            record.found = false;
            closing = true;
            real.hide();
            return;
          }
          real.activeItems = [chosen];
          selection = [chosen];
          closing = true;
          accepted.forEach((handler) => handler());
        };
        setTimeout(() => pick(answer.type !== undefined ? 150 : 0), 200);
      }, (answer && answer.after) || 200);    // `after`: answered only then (ms)
    };
    return real;
  });
  return {
    asked,
    restore: () => Object.assign(window, saved),
    left: () => queue.length
  };
}

function read(relative) {
  return fs.readFileSync(path.join(WORKSPACE, relative), 'utf-8');
}

const SHAPES = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/';

/** `text` matched literally inside a RegExp: every metacharacter escaped. */
function escapeRegExp(text) {
  return text.replace(/[\\^$.*+?()[\]{}|/-]/g, '\\$&');
}

/**
 * Give a shape back its original name, by hand: Rename… keeps a shape's random
 * part (FilterShape-3f9a1c2e) and can never return it to a bare name -- but the
 * suites after a rename test expect the corpus as it was. So the name is
 * written back into shacl.ttl as a person would, and followRename carries the
 * asserts, residues and (asked) the suite folder along.
 */
async function restoreShapeName(api, from, to, suite) {
  const file = path.join(WORKSPACE, 'shacl.ttl');
  const text = fs.readFileSync(file, 'utf-8');
  const named = new RegExp(`iffBaseShacl:${escapeRegExp(from)}(?![\\w-])`, 'g');
  fs.writeFileSync(file, text.replace(named, `iffBaseShacl:${to}`));
  const done = await request(api, 'semforge/followRename',
    { shape: SHAPES + from, newIri: SHAPES + to, suite: Boolean(suite) });
  if (!done || !done.ok) {
    throw new Error(`restoring ${to}: ${JSON.stringify(done)}`);
  }
  return done;
}

/**
 * A page done with what came before: its verdicts in, no click of its own
 * being handled, no refresh waiting. What a person acts on -- a picker opened
 * while the page was still settling after an edit could close by itself
 * (measured 4 of 20 without this wait, 0 of 20 with it).
 */
async function pageSettled(pages, what = 'the page') {
  const verdicts = () => pages.page && pages.page.verdicts;
  const settled = () => !pages.busy && !pages.refreshPending &&
    (!verdicts() || ['ready', 'failed'].includes(verdicts().state));
  await until(settled, `${what} settled`).catch(() => {
    throw new Error(`${what} did not settle: verdicts ${verdicts() && verdicts().state}, ` +
      `busy ${pages.busy}, refresh pending ${pages.refreshPending}`);
  });
  return pages.page;
}

// What a page tells the extension about itself, not something a person does.
const NOTICES = new Set(['editing', 'landed', 'idle']);

/** A page's clicks wait until it has settled, as a person acts on a finished page. */
function settledFirst(page, name) {
  if (!page || typeof page.receive !== 'function' || page.semforgeSettledFirst) {
    return page;
  }
  // The page's own code calls receive() too, also from inside a message it is
  // handling: such a call goes straight through -- waiting for the page to be
  // idle there would wait on itself.
  if (typeof page.handle === 'function') {
    const handle = page.handle.bind(page);
    page.handle = async (message) => {
      page.semforgeHandling = (page.semforgeHandling || 0) + 1;
      try {
        return await handle(message);
      } finally {
        page.semforgeHandling -= 1;
      }
    };
  }
  const receive = page.receive.bind(page);
  page.receive = async (message) => {
    if (!page.semforgeHandling && !(message && NOTICES.has(message.command))) {
      await pageSettled(page, `the ${name} page`);
    }
    return receive(message);
  };
  page.semforgeSettledFirst = true;
  return page;
}

module.exports = { WORKSPACE, PACKAGE_URI, OPCUA, OPCUA_URI, until, semforge, request, rows, row,
  answering, read, restoreShapeName, pageSettled };
