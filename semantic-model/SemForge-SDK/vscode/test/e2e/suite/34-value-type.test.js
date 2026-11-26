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

// The type of a value: said on the page, made another and back again.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, semforge, until, read, answering } = require('./helpers');

const MODEL = 'model-instance.jsonld';
const XSD = 'http://www.w3.org/2001/XMLSchema#';

describe('the type of a value', () => {
  it('is said, made another, refused and back to what the shape says', async () => {
    const api = await semforge();
    const saved = { [MODEL]: read(MODEL), 'shacl.ttl': read('shacl.ttl') };
    try {
      // hasStrength is a double alone, so that a type the shape does not ask for fires.
      fs.writeFileSync(path.join(WORKSPACE, 'shacl.ttl'), saved['shacl.ttl']
        .replace('sh:or ([sh:datatype xsd:double] [sh:datatype xsd:integer]) ;', 'sh:datatype xsd:double ;'));
      await vscode.commands.executeCommand('workbench.action.closeAllEditors');
      await vscode.commands.executeCommand('semforge.openModelPage');
      const strength = async (wanted) => {
        const page = await until(() => api.pages.case.page && api.pages.case.page.kind === 'model' &&
          api.pages.case.panel && api.pages.case.page, 'the Main page');
        let found;
        page.files.forEach((file, f) => file.cards.forEach((card, c) => card.attributes.forEach((attribute, r) => {
          if (card.id === 'urn:filter:1' && attribute.name === 'hasStrength' && !attribute.superseded &&
              (!wanted || attribute.valueType === wanted)) {
            found = { at: `${f}.${c}.${r}`, row: attribute };
          }
        })));
        return found;
      };
      const value = () => {
        const { row } = api.pages.case.page.files.flatMap((f) => f.cards).flatMap((c) => c.attributes)
          .map((row) => ({ row })).find(({ row }) => row.node && row.node.entity === 'urn:filter:1' &&
            row.name === 'hasStrength' && !row.superseded);
        const entity = JSON.parse(read(MODEL)).find((e) => e.id === 'urn:filter:1');
        return row.node.path.reduce((at, step) => at[step], entity);
      };
      const choose = async (label, wanted) => {
        const { at } = await until(() => strength(), 'the strength of urn:filter:1');
        const session = answering([{ kind: 'pick', label }]);
        try {
          await api.pages.case.receive({ command: 'valueType', at });
        } finally {
          session.restore();
        }
        return until(() => strength(wanted), `the page saying ${wanted}`);
      };

      const first = await until(() => strength(), 'the strength of urn:filter:1');
      assert.ok(first.row.valueType, 'the page says its type');
      assert.strictEqual(first.row.valueType, 'double', '0.6 is a double');
      await choose('Text', 'text');
      assert.strictEqual(value(), '0.6');
      await until(() => api.pages.case.page.files.some((f) => f.cards.some((c) => c.id === 'urn:filter:1' &&
        JSON.stringify(c.violations.concat(...c.attributes.map((a) => a.violations))).includes('Datatype'))),
      'a text, which is no double, to violate');
      const before = read(MODEL);
      await choose('True / false', 'text');
      assert.strictEqual(read(MODEL), before, 'refused, and the file is as it was');
      await choose('As the shape says', 'double');
      assert.deepStrictEqual(value(), { '@value': 0.6, '@type': `${XSD}double` });
    } finally {
      for (const [name, text] of Object.entries(saved)) {
        fs.writeFileSync(path.join(WORKSPACE, name), text);
      }
    }
  });
});
