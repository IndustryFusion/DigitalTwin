/*
 * Drive one command handler, or one tree provider, against a stub `vscode`.
 *
 * The activation harness proves the extension LOADS and registers its commands.
 * It could not see what a command DOES -- and that is where the failures have
 * been: an icon that sent the parent attribute's name, a tree that turned a
 * server error into an empty panel, a reveal that could not resolve its own
 * node after a refresh. None of those throw, and none of them log.
 *
 * Usage: node drive.js <workspace folder> <extension.js|src dir> <scenario.json>
 * Prints one JSON line describing what happened.
 */
const Module = require('module');
const path = require('path');
const original = Module._load;

const scenario = require(path.resolve(process.argv[4]));
const seen = {
  commands: [],
  requests: [],
  shown: [],
  quickPicks: [],
  inputs: [],
  info: [],
  warnings: [],
  errors: [],
  revealed: [],
  messages: [],
  statusBar: [],
  deleted: [],
  webviews: [],
  executed: [],
  // Each view's own state -- its subtitle says which package it is showing,
  // and its message is what an empty panel tells you instead of nothing.
  views: {},
  // In order, because the order is the bug: VS Code drops its element handles
  // when a tree fires onDidChangeTreeData, so a reveal after a refresh resolves
  // nothing and logs "Failed to resolve tree node".
  events: []
};

const noop = () => undefined;
const registry = new Map();
const selections = [];
const providers = {};
// Documents of a file system an extension registers (the SPARQL workbench's
// semforge-sparql: queries): opened through its provider, edited in memory,
// saved through it -- so a test sees what a save sent and what it refused.
const fileSystems = {};
const documents = [];
const changeListeners = [];
const saveListeners = [];

function lineAt(text, offset) {
  const before = text.slice(0, offset);
  const line = before.split('\n').length - 1;
  return { line, character: offset - (before.lastIndexOf('\n') + 1) };
}

async function openDocument(uri) {
  const key = uri.toString();
  const known = documents.find((d) => d.uri.toString() === key);
  if (known) {
    return known;
  }
  const content = await fileSystems[uri.scheme].readFile(uri);
  const doc = {
    uri, text: Buffer.from(content).toString('utf-8'), isDirty: false,
    getText() { return this.text; },
    positionAt(offset) {
      const at = lineAt(this.text, offset);
      return new stub.Position(at.line, at.character);
    },
    get lineCount() { return this.text.split('\n').length; },
    async save() {
      try {
        await fileSystems[uri.scheme].writeFile(uri, Buffer.from(this.text, 'utf-8'),
          { create: false, overwrite: true });
      } catch (error) {
        seen.saveErrors = (seen.saveErrors || []).concat([error.message]);
        return false;
      }
      this.isDirty = false;
      seen.events.push({ type: 'saved', uri: key });
      saveListeners.forEach((listener) => listener(this));
      return true;
    }
  };
  documents.push(doc);
  return doc;
}
// VS Code fires this when a document is shown, and the trees listen to it. The
// harness used to model it as a no-op, which hid a refresh landing in the middle
// of a reveal.
const editorListeners = [];

