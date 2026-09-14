/*
 * The model, as a tree: the data the constraints judge.
 *
 * Two kinds of it, at the same level, because that is what `model/` holds -- the
 * declared cases of the suite, and the model instance as the scratchpad. What
 * makes this worth a view of its own rather than the JSON outline VS Code
 * already gives you is the verdicts: an entity says how many violations it
 * carries, and editing a value re-validates, so the effect of a change is
 * visible where the change was made.
 */

const vscode = require('vscode');

const { noPackageMessage } = require('./locate');
const { showLocation } = require('./reveal');

// The contextValue vocabulary, spelled out. `when: viewItem == x` matches a
// string and nothing else: a row whose contextValue drifts from what
// package.json says loses its icons silently -- no error, no log line.
const CONTEXT_BY_KIND = {
  group: 'group',
  suite: 'suite',
  type: 'type',
  example: 'example',
  entity: 'entity',
  include: 'include',
  attribute: 'attribute',
  instance: 'instance',
  dataset: 'dataset',
  meta: 'meta'
};

class ModelTreeNode {
  constructor(key, raw, packageUri) {
    this.key = key;
    this.raw = raw;
    this.packageUri = packageUri;
  }
}

/**
 * A node's address in the tree, stable across refetches.
 *
 * Identity by raw object breaks the moment anything refreshes -- and opening the
 * file a click selected DOES refresh, because the tree follows the active
 * editor. The view then cannot resolve the node being revealed and logs
 * "Failed to resolve tree node", which is exactly how the unfold-on-click
 * looked like it was doing nothing.
 */
function keyOf(raw, parentKey, position) {
  const own = raw.entity || raw.label || raw.kind;
  return `${parentKey}/${position}:${raw.kind}:${own}:${raw.datasetId || ''}`;
}

/** The attribute this row is about: the last name in its address.
 *
 * `attributePath[0]` is the TOP-level attribute, so on a sub-attribute row it
 * named the parent -- the jump would land on the wrong shape and the value
 * picker would offer the wrong class.
 */
function attributeOf(raw) {
  const address = [].concat(raw.attributePath || [], raw.path || []);
  const names = address.filter((part) => typeof part === 'string' &&
    part !== 'value' && part !== 'object' && part !== 'json' &&
    part !== 'valueList');
  return names.length ? names[names.length - 1] : undefined;
}

class ModelTreeProvider {
  constructor(clientHolder) {
    this.clientHolder = clientHolder;
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
    this.nodes = new Map();
    this.parents = new Map();
  }

  message(text) {
    if (this.view) {
      this.view.message = text;
    }
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
    const made = new ModelTreeNode(key, raw, this.uri);
    this.nodes.set(key, made);
    return made;
  }

  // reveal() refuses to work without this, and reveal is how a click unfolds
  // the row it selected.
  getParent(node) {
    return this.parents.get(node.key);
  }

  /**
   * The chain of (raw, key) from a root down to this entity's row.
   *
   * `file` decides between occurrences: one id appears in a good case and a bad
   * one, and revealing the good row for a click on the bad one would be wrong
   * in the quietest possible way.
   */
  chainToEntity(entity, file) {
    let fallback;
    const walk = (raws, parentKey, chain) => {
      for (let position = 0; position < raws.length; position += 1) {
        const raw = raws[position];
        const key = keyOf(raw, parentKey, position);
        const here = chain.concat([{ raw, key }]);
        if (raw.kind === 'entity' && raw.entity === entity) {
          if (!file || raw.file === file) {
            return here;
          }
          fallback = fallback || here;
        }
        const deeper = walk(raw.children || [], key, here);
        if (deeper) {
          return deeper;
        }
      }
      return undefined;
    };
    return walk(this.rawRoots || [], '', []) || fallback;
  }

