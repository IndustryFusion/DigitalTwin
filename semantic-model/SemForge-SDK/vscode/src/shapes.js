/**
* Copyright (c) 2026 IndustryFusion Foundation
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*    http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/

/*
 * Every shape, whatever it targets.
 *
 * The Entity Types & Constraints view reads constraints by entity type. But a SHACL shape is not
 * tied to one: it selects focus nodes by class, by named node, by the subjects
 * or objects of a predicate, by a SPARQL query -- or it has no target and is
 * reached from another shape through sh:node. A shape of that second kind
 * belongs to no type, and in a tree organised by type it was nowhere.
 *
 * So each shape is a row here, its description saying in words what it
 * targets ("targets subjects of hasValve"), and a click opens its page.
 */

const vscode = require('vscode');

// What this view is, at its top: its name alone left it to be guessed.
const HEADING = 'The SHACL shapes as written, one row per shape with what it targets. A shape opens its shape page.';

const { noPackageMessage } = require('./locate');
const { showLocation, treeDetail, treeClick, icon, rowClicks } = require('./reveal');

class ShapeNode {
  constructor(raw, packageUri) {
    this.raw = raw;
    this.packageUri = packageUri;
  }
}

class ShapesTreeProvider {
  constructor(clientHolder) {
    this.clientHolder = clientHolder;
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
  }

  refresh(uri) {
    if (uri) {
      this.uri = uri;
    }
    this._onDidChangeTreeData.fire();
  }

  setPackage(uri) {
    this.uri = uri || undefined;
    this._onDidChangeTreeData.fire();
  }

  message(text) {
    if (this.view) {
      this.view.message = text || HEADING;
    }
  }

  getParent() {
    return undefined;                  // a flat list
  }

  getTreeItem(node) {
    const raw = node.raw;
    const item = new vscode.TreeItem(raw.label, vscode.TreeItemCollapsibleState.None);
    item.description = raw.detail || '';
    item.contextValue = raw.rule ? 'rule' : 'shape';
    item.iconPath = icon(raw.rule ? 'symbol-event' : 'symbol-interface',
      raw.severity ? 'error' : '');
    item.tooltip = [raw.term || raw.label, raw.detail, raw.definedAt]
      .filter(Boolean).join('\n');
    return item;
  }

  async getChildren(node) {
    if (node) {
      return [];
    }
    const client = this.clientHolder.client;
    if (!client) {
      this.message('The language server is not running — run "SemForge: Doctor".');
      return [];
    }
    if (!this.uri) {
      this.message(noPackageMessage());
      return [];
    }
    let result;
    try {
      result = await client.sendRequest('semforge/shapes',
        { uri: this.uri, detail: treeDetail() });
    } catch (error) {
      this.message(`SemForge: ${error.message || error}`);
      return [];
    }
    if (result.error) {
      this.message(`SemForge: ${result.error}`);
      return [];
    }
    const roots = result.roots || [];
    this.message(roots.length ? undefined : 'This package declares no shapes.');
    return roots.map((raw) => new ShapeNode(raw, this.uri));
  }
}

const KINDS = [
  { label: '$(symbol-class) An entity type', kind: 'class',
    description: 'every entity of a type and its subtypes (sh:targetClass)' },
  { label: '$(symbol-object) One entity', kind: 'node',
    description: 'a single named entity (sh:targetNode)' },
  { label: '$(symbol-field) Everything that has an attribute', kind: 'subjectsOf',
    description: 'every entity carrying it, whatever its type (sh:targetSubjectsOf)' },
  { label: '$(references) Everything a relationship points at', kind: 'objectsOf',
    description: 'every entity some Relationship targets (sh:targetObjectsOf ngsild:hasObject)' }
];

function suggestedName(kind, target, label) {
  const words = String(label || target || '').split(/[^A-Za-z0-9]+/).filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1));
  if (kind === 'objectsOf') {
    return 'RelationshipTargetShape';
  }
  if (kind === 'node') {
    return `${words.slice(-2).join('')}Shape`;
  }
  return `${words.join('')}Shape`;
}

/**
 * What a shape should select: {kind, target, label}, or undefined when the
 * person stops. Used by New shape… and by + Target on a shape page.
 */