const stub = {
  workspace: {
    getConfiguration: () => ({ get: (key) => (scenario.config || {})[key] || '' }),
    workspaceFolders: [{ uri: { fsPath: process.argv[2] } }],
    createFileSystemWatcher: () => ({ dispose: noop }),
    onDidChangeConfiguration: noop,
    onDidSaveTextDocument: (listener) => {
      saveListeners.push(listener);
      return { dispose: noop };
    },
    onDidChangeTextDocument: (listener) => {
      changeListeners.push(listener);
      return { dispose: noop };
    },
    registerFileSystemProvider: (scheme, provider) => {
      fileSystems[scheme] = provider;
      return { dispose: noop };
    },
    get textDocuments() { return documents; },
    applyEdit: (edit) => {
      for (const change of edit.changes) {
        const doc = documents.find((d) => d.uri.toString() === change.uri.toString());
        if (doc) {
          doc.text = change.text;              // a whole-text replace is all the workbench does
          doc.isDirty = true;
          seen.events.push({ type: 'edited', uri: change.uri.toString() });
          changeListeners.forEach((listener) => listener({ document: doc }));
        }
      }
      return Promise.resolve(true);
    },
    // Recorded AND performed, but only inside the workspace the test built --
    // which is a pytest tmp_path. Recording alone was not enough: what happens
    // after a deletion is that the package is gone, and a stub that leaves it
    // on disk cannot show the views noticing.
    fs: {
      delete: (uri, options) => {
        seen.deleted.push({ path: uri.fsPath, options: options || {} });
        const root = path.resolve(process.argv[2]);
        const target = path.resolve(uri.fsPath);
        if (target !== root && target.startsWith(root + path.sep)) {
          require('fs').rmSync(target, { recursive: true, force: true });
        }
        return Promise.resolve();
      }
    },
    // A real document's uri answers both fsPath and toString; the trees use
    // one to filter and the other to compare packages, so a stub with only
    // fsPath made every opened file look like a different package.
    openTextDocument: (file) => (file && file.scheme && fileSystems[file.scheme]
      ? openDocument(file)
      : Promise.resolve({ uri: stub.Uri.file(file), lineCount: 10000,
        save() {
          seen.events.push({ type: 'saved', uri: `file://${file}` });
          return Promise.resolve(true);
        } }))
  },
  window: {
    // The provider is kept aside, not on the view: `seen` is printed as JSON.
    createTreeView: (id, options) => (providers[id] = (options || {}).treeDataProvider,
                                      seen.views[id] = {
      dispose: noop,
      reveal: (node, options) => {
        seen.events.push({ type: 'reveal', view: id, key: node.key });
        return Promise.resolve(seen.revealed.push({
          view: id, key: node.key, options: options || {} }));
      },
      onDidChangeSelection: (handler) => {
        selections.push({ view: id, handler });
        return { dispose: noop };
      }
    }),
    onDidChangeActiveTextEditor: (handler) => {
      editorListeners.push(handler);
      return { dispose: noop };
    },
    activeTextEditor: undefined,
    showTextDocument: (document, options) => {
      const editor = {
        document,
        selection: undefined,
        revealRange: (range) => {
          seen.events.push({ type: 'shown', file: document.uri.fsPath });
          return seen.shown.push({
            file: document.uri.fsPath,
            line: range && range.start && range.start.line,
            preserveFocus: !!(options || {}).preserveFocus });
        }
      };
      stub.window.activeTextEditor = editor;
      for (const listener of editorListeners) {
        listener(editor);               // as VS Code does, synchronously
      }
      return Promise.resolve(editor);
    },
    showQuickPick: (items, options) => {
      const offered = (items || []).map((item) => ({
        label: item.label, description: item.description,
        detail: item.detail, value: item.value, picked: !!item.picked
      }));
      seen.quickPicks.push({ items: offered,
                             placeHolder: (options || {}).placeHolder });
      // A flow can ask more than once -- pick a type, then pick its parent --
      // and answering both with one value cannot drive it. `picks` is consumed
      // in order; `pick` still answers every prompt, which most scenarios want.
      const answer = Array.isArray(scenario.picks)
        ? scenario.picks[seen.quickPicks.length - 1]
        : scenario.pick;
      if (answer === undefined) {
        return Promise.resolve(undefined);
      }
      // A multi-select is answered with a list of labels.
      if ((options || {}).canPickMany && Array.isArray(answer)) {
        return Promise.resolve(items.filter((item) => answer.includes(item.label)));
      }
      const chosen = typeof answer === 'number'
        ? items[answer]
        : items.find((item) => item.label === answer);
      return Promise.resolve(chosen);
    },
    // A quick pick the code drives itself. `typed` is what is typed into its
    // box first (consumed in order when a list); then `pick`/`picks` choose
    // as for showQuickPick -- by index, or by label. An accept the code
    // refuses leaves it open: that is recorded, and it is then dismissed.
    createQuickPick: () => {
      const handlers = { value: [], accept: [], hide: [] };
      let closed = false;
      const on = (list) => (handler) => {
        list.push(handler);
        return { dispose: noop };
      };
      const pick = {
        items: [], value: '', selectedItems: [], activeItems: [],
        onDidChangeValue: on(handlers.value),
        onDidAccept: on(handlers.accept),
        onDidHide: on(handlers.hide),
        dispose: noop,
        hide: () => {
          if (!closed) {
            closed = true;
            handlers.hide.forEach((handler) => handler());
          }
        },
        show: () => {
          const position = seen.quickPicks.length;
          const typed = Array.isArray(scenario.typed) ? scenario.typed[position]
            : scenario.typed;
          setTimeout(async () => {
            if (typed !== undefined) {
              pick.value = typed;
              handlers.value.forEach((handler) => handler(typed));
            }
            seen.quickPicks.push({
              items: pick.items.map((item) => ({
                label: item.label, description: item.description, detail: item.detail,
                value: item.value, separator: item.kind === -1 })),
              placeHolder: pick.placeholder, typed });
            const answer = Array.isArray(scenario.picks)
              ? scenario.picks[seen.quickPicks.length - 1] : scenario.pick;
            const chosen = typeof answer === 'number' ? pick.items[answer]
              : pick.items.find((item) => item.label === answer);
            if (!chosen) {
              pick.hide();
              return;
            }
            pick.selectedItems = [chosen];
            pick.activeItems = [chosen];
            for (const handler of handlers.accept) {
              await handler();
            }
            if (!closed) {
              seen.events.push({ type: 'quickPickStayedOpen', label: chosen.label });
              pick.hide();
            }
          }, 0);
        }
      };
      return pick;
    },
    showInputBox: (options) => {
      seen.inputs.push({ title: (options || {}).title,
                         prompt: (options || {}).prompt,
                         value: (options || {}).value });
      const answer = Array.isArray(scenario.inputs)
        ? scenario.inputs[seen.inputs.length - 1]
        : scenario.input;
      return Promise.resolve(answer);
    },
    showInformationMessage: (message, ...rest) => {
      seen.info.push(message);
      return Promise.resolve(scenario.answer);
    },
    showWarningMessage: (message, options) => {
      // A modal's `detail` is where the reasoning goes -- "it is in use, and
      // removing it is safe anyway because ..." -- so a test that can only see
      // the title cannot check what the person was actually told.
      const detail = (options || {}).detail;
      seen.warnings.push(detail ? `${message}\n${detail}` : message);
      // A warning can be a question too -- "Edit anyway" lives on one -- so it
      // answers with `answer` like the information messages. Without this a
      // confirmation flow could only ever be declined in a test.
      return Promise.resolve(scenario.answer);
    },
    showErrorMessage: (message) => {
      seen.errors.push(message);
      return Promise.resolve(undefined);
    },
    createOutputChannel: () => ({ appendLine: noop, show: noop }),
    setStatusBarMessage: (message) => seen.messages.push(message),
    withProgress: (options, task) => task({ report: noop }),
    // A webview panel that records what it was given: its title, every HTML
    // it was set to, and a way for the scenario to "click" in it by posting
    // the messages the page's script would post.
    createWebviewPanel: (viewType, title, column, options) => {
      // `posted`: what the extension sent INTO the page (results that must
      // not re-render it, so the editor keeps its text).
      const record = { viewType, title, column, options, html: [], receivers: [], posted: [] };
      seen.webviews.push(record);
      const panel = {
        visible: true,
        get title() { return record.title; },
        set title(value) { record.title = value; },
        reveal: () => { record.revealed = (record.revealed || 0) + 1; },
        onDidDispose: noop,
        webview: {
          set html(value) { record.html.push(value); },
          get html() { return record.html[record.html.length - 1]; },
          onDidReceiveMessage: (fn) => record.receivers.push(fn),
          postMessage: (message) => Promise.resolve(record.posted.push(message)),
          cspSource: 'vscode-resource:'
        }
      };
      return panel;
    },
    // The status bar is where "which package am I on" is answered, so a test
    // has to be able to read it.
    createStatusBarItem: () => {
      const item = { text: '', tooltip: '', command: undefined,
                     show: () => seen.statusBar.push(item.text),
                     hide: noop, dispose: noop };
      seen.statusBarItem = item;
      return item;
    }
  },
  commands: {
    registerCommand: (id, handler) => {
      seen.commands.push(id);
      registry.set(id, handler);
      return { dispose: noop };
    },
    // Recorded, not run: a command that hands work to another one is tested
    // by what it asked for. Running it too would need that command's replies.
    executeCommand: (command, ...args) => {
      seen.executed.push({ command, args });
      // `commandResults` answers for a command another one chains on (a
      // shape created first, then filled).
      return Promise.resolve((scenario.commandResults || {})[command]);
    }
  },
  EventEmitter: class {
    // Subscribing used to be a no-op, so nothing an emitter fired ever
    // arrived. That is fine for a tree's own onDidChangeTreeData, which VS
    // Code consumes -- and wrong for the package session, whose whole job is
    // to tell the three views that the package changed.
    constructor() {
      this.listeners = [];
      this.event = (listener) => {
        this.listeners.push(listener);
        return { dispose: noop };
      };
    }

    fire(value) {
      seen.events.push({ type: 'refresh' });
      for (const listener of this.listeners.slice()) {
        listener(value);
      }
    }
  },
  ThemeIcon: class { constructor(i, c) { this.id = i; this.color = c; } },
  ThemeColor: class { constructor(i) { this.id = i; } },
  QuickPickItemKind: { Separator: -1, Default: 0 },
  ViewColumn: { Active: -1, Beside: -2, One: 1 },
  ProgressLocation: { SourceControl: 1, Window: 10, Notification: 15 },
  TreeItem: class { constructor(l, c) { this.label = l; this.collapsibleState = c; } },
  TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 },
  Position: class { constructor(line, character) { this.line = line; this.character = character; } },
  Selection: class { constructor(a) { this.start = a; } },
  Range: class { constructor(a, b) { this.start = a; this.end = b; } },
  TextEditorRevealType: { InCenter: 2 }, SymbolKind: { Class: 4 },
  StatusBarAlignment: { Left: 1, Right: 2 },
  MarkupKind: { Markdown: 'markdown' },
  Uri: {
    file: (p) => ({ scheme: 'file', path: p, fsPath: p, toString: () => 'file://' + p }),
    from: (parts) => ({ scheme: parts.scheme, path: parts.path || '', query: parts.query || '',
      fsPath: parts.path || '',
      toString() { return `${this.scheme}:${this.path}${this.query ? `?${this.query}` : ''}`; } })
  },
  WorkspaceEdit: class {
    constructor() { this.changes = []; }
    replace(uri, range, text) { this.changes.push({ uri, range, text }); }
  },
  Disposable: class { constructor(fn) { this.dispose = fn; } },
  FileType: { File: 1, Directory: 2 },
  FileChangeType: { Changed: 1, Created: 2, Deleted: 3 },
  FileSystemError: {
    FileNotFound: (m) => new Error(m), NoPermissions: (m) => new Error(m),
    Unavailable: (m) => new Error(m)
  }
};