  /**
   * Show an entity's row, expanding whatever is needed to get to it.
   *
   * reveal() only works on nodes the view has already realised, so each level
   * down to the target is fetched first. Called from the knowledge view: a row
   * saying "urn:filter:1 uses this term" should be able to show you
   * urn:filter:1.
   */
  async revealEntity(entity, file) {
    if (!this.rawRoots) {
      await this.getChildren();
    }
    let chain = this.chainToEntity(entity, file);
    if (!chain) {
      await this.getChildren();            // the tree may have moved on
      chain = this.chainToEntity(entity, file);
    }
    if (!chain || !this.view) {
      return false;
    }
    // The chain is realised here rather than by calling getChildren down it:
    // the root fetch re-validates the whole package, so one click would have
    // cost a re-validation per level. wrap() and the parents map are all
    // reveal() needs; VS Code walks the rest itself, from children it reads out
    // of the raw nodes.
    let parent;
    let target;
    for (const step of chain) {
      target = this.wrap(step.raw, step.key);
      if (parent) {
        this.parents.set(step.key, parent);
      }
      parent = target;
    }
    try {
      await this.view.reveal(target, { select: true, focus: false, expand: true });
      return true;
    } catch (error) {
      return false;                       // not rendered yet; nothing to show
    }
  }

  getTreeItem(node) {
    const raw = node.raw;
    const hasChildren = (raw.children || []).length > 0;
    const item = new vscode.TreeItem(
      raw.label || raw.kind,
      hasChildren
        ? raw.kind === 'example' && !raw.severity
          ? vscode.TreeItemCollapsibleState.Collapsed
          : vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.None
    );
    item.description = raw.detail || '';
    // What this row can be asked to do, decided by `editable` and nothing
    // else. Two earlier versions keyed on other things and each hid an edit:
    //
    //   * on the datasetId -- but every attribute has one (`@none` is the
    //     default instance, a real value), so nearly every row landed on a
    //     contextValue whose menu had no edit at all;
    //   * on the kind -- but an attribute with sub-attributes does not fold, so
    //     its value sits on an `instance` row, and hasState on the plasmacutter
    //     could not be changed while hasState on the filter could.
    //
    // Anything carrying a value is editable; a row that could carry one and is
    // locked says so; everything else keeps its structural kind.
    const series = raw.observations > 1;
    const holdsValue = ['attribute', 'dataset', 'instance', 'meta']
      .includes(raw.kind);
    if (!raw.editable) {
      item.contextValue = holdsValue
        ? 'attributeReadOnly'
        : CONTEXT_BY_KIND[raw.kind] || raw.kind;
    } else if (series) {
      item.contextValue = 'exampleSeries';
    } else if (raw.datasetId) {
      item.contextValue = 'exampleDataset';
    } else {
      // An instance, a metadata field or a nested value: editable, but not a
      // row that stands for a datasetId, so no observation can be added to it.
      item.contextValue = 'exampleEditable';
    }

    if (raw.kind === 'group') {
      // Tests and Main: the two kinds of data, judged by different rules.
      item.iconPath = new vscode.ThemeIcon(
        raw.label === 'Main' ? 'edit' : 'beaker'
      );
    } else if (raw.kind === 'suite') {
      // One test_<Shape> directory: its cases pass or they do not.
      item.iconPath = new vscode.ThemeIcon(
        raw.severity ? 'testing-failed-icon' : 'folder-library'
      );
    } else if (raw.kind === 'example') {
      // A declared case: green when it did what it says, red when it did not.
      item.iconPath = new vscode.ThemeIcon(
        raw.severity ? 'testing-failed-icon' : 'beaker'
      );
    } else if (raw.kind === 'include') {
      // A subobject. Editing it here would change every case that includes it,
      // so it is shown read-only and edited where it is declared.
      item.iconPath = new vscode.ThemeIcon('references');
    } else if (raw.kind === 'entity') {
      // A violation says the entity is wrong; a warning says we cannot be sure
      // which entity it is. Same icon for both would conflate them.
      item.iconPath = new vscode.ThemeIcon(
        raw.severity === 'violation'
          ? 'error'
          : raw.severity
          ? 'warning'
          : 'symbol-object'
      );
    } else if (raw.kind === 'type') {
      // The type decides which shapes judge the entity at all, so it reads as
      // a field rather than as grey text beside the id.
      item.iconPath = new vscode.ThemeIcon('symbol-class');
      item.description = raw.detail;
      item.tooltip = `${raw.entity} is a ${raw.detail}`;
    } else if (raw.kind === 'meta') {
      item.iconPath = new vscode.ThemeIcon('watch');
    } else if (series) {
      // A time series: the row shows the value validation reads, the children
      // are the observations behind it.
      item.iconPath = new vscode.ThemeIcon('graph-line');
      item.tooltip =
        `${raw.observations} observations for datasetId ${raw.datasetId}\n` +
        'The row shows the one validation reads (latest observedAt).\n' +
        'Right-click to add another.';
    } else if (raw.severity) {
      item.iconPath = new vscode.ThemeIcon('warning');
    } else if (raw.editable) {
      item.iconPath = new vscode.ThemeIcon('edit');
    } else {
      item.iconPath = new vscode.ThemeIcon('symbol-field');
    }

    // The id is not an address: the same one appears in several example files,
    // which is legitimate -- the file is the rest of it. So say which file.
    const lines = (raw.messages || []).slice();
    if (raw.kind === 'entity' && raw.file) {
      lines.push(`read from ${raw.file}`);
    }
    if (item.contextValue === 'attributeReadOnly') {
      // An absent pencil with no explanation reads as a broken tree. The only
      // rows left without one are rows with no value OF THEIR OWN -- the value
      // is on the rows beneath them.
      lines.push(
        'No value on this row: edit the rows beneath it. (An attribute whose ' +
          'instances carry sub-attributes has no single value of its own.)'
      );
    }
    if ((raw.sharedBy || []).length > 1) {
      lines.push(
        `Shared: this file is included by ${raw.sharedBy.length} cases ` +
          `(${raw.sharedBy.join(', ')}). An edit here changes all of them.`
      );
    }
    if (lines.length) {
      item.tooltip = lines.join('\n');
    }
    // No command on click. Clicking used to open the edit box, which is a
    // surprising thing for a single click to do -- and it replaced the one
    // thing a click should do, which is show you the row in the file. Editing
    // is the inline pencil and the context menu.
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
      result = await client.sendRequest('semforge/model', {
        uri: this.uri
      });
    } catch (error) {
      // An empty tree with no explanation is the failure mode this project
      // keeps meeting. Say what went wrong where it is visible.
      this.message(`SemForge: ${error.message || error}`);
      return [];
    }
    if (result.error) {
      this.message(`SemForge: ${result.error}`);
      return [];
    }
    this.message(undefined);
    this.parents = new Map();
    // Kept so a row can be found without the view having expanded to it: the
    // knowledge view asks for an entity by id, and that entity usually sits
    // inside a suite nobody has opened yet.
    this.rawRoots = result.roots || [];
    return this.rawRoots.map((raw, position) =>
      this.wrap(raw, keyOf(raw, '', position)));
  }
}