async function pickTarget(client, packageUri, title) {
  const picked = await vscode.window.showQuickPick(KINDS, { title });
  if (!picked) {
    return undefined;
  }
  const kind = picked.kind;
  if (kind === 'class') {
    const answer = await client.sendRequest('semforge/entityTypes', { uri: packageUri });
    const chosen = await vscode.window.showQuickPick((answer.types || []).map((t) => ({
      label: t.label, description: t.term,
      detail: t.ownShape ? `already has ${t.ownShape.split(/[/#]/).pop()}`
        : 'no shape of its own yet',
      type: t })), { title: 'Which entity type?', matchOnDescription: true });
    return chosen ? { kind, target: chosen.type.iri, label: chosen.type.label } : undefined;
  }
  if (kind === 'subjectsOf') {
    const answer = await client.sendRequest('semforge/attributes',
      { uri: packageUri, all: true });
    const chosen = await vscode.window.showQuickPick((answer.attributes || []).map((a) => ({
      label: a.label, description: a.term, detail: a.domain ? `on ${a.domain}` : '',
      attribute: a })), { title: 'Every entity that has which attribute?',
      matchOnDescription: true });
    return chosen ? { kind, target: chosen.attribute.iri,
      label: `has ${chosen.attribute.label.replace(/^has/, '')}` } : undefined;
  }
  if (kind === 'node') {
    const target = await vscode.window.showInputBox({
      title: 'One entity',
      prompt: 'Its id, e.g. urn:my-model:machine:1',
      validateInput: (text) => (/^[A-Za-z][A-Za-z0-9+.-]*:\S+$/.test(text.trim())
        ? undefined : 'an IRI, e.g. urn:my-model:machine:1')
    });
    return target ? { kind, target: target.trim(), label: target.trim() } : undefined;
  }
  return { kind, target: 'ngsild:hasObject', label: 'relationship target' };
}

/**
 * New shape…: a node shape with one target, written into the shapes file;
 * its attributes and constraints are then added on its page. A node whose
 * raw names a type (a Types row, the type page) presets the target.
 */
