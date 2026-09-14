/*
 * Deleting a project.
 *
 * The one gesture here that cannot be undone by another gesture, so it is the
 * one that has to say the most before it happens. Three things a person needs
 * and cannot see from a tree row: what in that directory is NOT the package,
 * whether it contains packages of its own, and whether git has any of it --
 * tracked files come back with one command, untracked ones do not come back at
 * all. The server reads all three; see semforge/package/removal.py.
 *
 * Then it goes to the TRASH, not to unlink. A confirmation is a guess about
 * what somebody meant; the trash is the thing that forgives being wrong.
 */

const path = require('path');
const vscode = require('vscode');

function describe(plan) {
  const size = plan.bytes > 1024 * 1024
    ? `${Math.round(plan.bytes / (1024 * 1024))} MB`
    : `${Math.max(1, Math.round(plan.bytes / 1024))} KB`;
  return [`${plan.path}`, '', `${plan.files} file(s), ${size}.`, '']
    .concat(plan.warnings || [])
    .join('\n');
}

/**
 * Ask, twice, and only then move it to the trash.
 *
 * The second ask is typing the name. A modal is dismissed by the same reflex
 * that opened it, and this is the wrong place for a reflex.
 */
async function deleteProject(client, uri, refreshAll) {
  const plan = await client.sendRequest('semforge/deletionPlan', { uri });
  if (!plan || !plan.ok) {
    vscode.window.showErrorMessage(
      `SemForge: ${(plan && plan.error) || 'nothing to delete here'}`
    );
    return false;
  }

  const answer = await vscode.window.showWarningMessage(
    `Delete the project "${plan.name}"?`,
    { modal: true, detail: describe(plan) },
    'Move to Trash'
  );
  if (answer !== 'Move to Trash') {
    return false;
  }

  const folder = path.basename(plan.path);
  const typed = await vscode.window.showInputBox({
    title: `Delete "${plan.name}"`,
    prompt: `Type ${folder} to confirm. This moves the whole directory to the trash.`,
    validateInput: (text) =>
      text === folder ? undefined : `Type ${folder} exactly, or press Escape.`
  });
  if (typed !== folder) {
    return false;
  }

  try {
    await vscode.workspace.fs.delete(vscode.Uri.file(plan.path), {
      recursive: true,
      useTrash: true
    });
  } catch (error) {
    vscode.window.showErrorMessage(
      `SemForge: ${plan.path} was not deleted — ${error.message || error}`
    );
    return false;
  }

  if (refreshAll) {
    refreshAll();
  }
  vscode.window.showInformationMessage(
    `SemForge: ${plan.name} moved to the trash.`
  );
  return true;
}

function register(context, clientHolder, session, refreshAll) {
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.deleteProject', async (node) => {
      // From the Explorer the node is a Uri; from the view title there is
      // none, and the project meant is the one the views are showing.
      const target = (node && node.fsPath && node.toString()) ||
        (node && node.packageUri) || session.uri;
      if (!target) {
        vscode.window.showWarningMessage(
          'SemForge: no package here to delete.'
        );
        return;
      }
      const gone = await deleteProject(clientHolder.client, target, () => {
        session.discover();
        if (refreshAll) {
          refreshAll();
        }
      });
      if (gone) {
        session.discover();
      }
    })
  );
}

module.exports = { register, deleteProject, describe };
