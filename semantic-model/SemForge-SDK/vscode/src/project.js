/*
 * The project itself: which package this is, how it is set up, what it holds.
 *
 * The other three views answer what the package SAYS -- its constraints, its
 * data, its vocabulary. None answered what it IS. A window showed a name and
 * nothing else, and two directories called `test` are not the same project:
 * there were no settings to read, no status to check, and no way to change
 * either without finding semforge.yaml by hand.
 *
 * So this view sits above the other three and holds the answers, with each
 * setting editable in place. Editing writes one line of semforge.yaml and
 * leaves every comment in it -- those comments are the documentation.
 */

const vscode = require('vscode');

const { noPackageMessage } = require('./locate');
const { showLocation, icon } = require('./reveal');

class ProjectTreeNode {
  constructor(key, raw, packageUri) {
    this.key = key;
    this.raw = raw;
    this.packageUri = packageUri;
  }
}

function keyOf(raw, parentKey, position) {
  return `${parentKey}/${position}:${raw.kind}:${raw.key || raw.label}`;
}

class ProjectTreeProvider {
  constructor(clientHolder) {
    this.clientHolder = clientHolder;
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    this.nodes = new Map();
    this.parents = new Map();
  }

  refresh(uri) {
    if (uri) {
      this.uri = uri;
    }
    // A refresh is a request to look again, health included.
    this.health = undefined;
    this.healthAsked = undefined;
    this._onDidChangeTreeData.fire();
  }

  /**
   * Point at another package, or at none.
   *
   * Separate from `refresh`, which means "ask again about the package you
   * already have" and therefore ignores a falsy uri. Nothing could clear a
   * provider, so a deleted package went on being displayed.
   */
  setPackage(uri) {
    this.uri = uri || undefined;
    // The wrappers are keyed by address within a package; carrying them across
    // means a row of the old one answering for a row of the new.
    if (this.nodes && this.nodes.clear) {
      this.nodes.clear();
    }
    if (this.parents && this.parents.clear) {
      this.parents.clear();
    }
    this._onDidChangeTreeData.fire();
  }

  wrap(raw, key) {
    const existing = this.nodes.get(key);
    if (existing) {
      existing.raw = raw;
      existing.packageUri = this.uri;
      return existing;
    }
    const made = new ProjectTreeNode(key, raw, this.uri);
    this.nodes.set(key, made);
    return made;
  }

  getParent(node) {
    return this.parents.get(node.key);
  }

  getTreeItem(node) {
    const raw = node.raw;
    const children = raw.children || [];
    const item = new vscode.TreeItem(
      raw.label || raw.kind,
      children.length
        ? raw.kind === 'group' || raw.kind === 'project'
          ? vscode.TreeItemCollapsibleState.Expanded
          : vscode.TreeItemCollapsibleState.Collapsed
        : vscode.TreeItemCollapsibleState.None
    );
    // The value is the point of the row, so it goes where the eye lands; what
    // the setting DECIDES is the tooltip, because it is a paragraph.
    item.description = raw.value || '';
    // `editable` decides, for every kind. Keying this on the kind is what left
    // the pencil off rows that carry a value -- twice.
    item.contextValue = raw.editable ? 'setting' : raw.kind;

    // A problem colours the row's own icon rather than replacing it.
    const tone = raw.severity ? 'warning' : '';
    if (raw.kind === 'health') {
      item.description = raw.detail || '';
      item.tooltip = 'The package at a glance. Click for the health page: what ' +
        'needs attention first.';
      item.iconPath = icon('pulse', raw.severity ? 'error' : raw.ok ? 'ok' : '');
      return item;
    }
    if (raw.kind === 'group' || raw.kind === 'project') {
      item.iconPath = icon('project', tone);
    } else if (raw.kind === 'cache') {
      item.iconPath = icon('database', tone);
    } else if (raw.kind === 'namespaces' || raw.kind === 'namespaceEntry') {
      item.iconPath = icon('symbol-namespace', tone);
    } else if (raw.editable) {
      item.iconPath = icon('settings-gear', tone);
    } else {
      item.iconPath = icon('info', tone);
    }

    const lines = [];
    if (raw.detail) {
      lines.push(raw.detail);
    }
    if (raw.doc && raw.doc !== raw.detail) {
      lines.push(raw.doc);
    }
    if (raw.definedAt) {
      lines.push(raw.definedAt);
    }
    if (lines.length) {
      item.tooltip = lines.join('\n\n');
    }
    return item;
  }

  async getChildren(node) {
    if (node) {
      return (node.raw.children || []).map((child, position) => {
        const key = keyOf(child, node.key, position);
        this.parents.set(key, node);
        return this.wrap(child, key);
      });
    }
    const client = this.clientHolder.client;
    if (!client) {
      this.view.message = 'The language server is not running — run ' +
        '"SemForge: Doctor".';
      return [];
    }
    if (!this.uri) {
      this.view.message = noPackageMessage();
      return [];
    }
    let result;
    try {
      result = await client.sendRequest('semforge/project', { uri: this.uri });
    } catch (error) {
      this.view.message = `SemForge: ${error.message || error}`;
      return [];
    }
    if (result.error) {
      this.view.message = `SemForge: ${result.error}`;
      return [];
    }
    this.view.message = undefined;
    this.parents = new Map();
    const rows = (result.roots || []).map((raw, position) =>
      this.wrap(raw, keyOf(raw, '', position)));
    return [this.wrap(this.healthRow(), 'health'), ...rows];
  }

