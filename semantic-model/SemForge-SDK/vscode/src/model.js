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
const { askDatasetId } = require('./datasetid');

const { noPackageMessage } = require('./locate');
const { showLocation, treeDetail, treeClick, icon } = require('./reveal');

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
// The model's own data in the Instances view. "Model data" is what an older
// language server called it in summary mode.
const DATA = ['Main', 'Model data'];

/** The test case a row belongs to (the row itself, or an ancestor). */
function caseOf(provider, node) {
  for (let at = node; at; at = provider.getParent(at)) {
    if (at.raw.kind === 'example') {
      return at.raw.file ? at : undefined;
    }
  }
  return undefined;
}

/**
 * The model's own data holding a node, or undefined. In the Instances view that
 * is the "Main" GROUP, under it one example per model file
 * (labelled by the file, e.g. main.jsonld) -- an example without a case file.
 */
function modelOf(provider, node) {
  for (let at = node; at; at = provider.getParent(at)) {
    if (at.raw.kind === 'example') {
      return at.raw.file ? undefined : at;
    }
    if (at.raw.kind === 'group' && DATA.includes(at.raw.label)) {
      return at;
    }
  }
  return undefined;
}

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
        ? (raw.kind === 'example' && !raw.severity)
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
    if (raw.kind === 'group' && raw.label === 'Tests') {
      item.contextValue = 'testsGroup';      // New suite… / New test case… on it
    } else if (!raw.editable) {
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

    // One icon per kind: beaker for the tests, an object for an entity, a
    // field for an attribute. Pass, fail and warning are the icon's colour
    // and the description's words -- never a different icon, or a failing
    // case would stop looking like a case.
    const tone = raw.severity === 'violation' || raw.severity === 'error'
      ? 'error' : raw.severity ? 'warning' : '';
    if (raw.kind === 'group') {
      // Tests and Main: the two kinds of data, judged by different rules.
      item.iconPath = icon(DATA.includes(raw.label) ? 'symbol-object' : 'beaker', tone);
    } else if (raw.kind === 'suite' || raw.kind === 'example') {
      // A declared case: green when it did what it says, red when it did not.
      item.iconPath = icon('beaker', raw.severity ? 'error' : 'ok');
    } else if (raw.kind === 'include' || raw.kind === 'entity') {
      // An include is a subobject. Editing it here would change every case
      // that includes it, so it is shown read-only and edited where declared.
      item.iconPath = icon('symbol-object', tone);
    } else if (raw.kind === 'type') {
      // The type decides which shapes judge the entity at all, so it reads as
      // a field rather than as grey text beside the id.
      item.iconPath = icon('symbol-class');
      item.description = raw.detail;
      item.tooltip = `${raw.entity} is a ${raw.detail}`;
    } else {
      // Attributes, their instances, metadata and time series alike: what
      // each one is goes in the description ("3 observations").
      item.iconPath = icon('symbol-field', tone);
      if (series) {
        if (!/observation/.test(item.description || '')) {
          item.description = [item.description, `${raw.observations} observations`]
            .filter(Boolean).join(' · ');
        }
        item.tooltip =
          `${raw.observations} observations for datasetId ${raw.datasetId}\n` +
          'The row shows the one validation reads (latest observedAt).\n' +
          'Right-click to add another.';
      }
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
        uri: this.uri,
        detail: treeDetail()
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
/**
 * What Remove… on a row takes out, as the server's address: the whole
 * attribute (an attribute row), the instances of one datasetId (a dataset
 * row), one observation (an instance row in a series), or one metadata key.
 */
function removalOf(raw) {
  const name = (steps) => String([...steps].reverse().find((s) => typeof s === 'string') || '')
    .split(/[/#:]/).pop();
  const attributePath = raw.attributePath || [];
  if (raw.kind === 'attribute' && attributePath.length) {
    return { path: attributePath, what: name(attributePath) };
  }
  if (raw.kind === 'dataset' && attributePath.length) {
    return { path: attributePath, dataset: raw.datasetId,
      what: raw.label && raw.label.includes('[') ? raw.label
        : `${name(attributePath)} (${raw.datasetId === '@none' ? 'default' : raw.datasetId})` };
  }
  const path = raw.path || [];
  if (raw.kind === 'instance' && path.length >= 3) {
    return { path, what: `this observation of ${name(path.slice(0, -2))}` };
  }
  if (raw.kind === 'meta' && path.length) {
    return { path, what: `${raw.label} of ${name(path.slice(0, -2))}` };
  }
  return undefined;
}

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
 * The value for an attribute: picked from the shape's classes, or typed.
 *
 * `semforge/choices` answers "what may this SHACL parameter say"; this asks the
 * other question, "what may this datum be", and the answer is a list only when
 * the shape constrains the value to a class.
 *
 * Shared by editing an existing value and by adding a new attribute. Adding
 * used to be a bare text box, so the one flow where you are LEAST likely to
 * know the vocabulary -- a brand-new entity, an attribute you have just
 * inherited -- was the one that offered no help. The shape knows: hasState on
 * anything descending from Machine is an individual of base:MachineState.
 */
async function chooseValue(client, packageUri, entityType, attribute, options) {
  const settings = options || {};
  const relationship = !!settings.relationship;
  const typeIt = () =>
    vscode.window.showInputBox({
      title: settings.title,
      prompt: settings.prompt || (relationship
        ? 'Any IRI — urn:…, https://… — even one no entity has yet.'
        : 'JSON is parsed, so 42 is a number and {"@id": "..."} a node ' +
          'reference. Anything else is taken as a string.'),
      value: settings.current,
      validateInput: relationship ? iriProblem : undefined
    });

  if ((!entityType || !attribute) && !relationship) {
    return typeIt();
  }
  let answer;
  try {
    answer = await client.sendRequest('semforge/valueChoices', {
      uri: packageUri, entityType: entityType || '', attribute: attribute || '',
      relationship, file: settings.file || ''
    });
  } catch (error) {
    answer = undefined;
  }
  answer = answer || { choices: [] };
  const choices = answer.choices || [];
  const others = answer.others || [];
  if (!choices.length && !others.length) {
    return typeIt();
  }

  const row = (choice) => ({
    label: choice.label,
    description: choice.detail,
    detail: choice.value === settings.current ? 'current value' : undefined,
    value: choice.value
  });
  const fixed = [];
  if (choices.length) {
    fixed.push({ label: relationship ? 'what the shape asks for' : 'the shape allows',
      kind: vscode.QuickPickItemKind.Separator });
    fixed.push(...choices.map(row));
  }
  if (others.length) {
    // A relationship may point at any entity. The shape (sh:class) judges the
    // choice afterwards; it does not decide what may be written.
    fixed.push({ label: 'other entities — the shape may flag these',
      kind: vscode.QuickPickItemKind.Separator });
    fixed.push(...others.map(row));
  }
  fixed.push({ label: '', kind: vscode.QuickPickItemKind.Separator });
  fixed.push({
    label: '$(edit) Type a value',
    description: relationship ? 'any IRI' : (answer.note || 'not one of the listed values'),
    alwaysShow: true, typeIt: true
  });

  // Typing in the list used to only filter it: an IRI nobody has yet matched
  // nothing, and Enter did nothing. Now what is typed is an entry of its own.
  return new Promise((resolve) => {
    const pick = vscode.window.createQuickPick();
    pick.title = settings.title;
    pick.placeholder = relationship
      ? 'pick an entity, or type any IRI'
      : (answer.note || 'pick a value, or type one');
    pick.matchOnDescription = true;
    pick.items = fixed;
    let done = false;
    const finish = (value) => {
      if (!done) {
        done = true;
        resolve(value);
        pick.hide();
      }
    };
    pick.onDidChangeValue((text) => {
      const typed = text.trim();
      if (!typed || fixed.some((item) => item.value === typed)) {
        pick.items = fixed;
        return;
      }
      const problem = relationship ? iriProblem(typed) : undefined;
      pick.items = [problem
        ? { label: `$(error) ${typed}`, description: problem, alwaysShow: true, invalid: true }
        : { label: `$(edit) Use ${typed}`, alwaysShow: true, value: typed,
          description: relationship ? 'typed — any IRI' : 'typed — JSON is parsed' }]
        .concat(fixed);
    });
    pick.onDidAccept(async () => {
      const chosen = pick.selectedItems[0];
      if (!chosen || chosen.invalid) {
        return;                        // stays open: fix the IRI or pick one
      }
      if (chosen.typeIt) {
        done = true;
        pick.hide();
        resolve(await typeIt());
        return;
      }
      finish(chosen.value);
    });
    pick.onDidHide(() => {
      finish(undefined);
      pick.dispose();
    });
    pick.show();
  });
}

/**
 * Why this is not an IRI, or undefined when it is. The one check a
 * relationship's target gets: a scheme, a colon, and no spaces or characters
 * an IRI cannot hold. Whether an entity has that id is not asked -- linking to
 * one that is not in this package is allowed.
 */
function iriProblem(text) {
  const value = (text || '').trim();
  if (!/^[A-Za-z][A-Za-z0-9+.-]*:/.test(value)) {
    return 'not an IRI: it needs a scheme, e.g. urn:… or https://…';
  }
  if (/[\s<>"{}|\\^`]/.test(value)) {
    return 'not an IRI: no spaces or <>"{}|\\^` characters';
  }
  if (value.endsWith(':')) {
    return 'not an IRI: nothing after the scheme';
  }
  return undefined;
}

/** The new value for an attribute row that already exists. */
async function askForValue(clientHolder, node, raw) {
  const path = [].concat(raw.path || []);
  return chooseValue(clientHolder.client, node.packageUri, raw.entityType,
                     attributeOf(raw), {
                       title: `${raw.label} on ${raw.entity}`,
                       current: raw.value,
                       relationship: path[path.length - 1] === 'object',
                       file: raw.file
                     });
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

/**
 * Add a class to knowledge.ttl, and return it ready to use. `parent` (an
 * entity type's term or IRI) skips the "is a kind of…" question: New subtype…
 * already knows it.
 */
async function declareEntityType(client, packageUri, types, parent) {
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
  const picked = parent ? { type: { term: parent } } : await vscode.window.showQuickPick(
    types.map((type) => ({
      label: type.term,
      description: type.isRoot ? 'the root of the hierarchy' : '',
      type
    })),
    { placeHolder: `${name} is a kind of…` }
  );
  if (!picked) {
    return undefined;
  }
  const made = await client.sendRequest('semforge/addEntityType', {
    uri: packageUri,
    name,
    parent: picked.type.term
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
  return { term: made.term, iri: made.iri, label: made.label, parent: made.parent,
    instances: 0 };
}

/**
 * New entity type… / New subtype…: declare a class in the knowledge without
 * having to add an entity of it. A subtype is checked by every shape of its
 * parent already (class targets include subclasses); what it lacks is a shape
 * of its own, so that is the first thing offered.
 */
async function newEntityType(clientHolder, session, node) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  if (!client || !packageUri) {
    vscode.window.showWarningMessage(
      'SemForge: no package is open, or the language server is not running.');
    return undefined;
  }
  const raw = (node && node.raw) || {};
  const parent = raw.targetClass || raw.typeClass || raw.iri || undefined;
  let types = [];
  if (!parent) {
    const answer = await client.sendRequest('semforge/entityTypes', { uri: packageUri });
    if (!answer || answer.error) {
      vscode.window.showErrorMessage(
        `SemForge: ${(answer && answer.error) || 'the types could not be read'}`);
      return undefined;
    }
    types = answer.types || [];
  }
  const made = await declareEntityType(client, packageUri, types, parent);
  if (!made) {
    return undefined;
  }
  for (const command of ['semforge.refreshTree', 'semforge.refreshKnowledge',
    'semforge.refreshModel']) {
    vscode.commands.executeCommand(command);
  }
  const next = await vscode.window.showInformationMessage(
    `SemForge: ${made.label} declared as a kind of ${made.parent}. Every shape of ` +
      `${made.parent} checks it already; give it a shape of its own for rules only it has.`,
    'Create its shape', 'Open its type page');
  if (next === 'Create its shape') {
    await vscode.commands.executeCommand('semforge.newShape',
      { raw: { kind: 'type', targetClass: made.iri, label: made.label }, packageUri });
  } else if (next === 'Open its type page') {
    await vscode.commands.executeCommand('semforge.openTypePage',
      { raw: { targetClass: made.iri }, packageUri });
  }
  return made;
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
async function pickAttribute(client, packageUri, entityType, entity, parent) {
  // With `parent` the question is what may nest inside that attribute: the
  // knowledge's answer for a sub-attribute, not the entity type's.
  const answer = await client.sendRequest('semforge/attributes', parent
    ? { uri: packageUri, parent }
    : { uri: packageUri, entityType: entityType || '' });
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
    label: parent ? '$(add) New sub-attribute…' : '$(add) New attribute…',
    description: parent
      ? `declare it in the knowledge as carried by ${parent}, then use it`
      : 'declare it in the knowledge, then use it',
    create: true
  });

  const chosen = await vscode.window.showQuickPick(items, {
    placeHolder: parent
      ? `Sub-attribute inside ${parent} on ${entity} — from the knowledge`
      : `Attribute for ${entity} — from the knowledge`,
    matchOnDescription: true
  });
  if (!chosen) {
    return undefined;
  }
  if (!chosen.create) {
    return chosen.attribute;
  }
  return declareAttribute(client, packageUri, parent || entityType);
}

/**
 * Which namespace the new attribute lives in. Returns a prefix (or IRI), ''
 * for the server's default -- the carrying type's namespace -- or undefined
 * when cancelled.
 *
 * Not asked when the name already says (`iffFilterEntities:hasX`), or when the
 * package offers only one place. Otherwise the default comes first and each
 * entry shows the full name it would produce, because "iffFilterEntities" is
 * an abstraction and `iffFilterEntities:hasPressure` is what gets written.
 */
async function pickNamespace(client, packageUri, entityType, name) {
  if (name.includes(':')) {
    return '';
  }
  let answer;
  try {
    answer = await client.sendRequest('semforge/attributeNamespaces',
      { uri: packageUri, domain: entityType });
  } catch (error) {
    return '';      // an older server: its default is the carrier's namespace
  }
  const spaces = (answer && answer.namespaces) || [];
  if (spaces.length < 2) {
    return '';
  }
  const items = [];
  let section;
  for (const space of spaces) {
    const heading = space.default || space.attributes
      ? 'Where this package keeps attributes' : 'Other namespaces in this package';
    if (heading !== section) {
      items.push({ label: heading, kind: vscode.QuickPickItemKind.Separator });
      section = heading;
    }
    items.push({
      label: space.prefix ? `${space.prefix}:${name}` : `<${space.namespace}${name}>`,
      description: space.default
        ? `default — the namespace of ${entityType.split(':').pop()}`
        : space.attributes ? `holds ${space.attributes} attribute(s)` : '',
      detail: space.namespace,
      value: space.default ? '' : (space.prefix || space.namespace)
    });
  }
  const picked = await vscode.window.showQuickPick(items, {
    title: `Namespace for ${name}`,
    placeHolder: 'the default is the namespace of the type that carries it',
    matchOnDescription: true,
    matchOnDetail: true
  });
  return picked ? picked.value : undefined;
}

/** Declare an attribute in knowledge.ttl, and return it ready to use. */
async function declareAttribute(client, packageUri, entityType, given) {
  // `given` comes from a quick fix on a use of an undeclared term: the name
  // and namespace are already settled by that use, so asking again would only
  // invite a typo that leaves the use as undeclared as before.
  const name = given && given.name ? given.name : await vscode.window.showInputBox({
    title: 'New attribute',
    prompt: 'Name, e.g. hasPressure — or prefix:hasPressure to choose its ' +
      'namespace. It is declared in the knowledge.',
    validateInput: (text) =>
      /^[A-Za-z][\w-]*$/.test((text || '').split(':').pop())
        ? undefined
        : 'A letter, then letters, digits, underscores or hyphens.'
  });
  if (!name) {
    return undefined;
  }
  const namespace = given && given.namespace
    ? given.namespace
    : await pickNamespace(client, packageUri, entityType, name);
  if (namespace === undefined) {
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
    label,
    namespace: namespace || null
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
      // A row inside a test case opens the case page, its entity marked: the
      // page shows the claims and the data together, which the .jsonld does
      // not. Rows under Main open the Main page instead.
      const holder = treeClick() === 'page' ? caseOf(provider, selected) : undefined;
      const model = treeClick() === 'page' && !holder ? modelOf(provider, selected) : undefined;
      if (holder) {
        await vscode.commands.executeCommand('semforge.openCasePage', holder,
          { focus: selected.raw.entity || undefined, preserveFocus: true });
      } else if (model) {
        await vscode.commands.executeCommand('semforge.openModelPage', model,
          { focus: selected.raw.entity || undefined, preserveFocus: true });
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

    vscode.commands.registerCommand('semforge.removeCaseValue', async (node) => {
      const raw = node && node.raw;
      const target = raw && removalOf(raw);
      if (!target || !clientHolder.client) {
        vscode.window.showWarningMessage('SemForge: Remove… works on an attribute of an entity.');
        return undefined;
      }
      const cases = raw.sharedBy || [];
      const answer = await vscode.window.showWarningMessage(
        `Remove ${target.what} from ${raw.entity}?`,
        { modal: true, detail: [
          cases.length > 1 ? `This file is included by ${cases.length} cases — all of them ` +
            `change:\n${cases.join('\n')}` : '',
          'A shape that requires it reports it missing — in a bad case, that can be the point.'
        ].filter(Boolean).join('\n\n') },
        'Remove');
      if (answer !== 'Remove') {
        return undefined;
      }
      const result = await clientHolder.client.sendRequest('semforge/removeCaseValue', {
        uri: node.packageUri, entity: raw.entity, path: target.path, file: raw.file,
        dataset: target.dataset });
      if (!result.ok) {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
        return undefined;
      }
      vscode.window.setStatusBarMessage(`SemForge: ${result.removed} removed from ${raw.entity}`,
        5000);
      provider.refresh();
      if (onChanged) {
        onChanged();
      }
      return result;
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

    vscode.commands.registerCommand('semforge.addSubAttribute', async (node) => {
      const raw = node && node.raw;
      if (!raw || !['attribute', 'dataset'].includes(raw.kind) ||
          !(raw.attributePath || []).length) {
        vscode.window.showInformationMessage(
          'SemForge: pick an attribute in the data to add a sub-attribute to.');
        return;
      }
      return addAttributeTo(node, {
        under: raw.attributePath,
        dataset: raw.datasetId || null,
        parent: raw.attributePath.filter((s) => typeof s === 'string').pop()
      });
    }),

    vscode.commands.registerCommand('semforge.addAttribute', async (node) => {
      const raw = node && node.raw;
      if (!raw || raw.kind !== 'entity') {
        return;
      }
      return addAttributeTo(node);
    })
  );

  /**
   * Add an attribute to an entity -- or, with `nested`, a sub-attribute inside
   * the attribute instance it addresses. One flow for both, so a sub-attribute
   * is picked from the knowledge, declared first when missing, and given a
   * value exactly as an attribute is.
   */
  async function addAttributeTo(node, nested) {
    const raw = node.raw;
    // Same rule as the type, one level down: the attribute's NAME is what a
    // shape's sh:path matches, so one the knowledge has never heard of is
    // not a broken document but an invisible one. So it is chosen, not
    // typed -- and a missing one is declared in the knowledge first.
    const attribute = await pickAttribute(
      clientHolder.client, node.packageUri, raw.entityType, raw.entity,
      nested && nested.parent);
    if (!attribute) {
      return;
    }
    // An attribute is (entity, name, datasetId), so one the entity already
    // has is simply another instance. Asked every time; empty is the default
    // instance, and only a datasetId the attribute already has is refused.
    const here = (raw.children || []).find((child) => child.kind === 'attribute' &&
      (child.attributePath || []).slice(-1)[0] === attribute.term);
    const taken = here ? (here.datasets && here.datasets.length ? here.datasets
      : [here.datasetId || '@none']) : [];
    const name = attribute.term.split(/[:/#]/).pop();
    let number = 2;
    while (taken.some((d) => d.endsWith(`${name}-${number}`))) {
      number += 1;
    }
    const datasetId = await askDatasetId(clientHolder.client, node.packageUri, {
      title: `${attribute.term} on ${raw.entity}: datasetId`,
      taken, allowDefault: true, observations: true,
      suggestion: `${name}-${number}`
    });
    if (datasetId === undefined) {
      return;
    }
    // A datasetId it already has: another observation of that instance, so
    // it needs a time none of them has -- validation reads the latest.
    let observedAt = null;
    if (taken.includes(datasetId || '@none')) {
      observedAt = await require('./timestamps').pickStamp({
        title: `${attribute.term} ${datasetId || '(default)'} again: when was it observed?`,
        removable: false });
      if (!observedAt) {
        return;
      }
    }
    // The shape decides what this may be, and it is inherited -- hasState
    // on anything descending from Machine takes an individual of
    // base:MachineState. Asking the server for those beats a text box in
    // exactly the case where a text box is worst: a new entity carrying an
    // attribute you have just inherited.
    const value = await chooseValue(
      clientHolder.client, node.packageUri, raw.entityType, attribute.term,
      {
        title: `${attribute.term} on ${raw.entity}`,
        relationship: attribute.kind === 'Relationship',
        file: raw.file,
        prompt: attribute.kind === 'Relationship'
          ? 'An entity IRI — a Relationship points at another entity.'
          : 'JSON is parsed. A literal, or {"@id": "…"} for a vocabulary term.'
      });
    if (value === undefined) {
      return;
    }
    // Its unit, when the shape names the units it may say -- the allowed
    // ones first. Otherwise none is asked: Unit… on the row sets one.
    let unitCode = null;
    if (attribute.kind !== 'Relationship') {
      let shaped;
      try {
        shaped = await clientHolder.client.sendRequest('semforge/units', {
          uri: node.packageUri, entityType: raw.entityType, attribute: attribute.term });
      } catch (error) {
        shaped = undefined;       // an older server: no units to offer
      }
      if (shaped && shaped.ok && (shaped.allowed || []).length) {
        const code = await require('./units').pickUnit(clientHolder.client, node.packageUri, {
          title: `Unit of ${attribute.term} on ${raw.entity}`, allowed: shaped.allowed,
          current: shaped.allowed[0], none: !shaped.required });
        if (code === undefined) {
          return;
        }
        unitCode = code || null;
      }
    }
    const result = await clientHolder.client.sendRequest(
      'semforge/addAttribute',
      {
        uri: node.packageUri,
        entity: raw.entity,
        file: raw.file,
        name: attribute.term,
        kind: attribute.kind || '',
        value,
        under: nested ? nested.under : null,
        underDataset: nested ? nested.dataset : null,
        datasetId: datasetId.trim() || null,
        unitCode,
        observedAt
      }
    );
    if (result.ok) {
      vscode.window.setStatusBarMessage(
        `SemForge: ${attribute.term} added as ${result.kind}` +
          (datasetId.trim() ? ` (datasetId ${datasetId.trim()})` : ''),
        5000
      );
      provider.refresh();
      if (onChanged) {
        onChanged();
      }
    } else {
      vscode.window.showErrorMessage(`SemForge: ${result.error}`);
    }
  }

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.newEntityType',
      () => newEntityType(clientHolder, session)),
    vscode.commands.registerCommand('semforge.newSubtype',
      (node) => newEntityType(clientHolder, session, node)),

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
      // When it was observed -- later than the current one, or it is not
      // the value validation reads. An observation needs a time: without
      // one it would count as now and supersede the rest.
      const observedAt = await require('./timestamps').pickStamp({
        title: `observedAt of the new observation of ${raw.label}`, removable: false });
      if (!observedAt) {
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
    }),

    // Another instance of an attribute: the same attribute under a new
    // datasetId. NGSI-LD identifies an attribute by (entity, name, datasetId),
    // so this is what sh:minCount and sh:maxCount count -- unlike an
    // observation, which is one instance seen again.
    vscode.commands.registerCommand('semforge.addInstance', async (node) => {
      const raw = node && node.raw;
      if (!raw || !raw.attributePath || !raw.attributePath.length) {
        return;
      }
      if (!(await confirmShared(raw, 'Adding an instance to'))) {
        return;
      }
      const name = String(raw.attributePath[raw.attributePath.length - 1])
        .split(/[:/#]/).pop();
      const known = (raw.datasets || []).concat(raw.datasetId ? [raw.datasetId] : []);
      let number = 2;
      while (known.some((d) => d.endsWith(`${name}-${number}`))) {
        number += 1;
      }
      // A copy of the current instance, under the datasetId picked here.
      const datasetId = await askDatasetId(clientHolder.client, node.packageUri, {
        title: `New instance of ${name} on ${raw.entity}: datasetId`,
        taken: known, allowDefault: false,
        suggestion: `${name}-${number}`
      });
      if (!datasetId) {
        return;
      }
      const result = await clientHolder.client.sendRequest('semforge/addInstance', {
        uri: node.packageUri, entity: raw.entity, attributePath: raw.attributePath,
        datasetId: datasetId.trim(), file: raw.file
      });
      if (!result.ok) {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
        return;
      }
      vscode.window.setStatusBarMessage(
        `SemForge: ${name} now has ${result.instances} instance(s)`, 5000);
      provider.refresh();
      if (onChanged) {
        onChanged();
      }
    }),

    // A dataset row's datasetId -- every observation of it moves along, since
    // they are one instance. Also what the datasetId quick fixes run, with
    // `old`, `index` and sometimes `new` already settled.
    vscode.commands.registerCommand('semforge.setDatasetId', async (node) => {
      const raw = (node && node.raw) || node || {};
      const where = {
        entity: raw.entity, attributePath: raw.attributePath, file: raw.file,
        old: raw.old !== undefined ? raw.old : raw.datasetId, index: raw.index
      };
      if (!where.entity || !where.attributePath) {
        return;
      }
      if (node.raw && !(await confirmShared(raw, 'Changing the datasetId of'))) {
        return;
      }
      let datasetId = raw.new;
      if (datasetId === undefined) {
        const old = where.old && where.old !== '@none' ? where.old : '';
        const name = String(where.attributePath.slice(-1)[0]).split(/[:/#]/).pop();
        const others = (raw.datasets || []).filter((d) => d !== where.old);
        datasetId = await askDatasetId(clientHolder.client, node.packageUri || raw.packageUri, {
          title: `datasetId of ${raw.label || name}${old ? ` — now ${old}` : ''}`,
          taken: others, allowDefault: !others.includes('@none'),
          suggestion: old ? old.split(/[:/#]/).pop() : `${name}-2`
        });
        if (datasetId === undefined) {
          return;
        }
      }
      const result = await clientHolder.client.sendRequest('semforge/setDatasetId', Object.assign(
        { uri: node.packageUri || raw.packageUri, new: datasetId.trim() || '@none' }, where));
      if (!result.ok) {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
        return;
      }
      provider.refresh();
      if (onChanged) {
        onChanged();
      }
    })
  );

  return provider;
}

module.exports = { register, ModelTreeProvider, CONTEXT_BY_KIND, declareAttribute, removalOf };
