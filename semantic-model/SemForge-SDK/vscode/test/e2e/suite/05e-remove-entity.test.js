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


// Remove entity, with the real server: from a row and from a card, what the
// question says, one of two with the same id, a file changed since, unsaved edits.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, PACKAGE_URI, semforge, row, rows, until, answering } = require('./helpers');

const run = (name, ...args) => vscode.commands.executeCommand(name, ...args);
const CASE = path.join(WORKSPACE, 'examples', 'test_FilterShape', 'bad', 'without-cartridge.jsonld');
const MODEL = path.join(WORKSPACE, 'model-instance.jsonld');
const SHARED = path.join(WORKSPACE, 'examples', 'subobjects', 'cartridge-fresh.jsonld');
const read = (file) => fs.readFileSync(file, 'utf-8');
const ids = (file) => JSON.parse(read(file)).map((d) => d.id);

describe('Remove entity', () => {
  const saved = {};
  let model;
  let pages;

  before(async () => {
    const api = await semforge();
    model = api.trees.model.provider || api.trees.model;
    pages = api.pages.case;
  });
  beforeEach(() => [CASE, MODEL, SHARED].forEach((file) => { saved[file] = read(file); }));
  afterEach(async () => {
    // An edit a test left unsaved is discarded first: closing would ask.
    for (const document of vscode.workspace.textDocuments.filter((d) => d.isDirty)) {
      await vscode.window.showTextDocument(document);
      await run('workbench.action.files.revert');
    }
    await run('workbench.action.closeAllEditors');
    Object.keys(saved).forEach((file) => fs.writeFileSync(file, saved[file]));
  });

  /** What a card's Remove… button posts about it. */
  const shown = (card) => ({ digest: card.digest, file: card.file, position: card.position, id: card.id });

  /** The row of the `nth` entity of that id in a file, as the file is now. */
  const entity = (id, file, nth = 0) => {
    // As the server reads it: a line ends in \n, however the file ends its lines.
    const text = read(file).replace(/\r\n?/g, '\n');
    const at = JSON.parse(text).map((d, n) => (d.id === id ? n : -1)).filter((n) => n >= 0)[nth];
    const digest = require('crypto').createHash('sha256').update(text).digest('hex').slice(0, 16);
    return row(model, (raw) => raw.kind === 'entity' && raw.entity === id && raw.file === file &&
      raw.position === at && raw.digest === digest, `the row of ${id}`);
  };

  /** Run `act`, its question answered; the question and the errors shown. */
  async function answered(button, act) {
    const errors = [];
    const details = [];
    const show = vscode.window.showErrorMessage;
    vscode.window.showErrorMessage = async (text) => { errors.push(text); };
    const answers = answering([{ kind: 'warning', button }]);
    const ask = vscode.window.showWarningMessage;
    vscode.window.showWarningMessage = (message, options, ...buttons) => {
      details.push(`${message}\n${(options || {}).detail || ''}`);
      return ask(message, options, ...buttons);
    };
    try {
      const done = await act();
      return { done, errors, details };
    } finally {
      answers.restore();
      vscode.window.showErrorMessage = show;
    }
  }

  it('from its row, and not when the question is dismissed', async () => {
    const node = await entity('urn:cartridge:1', MODEL);
    const dismissed = await answered(undefined, () => run('semforge.removeEntity', node));
    assert.strictEqual(dismissed.done, undefined);
    assert.strictEqual(read(MODEL), saved[MODEL]);
    assert.match(dismissed.details[0], /Remove urn:cartridge:1\?[^]*main model[^]*pointing at it[^]*urn:filter:1/);
    const { done } = await answered('Remove', () => run('semforge.removeEntity', node));
    assert.ok(done && done.ok);
    assert.deepStrictEqual(ids(MODEL), JSON.parse(saved[MODEL]).map((d) => d.id).filter((i) => i !== 'urn:cartridge:1'));
    await until(async () => !(await rows(model)).some((node) => node.raw.kind === 'entity' &&
      node.raw.entity === 'urn:cartridge:1' && node.raw.file === MODEL), 'the row gone');
  });

  it('from its card: the case is left empty, its asserts stay, and the page shows it', async () => {
    const declared = path.join(path.dirname(CASE), 'expectations.yaml');
    const asserts = read(declared);
    await run('semforge.openCasePage', { raw: { kind: 'example', file: CASE }, packageUri: PACKAGE_URI });
    const page = await until(() => pages.page && pages.page.file === CASE && pages.page, 'the case page');
    const at = page.files[0].cards.findIndex((card) => card.id === 'urn:filter:9');
    assert.ok(pages.panel.webview.html.includes(`data-removeentity="0.${at}"`));
    const { details } = await answered('Remove', () => pages.receive(
      { command: 'removeEntity', at: `0.${at}`, value: shown(page.files[0].cards[at]) }));
    assert.match(details[0], /No entity is left in the file[^]*Asserting something on it[^]*without-cartridge/);
    assert.deepStrictEqual(JSON.parse(read(CASE)), []);
    assert.strictEqual(read(declared), asserts);
    await until(() => pages.page.files[0].cards.length === 0, 'the card gone');
  });

  it('of two with the same id, the one the row stands for', async () => {
    const scene = JSON.parse(saved[CASE]);
    // Written with CRLF line ends, as on Windows.
    fs.writeFileSync(CASE, JSON.stringify([scene[0], Object.assign({}, scene[0],
      { other: { type: 'Property', value: 1 } })], null, 2).replace(/\n/g, '\r\n'));
    const first = await entity('urn:filter:9', CASE, 0);
    const { done, details } = await answered('Remove', () => run('semforge.removeEntity', first));
    assert.ok(done && done.remains);
    assert.match(details[0], /defines it once more/);
    assert.ok(JSON.parse(read(CASE)).length === 1 && JSON.parse(read(CASE))[0].other, 'the second stays');
  });

  it('a file changed since the row was read is refused', async () => {
    const node = await entity('urn:filter:9', CASE);
    const raw = Object.assign({}, node.raw);
    const scene = JSON.parse(saved[CASE]);
    const changed = JSON.stringify(scene.concat([Object.assign({}, scene[0], { id: 'urn:more' })]));
    fs.writeFileSync(CASE, changed);
    const { done, errors, details } = await answered('Remove', () => run('semforge.removeEntity',
      { raw, packageUri: node.packageUri }));
    assert.strictEqual(done, undefined);
    assert.match(errors[0], /has changed since it was read/);
    assert.deepStrictEqual(details, [], 'nothing was asked');
    assert.strictEqual(read(CASE), changed);
  });

  it('a click from an older page removes nothing', async () => {
    await run('semforge.openCasePage', { raw: { kind: 'example', file: CASE }, packageUri: PACKAGE_URI });
    await until(() => pages.page && pages.page.file === CASE && pages.page.files[0].cards.length, 'the case page');
    const { errors, details } = await answered('Remove', () => pages.receive(
      { command: 'removeEntity', at: '0.0', value: Object.assign(shown(pages.page.files[0].cards[0]),
        { digest: 'olderolderolder1' }) }));
    assert.match(errors[0], /has changed since it was read/);
    assert.deepStrictEqual(details, []);
    assert.strictEqual(read(CASE), saved[CASE]);
  });

  it('says which cases use the file, and refuses unsaved edits', async () => {
    const node = await entity('urn:cartridge:1', SHARED);
    const shared = await answered(undefined, () => run('semforge.removeEntity', node));
    assert.match(shared.details[0], /3 cases use this file and change/);
    const editor = await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(SHARED));
    await editor.edit((edit) => edit.insert(new vscode.Position(0, 0), ' '));
    try {
      const dirty = await answered('Remove', () => run('semforge.removeEntity', node));
      assert.match(dirty.errors[0], /unsaved edits/);
      assert.strictEqual(read(SHARED), saved[SHARED]);
    } finally {
      await vscode.window.showTextDocument(editor.document);
      await run('workbench.action.files.revert');
    }
  });
});