  /**
   * The package at a glance, first: "6/6 cases pass · 3 violations · 67
   * untested". Asked for after the rest of the view, so a slow first health
   * computation never holds up the settings beneath it.
   */
  healthRow() {
    const uri = this.uri;
    if (this.health && this.health.uri === uri) {
      return this.health.row;
    }
    if (this.healthAsked !== uri && this.clientHolder.client) {
      this.healthAsked = uri;
      this.clientHolder.client.sendRequest('semforge/health', { uri })
        .then((page) => {
          this.health = { uri, row: healthRow(page) };
          this._onDidChangeTreeData.fire();
        }, (error) => {
          this.health = { uri, row: healthRow({ ok: false, error: error.message }) };
          this._onDidChangeTreeData.fire();
        });
    }
    return { kind: 'health', label: 'Health', detail: 'checking…' };
  }
}

function healthRow(page) {
  if (!page || !page.ok) {
    return { kind: 'health', label: 'Health', severity: 'error',
      detail: `unavailable: ${(page && page.error) || 'no answer'}` };
  }
  const t = page.tiles || {};
  const failing = (t.cases || 0) - (t.casesPassing || 0);
  return {
    kind: 'health', label: 'Health',
    detail: [
      t.cases ? `${t.casesPassing}/${t.cases} cases pass` : 'no test cases',
      t.modelViolations ? `${t.modelViolations} violation(s)` : '',
      t.neverFired ? `${t.neverFired} untested` : '',
      t.brokenReferences ? `${t.brokenReferences} broken reference(s)` : ''
    ].filter(Boolean).join(' · '),
    // Red only for what is wrong with the PACKAGE: a failing case or a
    // broken reference. Violations in the model data are information.
    severity: failing || t.brokenReferences ? 'error' : '',
    ok: !failing && !t.brokenReferences
  };
}

function register(context, clientHolder, session, onChanged) {
  const provider = new ProjectTreeProvider(clientHolder);
  const view = vscode.window.createTreeView('semforgeProject', {
    treeDataProvider: provider
  });
  provider.view = view;
  context.subscriptions.push(view);

  // Selecting a row that names a line opens it. A setting's row points at its
  // own line in semforge.yaml, so reading the comment around it is one click.
  context.subscriptions.push(
    view.onDidChangeSelection(async (event) => {
      const selected = event.selection && event.selection[0];
      if (selected && selected.raw.kind === 'health') {
        await vscode.commands.executeCommand('semforge.openHealthPage', selected);
      } else if (selected && selected.raw.definedAt) {
        await showLocation(selected.raw.definedAt, false);
      }
    })
  );

  provider.refresh(session.uri);
  context.subscriptions.push(
    session.onDidChange((uri) => provider.setPackage(uri)),
    vscode.workspace.onDidSaveTextDocument(() => provider.refresh())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.editSetting', async (node) => {
      const raw = node && node.raw;
      if (!raw || !raw.editable) {
        return;
      }
      const value = await vscode.window.showInputBox({
        title: `${raw.label}`,
        prompt: raw.doc || raw.detail,
        value: raw.value === '—' ? '' : raw.value,
        ignoreFocusOut: true
      });
      if (value === undefined) {
        return;                       // cancelled; nothing is written
      }
      const result = await clientHolder.client.sendRequest(
        'semforge/setSetting',
        { uri: node.packageUri, key: raw.key, value }
      );
      if (!result || !result.ok) {
        vscode.window.showErrorMessage(
          `SemForge: ${(result && result.error) || 'the setting was not written'}`
        );
        return;
      }
      provider.refresh();
      if (onChanged) {
        // The context and the entity root change what the other views mean,
        // so they are re-read rather than left showing the old answer.
        onChanged();
      }
      await showLocation(`${result.file}:${result.line}`, false);
    }),

    vscode.commands.registerCommand('semforge.addNamespace', async (node) => {
      // Prefixes are a package-wide table, agreed once. There was no way to
      // add to it from the editor at all -- you found semforge.yaml and typed.
      // The same prompts as "New namespace…" in a vocabulary dialog.
      const made = await require('./namespacepick').defineNamespace(
        clientHolder.client, (node && node.packageUri) || provider.uri,
        node && node.namespace);
      if (!made) {
        return;
      }
      provider.refresh();
      if (onChanged) {
        onChanged();
      }
      await showLocation(`${made.file}:${made.line}`, false);
    }),

    vscode.commands.registerCommand('semforge.removeNamespace', async (node) => {
      const raw = node && node.raw;
      if (!raw || !raw.label) {
        return;
      }
      const uri = node.packageUri || provider.uri;
      // The server decides whether it CAN go; it also answers "it is in use"
      // as a question rather than doing it. A line that changes nothing is
      // still a line somebody wrote on purpose, and what the person clicking
      // is thinking about is that three files bind it.
      const ask = async (force) =>
        clientHolder.client.sendRequest('semforge/removeNamespace',
                                        { uri, prefix: raw.label, force });

      let gone = await ask(false);
      if (gone && gone.confirm) {
        const answer = await vscode.window.showWarningMessage(
          `Remove ${raw.label}: ?`,
          { modal: true, detail: gone.detail },
          'Remove'
        );
        if (answer !== 'Remove') {
          return;
        }
        gone = await ask(true);
      }
      if (!gone || !gone.ok) {
        vscode.window.showWarningMessage(
          `SemForge: ${(gone && gone.error) || 'the prefix was not removed'}`
        );
        return;
      }
      provider.refresh();
      if (onChanged) {
        onChanged();
      }
      vscode.window.setStatusBarMessage(
        gone.survivesVia
          ? `SemForge: ${raw.label}: removed — ${gone.survivesVia} still names it`
          : `SemForge: ${raw.label}: removed`,
        5000
      );
    }),

    vscode.commands.registerCommand('semforge.refreshProject', () =>
      provider.refresh()
    )
  );

  return provider;
}

module.exports = { register, ProjectTreeProvider, healthRow };
