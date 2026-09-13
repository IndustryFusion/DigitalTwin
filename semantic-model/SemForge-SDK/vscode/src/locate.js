/*
 * Finding the package in the opened folder.
 *
 * Each tree used to carry its own copy of this, looking only for the three
 * artifacts directly inside a workspace folder root. Open `semantic-model/`
 * rather than `semantic-model/kms/` and that finds nothing, so the trees
 * started empty and waited for an editor to be opened — which the Constraints
 * and Examples trees then did silently, and the Knowledge tree never did at
 * all, because it had no editor tracking.
 *
 * So: look in the folder, then one level down, and say what was looked for when
 * nothing turns up.
 */

const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const ARTIFACTS = ['shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'];

// A role may be a directory of documents instead of one file, and the loader
// reads either. Recognising only the files would leave such a package invisible
// here -- three empty trees over a package the server can read perfectly well.
const FOLDERS = {
  'shacl.ttl': ['shacl', 'shapes'],
  'knowledge.ttl': ['knowledge'],
  'model-instance.jsonld': ['main', 'model-instance', 'model']
};

// `main.jsonld` and `model-instance.jsonld` name the same role.
const FILE_ALIASES = { 'model-instance.jsonld': ['main.jsonld', 'model.jsonld'] };

function documentIn(directory) {
  if (!fs.existsSync(directory) || !fs.statSync(directory).isDirectory()) {
    return undefined;
  }
  const inside = fs.readdirSync(directory).sort()
    .filter((entry) => /\.(ttl|jsonld|json)$/.test(entry));
  return inside.length ? path.join(directory, inside[0]) : undefined;
}

function roleFile(directory, name) {
  for (const candidate of [name].concat(FILE_ALIASES[name] || [])) {
    const file = path.join(directory, candidate);
    if (fs.existsSync(file) && fs.statSync(file).isFile()) {
      return file;
    }
  }
  for (const folder of FOLDERS[name] || []) {
    const candidate = path.join(directory, folder);
    if (!fs.existsSync(candidate) || !fs.statSync(candidate).isDirectory()) {
      continue;
    }
    // Any document inside will do: the server resolves the package from any
    // file in it. `model/` may group the instance beside examples/, so look one
    // level down as well -- otherwise a grouped package looks like no package.
    const found = documentIn(candidate) ||
      documentIn(path.join(candidate, 'main')) ||
      documentIn(path.join(candidate, 'model-instance')) ||
      documentIn(path.join(candidate, 'instance'));
    if (found) {
      return found;
    }
  }
  return undefined;
}

/** True when this directory holds all three artifacts, as files or folders. */
function isPackage(directory) {
  return ARTIFACTS.every((name) => roleFile(directory, name) !== undefined);
}

function firstArtifact(directory) {
  for (const name of ARTIFACTS) {
    const found = roleFile(directory, name);
    if (found) {
      return vscode.Uri.file(found).toString();
    }
  }
  return undefined;
}

/**
 * A URI inside a package in the opened folders, or undefined.
 *
 * The URI is a file rather than the directory because that is what the server
 * resolves a package from: it walks up from a file, which is what an editor
 * hands you.
 */
function findPackageUri() {
  const folders = vscode.workspace.workspaceFolders || [];
  const roots = [];
  for (const folder of folders) {
    roots.push(folder.uri.fsPath);
  }
  // The folder itself wins over anything beneath it.
  for (const root of roots) {
    if (isPackage(root)) {
      return firstArtifact(root);
    }
  }
  for (const root of roots) {
    let names = [];
    try {
      names = fs.readdirSync(root, { withFileTypes: true })
        .filter((entry) => entry.isDirectory() && !entry.name.startsWith('.'))
        .map((entry) => entry.name)
        .sort();
    } catch (error) {
      continue;                       // unreadable folder; nothing to find
    }
    for (const name of names) {
      const candidate = path.join(root, name);
      if (isPackage(candidate)) {
        return firstArtifact(candidate);
      }
    }
  }
  return undefined;
}

/**
 * Is this file inside the package the tree is already showing?
 *
 * Following the active editor is how a tree reaches a package in a window
 * opened too high up. But refreshing for a file in the SAME package is pure
 * churn -- it re-validates the whole package -- and worse than wasteful:
 * firing onDidChangeTreeData makes VS Code drop its element handles, so a
 * reveal that follows resolves nothing and logs "Failed to resolve tree node".
 * Which is precisely what happened on every click, because the click opens a
 * file.
 */
function samePackage(currentUri, candidateUri) {
  if (!currentUri || !candidateUri) {
    return false;
  }
  const directory = (uri) => {
    const file = uri.startsWith('file://') ? uri.slice('file://'.length) : uri;
    return path.dirname(decodeURIComponent(file));
  };
  const here = directory(currentUri);
  const there = directory(candidateUri);
  return there === here || there.startsWith(here + path.sep);
}


/** What to tell someone whose tree is empty. */
function noPackageMessage() {
  const folders = (vscode.workspace.workspaceFolders || [])
    .map((folder) => folder.uri.fsPath)
    .join(', ');
  return (
    'No SemForge package found in ' + (folders || 'this window') +
    ' or one level below it. A package is a directory holding ' +
    ARTIFACTS.join(', ') + ' — each of which may be a directory of documents ' +
    'instead (shacl/, knowledge/, model-instance/). Open one, or run ' +
    '"SemForge: Doctor".'
  );
}

module.exports = { ARTIFACTS, isPackage, findPackageUri, noPackageMessage,
                   samePackage };
