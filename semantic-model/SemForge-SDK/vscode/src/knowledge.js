/*
 * The knowledge, as a tree: the third ingredient beside shapes and examples.
 *
 * Entity types nest by rdfs:subClassOf; vocabulary classes list their members.
 * What makes it more than an outline of knowledge.ttl is the joins it shows --
 * which shape judges a class, how many examples instantiate it, which terms the
 * data actually uses -- and the two jumps that follow those joins: one to the
 * class in knowledge.ttl, one to the shape in shacl.ttl.
 */

const vscode = require('vscode');

const { noPackageMessage } = require('./locate');
const { showLocation } = require('./reveal');

class KnowledgeTreeNode {
  constructor(key, raw, packageUri) {
    this.key = key;
    this.raw = raw;
    this.packageUri = packageUri;
  }
}

/** A node's address in the tree, stable across refetches. */
function keyOf(raw, parentKey, position) {
  return `${parentKey}/${position}:${raw.kind}:${raw.iri || raw.label}`;
}

class KnowledgeTreeProvider {
  constructor(clientHolder) {
    this.clientHolder = clientHolder;
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    // Keyed by address, not by the raw object: the server sends fresh objects
    // on every fetch, and a view holding a wrapper from the previous fetch
    // cannot resolve it -- which is the "Failed to resolve tree node" that made
    // reveal() a no-op.
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
      existing.raw = raw;             // same row, fresher data
      existing.packageUri = this.uri;
      return existing;
    }
    const made = new KnowledgeTreeNode(key, raw, this.uri);
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
        ? // Groups open; a class with a long member list does not, or the
          // vocabularies bury the hierarchy.
          raw.kind === 'group'
          ? vscode.TreeItemCollapsibleState.Expanded
          : vscode.TreeItemCollapsibleState.Collapsed
        : vscode.TreeItemCollapsibleState.None
    );
    item.description = raw.detail || '';
    // Spelled out, because `when: viewItem == x` matches a string and a row
    // whose contextValue drifts from package.json silently loses its icons.
    // Spelled out, because `when: viewItem == x` matches a string and a row
    // whose contextValue drifts from package.json silently loses its icons.
    if (raw.kind === 'class') {
      item.contextValue = raw.shapeAt ? 'classWithShape' : 'class';
    } else if (raw.kind === 'attribute') {
      item.contextValue = raw.shapeAt ? 'attributeWithShape' : 'attribute';
    } else {
      item.contextValue = raw.kind;
    }

    if (raw.kind === 'group') {
      item.iconPath = new vscode.ThemeIcon('library');
    } else if (raw.kind === 'carrier') {
      item.iconPath = new vscode.ThemeIcon(
        raw.severity ? 'warning' : 'symbol-class'
      );
    } else if (raw.kind === 'attribute') {
      item.iconPath = new vscode.ThemeIcon(
        raw.severity ? 'warning' : 'symbol-field'
      );
    } else if (raw.kind === 'relation') {
      item.iconPath = new vscode.ThemeIcon(
        raw.severity ? 'warning' : 'symbol-property'
      );
    } else if (raw.kind === 'class') {
      item.iconPath = new vscode.ThemeIcon(
        raw.severity ? 'warning' : 'symbol-class'
      );
    } else if (raw.kind === 'individual') {
      item.iconPath = new vscode.ThemeIcon(
        raw.severity ? 'warning' : 'symbol-enum-member'
      );
    } else if (raw.kind === 'instance') {
      item.iconPath = new vscode.ThemeIcon('symbol-object');
    } else {
      item.iconPath = new vscode.ThemeIcon('references');
    }

    const lines = (raw.messages || []).slice();
    if (raw.iri) {
      lines.push(raw.iri);
    }
    if (raw.shapeName) {
      lines.push(`judged by ${raw.shapeName}`);
    }
    if (lines.length) {
      item.tooltip = lines.join('\n');
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
      result = await client.sendRequest('semforge/knowledge', {
        uri: this.uri
      });
    } catch (error) {
      // An empty tree with no explanation is the failure mode this project
      // keeps meeting. Say what went wrong where it is visible.
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

function register(context, clientHolder, session, onShape, onEntity) {
  const provider = new KnowledgeTreeProvider(clientHolder);
  const view = vscode.window.createTreeView('semforgeKnowledge', {
    treeDataProvider: provider
  });
  provider.view = view;
  context.subscriptions.push(view);

  // Selecting a class moves knowledge.ttl to its declaration; selecting an
  // instance moves the .jsonld to the entity. Same rule as the other two views,
  // and as there the row also unfolds rather than toggling shut.
  context.subscriptions.push(
    view.onDidChangeSelection(async (event) => {
      const selected = event.selection && event.selection[0];
      if (!selected) {
        return;
      }
      // Both kinds of row name an entity: an instance row says this class is
      // instantiated here, a usage row says this term is given as a value
      // there. Opening the file is half of showing it; the other half is the
      // row in the examples tree, where its verdicts and its other attributes
      // are.
      //
      // This happens BEFORE the file is opened, deliberately. Opening a file
      // can refresh a tree, and a refresh makes VS Code drop its element
      // handles, so a reveal afterwards resolves nothing -- it logged "Failed
      // to resolve tree node" and looked like the click doing nothing.
      const names = selected.raw.kind === 'usage' ||
        selected.raw.kind === 'instance';
      if (names && selected.raw.entity && onEntity) {
        // The file comes along: the same id appears in a good case and a bad
        // one, and the row you clicked named one of them.
        await onEntity(selected.raw.entity, selected.raw.file);
      }
      if ((selected.raw.children || []).length) {
        try {
          await view.reveal(selected, { expand: true, select: false, focus: false });
        } catch (error) {
          // Gone after a refresh; nothing to reveal.
        }
      }
      if (selected.raw.definedAt) {
        await showLocation(selected.raw.definedAt, false);
      }
    })
  );

  // Which package this view shows is decided ONCE, for all three views, by the
  // session in packages.js -- including following the active editor. Each view
  // used to decide for itself, with a different rule in the knowledge view, so
  // the three could be showing three different packages with nothing on screen
  // naming any of them.
  provider.refresh(session.uri);
  context.subscriptions.push(
    session.onDidChange((uri) => provider.refresh(uri)),
    vscode.workspace.onDidSaveTextDocument(() => provider.refresh())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.refreshKnowledge', () =>
      provider.refresh()
    ),

    vscode.commands.registerCommand('semforge.showShapeForClass', async (node) => {
      const raw = node && node.raw;
      if (!raw) {
        return;
      }
      if (raw.shapeAt) {
        await showLocation(raw.shapeAt, true);
        if (onShape) {
          onShape(raw.shape);
        }
        return;
      }
      // No shape of its own. Saying which ancestor checks it is more useful
      // than an empty jump -- and the detail already says whether anything
      // does.
      vscode.window.showInformationMessage(
        `SemForge: no shape targets ${raw.label} directly. ` +
          (raw.detail && raw.detail.includes('inherited')
            ? 'It is checked by a shape further up the hierarchy.'
            : 'Nothing checks it.')
      );
    })
  );

  return provider;
}

module.exports = { register, KnowledgeTreeProvider };
