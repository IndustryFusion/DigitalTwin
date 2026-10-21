/*
 * The project cache, from the GUI: rescan, delete, and where it is.
 *
 * The SDK stores what every view and the Problems panel show, per package,
 * and serves it while no file of the package has changed. These two commands
 * are the author's override: Rescan rebuilds it from nothing, Delete removes
 * it (optionally with the downloaded JSON-LD contexts, which every package on
 * the machine shares).
 */

const vscode = require('vscode');

function register(context, clientHolder, session, refreshAll) {
  const uriOf = (node) => (node && node.packageUri) || session.uri;

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.rescan', async (node) => {
      const client = clientHolder.client;
      const uri = uriOf(node);
      if (!client || !uri) {
        vscode.window.showWarningMessage(
          'SemForge: no package is open, or the language server is not running.');
        return;
      }
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Window, title: 'SemForge: rescanning' },
        async () => {
          const result = await client.sendRequest('semforge/rescan', { uri });
          if (!result.ok) {
            vscode.window.showErrorMessage(`SemForge: ${result.error}`);
            return;
          }
          if (refreshAll) {
            refreshAll();
          }
          vscode.window.setStatusBarMessage('SemForge: rescanned from scratch', 5000);
        });
    }),

    vscode.commands.registerCommand('semforge.deleteCache', async (node) => {
      const client = clientHolder.client;
      const uri = uriOf(node);
      if (!client || !uri) {
        vscode.window.showWarningMessage(
          'SemForge: no package is open, or the language server is not running.');
        return;
      }
      const state = await client.sendRequest('semforge/cacheStatus', { uri });
      const views = (state.entries || []).length;
      const ONLY = 'Delete the cache';
      const ALSO = 'Also delete downloaded contexts';
      const answer = await vscode.window.showWarningMessage(
        `Delete the SemForge cache of this package?`,
        { modal: true,
          detail: `${views} stored view(s), ${Math.round((state.bytes || 0) / 1024)} KB, ` +
            `in ${state.path}.\n\nNothing is lost: the next scan rebuilds it. ` +
            'The downloaded JSON-LD contexts (the NGSI-LD core context) are ' +
            'shared by every package on this machine; deleting them too means ' +
            'the next scan downloads them again.' },
        ONLY, ALSO);
      if (answer !== ONLY && answer !== ALSO) {
        return;
      }
      const result = await client.sendRequest('semforge/clearCache',
        { uri, contexts: answer === ALSO });
      if (!result.ok) {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
        return;
      }
      vscode.window.setStatusBarMessage(
        `SemForge: cache deleted (${Math.round(result.bytes / 1024)} KB)`, 5000);
      if (refreshAll) {
        refreshAll();
      }
    })
  );
}

module.exports = { register };
