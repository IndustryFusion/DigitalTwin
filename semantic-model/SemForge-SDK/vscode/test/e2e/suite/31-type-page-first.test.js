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

// After an attribute is added on a type page, the page is asked for before
// the trees: the server answers one request at a time, and the page is what
// one waits for. And it comes back within seconds.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, PACKAGE_URI, semforge, until, read, answering } = require('./helpers');

describe('the type page after an edit', () => {
  it('is asked for before the trees', async () => {
    const api = await semforge();
    const saved = { shapes: read('shacl.ttl'), knowledge: read('knowledge.ttl') };
    const client = api.clientHolder.client;
    const real = client.sendRequest;
    const asked = [];
    client.sendRequest = function (method, ...rest) {
      asked.push(method);
      return real.call(client, method, ...rest);
    };
    try {
      await vscode.commands.executeCommand('workbench.action.closeAllEditors');
      await vscode.commands.executeCommand('semforge.openTypePage', { packageUri: PACKAGE_URI, raw: {
        targetClass: 'https://industryfusion.github.io/contexts/example/v0/base_entities/Workpiece' } });
      await until(() => api.pages.type.page && api.pages.type.page.label === 'Workpiece', 'the type page');
      let picked;
      const session = answering([
        { kind: 'pick', choose: (items) => {
          picked = items.find((item) => item.option && item.option.status === 'elsewhere' &&
            item.option.label === 'hasStrength');
          return picked;
        } },
        { kind: 'warning', button: 'Give it to this type too' },
        { kind: 'pick', label: 'Optional' },
        { kind: 'pick', choose: (items) => items.find((item) => ['Any value', 'Any entity'].includes(item.label)) }]);
      try {
        await api.pages.type.receive({ command: 'addAttribute', row: -1 });
      } finally {
        session.restore();
      }
      assert.ok(picked, 'hasStrength, a Filter attribute, was offered');
      await until(() => api.pages.type.page.attributes.some((a) => a.label === picked.option.label && !a.inherited),
        'the page to show it', 15000);
      const written = asked.lastIndexOf('semforge/addAttributeConstraint');
      const after = asked.slice(written + 1);
      await until(() => asked.slice(written + 1).includes('semforge/tree'), 'the trees to follow');
      assert.ok(after.includes('semforge/typePage'), after.join(', '));
      const first = asked.slice(written + 1);
      assert.ok(first.indexOf('semforge/typePage') < first.indexOf('semforge/tree'), first.join(', '));
    } finally {
      client.sendRequest = real;
      fs.writeFileSync(path.join(WORKSPACE, 'shacl.ttl'), saved.shapes);
      fs.writeFileSync(path.join(WORKSPACE, 'knowledge.ttl'), saved.knowledge);
      await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    }
  });
});
