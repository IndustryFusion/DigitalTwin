/*
 * "SemForge: New attribute…" -- declare an attribute in the knowledge and,
 * in the same gesture, constrain it on its type's shape.
 *
 * The order is the model's own: an attribute has to be DECLARED before a shape
 * may name it, because a sh:path the ontology has never heard of is how a
 * constraint ends up checking nothing. Making that two trips through two views
 * was the friction; this is one flow that does both steps in that order.
 *
 * VS Code has no extension-owned top-level menu, so the flow is reachable from
 * everywhere an extension IS allowed to put it: the Command Palette, the
 * SemForge submenu (Explorer and editor right-click, the Project view title),
 * the status bar menu, and the + picker in the Constraints view.
 */

const vscode = require('vscode');

const { declareAttribute } = require('./model');
const { showLocation } = require('./reveal');

async function valueChoices(client, packageUri, path, parameter) {
  try {
    const result = await client.sendRequest('semforge/choices', {
      uri: packageUri, path, parameter, search: null
    });
    return result.choices || [];
  } catch (error) {
    return [];
  }
}

/**
 * What the value must be. Asked, not read: the knowledge says which KIND an
 * attribute is, and deliberately leaves what its value may be to the shapes.
 * Returns {datatype, valueClass}, or undefined when cancelled.
 */
async function pickValue(client, packageUri, option) {
  const anything = { label: 'Any value', detail: 'constrain only that a value is there', value: {} };
  let items;
  if (option.kind === 'Relationship') {
    const entities = await valueChoices(
      client, packageUri, [option.term, 'ngsild:hasObject'], 'sh:class');
    items = [{ ...anything, label: 'Any entity' }].concat(entities.map((c) => ({
      label: c.label, description: c.value, detail: c.detail,
      value: { valueClass: c.value }
    })));
  } else if (option.kind === 'Property') {
    const [datatypes, classes] = await Promise.all([
      valueChoices(client, packageUri, [option.term, 'ngsild:hasValue'], 'sh:datatype'),
      valueChoices(client, packageUri, [option.term, 'ngsild:hasValue'], 'sh:class')
    ]);
    items = [anything,
      { label: 'A literal', kind: vscode.QuickPickItemKind.Separator }]
      .concat(datatypes.map((c) => ({
        label: c.label, description: 'datatype', value: { datatype: c.value }
      })))
      .concat([{ label: 'A vocabulary term', kind: vscode.QuickPickItemKind.Separator }])
      .concat(classes.map((c) => ({
        label: c.label, description: c.value, detail: c.detail,
        value: { valueClass: c.value }
      })));
  } else {
    return {};      // a JSON, list or geo payload has no class or datatype to ask
  }
  const picked = await vscode.window.showQuickPick(items, {
    title: `${option.label}: what must its value be?`,
    matchOnDescription: true,
    matchOnDetail: true
  });
  return picked ? picked.value : undefined;
}

const OPTIONAL = { label: 'Optional', description: 'sh:minCount 0',
  detail: 'checked when present, fine when absent', required: false };
const REQUIRED = { label: 'Required', description: 'sh:minCount 1',
  detail: 'every entity of this type must carry it', required: true };
const NOT_NOW = { label: 'Not now', description: 'declared only',
  detail: 'no shape names it yet — add it later with the + on the shape',
  skip: true };

/**
 * Constrain one declared attribute on a shape: presence, value, write.
 *
 * `target` is {shape} for a tree row, or {entityType} when the flow started
 * from a type -- the server then picks that type's OWN shape. With `optional`
 * set the first question also offers to stop at the declaration.
 * Returns the server's result, or undefined when cancelled or declined.
 */
async function constrainAttribute(client, packageUri, option, target, optional) {
  const presence = await vscode.window.showQuickPick(
    optional ? [OPTIONAL, REQUIRED, NOT_NOW] : [OPTIONAL, REQUIRED],
    { title: `${option.label} on ${target.label}` });
  if (!presence || presence.skip) {
    return undefined;
  }
  const value = await pickValue(client, packageUri, option);
  if (value === undefined) {
    return undefined;
  }
  const result = await client.sendRequest('semforge/addAttributeConstraint', {
    uri: packageUri,
    shape: target.shape || null,
    entityType: target.entityType || null,
    parentPath: target.parentPath || null,
    attribute: option.iri || option.term,
    required: presence.required,
    datatype: value.datatype || null,
    valueClass: value.valueClass || null,
    extendDomain: !!option.extendDomain
  });
  if (!result.ok) {
    vscode.window.showErrorMessage(`SemForge: ${result.error}`);
    return undefined;
  }
  vscode.window.setStatusBarMessage(
    `SemForge: ${option.label} added to ${target.label}` +
      ((result.domainAdded || []).length
        ? ` — its domain now includes ${result.domainAdded.join(', ')}` : ''), 5000);
  if (result.line) {
    await showLocation(`${result.file}:${result.line}`, false);
  }
  return result;
}

