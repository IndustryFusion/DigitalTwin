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

// sh:in and sh:hasValue in plain words, one value per row, against the real
// language server: what the rows say is what the shapes file holds.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, PACKAGE_URI, semforge, until, read } = require('./helpers');

const FILTER = 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter';

describe('a list of values', () => {
  it('is set, added to, taken from and shown in plain words', async () => {
    const api = await semforge();
    const shapes = read('shacl.ttl');
    try {
      await vscode.commands.executeCommand('semforge.openTypePage',
        { raw: { targetClass: FILTER }, packageUri: PACKAGE_URI });
      const type = await until(() => api.pages.type.page, 'the type page');
      const row = type.attributes.findIndex((a) => a.label === 'hasStrength');
      await api.pages.type.receive({ command: 'attribute', row });
      const editor = await until(() => require('../../../src/attributepanel').current(), 'the attribute editor');
      const set = (rows) => editor.receive({ command: 'edit', action: { op: 'set', form: 0, node: [0],
        parameter: 'sh:in', value: rows } });
      const text = (t) => ({ kind: 'text', text: t });

      await set([text('Executing')]);
      assert.strictEqual(editor.error, '');
      assert.ok(read('shacl.ttl').includes('sh:in ( "Executing" )'), 'one text');

      // A value added: a text with a comma and quotes, and a number.
      await set([text('Executing'), text('say "hi", twice'), { kind: 'number', text: '5' }]);
      assert.strictEqual(editor.error, '');
      assert.ok(read('shacl.ttl').includes('sh:in ( "Executing" "say \\"hi\\", twice" 5 )'),
        read('shacl.ttl').match(/sh:in \([^)]*\)/));
      await until(() => editor.panel.webview.html.includes('Executing · say &quot;hi&quot;, twice · 5'),
        'the values in plain words');

      // One taken out; a word as a number is refused and nothing is written.
      await set([text('say "hi", twice'), { kind: 'number', text: '5' }]);
      assert.ok(read('shacl.ttl').includes('sh:in ( "say \\"hi\\", twice" 5 )'));
      const before = read('shacl.ttl');
      await set([{ kind: 'number', text: 'many' }]);
      assert.match(editor.error, /many is not a number/);
      assert.strictEqual(read('shacl.ttl'), before, 'the shapes file is unchanged');

      // The type page says the list the same way.
      await until(() => {
        const page = api.pages.type.page;
        const strength = page && page.attributes.find((a) => a.label === 'hasStrength');
        return strength && strength.value.includes('one of: say "hi", twice · 5');
      }, 'the type page row in plain words');
    } finally {
      fs.writeFileSync(path.join(WORKSPACE, 'shacl.ttl'), shapes);
      await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    }
  });
});
