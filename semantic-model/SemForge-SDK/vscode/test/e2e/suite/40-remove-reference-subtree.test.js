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

'use strict';

// Remove with subtree… on a reference row: the row of one datasetId of a
// Relationship with several instances. The entity it points at goes with its
// subtree and that one reference; the other instances and their entities stay.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, semforge, row, answering } = require('./helpers');

const CUTTER = 'urn:plasmacutter:1';
const FILTER = 'iffBaseEntities:hasFilter';

describe('Remove with subtree… on a reference row', () => {
  it('removes the entity one datasetId points at, and only that reference', async function () {
    this.timeout(120000);
    const api = await semforge();
    const provider = api.trees.model.provider || api.trees.model;
    const model = path.join(WORKSPACE, 'model-instance.jsonld');
    const saved = fs.readFileSync(model, 'utf-8');
    try {
      const documents = JSON.parse(saved);
      const cutter = documents.find((d) => d.id === CUTTER);
      cutter[FILTER] = [{ type: 'Relationship', object: 'urn:filter:1', datasetId: 'urn:ds:a' },
        { type: 'Relationship', object: 'urn:filter:2', datasetId: 'urn:ds:b' }];
      fs.writeFileSync(model, JSON.stringify(documents, null, 2));
      const reference = await row(provider, (raw) => raw.kind === 'dataset' && raw.entity === CUTTER &&
        raw.object === 'urn:filter:2', 'the row of urn:ds:b');

      const session = answering([{ kind: 'warning', button: 'Remove' }]);
      let done;
      try {
        done = await vscode.commands.executeCommand('semforge.removeSubtree', reference);
      } finally {
        session.restore();
      }
      assert.ok(done && done.ok, JSON.stringify(done));
      assert.ok(session.asked[0].offered.message.startsWith('Remove urn:filter:2 with its subtree'),
        session.asked[0].offered.message);
      assert.ok(done.removed.includes('urn:filter:2'));
      const after = JSON.parse(fs.readFileSync(model, 'utf-8'));
      const ids = after.map((d) => d.id);
      assert.ok(done.removed.every((id) => !ids.includes(id)), 'the subtree is gone');
      assert.ok(ids.includes('urn:filter:1'), 'the other child stays');
      const left = [].concat(after.find((d) => d.id === CUTTER)[FILTER]);
      assert.deepStrictEqual(left.map((i) => [i.object, i.datasetId]), [['urn:filter:1', 'urn:ds:a']],
        'of the references only that one went');
    } finally {
      fs.writeFileSync(model, saved);
    }
  });
});