/** The entity type the new attribute belongs to, picked from the knowledge. */
async function pickEntityType(client, packageUri) {
  let answer;
  try {
    answer = await client.sendRequest('semforge/entityTypes', { uri: packageUri });
  } catch (error) {
    answer = { error: error.message || String(error) };
  }
  if (!answer || answer.error) {
    vscode.window.showErrorMessage(
      `SemForge: ${(answer && answer.error) || 'the entity types could not be read'}`);
    return undefined;
  }
  const items = (answer.types || []).map((type) => ({
    label: type.label,
    description: type.term,
    detail: [type.parent ? `under ${type.parent}` : 'the root',
             type.ownShape ? 'has its own shape' : 'no shape of its own yet']
      .join(' · '),
    type
  }));
  const picked = await vscode.window.showQuickPick(items, {
    title: 'New attribute — which entity type carries it?',
    placeHolder: 'it is inherited by every type below the one you pick',
    matchOnDescription: true
  });
  return picked ? picked.type : undefined;
}

/**
 * The whole flow. `preset` may already name the type ({entityType, shape,
 * label}) -- the Constraints view's + knows which shape it was clicked on.
 */
/**
 * The name and namespace a quick fix already knows, from the term as the use
 * wrote it: a full IRI splits into namespace and name; a prefixed name is
 * passed whole, because the server honours a typed prefix.
 */
function givenFromTerm(term) {
  if (!term) {
    return undefined;
  }
  const cut = Math.max(term.lastIndexOf('/'), term.lastIndexOf('#'));
  if (term.includes('://') && cut > 0) {
    return { name: term.slice(cut + 1), namespace: term.slice(0, cut + 1) };
  }
  return { name: term, namespace: '' };
}

/**
 * A sub-attribute, declared from its parent's row in the Knowledge view.
 *
 * The declaration is the knowledge's: carried by the parent attribute, so its
 * rdfs:domain becomes the parent's kind of node. The constraint has no tree
 * row to say where it goes, so it is offered inside each property shape that
 * constrains the parent -- or not at all, which is a fine place to stop.
 */
async function newSubAttribute(client, packageUri, parent) {
  const made = await declareAttribute(client, packageUri, parent.iri);
  if (!made) {
    return undefined;
  }
  let places = [];
  try {
    const answer = await client.sendRequest('semforge/attributePlaces',
      { uri: packageUri, attribute: parent.iri });
    places = (answer && answer.places) || [];
  } catch (error) {
    places = [];
  }
  if (!places.length) {
    vscode.window.showInformationMessage(
      `SemForge: ${made.label} is declared, carried by ${parent.label}. No ` +
        `shape constrains ${parent.label} yet, so there is no property shape ` +
        'to nest it in.');
    return made;
  }
  const picked = await vscode.window.showQuickPick(
    places.map((place) => ({
      label: `Constrain inside ${place.shapeName} › ${place.path.join(' › ')}`,
      description: `${place.file.split('/').pop()}:${place.line}`,
      place
    })).concat([NOT_NOW]),
    { title: `${made.label}: constrain it now?` });
  if (!picked || picked.skip) {
    return made;
  }
  await constrainAttribute(client, packageUri, made,
    { shape: picked.place.shape, parentPath: picked.place.path,
      label: `${picked.place.shapeName} › ${parent.label}` }, false);
  return made;
}

async function newAttribute(client, packageUri, preset, given) {
  if (!client) {
    vscode.window.showErrorMessage(
      'SemForge: the language server is not running — run "SemForge: Doctor".');
    return undefined;
  }
  if (!packageUri) {
    vscode.window.showWarningMessage(
      'SemForge: no package is open. Open a file in one, or run ' +
      '"SemForge: New project…".');
    return undefined;
  }
  let target = preset;
  if (!target) {
    const type = await pickEntityType(client, packageUri);
    if (!type) {
      return undefined;
    }
    target = { entityType: type.term, label: type.label,
               hasShape: Boolean(type.ownShape) };
  }

  const made = await declareAttribute(client, packageUri, target.entityType, given);
  if (!made) {
    return undefined;
  }
  if (!target.shape && !target.hasShape) {
    vscode.window.showInformationMessage(
      `SemForge: ${made.label} is declared. No shape targets ${target.label} ` +
        'itself yet, so nothing constrains it — that needs a shape first.');
    return made;
  }
  // From a shape's + the author has already said they want a constraint; from
  // anywhere else declaring alone is a legitimate place to stop.
  await constrainAttribute(client, packageUri, made, target, !target.shape);
  return made;
}

