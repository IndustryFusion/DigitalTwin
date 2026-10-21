/*
 * Delete… for a test case and for a whole suite.
 *
 * A case is its file and its entry in expectations.yaml; both go. What a
 * deletion really costs is evidence -- the last case asserting a constraint
 * is the only proof that it can fire -- so the question names those
 * constraints. A file another case includes is shared data: its entry goes,
 * the file stays, and the question says so. The SDK refuses a suite while a
 * case outside it includes one of its files.
 */

const path = require('path');
const vscode = require('vscode');

const { closeTabs, refreshViews } = require('./rename');

/** The question's detail: what goes, what stays, what it costs. */
function described(plan) {
  const lines = [];
  if (plan.suite) {
    lines.push(`The folder ${plan.suite} goes, with its ${plan.cases.length} case(s):`,
      ...plan.cases.map((c) => `  ${c.case.slice(plan.suite.length + 1)}`));
  } else {
    const only = plan.cases[0];
    lines.push(`${path.basename(only.case)} and its entry in expectations.yaml go.`);
    if (only.keptFile) {
      lines.push(`The file itself stays: ${only.includedBy.join(', ')} include(s) it.`);
    }
  }
  if (plan.lost.length) {
    lines.push('', 'No other case asserts:', ...plan.lost.map((c) => `  ${c}`),
      'After this, nothing proves it can fire.');
  }
  return lines.join('\n');
}

async function deleteCases(clientHolder, session, node, pages) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  const raw = node && node.raw;
  const suite = raw && raw.kind === 'suite' ? (raw.term || raw.label) : '';
  const file = raw && raw.kind !== 'suite' ? raw.file : '';
  if (!client || !packageUri || !(suite || file)) {
    vscode.window.showWarningMessage('SemForge: Delete… works on a test case or a suite.');
    return undefined;
  }
  const params = { uri: packageUri, case: file || '', suite };
  const plan = await client.sendRequest('semforge/deleteCasePlan', params);
  if (!plan.ok) {
    vscode.window.showErrorMessage(`SemForge: ${plan.error}`);
    return undefined;
  }
  const what = suite ? `the suite ${suite}` : path.basename(file);
  const answer = await vscode.window.showWarningMessage(`Delete ${what}?`,
    { modal: true, detail: described(plan) }, 'Delete');
  if (answer !== 'Delete') {
    return undefined;
  }
  const done = await client.sendRequest('semforge/deleteCase', params);
  if (!done.ok) {
    vscode.window.showErrorMessage(`SemForge: ${done.error}`);
    return undefined;
  }
  // What showed the deleted files goes too.
  for (const gone of done.removed) {
    await closeTabs(gone);
  }
  const page = pages && pages.case;
  if (page && page.panel && page.current &&
      done.cases.some((c) => c.file === page.current.caseFile)) {
    page.panel.dispose();
  }
  refreshViews();
  vscode.window.setStatusBarMessage(`SemForge: ${what} deleted` +
    (done.lost.length ? ` — ${done.lost.length} constraint(s) no longer asserted anywhere` : ''),
  6000);
  return done;
}

function register(context, clientHolder, session, pages) {
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.deleteTestCase',
      (node) => deleteCases(clientHolder, session, node, pages)),
    vscode.commands.registerCommand('semforge.deleteSuite',
      (node) => deleteCases(clientHolder, session, node, pages)));
}

module.exports = { register, deleteCases, described };
