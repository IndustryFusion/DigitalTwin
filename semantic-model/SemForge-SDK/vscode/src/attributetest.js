/*
 * New test… for one attribute of an entity type.
 *
 * Asked where the question arises -- an attribute row in the Types view, a
 * row on the type page -- because that is where "hasPressure is new, what
 * proves its constraints work?" comes up. It offers what a test can prove:
 * the attribute valid, or one of its constraints firing. The SDK writes the
 * case from a scene with an entity of the type, breaking the attribute the
 * way the constraint forbids where that can be done mechanically, and runs it
 * once -- so the answer says whether the test already proves what it claims.
 */

const vscode = require('vscode');

const { showLocation } = require('./reveal');
const { typeOf } = require('./typepage');

const REFRESH_VIEWS = ['semforge.refreshModel', 'semforge.refreshTree',
  'semforge.refreshShapes'];

async function newAttributeTest(clientHolder, session, node) {
  const client = clientHolder.client;
  const raw = node && node.raw;
  const packageUri = (node && node.packageUri) || session.uri;
  const entityType = raw && typeOf(node);
  if (!client || !packageUri || !raw || !entityType || !Array.isArray(raw.path)) {
    vscode.window.showWarningMessage(
      'SemForge: New test… works on an attribute of an entity type — right-click ' +
        'one in the Types view, or use the row on its type page.');
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
      label: option.purpose === 'valid' ? '$(pass) valid' : `$(error) ${option.label}`,
      description: option.detail,
      detail: option.automatic ? undefined
        : 'Written from a valid scene; it fails until you edit the data.',
      option
    })),
    { title: `New test for ${offered.attribute} on ${offered.type}: what should it prove?`,
      matchOnDescription: true });
  if (!picked) {
    return false;
  }
  const name = await vscode.window.showInputBox({
    title: `New test: ${offered.attribute} · ${picked.option.label}`,
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
  const said = made.passes
    ? `SemForge: ${made.case} written, and it passes` +
      (made.constraint ? ` — ${made.constraint.split('/').slice(1).join(' ')} fires on ` +
        `${made.resource}.` : ' — the entity conforms.')
    : `SemForge: ${made.case} written; it fails until its data is edited: ` +
      made.failures.join('; ');
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
