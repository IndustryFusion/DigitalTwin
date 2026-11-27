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

// Remove with subtree… on a row of Entities & Test Cases: the subtree Copy
// with subtree copies, from the file the row is in -- and only that file.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, OPCUA, OPCUA_URI, semforge, row, until, answering } = require('./helpers');

describe('Remove with subtree… on an entity row', () => {
  it('asks, naming the subtree, and removes it from that file only', async function () {
    this.timeout(120000);
    const api = await semforge();
    const provider = api.trees.model.provider || api.trees.model;
    const target = path.join(WORKSPACE, 'examples', 'test_FilterShape', 'bad', 'without-cartridge.jsonld');
    const model = path.join(WORKSPACE, 'model-instance.jsonld');
    const saved = fs.readFileSync(target, 'utf-8');
    const main = fs.readFileSync(model, 'utf-8');
    try {
      const entity = await row(provider, (raw) => raw.kind === 'entity' && raw.entity === 'urn:plasmacutter:1' &&
        (!raw.file || raw.file === model),
        'the entity');
      const copied = await vscode.commands.executeCommand('semforge.copySubtree', entity);
      const onto = await row(provider, (raw) => raw.kind === 'example' && raw.file === target, 'the case');
      await vscode.commands.executeCommand('semforge.pasteEntity', onto);
      const pasted = await until(async () => row(provider, (raw) => raw.kind === 'entity' &&
        raw.entity === 'urn:plasmacutter:1' && raw.file === target), 'its row in the case');

      const session = answering([{ kind: 'warning', button: 'Remove' }]);
      let done;
      try {
        done = await vscode.commands.executeCommand('semforge.removeSubtree', pasted);
      } finally {
        session.restore();
      }
      assert.ok(done && done.ok, JSON.stringify(done));
      const asked = session.asked[0].offered.message;
      assert.strictEqual(asked, `Remove urn:plasmacutter:1 with its subtree (${copied.copied.length} ` +
        `entit${copied.copied.length === 1 ? 'y' : 'ies'})?`);
      assert.deepStrictEqual(done.removed, copied.copied, 'the subtree Copy with subtree copies');
      const ids = JSON.parse(fs.readFileSync(target, 'utf-8')).map((d) => d.id);
      assert.ok(!done.removed.some((id) => ids.includes(id)), 'gone from the case');
      assert.strictEqual(fs.readFileSync(model, 'utf-8'), main, 'Main is not touched');
    } finally {
      fs.writeFileSync(target, saved);
    }
  });

  it('removes a real subtree and the parent\'s reference to it, in a package with a hierarchy', async function () {
    this.timeout(120000);
    assert.ok(OPCUA_URI, 'the OPC UA pump slice beside the kms');
    await semforge();
    const model = path.join(OPCUA, 'model-instance.jsonld');
    const saved = fs.readFileSync(model, 'utf-8');
    // A pump part with three parts of its own, held by one parent.
    const root = 'sn1234c3Z1PXVybjpleGFtcGxlOm9wY3VhLXNlcnZlcjtuc3U9aHR0cDovL3lvdXJvcmdhbmlzYXRpb24ub3JnL0luc3RhbmNlRXhhbXBsZS87aT01MDEy';
    const holds = (doc) => JSON.stringify(doc).includes(`"${root}"`) && doc.id !== root;
    const before = JSON.parse(saved);
    assert.strictEqual(before.filter(holds).length, 1, 'one parent points at it');
    try {
      const session = answering([{ kind: 'warning', button: 'Remove' }]);
      let done;
      try {
        done = await vscode.commands.executeCommand('semforge.removeSubtree',
          { raw: { kind: 'entity', entity: root, file: model }, packageUri: OPCUA_URI });
      } finally {
        session.restore();
      }
      assert.ok(done && done.ok, JSON.stringify(done));
      assert.ok(session.asked[0].offered.message.startsWith(`Remove ${root} with its subtree (4 entities)?`),
        session.asked[0].offered.message);
      assert.strictEqual(done.removed.length, 4);
      assert.strictEqual(done.dropped.length, 1, 'the parent\'s reference');
      const after = JSON.parse(fs.readFileSync(model, 'utf-8'));
      const left = new Set(after.map((d) => d.id));
      assert.ok(done.removed.every((id) => !left.has(id)), 'the subtree is gone');
      assert.strictEqual(after.length, before.length - 4, 'nothing else');
      assert.strictEqual(after.filter(holds).length, 0, 'nothing points at it any more');
    } finally {
      fs.writeFileSync(model, saved);
    }
  });
});
