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

/** `kms`, or `kms (pinned)`, or what to do when there is none. */
function label(session) {
  if (!session.uri) {
    return 'no package';
  }
  return session.name + (session.pinned ? ' (pinned)' : '');
}

function tooltip(session) {
  const lines = ['SemForge package'];
  lines.push(session.directory || '(none found in this window)');
  lines.push(session.pinned
    ? 'Pinned — the views stay here whatever you open.'
    : 'Following the active editor.');
  lines.push('Click to switch.');
  return lines.join('\n');
}

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
      item.command = 'semforge.selectPackage';
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
