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

// A query open in the SPARQL workbench while shacl.ttl changes underneath --
// a text editor, a checkout, Undo: the editor shows what the file now holds,
// and saving is held against that. It used to keep the old text, and a save
// was refused as if the file had changed since the workbench opened it.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, WORKSPACE, semforge, until } = require('./helpers');

const SHAPE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnFilterShape';

describe('A query changed outside the workbench', () => {
  it('is shown as the file now holds it, and saves against that', async function () {
    this.timeout(120000);
    const api = await semforge();
    const shapes = path.join(WORKSPACE, 'shacl.ttl');
    const before = fs.readFileSync(shapes, 'utf-8');
    try {
      await vscode.commands.executeCommand('semforge.openSparqlBench',
        { raw: { shape: SHAPE }, packageUri: PACKAGE_URI }, {});
      await until(() => api.pages.sparql.page && api.pages.sparql.page.shape === SHAPE, 'the workbench');
      const doc = await until(() => api.pages.sparql.document(), 'its document');
      assert.ok(!doc.getText().includes('# changed outside'));
      // Written as a checkout or another editor would: not through SemForge.
      const changed = before.replace('FILTER(?v1 = base:state_ON', '# changed outside\n    FILTER(?v1 = base:state_ON');
      assert.notStrictEqual(changed, before, 'the query is in shacl.ttl');
      fs.writeFileSync(shapes, changed);
      await until(() => doc.getText().includes('# changed outside'), 'the editor showing the new text');
      assert.strictEqual(doc.isDirty, false);

      // And a save goes through: held against what the file holds now.
      const edit = new vscode.WorkspaceEdit();
      edit.insert(doc.uri, doc.positionAt(doc.getText().indexOf('# changed outside')), '# and saved\n    ');
      await vscode.workspace.applyEdit(edit);
      assert.ok(await doc.save(), 'saved');
      await until(() => fs.readFileSync(shapes, 'utf-8').includes('# and saved'), 'shacl.ttl holding the save');
    } finally {
      await vscode.commands.executeCommand('workbench.action.closeAllEditors');
      fs.writeFileSync(shapes, before);
    }
  });
});
