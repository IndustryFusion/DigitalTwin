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

// The entity type page names the main-model's entities of its type; a click on
// one opens the Main page at it -- as a test case opens its case page.

const assert = require('assert');
const vscode = require('vscode');
const { PACKAGE_URI, semforge, until } = require('./helpers');

const ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/';

describe('The main-model from an entity type page', () => {
  it('a main-model entity opens the Main page at it', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openTypePage',
      { raw: { kind: 'type', targetClass: `${ENT}Filter`, label: 'Filter', children: [] },
        packageUri: PACKAGE_URI });
    const page = await until(() => api.pages.type.page && api.pages.type.page.label === 'Filter' &&
      api.pages.type.page, 'the Filter page');
    const entity = (page.instances || [])[0];
    assert.ok(entity, 'a Filter in the main-model');
    assert.ok(api.pages.type.panel.webview.html.includes(`data-model="${entity.id}"`));
    await api.pages.type.receive({ command: 'model', entity: entity.id });
    const main = await until(() => api.pages.case.page && api.pages.case.page.kind === 'model' &&
      api.pages.case.page, 'the Main page');
    assert.ok(main.files.some((f) => f.cards.some((c) => c.id === entity.id)));
    assert.ok(api.pages.case.panel.webview.html.includes('id="focus"'), 'scrolled to it');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
