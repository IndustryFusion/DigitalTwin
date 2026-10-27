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

// Editing, the way a person does it: from the pages, answering the questions
// the extension asks -- and the files, trees and pages changing as a result.
// These change the workspace copy, so they run after the read-only suites.

const assert = require('assert');
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { WORKSPACE, semforge, row, until, answering, read } = require('./helpers');

const MODEL = 'model-instance.jsonld';

/** What a page row's tree node addresses, read back from the file. */
function stored(id, path) {
  return path.reduce((at, step) => (at === undefined ? undefined : at[step]), entity(id));
}

function entity(id) {
  const document = JSON.parse(read(MODEL));
  return (Array.isArray(document) ? document : [document]).find((e) => e.id === id);
}

async function mainPage(api) {
  await vscode.commands.executeCommand('semforge.openModelPage');
  return until(() => api.pages.case.panel && api.pages.case.panel.title === 'Entities: Main' &&
    api.pages.case.page && api.pages.case.page.kind === 'model' && api.pages.case.page,
  'the Main page');
}

/** The page address ("file.card.row") of an attribute on an entity's card. */
function address(page, id, name) {
  for (const [f, file] of page.files.entries()) {
    for (const [c, card] of file.cards.entries()) {
      if (card.id !== id) {
        continue;
      }
      const r = card.attributes.findIndex((attribute) => attribute.name === name);
      if (r >= 0) {
        return { at: `${f}.${c}.${r}`, row: card.attributes[r] };
      }
    }
  }
  throw new Error(`${name} on ${id} is not on the page`);
}

async function withAnswers(answers, action) {
  const session = answering(answers);
  try {
    await action();
  } finally {
    session.restore();
    if (process.env.SEMFORGE_E2E_DEBUG) {
      console.log('ASKED', JSON.stringify(session.asked).slice(0, 1500), 'LEFT', session.left());
    }
  }
  return session;
}

function rowOn(api, id, name) {
  const page = api.pages.case.page;
  return page && address(page, id, name).row;
}

describe('editing from the Main page', () => {
  it('a value: click, answer, written, and the page shows it', async () => {
    const api = await semforge();
    const page = await mainPage(api);
    const { at, row: before } = address(page, 'urn:filter:1', 'hasStrength');
    assert.ok(before.node.editable);
    assert.notStrictEqual(before.value, '0.95');
    const session = await withAnswers([{ kind: 'input', value: '0.95' }],
      () => api.pages.case.receive({ command: 'edit', at }));
    assert.strictEqual(session.left(), 0, 'it asked for the value');
    assert.strictEqual(stored('urn:filter:1', before.node.path), 0.95);
    await until(() => rowOn(api, 'urn:filter:1', 'hasStrength').value === '0.95',
      'the page to show 0.95');
  });

  it('a relationship to any typed IRI', async () => {
    const api = await semforge();
    const page = await mainPage(api);
    const { at, row: before } = address(page, 'urn:filter:1', 'hasCartridge');
    await withAnswers([{ kind: 'quickPick', type: 'urn:pump:42', labelStarts: '$(edit) Use' }],
      () => api.pages.case.receive({ command: 'edit', at }));
    await until(() => stored('urn:filter:1', before.node.path) === 'urn:pump:42',
      'urn:pump:42 written');
  });

  it('a relationship to another entity, which the shape then reports', async () => {
    const api = await semforge();
    const page = await mainPage(api);
    const { at, row: before } = address(page, 'urn:filter:1', 'hasCartridge');
    const session = await withAnswers([{ kind: 'quickPick', label: 'urn:workpiece:1' }],
      () => api.pages.case.receive({ command: 'edit', at }));
    const offered = session.asked[0].offered;
    assert.ok(offered.indexOf('urn:cartridge:2') < offered.indexOf('urn:workpiece:1'),
      'the shape\'s entities come first');
    await until(() => stored('urn:filter:1', before.node.path) === 'urn:workpiece:1',
      'urn:workpiece:1 written');
    await until(() => {
      const now = rowOn(api, 'urn:filter:1', 'hasCartridge');
      return now.value === 'urn:workpiece:1' && now.violations.length;
    }, 'the sh:class violation on the page');
  });

  it('+ Entity on a file', async () => {
    const api = await semforge();
    await mainPage(api);
    await withAnswers([{ kind: 'pick', choose: (items) => items.find((item) =>
      String(item.label).endsWith(':Workpiece')) },
    { kind: 'input', value: 'urn:workpiece:99' }],
    () => api.pages.case.receive({ command: 'addEntity', at: '0' }));
    assert.ok(entity('urn:workpiece:99'), 'written into the model file');
    await until(() => api.pages.case.page.files[0].cards.some((c) => c.id === 'urn:workpiece:99'),
      'its card on the page');
  });
});

