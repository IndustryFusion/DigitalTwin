// What every end-to-end test needs: the running extension, its server, the
// rows of its trees, and a way to answer the questions it asks.

const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const WORKSPACE = process.env.SEMFORGE_E2E_WORKSPACE;
const PACKAGE_URI = vscode.Uri.file(path.join(WORKSPACE, 'shacl.ttl')).toString();

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
  const next = (kind, offered) => {
    asked.push({ kind, offered });
    const answer = queue.shift();
    if (answer && answer.kind && answer.kind !== kind) {
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
    let selection = [];
    Object.defineProperty(real, 'selectedItems', {
      configurable: true, get: () => selection, set: (items) => { selection = items; } });
    const shown = real.show.bind(real);
    real.show = () => {
      shown();
      const answer = next('quickPick', real.items.map((i) => i.label));
      setTimeout(() => {
        if (!answer) {
          real.hide();
          return;
        }
        if (answer.type !== undefined) {
          real.value = answer.type;     // fires onDidChangeValue
        }
        setTimeout(() => {
          const chosen = by(real.items, answer);
          if (!chosen) {
            real.hide();
            return;
          }
          real.activeItems = [chosen];
          selection = [chosen];
          accepted.forEach((handler) => handler());
        }, 200);
      }, 200);
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
  const named = new RegExp(`iffBaseShacl:${from.replace(/[-]/g, '\\-')}(?![\\w-])`, 'g');
  fs.writeFileSync(file, text.replace(named, `iffBaseShacl:${to}`));
  const done = await request(api, 'semforge/followRename',
    { shape: SHAPES + from, newIri: SHAPES + to, suite: Boolean(suite) });
  if (!done || !done.ok) {
    throw new Error(`restoring ${to}: ${JSON.stringify(done)}`);
  }
  return done;
}

module.exports = { WORKSPACE, PACKAGE_URI, until, semforge, request, rows, row, answering, read,
  restoreShapeName };
