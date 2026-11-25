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

// The shape may write an attribute with another prefix of the same namespace
// than the data does: a number typed for a double is declared all the same.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, semforge, until, read, answering } = require('./helpers');

const MODEL = 'model-instance.jsonld';

describe('a value of an attribute the shape writes with another prefix', () => {
  it('is declared a double', async () => {
    const api = await semforge();
    const saved = { [MODEL]: read(MODEL), 'shacl.ttl': read('shacl.ttl') };
    try {
      fs.writeFileSync(path.join(WORKSPACE, 'shacl.ttl'),
        '@prefix other: <https://industryfusion.github.io/contexts/example/v0/base_entities/> .\n' +
        saved['shacl.ttl'].replaceAll('iffBaseEntities:hasStrength', 'other:hasStrength')
          .replace('sh:or ([sh:datatype xsd:double] [sh:datatype xsd:integer]) ;', 'sh:datatype xsd:double ;'));
      assert.ok(read('shacl.ttl').includes('sh:path other:hasStrength'), 'the shape is rewritten');
      await vscode.commands.executeCommand('workbench.action.closeAllEditors');
      await vscode.commands.executeCommand('semforge.openModelPage');
      const page = await until(() => api.pages.case.page && api.pages.case.page.kind === 'model' &&
        api.pages.case.panel && api.pages.case.page, 'the Main page');
      let at;
      let edited;
      page.files.forEach((file, f) => file.cards.forEach((card, c) => card.attributes.forEach((attribute, r) => {
        if (card.id === 'urn:filter:1' && attribute.name === 'hasStrength') {
          at = `${f}.${c}.${r}`;
          edited = attribute.node.path;
        }
      })));
      assert.ok(at, 'the strength of urn:filter:1 is on the page');
      const session = answering([{ kind: 'input', value: '50.0' }]);
      try {
        await api.pages.case.receive({ command: 'edit', at });
      } finally {
        session.restore();
      }
      const entity = JSON.parse(read(MODEL)).find((e) => e.id === 'urn:filter:1');
      assert.deepStrictEqual(edited.reduce((value, step) => value[step], entity),
        { '@value': 50, '@type': 'http://www.w3.org/2001/XMLSchema#double' });
    } finally {
      for (const [name, text] of Object.entries(saved)) {
        fs.writeFileSync(path.join(WORKSPACE, name), text);
      }
    }
  });
});