describe('a new suite', () => {
  it('New suite… on the Tests group makes the folder with its first case', async () => {
    const api = await semforge();
    const tests = await row(api.trees.model, (raw) => raw.kind === 'group' &&
      raw.label === 'Tests', 'the Tests group');
    assert.strictEqual((await api.trees.model.getTreeItem(tests)).contextValue, 'testsGroup',
      'its right-click menu is the one with New suite…');
    await withAnswers([
      { kind: 'input', value: 'pump limits' },
      { kind: 'pick', label: '$(pass) Should conform' },
      { kind: 'pick', label: '$(file) An empty file' },
      { kind: 'input', value: 'first' },
      { kind: 'message', button: undefined }],
    () => vscode.commands.executeCommand('semforge.newSuite', tests));
    const folder = path.join(WORKSPACE, 'examples', 'test_pump-limits', 'good');
    assert.ok(fs.existsSync(path.join(folder, 'first.jsonld')), 'the case file');
    assert.match(fs.readFileSync(path.join(folder, 'expectations.yaml'), 'utf-8'),
      /first\.jsonld/);
    // Summary mode names a suite without its test_ prefix; the term keeps it.
    await row(api.trees.model, (raw) => raw.kind === 'suite' &&
      (raw.term === 'test_pump-limits' || raw.label === 'test_pump-limits'),
    'the suite in the Instances view');
  });
});

describe('a new subtype, then its first own attribute', () => {
  it('New subtype… declares it under its parent and opens its page', async () => {
    const api = await semforge();
    const cutter = await row(api.trees.constraints,
      (raw) => raw.kind === 'type' && raw.label === 'Cutter');
    await withAnswers([{ kind: 'input', value: 'Watercutter' },
      { kind: 'message', button: 'Open its type page' }],
    () => vscode.commands.executeCommand('semforge.newSubtype', cutter));
    assert.match(read('knowledge.ttl'), /Watercutter a owl:Class ;\s+rdfs:subClassOf \S*Cutter/);
    await until(() => api.pages.type.panel && api.pages.type.panel.title === 'Entity type: Watercutter',
      'its type page');
    assert.ok(api.pages.type.page.attributes.length, 'what it inherits from Cutter');
    await row(api.trees.constraints, (raw) => raw.kind === 'type' && raw.label === 'Watercutter',
      'Watercutter in Types');
  });

  it('+ Attribute writes its shape first, then the attribute into it', async () => {
    const api = await semforge();
    let picked;
    await withAnswers([
      { kind: 'input', value: 'WatercutterShape' },
      { kind: 'pick', choose: (items) => {
        picked = items.find((item) => item.option && item.option.status === 'free');
        return picked;
      } },
      { kind: 'pick', label: 'Optional' },
      { kind: 'pick', choose: (items) => items.find((item) =>
        ['Any value', 'Any entity'].includes(item.label)) }],
    () => api.pages.type.receive({ command: 'addAttribute', row: -1 }));
    assert.ok(picked, 'a free attribute was offered');
    const shapes = read('shacl.ttl');
    assert.match(shapes, /WatercutterShape/);
    assert.match(shapes, new RegExp(`sh:path \\S*${picked.option.label}`));
    await until(() => {
      const page = api.pages.type.page;
      return /WatercutterShape-[0-9a-f]{8}$/.test(page.ownShape) &&
        page.attributes.some((attribute) => attribute.label === picked.option.label &&
          !attribute.inherited);
    }, 'the type page to show it as its own');
  });
});
