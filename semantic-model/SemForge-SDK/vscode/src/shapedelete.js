/*
 * Delete… for a shape.
 *
 * What goes with a shape is the person's choice and is said first: the
 * asserts naming its constraints, and the cases that assert nothing else --
 * with their asserts gone they test nothing. A shape another shape reaches
 * through sh:node is refused by the SDK, which names the reference. Pinned
 * residues the shape was part of are pinned again.
 */

const path = require('path');
const vscode = require('vscode');

const REFRESH_VIEWS = ['semforge.refreshShapes', 'semforge.refreshTree',
  'semforge.refreshModel'];

const ALL = 'Delete it, its asserts and the cases';
const ASSERTS = 'Delete it and its asserts';
const ONLY = 'Delete it only';

/** What deleting says before it writes, and the buttons it offers. */
function planned(plan) {
  const lines = [`${path.basename(plan.file)}: its statement, and the property shapes ` +
    'inside it, go.'];
  let buttons = ['Delete'];
  if (plan.asserts) {
    lines.push('', `${plan.asserts} assert(s) in ${plan.cases.length} test case(s) name ` +
      'its constraints:', ...plan.cases.map((c) => `  ${c.case}` +
        (c.only ? ' — asserts nothing else' : '')));
    buttons = [ASSERTS, ONLY];
    if (plan.onlyCases.length) {
      lines.push('', `${plan.onlyCases.length} of them assert nothing else: with its asserts ` +
        'gone they test nothing, and can go with it' + (plan.suiteEmpties
        ? `, and ${plan.suite} with them, which then holds no case.` : '.'));
      buttons = [ALL, ASSERTS, ONLY];
    }
    lines.push(`"${ONLY}" keeps the asserts: those cases fail until you change them.`);
  }
  if (plan.residues.length) {
    lines.push('', `${plan.residues.length} case(s) pin a residue: each that holds now is ` +
      'pinned again.');
  }
  lines.push('', 'Deployed, its open alerts close for good after the next redeploy: nothing ' +
    'checks this any more.');
  return { detail: lines.join('\n'), buttons };
}

async function deleteShape(clientHolder, session, node, pages) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  const shape = node && node.raw && node.raw.shape;
  if (!client || !packageUri || !shape) {
    vscode.window.showWarningMessage('SemForge: Delete… works on a shape.');
    return undefined;
  }
  const plan = await client.sendRequest('semforge/deleteShapePlan', { uri: packageUri, shape });
  if (!plan.ok) {
    vscode.window.showErrorMessage(`SemForge: ${plan.error}`);
    return undefined;
  }
  const { detail, buttons } = planned(plan);
  const answer = await vscode.window.showWarningMessage(
    `Delete ${plan.name}?`, { modal: true, detail }, ...buttons);
  if (!answer) {
    return undefined;
  }
  // Its views go first: the workbench's query document is named by it.
  const bench = pages && pages.bench;
  if (bench && bench.current && bench.current.shape === shape && bench.panel) {
    if (bench.uri) {
      await bench.close(bench.uri);
    }
    bench.panel.dispose();
  }
  const done = await client.sendRequest('semforge/deleteShape', {
    uri: packageUri, shape, asserts: answer === ALL || answer === ASSERTS,
    cases: answer === ALL });
  if (!done.ok) {
    vscode.window.showErrorMessage(`SemForge: ${done.error}`);
    return undefined;
  }
  const page = pages && pages.shape;
  if (page && page.current && page.current.shape === shape && page.panel) {
    page.panel.dispose();
  }
  for (const command of REFRESH_VIEWS) {
    vscode.commands.executeCommand(command);
  }
  vscode.window.showInformationMessage(`SemForge: ${plan.name} deleted` +
    (done.assertsRemoved ? `, with ${done.assertsRemoved} assert(s)` : '') +
    (done.casesRemoved.length ? ` and ${done.casesRemoved.length} case(s)` : '') +
    (done.suiteRemoved ? `; ${done.suiteRemoved} is gone` : '') +
    (done.repinned.length ? `; ${done.repinned.length} residue(s) pinned again` : '') + '.');
  return done;
}

function register(context, clientHolder, session, pages) {
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.deleteShape',
      (node) => deleteShape(clientHolder, session, node, pages)));
}

module.exports = { register, deleteShape, planned };