// --- deleting one ---------------------------------------------------------------

const DEPENDENT_KIND = {
  declaration: 'the declaration',
  constraint: 'property shapes',
  data: 'entities carrying it',
  expectation: 'expectation asserts',
  sparql: 'SPARQL bodies',
  shapes: 'other shape statements',
  knowledge: 'other ontology statements'
};

/** The plan as the modal's detail: what goes, grouped, then what blocks. */
function describePlan(plan) {
  const groups = {};
  for (const dependent of plan.dependents) {
    (groups[dependent.kind] = groups[dependent.kind] || []).push(dependent);
  }
  const lines = [];
  for (const kind of Object.keys(DEPENDENT_KIND)) {
    const items = groups[kind];
    if (!items) {
      continue;
    }
    lines.push(`${DEPENDENT_KIND[kind]} (${items.length})` +
      (items[0].removable ? '' : ' — must be edited by hand first'));
    for (const item of items.slice(0, 8)) {
      lines.push(`   ${item.where}  ${item.detail}`);
    }
    if (items.length > 8) {
      lines.push(`   … and ${items.length - 8} more`);
    }
  }
  return lines.join('\n');
}

/** Which attribute to delete, when the gesture did not come from a row. */
async function pickAttributeToDelete(client, packageUri) {
  let answer;
  try {
    answer = await client.sendRequest('semforge/attributes', { uri: packageUri, all: true });
  } catch (error) {
    answer = { error: error.message || String(error) };
  }
  if (!answer || answer.error) {
    vscode.window.showErrorMessage(
      `SemForge: ${(answer && answer.error) || 'the attributes could not be read'}`);
    return undefined;
  }
  const picked = await vscode.window.showQuickPick(
    (answer.attributes || []).map((a) => ({
      label: a.term,
      description: [a.kind, a.domain ? `on ${a.domain}` : 'no domain'].join(' · '),
      detail: a.comment || '',
      iri: a.iri
    })),
    { title: 'Delete an attribute', placeHolder: 'the dependents are shown before anything is removed',
      matchOnDescription: true });
  return picked ? picked.iri : undefined;
}

const DECLARATION_ONLY = 'Delete declaration only';
const EVERYTHING = Symbol('everything');

/**
 * Delete an attribute, after showing everything that goes with it.
 *
 * Three answers, depending on the plan. Something blocks (a SPARQL body, an
 * ontology statement): say what and where, offer to open the first. In use:
 * list every dependent and ask for one yes to remove them all. Used nowhere:
 * an ordinary confirmation. Whenever there are uses, "Delete declaration
 * only" is the other answer -- the term goes, its uses stay.
 */