// The server, canned: method -> result. Anything not listed rejects, which is
// itself a case worth driving.
const pending = new Map();
// The client the extension started: its notification handlers live here.
let activeClient = null;
const client = {
  sendRequest: (method, params) => {
    seen.requests.push({ method, params });
    const replies = scenario.replies || {};
    if (!(method in replies)) {
      return Promise.reject(new Error(`Unhandled method ${method}`));
    }
    let reply = replies[method];
    // A method may legitimately answer differently on successive calls -- the
    // first ask to remove a namespace comes back as a question, the forced
    // retry removes it. One canned answer per method could not drive that: the
    // retry got the question again, or never happened at all.
    if (Array.isArray(reply)) {
      const queue = pending.get(method) || reply.slice();
      reply = queue.length > 1 ? queue.shift() : queue[0];
      pending.set(method, queue);
    }
    if (reply && reply.__reject) {
      return Promise.reject(new Error(reply.__reject));
    }
    return Promise.resolve(reply);
  },
  start: noop,
  stop: () => Promise.resolve(),
  // The server's own notifications: the scenario's `notify` delivers them,
  // after activation and before the command, as the real client would.
  handlers: {},
  onNotification(method, handler) { this.handlers[method] = handler; }
};

Module._load = function (request, parent, isMain) {
  if (request === 'vscode') return stub;
  if (request === 'vscode-languageclient/node') {
    return {
      LanguageClient: class {
        constructor() {
          Object.assign(this, client);
          this.handlers = {};
          activeClient = this;
        }
      },
      TransportKind: { stdio: 0 }
    };
  }
  return original(request, parent, isMain);
};

