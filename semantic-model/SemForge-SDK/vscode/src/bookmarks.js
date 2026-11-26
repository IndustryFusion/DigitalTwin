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
 * Pins: what one comes back to -- and where one has just been.
 *
 * A pin is WHAT something is (a shape's IRI, an entity's id and the case that
 * holds it), not where it is written: a line number is gone after the next
 * edit. Pins and the places visited last are one list, opened with a key: the
 * pinned, put there on purpose, first; the recent, kept by themselves, after
 * them. Both are this person's, in this workspace -- nothing is written into
 * the package.
 *
 * What a pin names may be gone: it stays in the list and says so, until it is
 * taken out. A rename done in SemForge takes its pin along.
 */

const path = require('path');
const vscode = require('vscode');

const { packageDirectory } = require('./locate');

const PINS = 'semforge.pins';
const RECENT = 'semforge.recent';
const RECENT_KEPT = 15;

const KINDS = {
  type: { icon: 'symbol-class', said: 'entity type' },
  attribute: { icon: 'symbol-field', said: 'attribute' },
  shape: { icon: 'symbol-interface', said: 'shape' },
  query: { icon: 'symbol-event', said: 'SPARQL query' },
  entity: { icon: 'symbol-object', said: 'entity' },
  case: { icon: 'beaker', said: 'test case' },
  model: { icon: 'symbol-namespace', said: 'main model' },
  vocabulary: { icon: 'symbol-enum', said: 'vocabulary' }
};

let memory;                       // the workspace's state, or a stand-in
let pages = {};

function read(key) {
  return (memory && memory.get(key, [])) || [];
}

function write(key, list) {
  return memory ? memory.update(key, list) : undefined;
}

/** Which thing it is, whatever it is called: the same key, the same pin. */
function keyOf(pin) {
  return JSON.stringify([packageDirectory(pin.packageUri) || pin.packageUri, pin.kind, pin.id,
    pin.names || [], pin.kind === 'entity' ? pin.file || '' : '']);
}

function isPinned(pin) {
  const key = keyOf(pin);
  return read(PINS).some((other) => keyOf(other) === key);
}

async function add(pin) {
  if (isPinned(pin)) {
    return false;
  }
  await write(PINS, read(PINS).concat([pin]));
  await mark();
  return true;
}

async function remove(pin) {
  const key = keyOf(pin);
  await write(PINS, read(PINS).filter((other) => keyOf(other) !== key));
  await mark();
}

async function toggle(pin) {
  if (isPinned(pin)) {
    await remove(pin);
    vscode.window.setStatusBarMessage(`SemForge: ${pin.label} is no longer pinned.`, 4000);
    return false;
  }
  await add(pin);
  vscode.window.setStatusBarMessage(`SemForge: ${pin.label} pinned — Ctrl+Alt+B lists what is.`, 5000);
  return true;
}

/** A page was shown: the newest place, once. */
async function visited(pin) {
  if (!pin) {
    return;
  }
  const key = keyOf(pin);
  await write(RECENT, [pin].concat(read(RECENT).filter((other) => keyOf(other) !== key))
    .slice(0, RECENT_KEPT));
  await mark();
}

