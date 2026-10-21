/*
 * Creating a project from the editor.
 *
 * Two gestures, because they are different things. "New project" makes a FOLDER
 * and then offers to open it -- the classical File > New Project. "Create a
 * package here" initialises the folder you already have. Both end in the same
 * scaffold, which lives in the SDK.
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

/** Ask for the three things a package needs; undefined if cancelled. */
async function askAbout(defaultName) {
  const name = await vscode.window.showInputBox({
    title: 'Project name',
    prompt: 'Used for the folder, the namespace prefixes and the README',
    value: defaultName,
    validateInput: (value) =>
      /[A-Za-z0-9]/.test(value || '') ? undefined
        : 'a name needs letters or digits in it'
  });
  if (name === undefined) {
    return undefined;
  }
  const slug = name.replace(/[^A-Za-z0-9]+/g, '-').toLowerCase();
  const namespace = await vscode.window.showInputBox({
    title: `Base IRI for ${name}`,
    prompt:
      'Every class, attribute and shape is named under this. It does not have ' +
      'to resolve yet, but it should be yours.',
    value: `https://example.org/${slug}/`
  });
  if (namespace === undefined) {
    return undefined;
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
    return undefined;
  }
  return { name, slug, namespace, layout: layout.value };
}

/** Create the package and report; returns the server's answer or undefined. */
async function scaffold(clientHolder, directory, answers) {
  const result = await clientHolder.client.sendRequest('semforge/init', {
    path: directory,
    name: answers.name,
    namespace: answers.namespace,
    layout: answers.layout
  });
  if (!result.ok) {
    vscode.window.showErrorMessage(`SemForge: ${result.error}`);
    return undefined;
  }
  vscode.window.showInformationMessage(
    `SemForge: ${result.files.length} files in ${directory}. ` +
      `${result.constraints} constraint(s) evaluated, ` +
      `${result.violations} violation(s). The bad example under examples/ is ` +
      'there to prove one of them can fire.'
  );
  return result;
}

function register(context, clientHolder, onCreated) {
  const ready = () => {
    if (clientHolder.client) {
      return true;
    }
    vscode.window.showErrorMessage(
      'SemForge: the language server is not running — run "SemForge: Doctor".'
    );
    return false;
  };

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.newProject', async (resource) => {
      // The classical gesture: a NEW folder, then open it. Right-clicking a
      // folder in the Explorer offers this too, and then that folder is the
      // parent.
      if (!ready()) {
        return;
      }
      const parent = (resource && resource.fsPath) || await chooseDirectory();
      if (!parent) {
        return;
      }
      const answers = await askAbout('my-model');
      if (!answers) {
        return;
      }

      const directory = path.join(parent, answers.slug);
      if (fs.existsSync(directory) && fs.readdirSync(directory).length) {
        vscode.window.showErrorMessage(
          `SemForge: ${directory} already exists and is not empty.`
        );
        return;
      }
      const result = await scaffold(clientHolder, directory, answers);
      if (!result) {
        return;
      }

      // Opening it is the other half of "new project". Adding it to the
      // workspace keeps what is already open, which is usually what somebody
      // creating a second package wants.
      const where = await vscode.window.showQuickPick(
        [
          { label: '$(folder-opened) Open the project', value: 'open' },
          { label: '$(multiple-windows) Open in a new window', value: 'window' },
          { label: '$(add) Add it to this workspace', value: 'add' },
          { label: '$(check) Stay here', value: 'stay' }
        ],
        { title: `${answers.name} created` }
      );
      const target = vscode.Uri.file(directory);
      if (where && where.value === 'open') {
        await vscode.commands.executeCommand('vscode.openFolder', target,
                                             { forceNewWindow: false });
      } else if (where && where.value === 'window') {
        await vscode.commands.executeCommand('vscode.openFolder', target,
                                             { forceNewWindow: true });
      } else if (where && where.value === 'add') {
        vscode.workspace.updateWorkspaceFolders(
          (vscode.workspace.workspaceFolders || []).length, 0, { uri: target });
      }
      if (onCreated) {
        onCreated(directory);
      }
    }),

    vscode.commands.registerCommand('semforge.initPackage', async () => {
      // The other gesture: the folder is already open, make it a package.
      if (!ready()) {
        return;
      }
      const directory = await chooseDirectory();
      if (!directory) {
        return;
      }
      const answers = await askAbout(path.basename(directory));
      if (!answers) {
        return;
      }
      const result = await scaffold(clientHolder, directory, answers);
      if (!result) {
        return;
      }
      // Open the shapes file: it is what the views are anchored to, and seeing
      // the two-layer NGSI-LD encoding once is worth more than reading about it.
      await showLocation(`${result.open}:1`, true);
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
