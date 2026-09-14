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
const { showLocation } = require('./reveal');

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

    if (raw.kind === 'group' || raw.kind === 'project') {
      item.iconPath = new vscode.ThemeIcon('project');
    } else if (raw.severity) {
      item.iconPath = new vscode.ThemeIcon('warning');
    } else if (raw.kind === 'namespaces' || raw.kind === 'namespaceEntry') {
      item.iconPath = new vscode.ThemeIcon('symbol-namespace');
    } else if (raw.editable) {
      item.iconPath = new vscode.ThemeIcon('settings-gear');
    } else {
      item.iconPath = new vscode.ThemeIcon('info');
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
    return (result.roots || []).map((raw, position) =>
      this.wrap(raw, keyOf(raw, '', position)));
  }
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
      if (selected && selected.raw.definedAt) {
        await showLocation(selected.raw.definedAt, false);
      }
    })
  );

  provider.refresh(session.uri);
  context.subscriptions.push(
    session.onDidChange((uri) => provider.refresh(uri)),
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
      const prefix = await vscode.window.showInputBox({
        title: 'New namespace prefix',
        prompt: 'The name this package uses for it, e.g. plant',
        validateInput: (text) =>
          /^[A-Za-z_][\w.-]*$/.test((text || '').replace(/:$/, ''))
            ? undefined
            : 'A letter or underscore, then letters, digits, dots, ' +
              'underscores or hyphens.'
      });
      if (!prefix) {
        return;
      }
      const namespace = await vscode.window.showInputBox({
        title: `What does ${prefix}: mean?`,
        prompt: 'The namespace IRI. It has to end in "/", "#" or ":", or a ' +
          'term appended to it runs into the last segment.',
        value: 'https://'
      });
      if (!namespace) {
        return;
      }
      const made = await clientHolder.client.sendRequest(
        'semforge/addNamespace',
        { uri: (node && node.packageUri) || provider.uri, prefix, namespace }
      );
      if (!made || !made.ok) {
        vscode.window.showErrorMessage(
          `SemForge: ${(made && made.error) || 'the prefix was not defined'}`
        );
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

module.exports = { register, ProjectTreeProvider };