/**
 * Ask before changing a file more than one case includes.
 *
 * A subobject is an ordinary JSON-LD file and editing it is allowed -- refusing
 * was a restriction the format does not have. What is worth a question is the
 * reach: "a cutter running with its filter off" and "with it on" share the same
 * workpiece, so changing the workpiece changes both verdicts.
 */
async function confirmShared(raw, what) {
  const cases = raw.sharedBy || [];
  if (cases.length < 2) {
    return true;
  }
  const answer = await vscode.window.showWarningMessage(
    `${what} ${raw.label} changes ${cases.length} cases that include this file.`,
    { modal: true, detail: cases.join('\n') },
    'Edit anyway'
  );
  return answer === 'Edit anyway';
}

/**
 * The new value for an attribute: picked from the shape's classes, or typed.
 *
 * `semforge/choices` answers "what may this SHACL parameter say"; this asks the
 * other question, "what may this datum be", and the answer is a list only when
 * the shape constrains the value to a class.
 */
async function askForValue(clientHolder, node, raw) {
  const typeIt = () =>
    vscode.window.showInputBox({
      title: `${raw.label} on ${raw.entity}`,
      prompt:
        'JSON is parsed, so 42 is a number and {"@id": "..."} a node ' +
        'reference. Anything else is taken as a string.',
      value: raw.value
    });

  const attribute = attributeOf(raw);
  if (!raw.entityType || !attribute) {
    return typeIt();
  }
  let answer;
  try {
    answer = await clientHolder.client.sendRequest('semforge/valueChoices', {
      uri: node.packageUri,
      entityType: raw.entityType,
      attribute
    });
  } catch (error) {
    return typeIt();
  }
  const choices = (answer && answer.choices) || [];
  if (!choices.length) {
    return typeIt();
  }
  const picked = await vscode.window.showQuickPick(
    choices
      .map((choice) => ({
        label: choice.label,
        description: choice.detail,
        detail: choice.value === raw.value ? 'current value' : undefined,
        value: choice.value
      }))
      .concat([
        {
          label: '$(edit) Type a value',
          description: answer.note || 'not one of the listed individuals',
          value: undefined
        }
      ]),
    {
      title: `${raw.label} on ${raw.entity}`,
      placeHolder: answer.note || 'the values this attribute\'s shape allows'
    }
  );
  if (picked === undefined) {
    return undefined;
  }
  return picked.value === undefined ? typeIt() : picked.value;
}

