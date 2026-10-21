/*
 * The cooked view: a TreeDataProvider over the SDK's constraint tree.
 *
 * It renders what `semforge/tree` returns and sends edits back through
 * `semforge/setConstraint`. It computes nothing itself -- the tree, which
 * parameters are editable, and what an edit does to the file are all decided in
 * the SDK, so the tree and the CLI cannot disagree about what a shape says.
 */

const vscode = require('vscode');

const { noPackageMessage } = require('./locate');
const { showLocation, treeDetail, treeClick, icon } = require('./reveal');
const { constrainAttribute, newAttribute } = require('./attribute');

// Candidate values come from the server, never from a list in here. Which
// classes may be offered is an ontology question -- entity types on one side of
// the NGSI-LD encoding, vocabulary classes on the other -- and a list hard-coded
// in JavaScript would drift from the model the moment somebody adds a class.
const CUSTOM = Symbol('custom');

class ConstraintNode {
  constructor(raw, packageUri) {
    this.raw = raw;
    this.packageUri = packageUri;
  }
}

class CookedTreeProvider {
  constructor(clientHolder) {
    this.clientHolder = clientHolder;
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    this.uri = undefined;
  }

  refresh(uri) {
    if (uri) {
      this.uri = uri;
    }
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

  /**
   * Index the whole tree in one pass.
   *
   * The server returns every node in a single reply, so the wrappers can be
   * built once and kept. That identity is what TreeView.reveal needs: a fresh
   * wrapper per getChildren call would make every element unrecognisable to
   * the view, and reveal a no-op.
   */
  _index(roots) {
    this.nodes = new Map();
    this.parents = new Map();
    this.owners = new Map();

    // The type a row belongs to is the NEAREST type above it: in summary mode
    // the tree is the type hierarchy, so a subtype's rows are its own.
    const ownerOf = (type) => ({
      label: type.label,
      targetClass: type.targetClass,
      // The type's OWN shape -- an override is added there, never to the
      // inherited shape the constraint came from.
      shape: ((type.children || []).find((c) => c.kind !== 'type' &&
        c.kind !== 'rules' && !c.inheritedFrom && c.shape) || {}).shape
    });
    const walk = (raw, parentRaw, owner) => {
      const mine = raw.kind === 'type' ? ownerOf(raw) : owner;
      // Every row knows its type, so "Open entity type page" works from any
      // of them -- in summary mode that page is where a row is edited.
      raw.typeClass = mine.targetClass;
      this.nodes.set(raw, new ConstraintNode(raw, this.uri));
      this.parents.set(raw, parentRaw);
      this.owners.set(raw, mine);
      (raw.children || []).forEach((child) => walk(child, raw, mine));
    };

    roots.forEach((root) => walk(root, null, ownerOf(root)));
    this.rawRoots = roots;
  }

  wrap(raw) {
    return raw && this.nodes ? this.nodes.get(raw) : undefined;
  }

  getParent(node) {
    return this.parents ? this.wrap(this.parents.get(node.raw)) : undefined;
  }

  /** The non-inherited node declaring the same thing, if the tree has one.
   *  Nothing before the Types view first loads (it may never have been
   *  opened): a jump from elsewhere then just opens the file. */
  findCanonical(raw) {
    for (const candidate of this.nodes ? this.nodes.keys() : []) {
      if (
        !candidate.inheritedFrom &&
        candidate.shape === raw.shape &&
        candidate.parameter === (raw.parameter || '') &&
        JSON.stringify(candidate.path) === JSON.stringify(raw.path || [])
      ) {
        return this.nodes.get(candidate);
      }
    }
    return undefined;
  }

  /**
   * The type node a tree node sits under.
   *
   * An override is added to the shape of the type being VIEWED, not the shape
   * the constraint came from -- that is the whole point of pulling it down.
   */
  ownerOf(node) {
    return this.owners ? this.owners.get(node.raw) : undefined;
  }

  getTreeItem(node) {
    const raw = node.raw;
    const hasChildren = (raw.children || []).length > 0;
    // In the hierarchy a closed root hides every type; the root opens.
    const root = raw.kind === 'type' && !this.parents.get(raw) &&
      (raw.children || []).some((c) => c.kind === 'type');
    const item = new vscode.TreeItem(
      raw.label,
      hasChildren
        ? root ? vscode.TreeItemCollapsibleState.Expanded
          : vscode.TreeItemCollapsibleState.Collapsed
        : vscode.TreeItemCollapsibleState.None
    );
    item.description = raw.detail || raw.value || '';
    item.contextValue = raw.inheritedFrom
      ? 'inherited'
      : raw.editable
      ? 'editable'
      : raw.kind;

    // One icon per kind of row. Whether it is inherited, editable or locked is
    // said by the icon's colour and the description, not by swapping the
    // icon: a tree where the same thing wears four different symbols cannot
    // be scanned.
    const tone = raw.inheritedFrom ? 'inherited' : '';
    if (raw.kind === 'type') {
      item.iconPath = icon('symbol-class');
    } else if (raw.kind === 'shape') {
      item.iconPath = icon(raw.rule ? 'symbol-event' : 'symbol-interface', tone);
    } else if (raw.kind === 'attribute') {
      item.iconPath = icon('symbol-field', tone);
    } else if (raw.kind === 'slot') {
      item.iconPath = icon('symbol-property', tone);
    } else if (raw.kind === 'raw' || raw.kind === 'rule' || raw.kind === 'rules') {
      item.iconPath = icon('symbol-event', tone);
    } else {
      item.iconPath = icon('symbol-constant', tone);
    }
    if (raw.inheritedFrom) {
      // Shown because it APPLIES here: sh:targetClass reaches subclasses, so a
      // shape on Machine validates every Filter. Not editable in place --
      // SHACL conjoins, so a constraint added on the subtype is evaluated
      // alongside this one rather than instead of it.
      item.tooltip =
        `Inherited from ${raw.inheritedClass.split('/').pop()}\n` +
        `Declared at ${raw.definedAt}\n\n` +
        'Right-click to jump there, or to declare it on this type.';
    } else if (raw.kind === 'constraint' && raw.editable) {
      item.tooltip = `${raw.parameter} = ${raw.value}\nRight-click to edit it.`;
    } else if (raw.kind === 'constraint' || raw.kind === 'raw') {
      // Shown, not offered. A tree that hid what it cannot edit would be
      // lying about what the shape contains.
      item.tooltip = raw.detail || 'raw only — edit in the .ttl file';
    }
    return item;
  }

  message(text) {
    if (this.view) {
      this.view.message = text;
    }
  }

  async getChildren(node) {
    if (node) {
      return (node.raw.children || []).map((child) => this.wrap(child));
    }
    const client = this.clientHolder.client;
    if (!client) {
      this.message('The language server is not running — run ' +
        '"SemForge: Doctor".');
      return [];
    }
    if (!this.uri) {
      this.message(noPackageMessage());
      return [];
    }
    let result;
    try {
      result = await client.sendRequest('semforge/tree',
        { uri: this.uri, detail: treeDetail() });
    } catch (error) {
      this.message(`SemForge: ${error.message || error}`);
      return [];
    }
    if (result.error) {
      this.lastError = result.error;
      this.message(`SemForge: ${result.error}`);
      return [];
    }
    this.message(undefined);
    this.lastError = undefined;
    this._index(result.roots || []);
    return this.rawRoots.map((raw) => this.wrap(raw));
  }
}

function freeText(raw) {
  return vscode.window.showInputBox({
    title: raw.parameter,
    prompt: `New value for ${raw.parameter}`,
    value: raw.value,
    validateInput: (text) =>
      text.trim().length ? undefined : 'a value is required'
  });
}

function toItems(choices) {
  const items = choices.map((choice) => ({
    label: choice.label,
    description: choice.value,
    detail: choice.detail,
    value: choice.value
  }));
  items.push({
    label: '$(edit) Enter a different value…',
    description: '',
    detail: 'anything valid in the shapes file',
    value: CUSTOM
  });
  return items;
}

async function fetchChoices(client, node, search) {
  try {
    const result = await client.sendRequest('semforge/choices', {
      uri: node.packageUri,
      path: node.raw.path,
      parameter: node.raw.parameter,
      search: search || null
    });
    return {
      choices: result.choices || [],
      note: result.note || '',
      total: result.total || 0
    };
  } catch (error) {
    return { choices: [], note: `suggestions unavailable: ${error.message}`, total: 0 };
  }
}

/**
 * Ask for the new value, offering what the model allows.
 *
 * When the candidate set fits, VS Code filters it locally as you type. When it
 * does not -- the server caps what it sends -- typing goes back to the server
 * instead, so an ontology of any size stays navigable rather than arriving as a
 * truncated list with no way to reach the rest.
 *
 * Either way the picker keeps a way out to a typed value. The suggestions are a
 * convenience, not a restriction: a list that cannot be escaped would make the
 * cooked view less capable than the file it edits.
 */
async function promptForValue(client, node) {
  const raw = node.raw;
  const first = await fetchChoices(client, node, '');

  if (!first.choices.length) {
    if (first.note) {
      vscode.window.setStatusBarMessage(`SemForge: ${first.note}`, 5000);
    }
    return freeText(raw);
  }

  const truncated = first.total > first.choices.length;
  if (!truncated) {
    const picked = await vscode.window.showQuickPick(toItems(first.choices), {
      title: `${raw.parameter} (currently ${raw.value})`,
      placeHolder: first.note || 'pick a value, or enter your own',
      matchOnDescription: true,
      matchOnDetail: true
    });
    if (!picked) {
      return undefined;
    }
    return picked.value === CUSTOM ? freeText(raw) : picked.value;
  }

  return new Promise((resolve) => {
    const quickPick = vscode.window.createQuickPick();
    quickPick.title = `${raw.parameter} (currently ${raw.value})`;
    quickPick.placeholder = first.note || 'type to search';
    quickPick.matchOnDescription = true;
    quickPick.matchOnDetail = true;
    // The server has already ranked and filtered; re-filtering locally would
    // hide entries it deliberately included.
    quickPick.items = toItems(first.choices);

    let pending;
    let generation = 0;
    quickPick.onDidChangeValue((text) => {
      clearTimeout(pending);
      const mine = ++generation;
      pending = setTimeout(async () => {
        quickPick.busy = true;
        const next = await fetchChoices(client, node, text);
        if (mine === generation) {
          quickPick.items = toItems(next.choices);
          quickPick.placeholder = next.note || 'pick a value, or enter your own';
        }
        quickPick.busy = false;
      }, 150);
    });

    let accepted = false;
    quickPick.onDidAccept(async () => {
      const picked = quickPick.selectedItems[0];
      accepted = true;
      quickPick.hide();
      if (!picked) {
        resolve(undefined);
      } else {
        resolve(picked.value === CUSTOM ? await freeText(raw) : picked.value);
      }
    });
    quickPick.onDidHide(() => {
      quickPick.dispose();
      if (!accepted) {
        resolve(undefined);
      }
    });
    quickPick.show();
  });
}

const STATUS_NOTE = {
  here: 'already constrained by this shape — edit it there',
  inherited: 'already constrained by'
};

/**
 * Which attribute to add. Every attribute the knowledge gives this type is
 * listed, the ones that cannot be added too: a picker that silently leaves out
 * the attribute you came for sends you to check whether it was ever declared.
 * Picking one of those says why instead of adding it.
 */
async function pickAttribute(client, node) {
  // On an attribute row the question is what may nest INSIDE it.
  const parentPath = node.raw.kind === 'attribute' ? node.raw.path : null;
  const result = await client.sendRequest('semforge/attributeOptions', {
    uri: node.packageUri,
    shape: node.raw.shape,
    parentPath
  });
  if (result.error) {
    vscode.window.showErrorMessage(`SemForge: ${result.error}`);
    return undefined;
  }
  const options = result.options || [];
  const items = [];
  let section;
  const targets = (result.targets || []).map((t) => t.split(/[/#:]/).pop());
  for (const option of options) {
    const heading = option.status === 'elsewhere'
      ? 'Declared for other types — adding one gives it to this type too'
      : option.status !== 'free'
      ? 'Already constrained'
      : parentPath
        ? (option.scoped ? 'Already placed inside it elsewhere'
                         : 'Allowed inside it by the knowledge')
        : option.scoped ? 'Declared for this type' : 'Declared without a domain';
    if (heading !== section) {
      items.push({ label: heading, kind: vscode.QuickPickItemKind.Separator });
      section = heading;
    }
    items.push({
      label: option.label,
      description: `${option.kind} · ${option.term}`,
      detail: option.status === 'free'
        ? option.comment || ''
        : option.status === 'elsewhere'
        ? `declared for ${option.by}${targets.length ? `; adding it extends its domain to ` +
          `${targets.join(', ')} too` : ''}`
        : `${STATUS_NOTE[option.status]}${option.by ? ' ' + option.by : ''}`,
      option
    });
  }
  // The attribute may not exist yet. Declaring it is the knowledge's business,
  // but making the author leave this picker for another view to do it was the
  // friction: the shape already says which type it is for.
  items.push({ label: '', kind: vscode.QuickPickItemKind.Separator });
  items.push({
    label: parentPath ? '$(add) New sub-attribute…' : '$(add) New attribute…',
    description: parentPath
      ? `declare it in the knowledge as carried by ${node.raw.label}, then constrain it here`
      : 'declare it in the knowledge, then constrain it here',
    create: true,
    targets: result.targets || []
  });
  const picked = await vscode.window.showQuickPick(items, {
    title: parentPath
      ? `Add a sub-attribute inside ${node.raw.label}`
      : `Add an attribute to ${node.raw.label}`,
    placeHolder: 'the attributes the knowledge says this type carries',
    matchOnDescription: true,
    matchOnDetail: true
  });
  if (!picked) {
    return undefined;
  }
  if (picked.create) {
    return { create: true, targets: picked.targets };
  }
  if (picked.option.status === 'elsewhere') {
    // Giving it to this type is a change to the knowledge, not just to this
    // shape: said first, written as the union (a second rdfs:domain triple
    // would make every carrier a member of both types).
    const owner = picked.option.by;
    const answer = await vscode.window.showWarningMessage(
      `Give ${picked.option.label} to ${targets.join(', ')} too?`,
      { modal: true,
        detail: `The knowledge declares ${picked.option.label} for ${owner}. Adding it here ` +
          `extends its rdfs:domain to "${owner} or ${targets.join(' or ')}" — written as ` +
          'owl:unionOf in its declaration — and then adds it to this shape.' },
      'Give it to this type too');
    return answer ? { ...picked.option, extendDomain: true } : undefined;
  }
  if (picked.option.status !== 'free') {
    vscode.window.showInformationMessage(
      `SemForge: ${picked.option.label} is ${picked.detail}.`
    );
    return undefined;
  }
  return picked.option;
}

function register(context, clientHolder, session) {
  const provider = new CookedTreeProvider(clientHolder);
  const view = vscode.window.createTreeView('semforgeConstraints', {
    treeDataProvider: provider
  });
  provider.view = view;
  context.subscriptions.push(view);

  // The knowledge view jumps here. Opening shacl.ttl alone would leave you to
  // find the same shape in this tree by hand, which is the work the jump exists
  // to remove -- the same reasoning as Go to Definition.
  provider.revealShape = async (shape) => {
    const canonical = provider.findCanonical({
      shape,
      path: [],
      parameter: ''
    });
    if (!canonical) {
      return false;
    }
    try {
      await view.reveal(canonical, { select: true, focus: false, expand: 2 });
      return true;
    } catch (error) {
      return false;     // not realised yet; the editor jump still happened
    }
  };

  // Selecting anything moves the .ttl to it. Every node carries its own
  // file:line -- an attribute, a single parameter, not just the shape -- so
  // this lands on the line you picked rather than the top of the block.
  context.subscriptions.push(
    view.onDidChangeSelection(async (event) => {
      const selected = event.selection && event.selection[0];
      if (!selected) {
        return;
      }
      // Every row here belongs to an entity type, and the type page says in
      // full what the row says in brief -- so a click opens it, with the
      // attribute marked, and the keyboard stays in the tree to go on browsing.
      if (treeClick() === 'page' && selected.raw.kind === 'rule') {
        // A rule is a shape of its own; its page has the query and evidence.
        await vscode.commands.executeCommand('semforge.openShapePage', selected,
          { preserveFocus: true });
      } else if (treeClick() === 'page' && (selected.raw.typeClass || selected.raw.targetClass)) {
        await vscode.commands.executeCommand('semforge.openTypePage', selected,
          { preserveFocus: true });
      } else if (selected.raw.definedAt) {
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
    session.onDidChange((uri) => provider.setPackage(uri)),
    vscode.workspace.onDidSaveTextDocument(() => provider.refresh())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.editConstraint', async (node) => {
      const raw = node && node.raw;
      if (!raw || !raw.editable) {
        return;
      }
      const value = await promptForValue(clientHolder.client, node);
      if (value === undefined) {
        return;
      }
      const result = await clientHolder.client.sendRequest(
        'semforge/setConstraint',
        {
          uri: node.packageUri,
          shape: raw.shape,
          path: raw.path,
          parameter: raw.parameter,
          value
        }
      );
      if (result.ok) {
        vscode.window.setStatusBarMessage(
          `SemForge: ${raw.parameter} = ${value} (${result.bytesChanged} byte(s) changed)`,
          4000
        );
        provider.refresh();
      } else {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      }
    }),

    vscode.commands.registerCommand('semforge.removeConstraint', async (node) => {
      const raw = node && node.raw;
      if (!raw || !raw.editable) {
        return;
      }
      const confirm = await vscode.window.showWarningMessage(
        `Remove ${raw.parameter} from ${raw.path[raw.path.length - 1]}?`,
        { modal: true },
        'Remove'
      );
      if (confirm !== 'Remove') {
        return;
      }
      const result = await clientHolder.client.sendRequest(
        'semforge/setConstraint',
        {
          uri: node.packageUri,
          shape: raw.shape,
          path: raw.path,
          parameter: raw.parameter,
          remove: true
        }
      );
      if (result.ok) {
        provider.refresh();
      } else {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      }
    }),

    vscode.commands.registerCommand('semforge.refreshTree', () =>
      provider.refresh()
    ),

    vscode.commands.registerCommand('semforge.addAttributeConstraint', async (node) => {
      const raw = node && node.raw;
      const client = clientHolder.client;
      const nests = raw && raw.kind === 'attribute';
      if (!raw || !['shape', 'attribute'].includes(raw.kind) || raw.inheritedFrom ||
          !client) {
        vscode.window.showInformationMessage(
          'SemForge: pick one of this type\'s own shapes, or one of its ' +
            'attributes, to add to.'
        );
        return;
      }
      const option = await pickAttribute(client, node);
      if (!option) {
        return;
      }
      // On an attribute row the new constraint goes INSIDE that attribute's
      // property shape: the NGSI-LD sub-attribute, hung off its node.
      const target = { shape: raw.shape, label: raw.label,
                       parentPath: nests ? raw.path : undefined };
      let done;
      if (option.create) {
        if (!option.targets.length) {
          vscode.window.showErrorMessage(
            `SemForge: ${raw.label} has no sh:targetClass, so there is no ` +
              'type to declare the attribute for.');
          return;
        }
        done = await newAttribute(client, node.packageUri,
          { ...target, entityType: option.targets[0] });
      } else {
        done = await constrainAttribute(client, node.packageUri, option, target, false);
      }
      if (done) {
        provider.refresh();
        vscode.commands.executeCommand('semforge.refreshKnowledge');
      }
    }),

    vscode.commands.registerCommand('semforge.goToDefinition', async (node) => {
      const raw = node && node.raw;
      if (!raw) {
        return;
      }
      // Navigate BOTH views. The tree is where the reader is looking, so
      // jumping only the editor leaves them to find the declaring shape by
      // hand -- which is the work this command exists to remove.
      const canonical = provider.findCanonical(raw);
      if (canonical) {
        try {
          await view.reveal(canonical, {
            select: true,
            focus: true,
            expand: 3
          });
        } catch (error) {
          // reveal can refuse for a node the view has not realised yet; the
          // editor jump below still happens.
        }
      }
      await showLocation(raw.definedAt, true);
    }),

    vscode.commands.registerCommand('semforge.overrideHere', async (node) => {
      const raw = node && node.raw;
      if (raw && raw.inheritedFrom && !raw.parameter && raw.typeClass) {
        // A summary row stands for an attribute, not one parameter: the
        // override is chosen on the type page, where every parameter is.
        vscode.window.setStatusBarMessage(
          'SemForge: choose the constraint to tighten on the type page', 5000);
        return vscode.commands.executeCommand('semforge.openTypePage',
          { raw: { targetClass: raw.typeClass }, packageUri: node.packageUri });
      }
      if (!raw || !raw.inheritedFrom || !raw.parameter) {
        vscode.window.showInformationMessage(
          'SemForge: pick an inherited constraint to declare on this type.'
        );
        return;
      }
      // The type node this constraint is being pulled down onto.
      const owner = provider.ownerOf(node);
      if (!owner) {
        vscode.window.showErrorMessage(
          'SemForge: could not tell which shape to add it to.'
        );
        return;
      }

      const value = await vscode.window.showInputBox({
        title: `${raw.parameter} on ${owner.label}`,
        prompt:
          `Inherited value is ${raw.value}. SHACL conjoins, so this can only ` +
          'make the constraint stricter.',
        value: raw.value
      });
      if (value === undefined) {
        return;
      }

      const send = (force) =>
        clientHolder.client.sendRequest('semforge/override', {
          uri: node.packageUri,
          targetShape: owner.shape,
          path: raw.path,
          parameter: raw.parameter,
          inheritedValue: raw.value,
          value,
          force
        });

      let result = await send(false);
      if (!result.ok && (result.effect === 'weaker' || result.effect === 'same')) {
        const choice = await vscode.window.showWarningMessage(
          `${raw.parameter} ${raw.value} → ${value} is ${result.effect}. ` +
            result.error,
          { modal: true },
          'Open the inherited shape',
          'Add it anyway'
        );
        if (choice === 'Open the inherited shape') {
          return vscode.commands.executeCommand('semforge.goToDefinition', node);
        }
        if (choice !== 'Add it anyway') {
          return;
        }
        result = await send(true);
      }

      if (result.ok) {
        vscode.window.setStatusBarMessage(
          `SemForge: ${raw.parameter} declared on ${owner.label} (${result.effect})`,
          5000
        );
        provider.refresh();
      } else {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      }
    })
  );

  return provider;
}

module.exports = { register, CookedTreeProvider };
