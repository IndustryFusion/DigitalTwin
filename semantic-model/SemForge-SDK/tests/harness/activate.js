/*
 * Activate the extension against a stub `vscode`.
 *
 * node --check only parses: it cannot see a function that is CALLED and never
 * DEFINED, which is how `sdkDirectory` went missing and left the extension
 * throwing ReferenceError at activation -- broken in exactly the way that looks
 * like "it finds nothing".
 */
const Module = require('module');
const path = require('path');
const original = Module._load;
const registered = [];
// What the views did, so a test can drive a click and see the effect. A click
// that does not unfold the row is invisible to `node --check` and to any test
// that only counts commands.
const selectionHandlers = [];
const revealed = [];
// The status bar is where the active package is named, so activation has to be
// able to show what it painted there.
const statusBar = [];
const seen = { deleted: [] };

const noop = () => undefined;
const stub = {
  workspace: {
    getConfiguration: () => ({ get: () => '' }),
    workspaceFolders: [{ uri: { fsPath: process.argv[2] } }],
    createFileSystemWatcher: () => ({ dispose: noop }),
    onDidChangeConfiguration: noop,
    onDidSaveTextDocument: noop,
    // Recorded, never performed: a test that actually deleted a directory
    // would be a test you could only run once.
    fs: {
      delete: (uri, options) => {
        seen.deleted.push({ path: uri.fsPath, options: options || {} });
        return Promise.resolve();
      }
    },
    openTextDocument: noop
  },
  window: {
    showWarningMessage: noop,
    showQuickPick: noop,
    showInputBox: noop,
    showTextDocument: noop,
    createTreeView: (id) => ({
      dispose: noop,
      reveal: (node, options) =>
        Promise.resolve(revealed.push({ view: id, options: options || {} })),
      onDidChangeSelection: (handler) => {
        selectionHandlers.push({ view: id, handler });
        return { dispose: noop };
      }
    }),
    onDidChangeActiveTextEditor: noop,
    activeTextEditor: undefined,
    showErrorMessage: (m) => { registered.push('ERROR: ' + m); return Promise.resolve(); },
    showInformationMessage: noop,
    createOutputChannel: () => ({ appendLine: noop, show: noop }),
    setStatusBarMessage: noop,
    createStatusBarItem: () => {
      const item = { text: '', tooltip: '', command: undefined,
                     show: () => statusBar.push(item.text),
                     hide: noop, dispose: noop };
      return item;
    }
  },
  commands: { registerCommand: (id) => { registered.push(id); return { dispose: noop }; },
              executeCommand: noop },
  EventEmitter: class { constructor() { this.event = noop; } fire() {} },
  ThemeIcon: class { constructor(i) { this.id = i; } },
  TreeItem: class { constructor(l) { this.label = l; } },
  TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 },
  Position: class {}, Selection: class {}, Range: class {},
  TextEditorRevealType: { InCenter: 2 }, SymbolKind: { Class: 4 },
  StatusBarAlignment: { Left: 1, Right: 2 },
  MarkupKind: { Markdown: 'markdown' },
  Uri: { file: (p) => ({ fsPath: p, toString: () => 'file://' + p }) }
};

Module._load = function (request, parent, isMain) {
  if (request === 'vscode') return stub;
  if (request === 'vscode-languageclient/node') {
    // Stubbed, because the real library wants a far fuller vscode API than a
    // stub can provide. Whether it SHIPS is a separate question, and stubbing
    // it here is what hid the extension being packaged without it -- so
    // test_extension_packaging.py checks that every bare require resolves
    // inside the package. The two tests cover different failures.
    return { LanguageClient: class { start() {} stop() { return Promise.resolve(); } },
             TransportKind: { stdio: 0 } };
  }
  return original(request, parent, isMain);
};

const extension = require(path.resolve(process.argv[3]));
const context = { subscriptions: [] };
extension.activate(context);

async function main() {
  // Select a row that has children and no location, so only the unfold is
  // under test and nothing tries to open a file.
  for (const { handler } of selectionHandlers) {
    await handler({
      selection: [{ raw: { kind: 'entity', definedAt: '', children: [{}] },
                    packageUri: 'file://x' }]
    });
  }
  console.log(JSON.stringify({
    commands: registered.filter((r) => !r.startsWith('ERROR')),
    errors: registered.filter((r) => r.startsWith('ERROR')),
    views: selectionHandlers.map((s) => s.view),
    revealed,
    statusBar,
    deleted: seen.deleted
  }));
}

main();