/**
 * Which type? Only what the knowledge declares.
 *
 * An entity's type decides which shapes judge it, so a free-text box is not a
 * convenience -- it is the one field where a typo produces silence instead of
 * an error. The list is the entity hierarchy; the way out when a type really
 * is missing is to declare it, which is the last entry.
 */
async function pickEntityType(client, packageUri) {
  const answer = await client.sendRequest('semforge/entityTypes', {
    uri: packageUri
  });
  if (!answer || answer.error) {
    vscode.window.showErrorMessage(
      `SemForge: ${(answer && answer.error) || 'the types could not be read'}`
    );
    return undefined;
  }
  const types = answer.types || [];
  const items = types.map((type) => ({
    label: type.term,
    description: type.shape
      ? `judged by ${type.shape}`
      : 'no shape judges this type',
    detail: [type.isRoot ? 'the root of the hierarchy' : `under ${type.parent}`,
             `${type.instances} in the model`].join(' · '),
    type
  }));
  items.push({
    label: '$(add) New entity type…',
    description: 'declare it in the knowledge, then use it',
    create: true
  });

  const chosen = await vscode.window.showQuickPick(items, {
    placeHolder: 'Type — from the knowledge',
    matchOnDescription: true
  });
  if (!chosen) {
    return undefined;
  }
  if (!chosen.create) {
    return chosen.type;
  }
  return declareEntityType(client, packageUri, types);
}

/** Add a class to knowledge.ttl, and return it ready to use. */
async function declareEntityType(client, packageUri, types) {
  const name = await vscode.window.showInputBox({
    title: 'New entity type',
    prompt: 'Class name, e.g. Waterjetcutter — it is declared in the knowledge',
    validateInput: (text) =>
      /^[A-Za-z][\w-]*$/.test(text || '')
        ? undefined
        : 'A letter, then letters, digits, underscores or hyphens.'
  });
  if (!name) {
    return undefined;
  }
  const parent = await vscode.window.showQuickPick(
    types.map((type) => ({
      label: type.term,
      description: type.isRoot ? 'the root of the hierarchy' : '',
      type
    })),
    { placeHolder: `${name} is a kind of…` }
  );
  if (!parent) {
    return undefined;
  }
  const made = await client.sendRequest('semforge/addEntityType', {
    uri: packageUri,
    name,
    parent: parent.type.term
  });
  if (!made || !made.ok) {
    vscode.window.showErrorMessage(
      `SemForge: ${(made && made.error) || 'the type was not declared'}`
    );
    return undefined;
  }
  // Show what was written: a class added out of sight is a class nobody
  // reviews, and this one is now part of the ontology.
  await showLocation(`${made.file}:${made.line}`, false);
  return { term: made.term, label: made.label, instances: 0 };
}


/**
 * Where an attribute belongs, in the words of whatever says it.
 *
 * Two statements, and they say different things. `rdfs:domain` says which KIND
 * of node carries it: an entity class for an ordinary attribute, and for a
 * sub-attribute the class of the parent's attribute node -- `ngsild:Property`
 * or `ngsild:Relationship`, because the encoding types those nodes. The shapes
 * say WHICH attribute it nests inside, which domain cannot express.
 */
