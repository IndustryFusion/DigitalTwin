/*
 * Which package am I working on?
 *
 * The three views used to answer this separately: each one called
 * findPackageUri() on activation and each one followed the active editor with
 * its own rule -- and the knowledge view's rule was different from the other
 * two's. So the Constraints view could be showing one package while Knowledge
 * showed another, with nothing on screen naming either. Opening a file quietly
 * moved a view to a different package; nothing said so.
 *
 * One session owns the answer instead. It is shown in the status bar, it is
 * shown as each view's subtitle, and it can be chosen -- which is what every
 * editor integration that can face several projects does (the Python
 * interpreter, the Java project, the active Docker context).
 *
 * Choosing PINS. Following the active editor is the right default when you
 * have one package, and exactly wrong when you are reading a second one and
 * do not want your views to move.
 */

const path = require('path');
const vscode = require('vscode');

const { findPackageUri, listPackages, packageDirectory,
        samePackage } = require('./locate');

class PackageSession {
  constructor() {
    this.uri = undefined;
    this.pinned = false;
    this.emitter = new vscode.EventEmitter();
    this.onDidChange = this.emitter.event;
  }

  /** The package directory, for display. */
  get directory() {
    return packageDirectory(this.uri);
  }

  get name() {
    const directory = this.directory;
    return directory ? path.basename(directory) : undefined;
  }

  /** Take the package found in the opened folders. */
  discover() {
    const found = findPackageUri();
    if (found) {
      this.set(found, { pinned: false });
    }
    return this.uri;
  }

  set(uri, options) {
    const pinned = !!(options || {}).pinned;
    if (samePackage(this.uri, uri) && this.pinned === pinned) {
      return false;
    }
    this.uri = uri;
    this.pinned = pinned;
    this.emitter.fire(this.uri);
    return true;
  }

  /**
   * Follow an editor into its package.
   *
   * Only when it is a DIFFERENT package: re-validating because somebody opened
   * a file we are already showing is wasted work, and the refresh it fires
   * invalidates any reveal in flight -- including the one the click that opened
   * the file is waiting on.
   */
  follow(editor) {
    if (this.pinned || !editor) {
      return false;
    }
    const file = editor.document && editor.document.uri;
    if (!file || !/\.(ttl|jsonld)$/.test(file.fsPath)) {
      return false;
    }
    const opened = file.toString();
    if (samePackage(this.uri, opened)) {
      return false;
    }
    return this.set(opened, { pinned: false });
  }
}

/**
 * What to call the active package.
 *
 * Its path relative to the opened folder, not its basename: two directories
 * called `test` are not the same project, and `kms/test` says which one this
 * is where `test` does not.
 */
function label(session) {
  if (!session.uri) {
    return 'no package';
  }
  const directory = session.directory;
  let name = session.name;
  for (const folder of vscode.workspace.workspaceFolders || []) {
    const root = folder.uri.fsPath;
    if (directory === root) {
      name = path.basename(root);
    } else if (directory && directory.startsWith(root + path.sep)) {
      name = directory.slice(root.length + 1);
    }
  }
  return name + (session.pinned ? ' (pinned)' : '');
}

function tooltip(session) {
  const lines = ['SemForge package'];
  lines.push(session.directory || '(none found in this window)');
  lines.push(session.pinned
    ? 'Pinned — the views stay here whatever you open.'
    : 'Following the active editor.');
  lines.push('Click for the SemForge menu.');
  return lines.join('\n');
}


/**
 * The SemForge menu.
 *
 * VS Code does not let an extension add a menu beside File and Edit -- there
 * is no contribution point for the menu bar, only for the menus inside the
 * workbench. So the one place everything hangs off is the status bar item,
 * which is where an editor integration that can face several projects puts it
 * (the Python interpreter, the Java project, the active Docker context).
 * Everything here is in the command palette under `SemForge:` as well.
 */
const MENU = [
  { label: '$(package) Switch package…', command: 'semforge.selectPackage',
    description: 'which package all three views show' },
  { label: '$(settings-gear) Project settings',
    command: 'semforgeProject.focus',
    description: 'name, contexts, namespaces — in the Project view' },
  { label: '$(check) Revalidate', command: 'semforge.revalidate',
    description: 're-run analysis over the package' },
  { label: '$(new-folder) New project…', command: 'semforge.newProject',
    description: 'create a folder with the basic structure' },
  { label: '$(file-directory) Create a package in this folder',
    command: 'semforge.initPackage',
    description: 'scaffold a directory you already have' },
  { label: '$(pulse) Doctor', command: 'semforge.doctor',
    description: 'what it sees: interpreter, package, server' },
  { label: '$(debug-restart) Restart language server',
    command: 'semforge.restart' }
];

/**
 * Wire the session to the window: a status bar item, a switcher, and the
 * subtitle on each view.
 */
function register(context, session, views, refreshAll) {
  const item = vscode.window.createStatusBarItem
    ? vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100)
    : undefined;

  const paint = () => {
    const text = label(session);
    if (item) {
      item.text = `$(package) ${text}`;
      item.tooltip = tooltip(session);
      item.command = 'semforge.menu';
      item.show();
    }
    for (const view of views || []) {
      if (view) {
        // The subtitle sits beside the view's name, so each of the three says
        // which package it is showing without being asked.
        view.description = session.uri ? text : undefined;
      }
    }
  };

  paint();
  context.subscriptions.push(session.onDidChange(() => paint()));
  if (item) {
    context.subscriptions.push(item);
  }

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.menu', async () => {
      const chosen = await vscode.window.showQuickPick(MENU, {
        placeHolder: `SemForge — ${label(session)}`
      });
      if (chosen) {
        await vscode.commands.executeCommand(chosen.command);
      }
    }),

    vscode.commands.registerCommand('semforge.selectPackage', async () => {
      const found = listPackages();
      const here = session.directory;
      const items = found.map((entry) => ({
        label: entry.name,
        description: entry.directory === here ? entry.directory + '  (current)'
                                              : entry.directory,
        uri: entry.uri
      }));
      items.push({
        label: 'Follow the active editor',
        description: 'unpin — the views move to whatever package you open',
        uri: undefined,
        follow: true
      });
      if (!found.length) {
        // Nothing to choose between is not a menu; it is a diagnosis.
        vscode.window.showWarningMessage(
          'No SemForge package in this window. Run "SemForge: New Project" ' +
          'to create one, or open a folder that holds one.');
        return;
      }
      const chosen = await vscode.window.showQuickPick(items, {
        placeHolder: 'Which package should the SemForge views show?'
      });
      if (!chosen) {
        return;
      }
      if (chosen.follow) {
        session.pinned = false;
        session.set(findPackageUri(), { pinned: false });
      } else {
        session.set(chosen.uri, { pinned: true });
      }
      paint();
      if (refreshAll) {
        refreshAll();
      }
    })
  );

  // One listener for the window, not one per view.
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => session.follow(editor))
  );

  return { paint };
}

module.exports = { PackageSession, register, label };