async function runCommand() {
  const extension = require(path.resolve(process.argv[3]));
  extension.activate({ subscriptions: [] });
  for (const { method, params } of scenario.notify || []) {
    const target = activeClient && activeClient.handlers[method];
    if (target) {
      await target(params);
    } else {
      seen.errors.push(`nothing listens for ${method}`);
    }
  }
  if (!scenario.command) {
    return;
  }
  const handler = registry.get(scenario.command);
  if (!handler) {
    seen.errors.push(`command ${scenario.command} is not registered`);
    return;
  }
  await handler(scenario.node, ...(scenario.args || []));
  // Clicks inside a webview, in order, after the command opened it.
  for (const message of scenario.webviewMessages || []) {
    const panel = seen.webviews[seen.webviews.length - 1];
    for (const receive of (panel && panel.receivers) || []) {
      await receive(message);
    }
  }
  // Further commands, in order -- a key pressed in the editor the first one
  // opened (Ctrl+Enter in a query document runs semforge.sparqlApply).
  for (const next of scenario.then || []) {
    const run = registry.get(next.command);
    if (!run) {
      seen.errors.push(`command ${next.command} is not registered`);
      continue;
    }
    seen.thenResults = (seen.thenResults || []).concat(
      [await run(next.node, ...(next.args || []))]);
  }
  for (const panel of seen.webviews) {
    delete panel.receivers;                     // functions do not serialise
  }
}

