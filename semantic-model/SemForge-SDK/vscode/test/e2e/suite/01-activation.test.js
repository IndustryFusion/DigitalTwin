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

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { semforge, request } = require('./helpers');

describe('activation', () => {
  it('starts its language server on the package', async () => {
    const api = await semforge();
    const answer = await request(api, 'semforge/methods', {});
    for (const method of ['semforge/model', 'semforge/casePage', 'semforge/modelPage',
      'semforge/typePage', 'semforge/valueChoices', 'semforge/addEntityType']) {
      assert.ok(answer.methods.includes(method), `the server cannot answer ${method}`);
    }
  });

  it('registers every command it contributes', async () => {
    await semforge();
    const manifest = JSON.parse(fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'package.json'), 'utf-8'));
    const registered = new Set(await vscode.commands.getCommands(true));
    const missing = manifest.contributes.commands.map((c) => c.command)
      .filter((command) => !registered.has(command));
    assert.deepStrictEqual(missing, []);
  });
});