const short = (iri) => String(iri || '').replace(/^<|>$/g, '').split(/[/#]/).filter(Boolean).pop() || '';

/** What the page `name` shows now, as a pin. */
function ofPage(name) {
  const view = pages[name];
  const current = view && view.current;
  const page = view && view.page;
  if (!current || !page) {
    return undefined;
  }
  const { packageUri } = current;
  if (name === 'type') {
    return { kind: 'type', id: page.iri, label: page.label, packageUri };
  }
  if (name === 'shape') {
    return { kind: 'shape', id: page.iri, label: page.label || short(page.iri), packageUri };
  }
  if (name === 'vocabulary') {
    return { kind: 'vocabulary', id: page.iri || current.cls, label: page.label, packageUri };
  }
  if (name === 'sparql') {
    // A shape may hold several queries: which one, by its kind and place.
    const holder = page.holder || {};
    return { kind: 'query', id: current.shape, names: [holder.kind || current.kind || 'constraint']
      .concat(holder.index !== undefined ? [String(holder.index)] : []),
    label: page.label || short(current.shape), packageUri };
  }
  return page.kind === 'model'
    ? { kind: 'model', id: 'main', label: 'Main model', packageUri }
    : { kind: 'case', id: page.file, label: page.name.replace(/\.jsonld$/, ''), where: page.suite, packageUri };
}

/** The page in front: the one whose panel is active. */
function activePage() {
  const name = Object.keys(pages).find((key) => pages[key] && pages[key].panel && pages[key].panel.active);
  return name ? ofPage(name) : undefined;
}

/** What a row of a view, or an id on a page, is -- as a pin. */
function ofNode(node, fallbackUri) {
  const said = node || {};
  const raw = said.raw || {};
  const packageUri = said.packageUri || fallbackUri;
  if (said.entity || raw.kind === 'entity' || ['usage', 'instance', 'violation'].includes(raw.kind)) {
    const id = said.entity || raw.entity;
    // An id on a test case's page is the entity of that case.
    const shown = said.webview === 'semforgeCasePage' && pages.case && pages.case.page;
    const file = said.file || raw.file || (shown && shown.kind !== 'model' ? shown.file : '') || '';
    return id && { kind: 'entity', id, label: id, file, where: file ? path.basename(file, '.jsonld') : '',
      packageUri: shown ? pages.case.current.packageUri : packageUri };
  }
  if (raw.kind === 'example' && raw.file) {
    return { kind: 'case', id: raw.file, label: path.basename(raw.file, '.jsonld'), packageUri };
  }
  if (raw.kind === 'example') {
    // A file of the main model: the Main page.
    return { kind: 'model', id: 'main', label: 'Main model', packageUri };
  }
  if (raw.kind === 'attribute' && raw.typeClass) {
    return { kind: 'attribute', id: raw.typeClass, names: [short(raw.path ? [].concat(raw.path).pop()
      : raw.label).split(':').pop()], label: raw.label, where: short(raw.typeClass), packageUri };
  }
  if (raw.kind === 'type' || raw.role === 'entityType') {
    const id = raw.targetClass || raw.iri;
    return id && { kind: 'type', id, label: raw.label || short(id), packageUri };
  }
  if (raw.kind === 'rule' && raw.shape) {
    return { kind: 'query', id: raw.shape, names: raw.queryKind ? [raw.queryKind] : [],
      label: raw.label || short(raw.shape), packageUri };
  }
  if (raw.shape) {
    return { kind: 'shape', id: raw.shape, label: raw.label || short(raw.shape), packageUri };
  }
  if (raw.kind === 'class' && raw.iri) {
    return { kind: 'vocabulary', id: raw.iri, label: raw.label || short(raw.iri), packageUri };
  }
  return undefined;
}

async function open(pin, clientHolder) {
  const run = (command, raw, options) =>
    vscode.commands.executeCommand(command, { raw, packageUri: pin.packageUri }, options);
  if (pin.kind === 'type') {
    return run('semforge.openTypePage', { targetClass: pin.id });
  }
  if (pin.kind === 'attribute') {
    return run('semforge.openTypePage', { targetClass: pin.id, focusNames: pin.names });
  }
  if (pin.kind === 'shape') {
    return run('semforge.openShapePage', { shape: pin.id });
  }
  if (pin.kind === 'query') {
    const [kind, index] = pin.names || [];
    return run('semforge.openSparqlBench', { shape: pin.id, label: pin.label },
      { kind, index: index === undefined ? undefined : Number(index) });
  }
  if (pin.kind === 'vocabulary') {
    return run('semforge.openVocabularyPage', { kind: 'class', iri: pin.id });
  }
  if (pin.kind === 'case') {
    return run('semforge.openCasePage', { kind: 'example', file: pin.id });
  }
  if (pin.kind === 'entity' && pin.file && clientHolder.client) {
    const found = await clientHolder.client.sendRequest('semforge/pageAt',
      { uri: vscode.Uri.file(pin.file).toString(), line: 1 });
    if (found.ok && found.page === 'case') {
      return run('semforge.openCasePage', { kind: 'example', file: found.file }, { focus: pin.id });
    }
  }
  return vscode.commands.executeCommand('semforge.openModelPage', { packageUri: pin.packageUri },
    pin.kind === 'entity' ? { focus: pin.id } : {});
}

/** {key: is it there?}, asked of the server per package. */
async function present(clientHolder, list) {
  const client = clientHolder.client;
  const there = {};
  const byPackage = new Map();
  list.forEach((pin) => byPackage.set(pin.packageUri, (byPackage.get(pin.packageUri) || []).concat([pin])));
  for (const [uri, mine] of byPackage) {
    let answer;
    try {
      answer = client && await client.sendRequest('semforge/pinsExist',
        { uri, pins: mine.map((pin) => ({ kind: pin.kind, id: pin.id, names: pin.names || [], file: pin.file || '' })) });
    } catch (error) {
      answer = undefined;
    }
    mine.forEach((pin, index) => {
      // Not answered: not known to be gone.
      there[keyOf(pin)] = !answer || (answer.ok ? answer.exist[index] : !answer.gone);
    });
  }
  return there;
}

/** The list: pinned first, then where one has been. Type to narrow it. */
async function list(clientHolder, session) {
  const here = packageDirectory(session.uri);
  const pinned = read(PINS);
  const keys = new Set(pinned.map(keyOf));
  const front = activePage();
  let recent = read(RECENT).filter((pin) => !keys.has(keyOf(pin)) &&
    !(front && keyOf(front) === keyOf(pin)));
  if (!pinned.length && !recent.length) {
    vscode.window.showInformationMessage('SemForge: nothing is pinned yet. Pin a page with the ☆ at the top ' +
      'right, or a row or an id with a right click.');
    return undefined;
  }
  const there = await present(clientHolder, pinned.concat(recent));
  // Pinned on purpose, a thing that is gone says so; visited, it is just gone.
  recent = recent.filter((pin) => there[keyOf(pin)] !== false);
  const removeButton = { iconPath: new vscode.ThemeIcon('trash'), tooltip: 'Take it out' };
  const pinButton = { iconPath: new vscode.ThemeIcon('star-empty'), tooltip: 'Pin it' };
  const item = (pin, isPin) => {
    const kind = KINDS[pin.kind] || KINDS.shape;
    const gone = there[keyOf(pin)] === false;
    const directory = packageDirectory(pin.packageUri);
    return { label: `$(${gone ? 'warning' : kind.icon}) ${pin.label}`,
      description: [kind.said, pin.where, directory && directory !== here ? path.basename(directory) : '',
        gone ? 'not found any more' : ''].filter(Boolean).join(' · '),
      pin, gone, buttons: [isPin ? removeButton : pinButton] };
  };
  return new Promise((resolve) => {
    const pick = vscode.window.createQuickPick();
    pick.title = 'Pinned and recent';
    pick.placeholder = 'Go to…';
    pick.matchOnDescription = true;
    const draw = () => {
      const now = read(PINS);
      const keyed = new Set(now.map(keyOf));
      const separator = (label) => ({ label, kind: vscode.QuickPickItemKind.Separator });
      const later = recent.filter((pin) => !keyed.has(keyOf(pin)));
      pick.items = (now.length ? [separator('pinned')].concat(now.map((pin) => item(pin, true))) : [])
        .concat(later.length ? [separator('recent')].concat(later.map((pin) => item(pin, false))) : []);
    };
    draw();
    let chosen;
    pick.onDidTriggerItemButton(async (event) => {
      await (event.button === removeButton ? remove(event.item.pin) : add(event.item.pin));
      draw();
    });
    pick.onDidAccept(() => {
      chosen = pick.selectedItems[0];
      pick.hide();
    });
    pick.onDidHide(async () => {
      pick.dispose();
      resolve(chosen && chosen.pin ? await go(chosen, clientHolder) : undefined);
    });
    pick.show();
  });
}

async function go(chosen, clientHolder) {
  if (chosen.gone) {
    const answer = await vscode.window.showWarningMessage(
      `SemForge: ${chosen.pin.label} is not in the package any more — renamed outside SemForge, or deleted.`,
      'Search for it', 'Take it out');
    if (answer === 'Take it out') {
      await remove(chosen.pin);
      await write(RECENT, read(RECENT).filter((pin) => keyOf(pin) !== keyOf(chosen.pin)));
    } else if (answer === 'Search for it') {
      await vscode.commands.executeCommand('semforge.showDetails');
      await require('./search').set(chosen.pin.label);
    }
    return undefined;
  }
  await open(chosen.pin, clientHolder);
  return chosen.pin;
}

/** A rename done in SemForge: what names the old one names the new one.
 *  `from` and `to` are IRIs or paths; a folder's rename moves what is in it. */
async function renamed(packageUri, from, to, label) {
  const directory = packageDirectory(packageUri) || packageUri;
  const moved = (name) => {
    const said = String(name || '');
    if (said === from) {
      return to;
    }
    return said.startsWith(`${from}${path.sep}`) ? to + said.slice(from.length) : undefined;
  };
  const follow = (pin) => {
    if ((packageDirectory(pin.packageUri) || pin.packageUri) !== directory || !from) {
      return pin;
    }
    const id = moved(pin.id);
    const file = pin.kind === 'entity' ? moved(pin.file) : undefined;
    if (id === undefined && file === undefined) {
      return pin;
    }
    const next = Object.assign({}, pin);
    if (id !== undefined) {
      next.id = id;
      // The name it was shown by, unless it has one of its own (a query's text).
      if (label && pin.id === from && (pin.kind !== 'query' || pin.label === short(from))) {
        next.label = label;
      } else if (pin.kind === 'case' && pin.id !== from) {
        next.label = path.basename(id, '.jsonld');
      }
    }
    if (file !== undefined) {
      next.file = file;
      next.where = path.basename(file, '.jsonld');
    }
    return next;
  };
  await write(PINS, read(PINS).map(follow));
  await write(RECENT, read(RECENT).map(follow));
}

/** The star of the page in front: filled when it is pinned. */
async function mark() {
  const front = activePage();
  await vscode.commands.executeCommand('setContext', 'semforge.pagePinned', !!front && isPinned(front));
}

function register(context, clientHolder, session, views) {
  memory = context.workspaceState && context.workspaceState.update ? context.workspaceState : standIn();
  pages = views;
  for (const name of Object.keys(views)) {
    const view = views[name];
    const show = view && view.show && view.show.bind(view);
    if (show) {
      view.show = async (...args) => {
        const before = view.page;
        const answer = await show(...args);
        // A page that did not render keeps the one before: that was not visited now.
        if (view.page && view.page !== before) {
          await visited(ofPage(name));
        }
        if (view.panel && view.panel.onDidChangeViewState && view.marked !== view.panel) {
          view.marked = view.panel;
          view.panel.onDidChangeViewState(() => mark());
        }
        return answer;
      };
    }
  }
  const pinNode = async (node) => {
    const pin = node ? ofNode(node, session.uri) : activePage();
    if (!pin) {
      vscode.window.showInformationMessage('SemForge: open a page, or right-click a row or an id, to pin it.');
      return undefined;
    }
    return toggle(pin);
  };
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.bookmarks', () => list(clientHolder, session)),
    vscode.commands.registerCommand('semforge.pin', pinNode),
    // The same on a page's title bar, where the arguments are the editor's.
    vscode.commands.registerCommand('semforge.pinPage', () => pinNode()),
    vscode.commands.registerCommand('semforge.unpinPage', () => pinNode()));
}

function standIn() {
  const kept = {};
  return { get: (key, otherwise) => (key in kept ? kept[key] : otherwise),
    update: async (key, value) => { kept[key] = value; } };
}

module.exports = { register, toggle, renamed, isPinned, ofNode, keyOf, read, PINS, RECENT };
