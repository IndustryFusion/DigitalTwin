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

/*
 * New test… for one attribute of an entity type.
 *
 * Asked where the question arises -- an attribute row in the Entity Types & Constraints view, a
 * row on the type page -- because that is where "hasPressure is new, what
 * proves its constraints work?" comes up. It offers what a test can prove:
 * that the attribute conforms, or that it fails. Why it fails is not chosen
 * here -- a list of everything SHACL can refuse never ends. The SDK writes the
 * case from a scene with an entity of the type; one that should fail asserts
 * nothing and fails, until its data is broken and what fires is asserted on
 * its case page.
 */

const vscode = require('vscode');

const { showLocation } = require('./reveal');
const { typeOf } = require('./typepage');

const REFRESH_VIEWS = ['semforge.refreshModel', 'semforge.refreshTree',
  'semforge.refreshShapes'];

const WORDS = { valid: '$(pass) Should conform', invalid: '$(error) Should fail' };

async function newAttributeTest(clientHolder, session, node) {
  const client = clientHolder.client;
  const raw = node && node.raw;
  const packageUri = (node && node.packageUri) || session.uri;
  const entityType = raw && typeOf(node);
  if (!client || !packageUri || !raw || !entityType || !Array.isArray(raw.path)) {
    vscode.window.showWarningMessage(
      'SemForge: New test… works on an attribute of an entity type — right-click ' +
        'one in the Entity Types & Constraints view, or use the row on its type page.');
    return false;
  }
  const offered = await client.sendRequest('semforge/attributeTestOptions',
    { uri: packageUri, entityType, path: raw.path });
  if (!offered.ok) {
    vscode.window.showErrorMessage(`SemForge: ${offered.error}`);
    return false;
  }
  const picked = await vscode.window.showQuickPick(
    offered.options.map((option) => ({
      label: WORDS[option.purpose],
      description: option.detail,
      option
    })),
    { title: `New test for ${offered.attribute} on ${offered.type}: what should it show?`,
      matchOnDescription: true });
  if (!picked) {
    return false;
  }
  const name = await vscode.window.showInputBox({
    title: `New test: ${offered.attribute} · ${picked.label.replace(/^\$\([a-z]+\) /, '')}`,
    prompt: 'A name for the case file (letters, digits, dashes)',
    value: picked.option.name,
    validateInput: (text) => (/[A-Za-z0-9]/.test(text) ? undefined : 'a name is required')
  });
  if (!name) {
    return false;
  }
  const made = await client.sendRequest('semforge/newAttributeTest',
    { uri: packageUri, entityType, path: raw.path, purpose: picked.option.purpose, name });
  if (!made.ok) {
    vscode.window.showErrorMessage(`SemForge: ${made.error}`);
    return false;
  }
  for (const command of REFRESH_VIEWS) {
    vscode.commands.executeCommand(command);
  }
  await vscode.commands.executeCommand('semforge.openCasePage',
    { raw: { kind: 'example', file: made.file }, packageUri });
  if (made.purpose === 'invalid') {
    vscode.window.showInformationMessage(
      `SemForge: ${made.case} written. It fails until you change its data so it violates, ` +
        'and assert what fires.');
    return true;
  }
  const said = made.passes ? `SemForge: ${made.case} written, and it passes — the entity conforms.`
    : `SemForge: ${made.case} written; it fails until its data is edited: ${made.failures.join('; ')}`;
  const open = await (made.passes ? vscode.window.showInformationMessage(said, 'Open .jsonld')
    : vscode.window.showWarningMessage(said, 'Open .jsonld'));
  if (open) {
    await showLocation(`${made.file}:1`, true);
  }
  return true;
}

function register(context, clientHolder, session) {
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.newAttributeTest',
      (node) => newAttributeTest(clientHolder, session, node)));
}

module.exports = { register, newAttributeTest };
