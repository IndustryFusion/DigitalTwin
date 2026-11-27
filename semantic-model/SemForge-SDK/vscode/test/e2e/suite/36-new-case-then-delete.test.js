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

// New case… on a shape page asks what the case should show and writes it
// empty; deleted again from its row in Entities & Test Cases, the delete
// finishes and no page is left showing the evaluating strip.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, PACKAGE_URI, semforge, row, until, answering } = require('./helpers');

const SHAPE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnFilterShape';
const SUITE = 'test_StateOnFilterShape';

function within(promise, ms, what) {
  let timer;
  return Promise.race([promise, new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`${what}: no answer after ${ms} ms`)), ms);
  })]).finally(() => clearTimeout(timer));
}

/** The open SemForge pages that still show the evaluating strip. */
function striped(api) {
  return [['shape', api.pages.shape], ['main', api.pages.case && api.pages.case.main],
    ['case', api.pages.case && api.pages.case.cases]]
    .filter(([, page]) => page && page.panel && page.panel.visible &&
      /class="vstrip"/.test(page.panel.webview.html))
    .map(([name]) => name);
}

describe('New case… on a shape page, then Delete… from its row', () => {
  it('asks good or bad, starts empty, and deletes again', async function () {
    this.timeout(180000);
    const api = await semforge();
    // Whatever happens, no run leaves its case for the next one.
    const bad = path.join(WORKSPACE, 'examples', SUITE, 'bad');
    const declared = path.join(bad, 'expectations.yaml');
    const before = fs.existsSync(declared) ? fs.readFileSync(declared, 'utf-8') : undefined;
    const written = path.join(bad, 'gone-again.jsonld');
    const folders = [path.join(WORKSPACE, 'examples'), path.dirname(bad), bad].filter((f) => !fs.existsSync(f));
    try {
      await vscode.commands.executeCommand('semforge.openShapePage',
        { raw: { shape: SHAPE }, packageUri: PACKAGE_URI });
      await until(() => api.pages.shape.page && api.pages.shape.page.iri === SHAPE, 'the shape page');

      const making = answering([{ kind: 'pick', label: '$(error) Should fail' },
        { kind: 'input', value: 'gone-again' },
        { kind: 'message', button: 'Open .jsonld' }]);
      try {
        await within(api.pages.shape.newCase(), 60000, 'New case…');
      } finally {
        making.restore();
      }
      assert.strictEqual(making.asked[0].kind, 'pick', 'good or bad is asked first');
      assert.deepStrictEqual(making.asked[0].offered, ['$(pass) Should conform', '$(error) Should fail']);

      const suite = await row(api.trees.model, (raw) => raw.kind === 'suite' &&
        (raw.term || raw.label) === SUITE, 'the suite');
      const children = await api.trees.model.getChildren(suite);
      const rows = children.concat(...await Promise.all(children.filter((n) => n.raw.kind !== 'example')
        .map((n) => api.trees.model.getChildren(n))));
      const made = rows.find((n) => n.raw.kind === 'example' && String(n.raw.file).endsWith('gone-again.jsonld'));
      assert.ok(made, 'the new case has its row');
      assert.deepStrictEqual(JSON.parse(fs.readFileSync(made.raw.file, 'utf-8')), [],
        'it starts empty: its entities are pasted from Main');

      const deleting = answering([{ kind: 'warning', button: 'Delete' }]);
      let done;
      try {
        done = await within(vscode.commands.executeCommand('semforge.deleteTestCase', made), 30000, 'Delete…');
      } finally {
        deleting.restore();
      }
      assert.ok(done && done.ok, JSON.stringify(done));
      assert.ok(!fs.existsSync(made.raw.file));

      // The shape page brought to the front again: once the background run is
      // over, nothing still says it is evaluating.
      await vscode.commands.executeCommand('semforge.openShapePage',
        { raw: { shape: SHAPE }, packageUri: PACKAGE_URI });
      await until(() => striped(api).length === 0, 'no page left evaluating', 60000);
    } finally {
      fs.rmSync(written, { force: true });
      if (before === undefined) {
        fs.rmSync(declared, { force: true });
      } else {
        fs.writeFileSync(declared, before);
      }
      for (const folder of folders.reverse()) {
        if (fs.existsSync(folder) && !fs.readdirSync(folder).length) {
          fs.rmdirSync(folder);
        }
      }
    }
  });
});
