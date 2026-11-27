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

// New test… of a SPARQL query, from its row on the type page to a case that
// fails until the query fires, and passes then.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, PACKAGE_URI, semforge, until, answering, read } = require('./helpers');

const FILTER = 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter';
const SUITE = path.join('examples', 'test_StateOnFilterShape', 'bad');

describe('New test of a query', () => {
  it('is written from the row on the type page, and passes once the query fires', async () => {
    const api = await semforge();
    const declared = path.join(WORKSPACE, SUITE, 'expectations.yaml');
    const before = fs.existsSync(declared) ? read(path.join(SUITE, 'expectations.yaml')) : undefined;
    // Removed whatever happens, so no run leaves a case for the next one.
    const written = path.join(WORKSPACE, SUITE, 'query-e2e.jsonld');
    const folders = [path.dirname(path.dirname(SUITE)), path.dirname(SUITE), SUITE]
      .filter((f) => !fs.existsSync(path.join(WORKSPACE, f)));
    let file;
    try {
      await vscode.commands.executeCommand('workbench.action.closeAllEditors');
      await vscode.commands.executeCommand('semforge.openTypePage',
        { raw: { targetClass: FILTER }, packageUri: PACKAGE_URI });
      const type = await until(() => api.pages.type.page && api.pages.type.page.iri === FILTER &&
        api.pages.type.page.rules && api.pages.type.page, 'the type page');
      const row = type.rules.findIndex((r) => r.shapeName.endsWith('StateOnFilterShape'));
      assert.ok(row >= 0, 'the query is on the page');
      const session = answering([{ kind: 'pick', label: '$(beaker) New test…' },
        { kind: 'pick', label: '$(error) Should fail' }, { kind: 'input', value: 'query-e2e' }]);
      try {
        await api.pages.type.receive({ command: 'ruleMenu', row });
      } finally {
        session.restore();
      }
      const page = await until(() => api.pages.case.page && api.pages.case.page.file &&
        api.pages.case.page.file.endsWith('query-e2e.jsonld') &&
        api.pages.case.page.verdicts.state === 'ready' && api.pages.case.page, 'its case page');
      file = page.file;
      assert.strictEqual(fs.realpathSync(file), fs.realpathSync(written));
      assert.deepStrictEqual(JSON.parse(fs.readFileSync(file, 'utf-8')), [], 'it starts empty');
      assert.strictEqual(page.passed, false, 'nothing in it, nothing fires');
      assert.strictEqual(page.claims.length, 0, 'no entity to name an assert for yet');

      // Its scene, pasted from Main: the filter and the cutter it belongs to.
      const client = api.clientHolder.client;
      let taken;
      for (const entity of ['urn:filter:1', 'urn:plasmacutter:1']) {
        const copied = await client.sendRequest('semforge/copyEntities', { uri: PACKAGE_URI, entity });
        assert.ok(copied.ok, copied.error);
        const content = JSON.parse(copied.content);
        if (taken) {
          taken.entities.push(...content.entities);
        } else {
          taken = content;
        }
      }
      const pasted = await client.sendRequest('semforge/pasteEntities',
        { uri: PACKAGE_URI, case: file, content: JSON.stringify(taken) });
      assert.ok(pasted.ok, pasted.error);

      // The filter is on, the cutter it belongs to stops: the query fires,
      // and the case fails until it says why.
      const set = await client.sendRequest('semforge/setValue', {
        // Main writes the cutter's state as a list of one instance.
        uri: PACKAGE_URI, entity: 'urn:plasmacutter:1', path: ['iffBaseEntities:hasState', 0, 'value'],
        file, value: JSON.stringify({ '@id': 'base:state_OFF' }) });
      assert.ok(set.ok, set.error);
      const ready = () => api.pages.case.page && api.pages.case.page.file === file &&
        api.pages.case.page.verdicts.state === 'ready' && api.pages.case.page;
      await vscode.commands.executeCommand('semforge.openCasePage',
        { raw: { kind: 'example', file }, packageUri: PACKAGE_URI });
      await until(() => ready() && ready().passed === false, 'the case to fire unasserted');
      const added = await client.sendRequest('semforge/addAssert', { uri: PACKAGE_URI,
        case: 'test_StateOnFilterShape/bad/query-e2e.jsonld',
        constraint: 'iffBaseShacl:StateOnFilterShape/SPARQLConstraintComponent', resource: 'urn:filter:1' });
      assert.ok(added.ok, added.error);
      await vscode.commands.executeCommand('semforge.openCasePage',
        { raw: { kind: 'example', file }, packageUri: PACKAGE_URI });
      await until(() => ready() && ready().passed === true, 'the case to pass once asserted');
    } finally {
      fs.rmSync(written, { force: true });
      if (file) {
        fs.rmSync(file, { force: true });
      }
      if (before === undefined) {
        fs.rmSync(declared, { force: true });
      } else {
        fs.writeFileSync(declared, before);
      }
      for (const folder of folders.reverse()) {
        fs.rmSync(path.join(WORKSPACE, folder), { recursive: true, force: true });
      }
      await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    }
  });
});
