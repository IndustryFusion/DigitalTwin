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

// Copy and paste of entities, with the real server: in the kms, whose shapes
// name no reference type, and in the OPC UA pump slice, whose relationships
// are its hierarchy. By the registered commands, by a drop, by the selected
// row, and from the page.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, PACKAGE_URI, OPCUA, OPCUA_URI, semforge, row, until, answering } = require('./helpers');

const run = (name, ...args) => vscode.commands.executeCommand(name, ...args);
const CASE = path.join(WORKSPACE, 'examples', 'test_FilterShape', 'bad', 'without-cartridge.jsonld');
const SHACL = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/';
const ids = (file) => JSON.parse(fs.readFileSync(file, 'utf-8')).map((d) => d.id);

describe('Copy and paste', () => {
  let saved;
  let model;
  beforeEach(() => { saved = fs.readFileSync(CASE, 'utf-8'); });
  afterEach(async () => {
    fs.writeFileSync(CASE, saved);
    await run('workbench.action.closeAllEditors');
  });

  async function rowsOf() {
    const api = await semforge();
    model = api.trees.model.provider || api.trees.model;
    const entity = (id) => row(model, (raw) => raw.kind === 'entity' && raw.entity === id &&
      raw.file !== CASE && raw.file.endsWith('model-instance.jsonld'), id);
    const onto = await row(model, (raw) => raw.kind === 'example' && raw.file === CASE, 'the case');
    return { api, entity, onto };
  }

  it('a subtree in a package without a hierarchy is the entity alone', async () => {
    const { entity, onto } = await rowsOf();
    const copied = await run('semforge.copySubtree', await entity('urn:plasmacutter:1'));
    assert.deepStrictEqual(copied.copied, ['urn:plasmacutter:1'], 'its shapes name no child reference');
    assert.ok(copied.left.includes('urn:filter:1'), 'what it only points at stays, and is said');
    const before = ids(CASE);
    const done = await run('semforge.pasteEntity', onto);
    assert.deepStrictEqual(done.pasted, ['urn:plasmacutter:1']);
    assert.deepStrictEqual(ids(CASE), before.concat(['urn:plasmacutter:1']));
    assert.ok(await row(model, (raw) => raw.kind === 'entity' && raw.entity === 'urn:plasmacutter:1' &&
      raw.file === CASE, 'its row in the case'), 'the view shows it');
    const again = fs.statSync(CASE).mtimeMs;
    assert.strictEqual(await run('semforge.pasteEntity', onto), undefined, 'nothing changes');
    assert.strictEqual(fs.statSync(CASE).mtimeMs, again, 'and nothing is written');
  });

  it('an entity\'s row dropped on a case is copied there, and what is held stays', async () => {
    const { api, entity, onto } = await rowsOf();
    await run('semforge.copyEntity', await entity('urn:workpiece:1'));
    const transfer = new vscode.DataTransfer();
    api.trees.model.drag.handleDrag([await entity('urn:filter:1')], transfer);
    await api.trees.model.drag.handleDrop(onto, transfer);
    assert.ok(ids(CASE).includes('urn:filter:1') && !ids(CASE).includes('urn:workpiece:1'));
    await run('semforge.pasteEntity', onto);
    assert.ok(ids(CASE).includes('urn:workpiece:1'));
  });

  it('it asks before it replaces', async () => {
    const { entity, onto } = await rowsOf();
    await run('semforge.copyEntity', await entity('urn:filter:1'));
    await run('semforge.pasteEntity', onto);
    const whole = fs.readFileSync(CASE, 'utf-8');
    const changed = JSON.parse(whole);
    changed[changed.length - 1]['iffBaseEntities:hasStrength'] = { type: 'Property', value: 1 };
    const other = JSON.stringify(changed, null, 2) + (whole.endsWith('\n') ? '\n' : '');
    fs.writeFileSync(CASE, other);
    for (const [button, text] of [[undefined, other], ['Replace', whole]]) {
      const answers = answering([{ kind: 'warning', button }]);
      try {
        await run('semforge.pasteEntity', onto);
        assert.deepStrictEqual(answers.asked[0].offered.buttons, ['Replace']);
        assert.strictEqual(fs.readFileSync(CASE, 'utf-8'), text);
      } finally {
        answers.restore();
      }
    }
  });

  it('the keyboard takes the selected row, and the page pastes', async () => {
    const { api, entity, onto } = await rowsOf();
    assert.ok(await model.revealEntity('urn:filter:1', (await entity('urn:filter:1')).raw.file));
    await until(() => ((model.view.selection || [])[0] || { raw: {} }).raw.entity === 'urn:filter:1',
      'the row to be selected');
    const copied = await run('semforge.copyEntity');
    assert.deepStrictEqual(copied.copied, ['urn:filter:1']);
    await run('semforge.openCasePage', onto);
    const pages = api.pages.case;
    await until(() => pages.page && pages.page.file === CASE, 'the case page');
    await pages.receive({ command: 'paste' });
    assert.ok(ids(CASE).includes('urn:filter:1'));
    assert.ok(pages.panel.webview.html.includes('urn:filter:1'), 'the page shows it');
    const at = pages.page.files[0].cards.findIndex((card) => card.id === 'urn:filter:1');
    await pages.receive({ command: 'copySubtree', at: `0.${at}` });
    assert.deepStrictEqual(model.drag.clipboard.held.copied, ['urn:filter:1'], 'from its card');
    assert.strictEqual(model.drag.clipboard.held.packageUri, PACKAGE_URI);
  });

  it('copied from an id on a page', async () => {
    const { api, onto } = await rowsOf();
    await run('semforge.openModelPage', { packageUri: PACKAGE_URI });
    await until(() => api.pages.case.page && api.pages.case.page.kind === 'model', 'the Main page');
    // What VS Code hands the command on a right click of an id on the page.
    const copied = await run('semforge.copyEntity', { webview: 'semforgeCasePage', webviewSection: 'semforgeEntity',
      entity: 'urn:filter:1' });
    assert.deepStrictEqual(copied.copied, ['urn:filter:1']);
    await run('semforge.pasteEntity', onto);
    assert.ok(ids(CASE).includes('urn:filter:1'));
  });

  it('in an OPC UA package a subtree is the hierarchy, and stays in its package', async () => {
    const { api, onto } = await rowsOf();
    const own = JSON.parse(fs.readFileSync(path.join(OPCUA, 'model-instance.jsonld'), 'utf-8'));
    const of = (type) => own.find((d) => d.type === `pumps:${type}`).id;
    const node = (type) => ({ packageUri: OPCUA_URI, raw: { kind: 'entity', entity: of(type),
      file: path.join(OPCUA, 'model-instance.jsonld') } });
    const pump = await run('semforge.copySubtree', node('PumpType'));
    assert.deepStrictEqual([...pump.copied].sort(), own.map((d) => d.id).sort(), 'the pump is all of it');
    const ports = await run('semforge.copySubtree', node('PortsGroupType'));
    const expected = ['PortsGroupType', 'DrivePortType', 'DriveMeasurementsType'].map(of);
    assert.deepStrictEqual(ports.copied, expected);

    // Pasted where the case is the OPC UA package's...
    const file = path.join(OPCUA, 'examples', 'test_DrivePortTypeShape', 'bad', 'measurements-too-many.jsonld');
    const before = fs.readFileSync(file, 'utf-8');
    try {
      const had = ids(file);
      const done = await run('semforge.pasteEntity', { file, packageUri: OPCUA_URI });
      assert.deepStrictEqual(done.pasted, expected);
      assert.deepStrictEqual(ids(file), had.concat(expected));
      const page = await api.clientHolder.client.sendRequest('semforge/casePage', { uri: OPCUA_URI, case: file });
      assert.ok(page.ok && expected.every((id) => page.files[0].cards.some((card) => card.id === id)), page.error);
    } finally {
      fs.writeFileSync(file, before);
    }
    // ... and refused in the kms.
    const errors = [];
    const show = vscode.window.showErrorMessage;
    vscode.window.showErrorMessage = async (text) => { errors.push(text); };
    try {
      assert.strictEqual(await run('semforge.pasteEntity', onto), undefined);
    } finally {
      vscode.window.showErrorMessage = show;
    }
    assert.match(errors[0], /copied in another package/);
    assert.strictEqual(fs.readFileSync(CASE, 'utf-8'), saved);
  });
  it('a file with an entity written in a relationship is refused, and named', async () => {
    const { entity, onto } = await rowsOf();
    await run('semforge.copyEntity', await entity('urn:filter:1'));
    const docs = JSON.parse(saved);
    docs[0]['iffBaseEntities:holds'] = { type: 'Relationship',
      object: { id: 'urn:inside:1', type: 'iffBaseEntities:Cartridge' } };
    const written = JSON.stringify(docs, null, 2);
    fs.writeFileSync(CASE, written);
    const errors = [];
    const show = vscode.window.showErrorMessage;
    vscode.window.showErrorMessage = async (text) => { errors.push(text); };
    try {
      assert.strictEqual(await run('semforge.pasteEntity', onto), undefined);
    } finally {
      vscode.window.showErrorMessage = show;
    }
    assert.ok(errors[0].includes(`without-cartridge.jsonld: ${docs[0].id} has urn:inside:1 written in a ` +
      'relationship\'s object'), errors[0]);
    assert.strictEqual(fs.readFileSync(CASE, 'utf-8'), written, 'nothing is written');
  });

  it('an id with a prefix only the package names is the case\'s entity of that IRI', async () => {
    const MODEL = path.join(WORKSPACE, 'model-instance.jsonld');
    const text = fs.readFileSync(MODEL, 'utf-8');
    const docs = JSON.parse(text);
    const filter = docs.find((d) => d.id === 'urn:filter:1');
    const opened = Object.assign({}, filter, { id: 'iffBaseShacl:one' });   // kms.yaml names it, the context not
    fs.writeFileSync(MODEL, JSON.stringify(docs.concat([opened]), null, 2));
    try {
      const { entity, onto } = await rowsOf();
      await run('semforge.copyEntity', await entity('iffBaseShacl:one'));
      const whole = Object.assign({}, filter, { id: SHACL + 'one',
        'iffBaseEntities:hasStrength': { type: 'Property', value: 1 } });
      fs.writeFileSync(CASE, JSON.stringify(JSON.parse(saved).concat([whole]), null, 2));
      const answers = answering([{ kind: 'warning', button: 'Replace' }]);
      try {
        await run('semforge.pasteEntity', onto);
        assert.deepStrictEqual(answers.asked[0].offered.buttons, ['Replace'], 'the case has it, by its IRI');
      } finally {
        answers.restore();
      }
      const ones = JSON.parse(fs.readFileSync(CASE, 'utf-8')).filter((d) => d.id.endsWith('one'));
      assert.deepStrictEqual(ones, [opened], 'once, as copied');
    } finally {
      fs.writeFileSync(MODEL, text);
    }
  });
});