async function newShape(clientHolder, session, node, options) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  if (!client || !packageUri) {
    vscode.window.showWarningMessage(
      'SemForge: no package is open, or the language server is not running.');
    return false;
  }
  const raw = (node && node.raw) || {};
  const chosen = raw.targetClass
    ? { kind: 'class', target: raw.targetClass,
      label: raw.label || raw.targetClass.split(/[/#]/).pop() }
    : await pickTarget(client, packageUri, 'New shape: what does it check?');
  if (!chosen) {
    return false;
  }
  const { kind, target, label } = chosen;
  const name = await vscode.window.showInputBox({
    title: 'New shape: its name',
    prompt: 'Letters, digits, "_" and "-"; a random part is added (PumpShape-3f9a1c2e) -- the IRI is the identity, the name only a label',
    value: suggestedName(kind, target, label),
    validateInput: (text) => (/^[A-Za-z_][A-Za-z0-9_.-]*$/.test(text.trim())
      ? undefined : 'letters, digits, "_", "-" and ".", starting with a letter')
  });
  if (!name) {
    return false;
  }
  const made = await client.sendRequest('semforge/addShape',
    { uri: packageUri, name: name.trim(), targetKind: kind, target });
  if (!made.ok) {
    vscode.window.showErrorMessage(`SemForge: ${made.error}`);
    return false;
  }
  for (const command of ['semforge.refreshShapes', 'semforge.refreshTree']) {
    vscode.commands.executeCommand(command);
  }
  if (options && options.quiet) {
    return made;                       // the caller goes straight on with it
  }
  if (options && options.stay) {
    // Asked from the type page, which re-renders with + Attribute.
    vscode.window.showInformationMessage(
      `SemForge: ${made.name} written. + Attribute now adds to it.`);
    return made;
  }
  await vscode.commands.executeCommand('semforge.openShapePage',
    { raw: { shape: made.iri }, packageUri });
  vscode.window.showInformationMessage(
    `SemForge: ${made.name} written. Add its attributes and constraints on its page.`);
  return made;
}

/**
 * Merge into…: fold a shape into another with the same targets. SHACL
 * conjoins them anyway, so nothing a validator decides changes; the SDK
 * refuses a merge that would, and says before writing what will happen.
 */
async function mergeShape(clientHolder, session, node) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  const shape = node && node.raw && node.raw.shape;
  if (!client || !packageUri || !shape) {
    vscode.window.showWarningMessage('SemForge: Merge into… works on a shape.');
    return false;
  }
  const offered = await client.sendRequest('semforge/mergePlan', { uri: packageUri, shape });
  if (!offered.ok) {
    vscode.window.showErrorMessage(`SemForge: ${offered.error}`);
    return false;
  }
  const short = shape.split(/[/#]/).pop();
  if (!offered.candidates.length) {
    vscode.window.showInformationMessage(
      `SemForge: no other shape selects exactly what ${short} selects, so there is ` +
        'nothing it can be merged into without changing what is checked.');
    return false;
  }
  const into = offered.candidates.length === 1 ? offered.candidates[0]
    : (await vscode.window.showQuickPick(offered.candidates.map((c) => ({
      label: c.name.split(':').pop(), description: c.name, candidate: c })),
    { title: `Merge ${short} into which shape?` }) || {}).candidate;
  if (!into) {
    return false;
  }
  const planned = await client.sendRequest('semforge/mergePlan',
    { uri: packageUri, shape, into: into.iri });
  if (!planned.ok) {
    vscode.window.showErrorMessage(`SemForge: ${planned.error}`);
    return false;
  }
  const detail = planned.said.join('\n') +
    (planned.asserts ? `\n\n${planned.asserts} test-case assert(s) naming ${planned.name} ` +
      `are renamed to ${planned.intoName}.` : '') +
    `\n\n${planned.name} is then deleted. What is checked does not change.`;
  const answer = await vscode.window.showWarningMessage(
    `Merge ${planned.name} into ${planned.intoName}?`, { modal: true, detail }, 'Merge');
  if (answer !== 'Merge') {
    return false;
  }
  const done = await client.sendRequest('semforge/mergeShape',
    { uri: packageUri, shape, into: into.iri });
  if (!done.ok) {
    vscode.window.showErrorMessage(`SemForge: ${done.error}`);
    return false;
  }
  for (const command of ['semforge.refreshShapes', 'semforge.refreshTree',
    'semforge.refreshModel']) {
    vscode.commands.executeCommand(command);
  }
  await vscode.commands.executeCommand('semforge.openShapePage',
    { raw: { shape: done.into }, packageUri });
  vscode.window.showInformationMessage(`SemForge: merged into ${done.intoName}.` +
    (done.notes.length ? ` ${done.notes.join(' ')}` : ''));
  return done;
}

function register(context, clientHolder, session) {
  const provider = new ShapesTreeProvider(clientHolder);
  const view = vscode.window.createTreeView('semforgeShapes', {
    treeDataProvider: provider
  });
  view.message = HEADING;
  provider.view = view;
  context.subscriptions.push(view);

  context.subscriptions.push(
    rowClicks(view, provider, 'semforge.clickShapesRow', async (event) => {
      const selected = event.selection && event.selection[0];
      if (!selected) {
        return;
      }
      if (treeClick() === 'page') {
        await vscode.commands.executeCommand('semforge.openShapePage', selected,
          { preserveFocus: true });
      } else if (selected.raw.definedAt) {
        await showLocation(selected.raw.definedAt, false);
      }
    })
  );

  provider.refresh(session.uri);
  context.subscriptions.push(
    session.onDidChange((uri) => provider.setPackage(uri)),
    vscode.workspace.onDidSaveTextDocument(() => provider.refresh()),
    vscode.commands.registerCommand('semforge.refreshShapes', () => provider.refresh()),
    vscode.commands.registerCommand('semforge.newShape',
      (node, options) => newShape(clientHolder, session, node, options)),
    vscode.commands.registerCommand('semforge.mergeShape',
      (node) => mergeShape(clientHolder, session, node))
  );
  return provider;
}

module.exports = { register, ShapesTreeProvider, newShape, suggestedName, pickTarget,
  mergeShape };
