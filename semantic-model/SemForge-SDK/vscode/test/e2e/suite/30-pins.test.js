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

// Pinned and recent: a page is pinned with its star, an entity with a right
// click; the list opens them again, says what is gone, and a rename carries a
// pin along.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, PACKAGE_URI, semforge, until, row, answering } = require('./helpers');

const ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/';
const SHAPE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/FilterShape';

describe('pinned and recent', () => {
  const pins = require('../../../src/bookmarks');
  const clear = async () => {
    for (const pin of pins.read(pins.PINS).slice()) {
      await pins.toggle(pin);
    }
  };
  before(async () => { await semforge(); await clear(); });
  after(async () => {
    await clear();
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('pins the page in front and an entity, and lists them before the recent', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    await vscode.commands.executeCommand('semforge.openShapePage', { raw: { shape: SHAPE }, packageUri: PACKAGE_URI });
    await until(() => api.pages.shape.page && api.pages.shape.panel.active, 'the shape page in front');
    const files = () => {
      const out = {};
      const walk = (directory) => fs.readdirSync(directory, { withFileTypes: true }).forEach((entry) => {
        const full = path.join(directory, entry.name);
        if (entry.isDirectory()) {
          if (entry.name !== '.semforge' && entry.name !== '.vscode') {
            walk(full);
          }
        } else {
          out[full] = fs.readFileSync(full, 'utf8');
        }
      });
      walk(WORKSPACE);
      return out;
    };
    const before = files();
    // The star: pinned, unpinned, pinned again.
    await vscode.commands.executeCommand('semforge.pinPage');
    assert.deepStrictEqual(pins.read(pins.PINS).map((p) => p.id), [SHAPE]);
    await vscode.commands.executeCommand('semforge.unpinPage');
    assert.deepStrictEqual(pins.read(pins.PINS), []);
    await vscode.commands.executeCommand('semforge.pinPage');
    const filter = await row(api.trees.model.provider || api.trees.model,
      (raw) => raw.kind === 'entity' && raw.entity === 'urn:filter:9', 'urn:filter:9');
    await vscode.commands.executeCommand('semforge.pin', filter);
    assert.deepStrictEqual(pins.read(pins.PINS).map((p) => [p.kind, p.id]),
      [['shape', SHAPE], ['entity', 'urn:filter:9']]);

    await vscode.commands.executeCommand('semforge.openTypePage',
      { raw: { targetClass: `${ENT}Filter` }, packageUri: PACKAGE_URI });
    await vscode.commands.executeCommand('semforge.openTypePage',
      { raw: { targetClass: `${ENT}Workpiece` }, packageUri: PACKAGE_URI });
    // Loaded and in front: a page that takes the focus later closes the list.
    await until(() => api.pages.type.page && /Workpiece/.test(api.pages.type.page.label) &&
      api.pages.type.panel.active, 'the Workpiece page in front');
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const session = answering([{ kind: 'quickPick', choose: (items) => items.find((i) => /urn:filter:9/.test(i.label)) }]);
    try {
      await vscode.commands.executeCommand('semforge.bookmarks');
    } finally {
      session.restore();
    }
    const offered = session.asked[0].offered;
    const recent = offered.slice(offered.indexOf('recent'));
    assert.deepStrictEqual(offered.slice(0, 4),
      ['pinned', '$(symbol-interface) FilterShape', '$(symbol-object) urn:filter:9', 'recent']);
    assert.ok(recent.some((label) => label.endsWith(' Filter')), offered.join(' | '));
    assert.ok(!recent.some((label) => label.includes('Workpiece')), `the page in front: ${offered.join(' | ')}`);
    assert.ok(!recent.some((label) => label.includes('FilterShape') || label.includes('warning')),
      `listed once, and only what is there: ${offered.join(' | ')}`);
    await until(() => api.pages.case.page && api.pages.case.page.file.endsWith('without-cartridge.jsonld'),
      'the entity, in its case');
    assert.deepStrictEqual(files(), before, 'nothing is written into the package');
  });

  it('a rename takes the pin along; what is gone says so and can be taken out', async () => {
    const api = await semforge();
    const file = path.join(WORKSPACE, 'examples', 'test_FilterShape', 'bad', 'pin-e2e.jsonld');
    const source = path.join(WORKSPACE, 'examples', 'test_FilterShape', 'bad', 'without-cartridge.jsonld');
    const made = await api.clientHolder.client.sendRequest('semforge/cloneCase',
      { uri: PACKAGE_URI, case: source, expect: 'same', name: 'pin-e2e' });
    assert.ok(made.ok, JSON.stringify(made));
    await clear();
    await vscode.commands.executeCommand('semforge.pin', { raw: { kind: 'example', file }, packageUri: PACKAGE_URI });
    const renaming = answering([{ kind: 'input', value: 'pin-renamed' }]);
    try {
      await vscode.commands.executeCommand('semforge.renameTestCase', { raw: { kind: 'example', file }, packageUri: PACKAGE_URI });
    } finally {
      renaming.restore();
    }
    const now = pins.read(pins.PINS)[0];
    assert.ok(now.id.endsWith('pin-renamed.jsonld') && now.label === 'pin-renamed', JSON.stringify(now));

    const deleting = answering([{ kind: 'warning', button: 'Delete' }]);
    try {
      await vscode.commands.executeCommand('semforge.deleteTestCase', { raw: { kind: 'example', file: now.id }, packageUri: PACKAGE_URI });
    } finally {
      deleting.restore();
    }
    assert.ok(!fs.existsSync(now.id));
    const session = answering([{ kind: 'quickPick', choose: (items) => items.find((i) => /pin-renamed/.test(i.label)) },
      { kind: 'warning', button: 'Take it out' }]);
    try {
      await vscode.commands.executeCommand('semforge.bookmarks');
    } finally {
      session.restore();
    }
    assert.ok(session.asked[0].offered.some((label) => label.includes('$(warning) pin-renamed')));
    assert.deepStrictEqual(pins.read(pins.PINS), []);
  });
});