async function deleteAttribute(client, packageUri, attribute) {
  const plan = await client.sendRequest('semforge/attributeRemovalPlan',
    { uri: packageUri, attribute });
  if (!plan.ok) {
    vscode.window.showErrorMessage(`SemForge: ${plan.error}`);
    return false;
  }
  const blocking = plan.dependents.filter((d) => !d.removable);
  const others = plan.dependents.filter((d) => d.kind !== 'declaration');
  const declared = plan.dependents.some((d) => d.kind === 'declaration');
  // The declaration alone, every use left where it is. Offered whenever there
  // ARE uses -- including when they block the full delete, since it touches
  // none of them. What it leaves is not silent: the Problems panel reports
  // each remaining use as naming an undeclared term.
  const declarationOnly = declared && others.length ? DECLARATION_ONLY : undefined;

  // Only an answer that was OFFERED counts: the declaration-only choice does
  // not exist for an attribute nothing uses, whatever comes back.
  let answer;
  let offered;
  if (blocking.length) {
    offered = ['Open the first one', declarationOnly].filter(Boolean);
    answer = await vscode.window.showWarningMessage(
      `${plan.label} cannot be deleted with its dependents: ${blocking.length} ` +
        'use(s) must be edited by hand first. You can still delete the ' +
        'declaration alone and leave every use in place.',
      { modal: true, detail: describePlan(plan) },
      ...offered
    );
    if (answer === 'Open the first one') {
      await showLocation(`${blocking[0].file}:${blocking[0].line}`, true);
      return false;
    }
  } else {
    const everything = others.length
      ? `Delete with ${others.length} dependent(s)`
      : 'Delete';
    offered = [everything, declarationOnly].filter(Boolean);
    answer = await vscode.window.showWarningMessage(
      others.length
        ? `${plan.label} is in use. Delete it and everything that depends on ` +
          'it, or only its declaration?'
        : `Delete ${plan.label}? It is declared and used nowhere.`,
      { modal: true, detail: describePlan(plan) },
      ...offered
    );
    if (answer === everything) {
      answer = EVERYTHING;
      offered.push(EVERYTHING);
    }
  }
  if (!offered.includes(answer) ||
      (answer !== EVERYTHING && answer !== DECLARATION_ONLY)) {
    return false;
  }
  const onlyDeclaration = answer === DECLARATION_ONLY;
  const result = await client.sendRequest('semforge/removeAttribute', {
    uri: packageUri, attribute: plan.iri, force: true,
    declarationOnly: onlyDeclaration
  });
  if (!result.ok) {
    vscode.window.showErrorMessage(`SemForge: ${result.error}`);
    return false;
  }
  vscode.window.setStatusBarMessage(onlyDeclaration
    ? `SemForge: the declaration of ${plan.label} deleted; ${others.length} use(s) left`
    : `SemForge: ${plan.label} deleted with ${others.length} dependent(s)`, 6000);
  for (const note of result.notes || []) {
    vscode.window.showWarningMessage(`SemForge: ${note}`);
  }
  return true;
}

/** The attribute a tree row stands for: its IRI, or its sh:path as written. */
function attributeOf(node) {
  const raw = node && node.raw;
  if (!raw) {
    return undefined;
  }
  if (raw.iri) {
    return raw.iri;
  }
  return raw.path && raw.path.length ? raw.path[raw.path.length - 1] : undefined;
}

function register(context, clientHolder, session, refresh) {
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.deleteAttribute', async (node) => {
      const client = clientHolder.client;
      const packageUri = (node && node.packageUri) || session.uri;
      if (!client || !packageUri) {
        vscode.window.showWarningMessage(
          'SemForge: no package is open, or the language server is not running.');
        return;
      }
      const attribute = node && node.raw ? attributeOf(node)
        : await pickAttributeToDelete(client, packageUri);
      if (!attribute) {
        return;
      }
      if (await deleteAttribute(client, packageUri, attribute) && refresh) {
        refresh();
      }
    })
  );
  context.subscriptions.push(
    // With an argument it is the quick fix "Declare it": the term is the one
    // the marked use names, so only the type and the kind are asked.
    vscode.commands.registerCommand('semforge.newAttribute', async (fix) => {
      const packageUri = (fix && fix.packageUri) || session.uri;
      const made = await newAttribute(clientHolder.client, packageUri, undefined,
        fix && fix.iri ? givenFromTerm(fix.iri) : undefined);
      if (made && refresh) {
        refresh();
      }
    }),

    vscode.commands.registerCommand('semforge.newSubAttribute', async (node) => {
      const raw = node && node.raw;
      const client = clientHolder.client;
      if (!raw || !raw.iri || !client) {
        vscode.window.showInformationMessage(
          'SemForge: pick an attribute in the Knowledge view to add a ' +
            'sub-attribute to.');
        return;
      }
      const made = await newSubAttribute(client, node.packageUri || session.uri,
        { iri: raw.iri, label: (raw.label || '').split(':').pop() });
      if (made && refresh) {
        refresh();
      }
    }),

    // The quick fix "Remove this use": exactly the marked property shape,
    // data key or assert, nothing else. Not in the palette -- it only means
    // something with the finding it was offered on.
    vscode.commands.registerCommand('semforge.removeUse', async (fix) => {
      const client = clientHolder.client;
      if (!client || !fix) {
        return;
      }
      const result = await client.sendRequest('semforge/removeUse', fix);
      if (!result.ok) {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
        return;
      }
      vscode.window.setStatusBarMessage(
        `SemForge: ${fix.said || `removed ${fix.label || 'it'}`}`, 5000);
      if (result.note) {
        vscode.window.showWarningMessage(`SemForge: ${result.note}`);
      }
      if (refresh) {
        refresh();
      }
    })
  );
}

module.exports = { register, newAttribute, constrainAttribute, pickValue, deleteAttribute };
