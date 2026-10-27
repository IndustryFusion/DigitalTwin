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

// What the OPC UA tool chain writes, in a real VS Code: the pump slice
// (tests/corpus/opcua-pumps), copied beside the workspace by run.js and
// answered for by the same server. Every Variable is one value or a list of
// them; New test… writes a case that passes; a list of rdf:JSON items is
// warned about; and rdf:JSON is a datatype the editor offers.

const assert = require('assert');
const path = require('path');
const vscode = require('vscode');
const { OPCUA, OPCUA_URI, semforge, until } = require('./helpers');

const PUMP = 'http://opcfoundation.org/UA/Pumps/';

function ask(api, method, params) {
  return api.clientHolder.client.sendRequest(method, Object.assign({ uri: OPCUA_URI }, params));
}

async function drivePage(api) {
  await vscode.commands.executeCommand('semforge.openTypePage',
    { raw: { kind: 'type', targetClass: `${PUMP}DriveMeasurementsType`, children: [] },
      packageUri: OPCUA_URI });
  return until(() => api.pages.type.page && api.pages.type.page.label === 'DriveMeasurementsType' &&
    api.pages.type.page, 'the DriveMeasurementsType page', 90000);
}

describe('An OPC UA package', () => {
  it('a Variable is one value or a list of them, on its type page', async () => {
    const api = await semforge();
    assert.ok(OPCUA, 'run.js copies the OPC UA slice');
    const page = await drivePage(api);
    const voltage = page.attributes.find((a) => a.label === 'hasVoltage');
    assert.deepStrictEqual(voltage.kinds, ['Property', 'ListProperty']);
    assert.strictEqual(voltage.value, 'number, or a list of them (possibly empty)');
    assert.ok(api.pages.type.panel.webview.html.includes('<h1>Entity type: DriveMeasurementsType</h1>'));
  });

  it('opens again in seconds, and its editor shows both forms', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
    const started = Date.now();
    const page = await drivePage(api);
    const seconds = (Date.now() - started) / 1000;
    assert.ok(seconds < 10, `the page took ${seconds}s the second time`);
    const row = page.attributes.findIndex((a) => a.label === 'hasVoltage');
    await api.pages.type.receive({ command: 'attribute', row });
    const html = await until(() => api.pages.attribute && api.pages.attribute.panel &&
      api.pages.attribute.panel.title === 'Attribute: hasVoltage' &&
      api.pages.attribute.panel.webview.html, 'the attribute editor');
    assert.ok(html.includes('data-act="lists-off"'), 'a list is allowed: One value only is offered');
    assert.match(html, /ngsi-ld:hasValue\b/);
    assert.match(html, /ngsi-ld:hasValueList\b/);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('New test… writes a valid case that passes, in seconds', async () => {
    const api = await semforge();
    const page = await ask(api, 'semforge/typePage', { entityType: `${PUMP}DriveMeasurementsType` });
    const row = page.attributes.find((a) => a.label === 'hasVoltage');
    const options = await ask(api, 'semforge/attributeTestOptions',
      { entityType: `${PUMP}DriveMeasurementsType`, path: row.path });
    assert.ok(options.ok, options.error);
    const started = Date.now();
    const made = await ask(api, 'semforge/newAttributeTest',
      { entityType: `${PUMP}DriveMeasurementsType`, path: row.path, purpose: 'valid',
        name: 'voltage-valid-e2e' });
    const seconds = (Date.now() - started) / 1000;
    assert.ok(made.ok, made.error);
    assert.ok(made.passes, JSON.stringify(made.failures));
    assert.ok(seconds < 10, `New test… took ${seconds}s`);
    assert.ok(made.file.startsWith(OPCUA), made.file);
  });

  it('a list of rdf:JSON items is a warning in the shapes file', async () => {
    const api = await semforge();
    const document = await vscode.workspace.openTextDocument(path.join(OPCUA, 'shacl.ttl'));
    await vscode.window.showTextDocument(document);
    const warned = await until(() => vscode.languages.getDiagnostics(document.uri)
      .find((d) => String(d.code && (d.code.value || d.code)) === 'json-never-holds'),
    'the json-never-holds warning', 90000);
    assert.strictEqual(warned.severity, vscode.DiagnosticSeverity.Warning);
    assert.match(warned.message, /hasDirectivesOfEUDeclarationOfConformity/);
    assert.ok(api);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('rdf:JSON is a datatype the editor offers', async () => {
    const api = await semforge();
    const page = await ask(api, 'semforge/typePage', { entityType: `${PUMP}DriveMeasurementsType` });
    const row = page.attributes.find((a) => a.label === 'hasVoltage');
    const offered = await ask(api, 'semforge/choices',
      { path: [row.term, 'ngsild:hasValue'], parameter: 'sh:datatype', search: null });
    assert.ok((offered.choices || []).some((c) => c.value === 'rdf:JSON'),
      JSON.stringify((offered.choices || []).map((c) => c.value)));
  });

  // The pump's Main page is many screens long: the jump to an entity, in the
  // real webview, from wherever the last one left it.
  it('opens its Main page at any entity, and that entity is in sight', async () => {
    const api = await semforge();
    const page = await until(async () => {
      const found = await ask(api, 'semforge/modelPage', {});
      return found.ok && found.files && found.files[0].cards.length > 3 && found;
    }, 'the Main page', 90000);
    const cards = page.files[0].cards;
    const picks = [cards[cards.length - 1], cards[Math.floor(cards.length / 2)], cards[0],
      cards[cards.length - 2]];
    for (const card of picks) {
      const attribute = (card.attributes.find((a) => a.name) || {}).name;
      api.pages.case.landed = undefined;
      await vscode.commands.executeCommand('semforge.openModelPage', { packageUri: OPCUA_URI },
        { focus: card.id, attribute, preserveFocus: true });
      const landed = await until(() => api.pages.case.landed &&
        api.pages.case.landed.entity === card.id && api.pages.case.landed,
      `${card.id} landed`, 90000);
      assert.ok(landed.page > 2 * landed.height, `a page to scroll: ${JSON.stringify(landed)}`);
      assert.ok(landed.inView, JSON.stringify(landed));
    }
  });
});