async function runTree() {
  const module = require(path.resolve(process.argv[3]));
  const Provider = module[scenario.provider];
  const provider = new Provider({ client });
  provider.view = {};
  provider.uri = scenario.uri;
  const first = await provider.getChildren();
  const firstKeys = first.map((node) => node.key);
  // Again, as happens whenever the tree follows the editor: the server sends
  // fresh objects, and the wrappers must stay the same ones the view holds.
  const second = await provider.getChildren();
  seen.tree = {
    roots: firstKeys,
    labels: first.map((node) => node.raw.label),
    message: provider.view.message,
    identityKept: first.length > 0 &&
      first.every((node, at) => node === second[at]),
    childIdentityKept: await (async () => {
      if (!first.length) {
        return null;
      }
      const kids = await provider.getChildren(first[0]);
      if (!kids.length) {
        return null;
      }
      await provider.getChildren();          // a refresh in between
      const again = await provider.getChildren(first[0]);
      return kids[0] === again[0] && provider.getParent(kids[0]) === first[0];
    })()
  };
}

async function runLocate() {
  const locate = require(path.resolve(process.argv[3]));
  seen.locate = {
    uri: locate.findPackageUri() || null,
    message: locate.noPackageMessage(),
    packages: locate.listPackages().map((entry) => entry.directory)
  };
}

