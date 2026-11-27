/*
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

'use strict';

// Undo and Redo over the package's own git history: a removed entity comes
// back, and goes again.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, semforge, row, until, answering } = require('./helpers');

const MODEL = path.join(WORKSPACE, 'model-instance.jsonld');
const ids = () => JSON.parse(fs.readFileSync(MODEL, 'utf-8')).map((d) => d.id);

describe('Undo and Redo', () => {
  it('a removed entity comes back with Undo, and goes again with Redo', async function () {
    this.timeout(120000);
    const api = await semforge();
    const provider = api.trees.model.provider || api.trees.model;
    const entity = await row(provider, (raw) => raw.kind === 'entity' && raw.entity === 'urn:workpiece:1' &&
      (!raw.file || raw.file === MODEL), 'the entity in Main');
    const session = answering([{ kind: 'warning', button: 'Remove' }]);
    try {
      assert.ok((await vscode.commands.executeCommand('semforge.removeEntity', entity)).ok);
    } finally {
      session.restore();
    }
    assert.ok(!ids().includes('urn:workpiece:1'), 'removed');
    const state = await until(async () => {
      const now = await api.undo.refresh();
      return now.undo && now;
    }, 'something to undo');
    assert.ok(state.undo.startsWith('SemForge: change model-instance.jsonld'), state.undo);

    const undone = await vscode.commands.executeCommand('semforge.undo');
    assert.ok(undone && undone.ok, JSON.stringify(undone));
    assert.ok(ids().includes('urn:workpiece:1'), 'back');
    assert.ok(api.undo.state().redo, 'and redoable');
    await until(async () => row(provider, (raw) => raw.kind === 'entity' && raw.entity === 'urn:workpiece:1'),
      'its row again');

    const redone = await vscode.commands.executeCommand('semforge.redo');
    assert.ok(redone && redone.ok, JSON.stringify(redone));
    assert.ok(!ids().includes('urn:workpiece:1'), 'gone again');
    assert.ok((await vscode.commands.executeCommand('semforge.undo')).ok, 'and back, for the tests after');
    assert.ok(ids().includes('urn:workpiece:1'));
  });
});
