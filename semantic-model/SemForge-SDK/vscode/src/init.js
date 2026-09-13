/*
 * Creating a package from the editor.
 *
 * "Open a folder and click the icon" needs an answer for the folder that is not
 * a package yet, and "run this CLI command" is not it. The scaffold itself
 * stays in the SDK -- the editor asks `semforge/init` for it -- so a package
 * made here is the same package `semforge init` makes.
 */

const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const { findPackageUri } = require('./locate');
const { showLocation } = require('./reveal');

/** Where to put it: a workspace folder, or one chosen with the dialog. */
async function chooseDirectory() {
  const folders = vscode.workspace.workspaceFolders || [];
  const choices = folders.map((folder) => ({
    label: folder.name,
    description: folder.uri.fsPath,
    value: folder.uri.fsPath
  }));
  choices.push({ label: '$(folder-opened) Choose another folder…', value: '' });

  const picked = choices.length === 2
    ? choices[0]
    : await vscode.window.showQuickPick(choices, {
      title: 'Where should the package go?'
    });
  if (!picked) {
    return undefined;
  }
  if (picked.value) {
    return picked.value;
  }
  const chosen = await vscode.window.showOpenDialog({
    canSelectFolders: true,
    canSelectFiles: false,
    openLabel: 'Create the package here'
  });
  return chosen && chosen.length ? chosen[0].fsPath : undefined;
}

function register(context, clientHolder, onCreated) {
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.initPackage', async () => {
      const client = clientHolder.client;
      if (!client) {
        vscode.window.showErrorMessage(
          'SemForge: the language server is not running — run "SemForge: Doctor".'
        );
        return;
      }

      const directory = await chooseDirectory();
      if (!directory) {
        return;
      }
      const name = await vscode.window.showInputBox({
        title: 'Package name',
        prompt: 'Used for the namespace prefixes and the README',
        value: path.basename(directory)
      });
      if (name === undefined) {
        return;
      }
      const namespace = await vscode.window.showInputBox({
        title: `Base IRI for ${name}`,
        prompt:
          'Every class, attribute and shape is named under this. It does not ' +
          'have to resolve yet, but it should be yours.',
        value: `https://example.org/${name.replace(/[^A-Za-z0-9]+/g, '-')
          .toLowerCase()}/`
      });
      if (namespace === undefined) {
        return;
      }
      const layout = await vscode.window.showQuickPick(
        [
          { label: 'model/ groups the data (recommended)',
            description: 'model/model-instance.jsonld + model/examples/',
            value: 'grouped' },
          { label: 'flat',
            description: 'model-instance.jsonld + examples/ beside the artifacts',
            value: 'flat' }
        ],
        { title: 'Layout' }
      );
      if (!layout) {
        return;
      }

      const result = await client.sendRequest('semforge/init', {
        path: directory, name, namespace, layout: layout.value
      });
      if (!result.ok) {
        vscode.window.showErrorMessage(`SemForge: ${result.error}`);
        return;
      }

      // Open the shapes file: it is what the views are anchored to, and seeing
      // the two-layer NGSI-LD encoding once is worth more than reading about
      // it.
      await showLocation(`${result.open}:1`, true);
      vscode.window.showInformationMessage(
        `SemForge: ${result.files.length} files written. ` +
          `${result.constraints} constraint(s) evaluated, ` +
          `${result.violations} violation(s). The bad example under ` +
          `examples/ is there to prove one of them can fire.`
      );
      if (onCreated) {
        onCreated(result.root);
      }
    })
  );
}

/** True when the opened folders hold no package at all. */
function noPackageHere() {
  if (findPackageUri()) {
    return false;
  }
  const folders = vscode.workspace.workspaceFolders || [];
  return folders.length > 0 && folders.every((folder) => {
    try {
      return fs.existsSync(folder.uri.fsPath);
    } catch (error) {
      return false;
    }
  });
}

module.exports = { register, noPackageHere };