/**
 * Drive a click: select a row in one view and see what happens.
 *
 * This goes through the real wiring -- the extension's own providers and
 * callbacks -- because the interesting part is the other view reacting, which no
 * handler test in isolation can show.
 */
async function runSelect() {
  const extension = require(path.resolve(process.argv[3]));
  extension.activate({ subscriptions: [] });
  const found = selections.filter((entry) => entry.view === scenario.view);
  if (!found.length) {
    seen.errors.push(`${scenario.view} registered no selection handler`);
    return;
  }
  // `label`: walk the view's real tree (so parents are known, as in VS Code)
  // and click the first row with that label; otherwise click `node` as given.
  let node = scenario.node;
  if (scenario.labelPath) {
    // The row at this path of labels from the top: an id can sit under Main
    // and in a case at once.
    const provider = providers[scenario.view];
    let parent;
    for (const label of scenario.labelPath) {
      const children = (await provider.getChildren(parent)) || [];
      parent = children.find((child) => child.raw.label === label);
      if (!parent) {
        seen.errors.push(`no row ${label} under ${scenario.labelPath.join(' › ')}: ` +
          children.map((child) => child.raw.label).join(', '));
        return;
      }
    }
    node = parent;
  } else if (scenario.label) {
    const provider = providers[scenario.view];
    const walk = async (parent) => {
      for (const child of (await provider.getChildren(parent)) || []) {
        if (child.raw.label === scenario.label) { return child; }
        const deeper = await walk(child);
        if (deeper) { return deeper; }
      }
      return undefined;
    };
    node = await walk(undefined);
    if (!node) {
      seen.errors.push(`no row labelled ${scenario.label}`);
      return;
    }
  }
  for (const entry of found) {
    seen.events.push({ type: 'click', view: entry.view });
    await entry.handler({ selection: [node] });
  }
}

/**
 * Every row the provider renders, with the contextValue its menus are matched
 * against.
 *
 * Which actions a row offers is decided by that string and by package.json, and
 * the two had drifted: every attribute carries a datasetId, so every attribute
 * landed on a contextValue whose menu had no edit -- and clicking hasState
 * offered no way to change it.
 */
async function runItems() {
  const module = require(path.resolve(process.argv[3]));
  const Provider = module[scenario.provider];
  const provider = new Provider({ client });
  provider.view = {};
  provider.uri = scenario.uri;

  const rows = [];
  const walk = async (node) => {
    for (const child of await provider.getChildren(node)) {
      const item = provider.getTreeItem(child);
      rows.push({
        label: child.raw.label,
        kind: child.raw.kind,
        editable: !!child.raw.editable,
        datasetId: child.raw.datasetId || '',
        observations: child.raw.observations || 0,
        contextValue: item.contextValue,
        icon: item.iconPath && item.iconPath.id,
        color: item.iconPath && item.iconPath.color && item.iconPath.color.id,
        typeClass: child.raw.typeClass || '',
        expanded: item.collapsibleState === 2
      });
      await walk(child);
    }
  };
  await walk(undefined);
  seen.rows = rows;
}

// A pure renderer, called directly: what HTML a payload becomes.
async function runRender() {
  const module = require(path.resolve(process.argv[3]));
  seen.html = module[scenario.function](scenario.payload, scenario.options || {});
}

const modes = { tree: runTree, locate: runLocate, select: runSelect,
                items: runItems, render: runRender };
((modes[scenario.mode] || runCommand)())
  .then(() => console.log(JSON.stringify(seen)))
  .catch((error) => {
    seen.errors.push(`threw: ${error && error.message}`);
    console.log(JSON.stringify(seen));
    process.exitCode = 0;
  });