function whereItBelongs(attribute) {
  if ((attribute.parents || []).length) {
    return `a sub-attribute of ${attribute.parents.join(', ')}`;
  }
  if (attribute.carrierKind) {
    return `a sub-attribute — carried by any ${attribute.carrierKind}, ` +
      'not placed in a shape yet';
  }
  return attribute.scoped
    ? `carried by ${attribute.domain}`
    : 'no domain declared — carried by anything';
}

/**
 * Which attribute? Only what the knowledge declares for this type.
 *
 * `rdfs:domain` says which entity type carries an attribute and is inherited,
 * so a Plasmacutter is offered what a Cutter and a Machine carry. Attributes
 * declared without a domain come last rather than being hidden -- a package may
 * simply not have said.
 */
async function pickAttribute(client, packageUri, entityType, entity) {
  const answer = await client.sendRequest('semforge/attributes', {
    uri: packageUri,
    entityType: entityType || ''
  });
  if (!answer || answer.error) {
    vscode.window.showErrorMessage(
      `SemForge: ${(answer && answer.error) || 'the attributes could not be read'}`
    );
    return undefined;
  }
  const declared = answer.attributes || [];
  const items = declared.map((attribute) => ({
    label: attribute.term,
    description: [attribute.kind || 'kind from the shapes',
                  attribute.constrained ? 'constrained' : 'no shape constrains it']
      .join(' · '),
    detail: [attribute.comment, whereItBelongs(attribute)]
      .filter(Boolean).join(' — '),
    attribute
  }));
  items.push({
    label: '$(add) New attribute…',
    description: 'declare it in the knowledge, then use it',
    create: true
  });

  const chosen = await vscode.window.showQuickPick(items, {
    placeHolder: `Attribute for ${entity} — from the knowledge`,
    matchOnDescription: true
  });
  if (!chosen) {
    return undefined;
  }
  if (!chosen.create) {
    return chosen.attribute;
  }
  return declareAttribute(client, packageUri, entityType);
}

/** Declare an attribute in knowledge.ttl, and return it ready to use. */
async function declareAttribute(client, packageUri, entityType) {
  const name = await vscode.window.showInputBox({
    title: 'New attribute',
    prompt: 'Name, e.g. hasPressure — it is declared in the knowledge',
    validateInput: (text) =>
      /^[A-Za-z][\w-]*$/.test((text || '').split(':').pop())
        ? undefined
        : 'A letter, then letters, digits, underscores or hyphens.'
  });
  if (!name) {
    return undefined;
  }
  // Property or Relationship is not a style choice: it decides which key
  // carries the payload and which half of the encoding a shape must constrain.
  const kind = await vscode.window.showQuickPick(
    [{ label: 'Property', description: 'a value — a literal, or a vocabulary term as {"@id": …}' },
     { label: 'Relationship', description: 'another entity, by its id' }],
    { placeHolder: `${name} carries…` }
  );
  if (!kind) {
    return undefined;
  }
  const label = await vscode.window.showInputBox({
    title: `What is ${name}?`,
    prompt: 'One line, for whoever reads the ontology next. Optional.'
  });
  if (label === undefined) {
    return undefined;
  }
  const made = await client.sendRequest('semforge/addAttributeTerm', {
    uri: packageUri,
    name,
    kind: kind.label,
    domain: entityType,
    label
  });
  if (!made || !made.ok) {
    vscode.window.showErrorMessage(
      `SemForge: ${(made && made.error) || 'the attribute was not declared'}`
    );
    return undefined;
  }
  await showLocation(`${made.file}:${made.line}`, false);
  return { term: made.term, kind: made.kind, label: made.label };
}


function register(context, clientHolder, session, onChanged) {
  const provider = new ModelTreeProvider(clientHolder);
  const view = vscode.window.createTreeView('semforgeModel', {
    treeDataProvider: provider
  });
  provider.view = view;
  context.subscriptions.push(view);

  // Selecting a row moves the .jsonld to it. Every node carries its own
  // file:line now, so this lands on the entity, the attribute or the single
  // observation you picked.
  context.subscriptions.push(
    view.onDidChangeSelection(async (event) => {
      const selected = event.selection && event.selection[0];
      if (!selected) {
        return;
      }
      // Unfold first, move the editor second. Opening a file can refresh a
      // tree, and a refresh makes VS Code drop its element handles -- a reveal
      // after that resolves nothing and logs "Failed to resolve tree node",
      // which is how the unfold looked like it was doing nothing.
      if ((selected.raw.children || []).length) {
        try {
          await view.reveal(selected, { expand: true, select: false, focus: false });
        } catch (error) {
          // reveal throws if the node is gone after a refresh; nothing to do.
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
    vscode.commands.registerCommand('semforge.editValue', async (node) => {
      const raw = node && node.raw;
      if (!raw || !raw.editable) {
        return;
      }
      if (!(await confirmShared(raw, 'Editing'))) {
        return;
      }
      // When the shape says sh:class, the value is an individual of that
      // class -- so offer those rather than asking someone to remember the
      // IRI. Typing it out by hand is how `{"object": ...}` vs `{"value":
      // ...}` mistakes get made.
      const value = await askForValue(clientHolder, node, raw);
      if (value === undefined) {
        return;
      }
      const result = await clientHolder.client.sendRequest('semforge/setValue', {
        uri: node.packageUri,
        entity: raw.entity,
        path: raw.path,
        file: raw.file,
        value
      });
      if (result.ok) {
        vscode.window.setStatusBarMessage(
          `SemForge: ${raw.label} ${result.old} → ${result.new}`,
          5000
        );
        provider.refresh();
        if (onChanged) {
          onChanged();
        }
      } else {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      }
    }),

    vscode.commands.registerCommand('semforge.goToShape', async (node) => {
      const raw = node && node.raw;
      const attribute = raw && attributeOf(raw);
      if (!raw || !attribute || !raw.entityType) {
        vscode.window.showWarningMessage(
          'SemForge: this row has no attribute and entity type to look a shape ' +
            `up with (attribute ${attribute || '—'}, type ` +
            `${(raw && raw.entityType) || '—'}). Reload the window if the ` +
            'language server is older than the extension.'
        );
        return;
      }
      const ask = async (create) => {
        try {
          return await clientHolder.client.sendRequest('semforge/shapeFor', {
            uri: node.packageUri,
            entityType: raw.entityType,
            attribute,
            create
          });
        } catch (error) {
          // A rejected request used to vanish: no jump, no message, nothing in
          // the log. That is indistinguishable from the command not running.
          return { ok: false, error: `${error.message || error}` };
        }
      };
      let result = await ask(false);
      if (!result.ok && result.exists === false) {
        // Nothing constrains this attribute. Offer to write the empty property
        // shape, because a jump to a rule that does not exist is useless --
        // but write it only on a yes: this edits shacl.ttl.
        const answer = await vscode.window.showInformationMessage(
          `No shape constrains ${attribute} on ${raw.entityType}.`,
          { modal: true },
          'Create an empty one'
        );
        if (answer !== 'Create an empty one') {
          return;
        }
        result = await ask(true);
      }
      if (!result.ok) {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
        return;
      }
      await showLocation(`${result.file}:${result.line}`, true);
      if (result.how === 'created') {
        vscode.window.showInformationMessage(
          `SemForge: added an empty sh:property for ${attribute} in ` +
            `${result.shapeName}. It constrains nothing yet — add parameters ` +
            'in the Constraints view.'
        );
        if (onChanged) {
          onChanged();
        }
      } else if (result.inherited) {
        vscode.window.setStatusBarMessage(
          `SemForge: ${attribute} is constrained by ${result.shapeName}, ` +
            'which this type inherits from.',
          6000
        );
      }
    }),

    vscode.commands.registerCommand('semforge.refreshModel', () =>
      provider.refresh()
    ),

    vscode.commands.registerCommand('semforge.addAttribute', async (node) => {
      const raw = node && node.raw;
      if (!raw || raw.kind !== 'entity') {
        return;
      }
      // Same rule as the type, one level down: the attribute's NAME is what a
      // shape's sh:path matches, so one the knowledge has never heard of is
      // not a broken document but an invisible one. So it is chosen, not
      // typed -- and a missing one is declared in the knowledge first.
      const attribute = await pickAttribute(
        clientHolder.client, node.packageUri, raw.entityType, raw.entity);
      if (!attribute) {
        return;
      }
      const value = await vscode.window.showInputBox({
        title: `Value for ${attribute.term}`,
        prompt: attribute.kind === 'Relationship'
          ? 'An entity IRI — a Relationship points at another entity.'
          : 'JSON is parsed. A literal, or {"@id": "…"} for a vocabulary term.'
      });
      if (value === undefined) {
        return;
      }
      const result = await clientHolder.client.sendRequest(
        'semforge/addAttribute',
        {
          uri: node.packageUri,
          entity: raw.entity,
          file: raw.file,
          name: attribute.term,
          kind: attribute.kind || '',
          value
        }
      );
      if (result.ok) {
        vscode.window.setStatusBarMessage(
          `SemForge: ${attribute.term} added as ${result.kind}`,
          5000
        );
        provider.refresh();
        if (onChanged) {
          onChanged();
        }
      } else {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      }
    }),

    vscode.commands.registerCommand('semforge.addEntity', async (node) => {
      const raw = node && node.raw;
      const file = raw && (raw.file || (raw.children || []).map((c) => c.file)[0]);
      if (!file) {
        return;
      }
      // The type comes FIRST, and it comes from the knowledge. Typing one by
      // hand is the quietest way to break a model: no shape targets an
      // undeclared class, so every constraint stays silent and the entity
      // reads as validated. A type that is genuinely missing is added to the
      // ontology here, and used afterwards.
      const entityType = await pickEntityType(clientHolder.client, node.packageUri);
      if (!entityType) {
        return;
      }
      const id = await vscode.window.showInputBox({
        title: `New ${entityType.label}`,
        prompt: 'id — a urn, unique within this file',
        value: `urn:${entityType.label.toLowerCase()}:${entityType.instances + 1}`
      });
      if (!id) {
        return;
      }
      const result = await clientHolder.client.sendRequest('semforge/addEntity', {
        uri: node.packageUri,
        file,
        id,
        entityType: entityType.term
      });
      if (result.ok) {
        provider.refresh();
        if (onChanged) {
          onChanged();
        }
      } else {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      }
    }),

    vscode.commands.registerCommand('semforge.addObservation', async (node) => {
      const raw = node && node.raw;
      if (!raw || !raw.attributePath || !raw.attributePath.length) {
        return;
      }
      if (!(await confirmShared(raw, 'Adding an observation to'))) {
        return;
      }
      const value = await vscode.window.showInputBox({
        title: `New observation of ${raw.label}`,
        prompt: `datasetId ${raw.datasetId || '@none'} — JSON is parsed`,
        value: raw.value
      });
      if (value === undefined) {
        return;
      }
      const observedAt = await vscode.window.showInputBox({
        title: 'observedAt',
        prompt:
          'ISO 8601 UTC with milliseconds. Later than the current one, or it ' +
          'will not become the value validation reads.',
        value: new Date().toISOString().replace(/\.\d{3}Z$/, '.000Z')
      });
      if (observedAt === undefined) {
        return;
      }
      const result = await clientHolder.client.sendRequest(
        'semforge/addObservation',
        {
          uri: node.packageUri,
          entity: raw.entity,
          attributePath: raw.attributePath,
          datasetId: raw.datasetId,
          file: raw.file,
          value,
          observedAt
        }
      );
      if (result.ok) {
        vscode.window.setStatusBarMessage(
          `SemForge: ${raw.label} now has ${result.count} observation(s)`,
          5000
        );
        provider.refresh();
        if (onChanged) {
          onChanged();
        }
      } else {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
      }
    })
  );

  return provider;
}

module.exports = { register, ModelTreeProvider, CONTEXT_BY_KIND };
