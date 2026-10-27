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

// End-to-end tests: the extension in a real VS Code, its real language server,
// on a fresh copy of the kms corpus.
//
//   npm run test:e2e            (from vscode/; downloads VS Code once into
//                                vscode/.vscode-test, needs a display -- WSLg,
//                                a desktop, or xvfb-run)
//
// The Node harness (tests/harness/drive.js) checks the extension's logic
// against a stubbed VS Code and hand-written payloads; that is fast, and it
// missed a click that matched no row the server really sends. These run what
// a person runs: the server answers, the trees hold its rows, a selection is
// a selection, a page is a webview panel.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { runTests } = require('@vscode/test-electron');

async function main() {
  const extensionDevelopmentPath = path.resolve(__dirname, '..', '..');
  const sdk = path.resolve(extensionDevelopmentPath, '..');
  const python = path.join(sdk, 'venv', 'bin', 'python');
  if (!fs.existsSync(python)) {
    throw new Error(`no SDK venv at ${python} -- run "make setup" in ${sdk}`);
  }

  // A copy: the tests edit data, shapes and knowledge. The corpus files are
  // SYMLINKS into semantic-model/kms, so the copy must follow them -- a copy
  // of the links let the tests write into the real kms package.
  // Laid out as in the repo: the kms names its NGSI-LD vocabulary as
  // ../ontology/ngsild.ttl, so the shared copy sits beside it.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'semforge-e2e-'));
  const workspace = path.join(root, 'kms');
  // The OPC UA pump slice beside it: a second package the server answers for
  // by its own uri, so a suite can open its pages without a second window.
  for (const part of ['kms', 'ontology', 'opcua-pumps']) {
    fs.cpSync(path.join(sdk, 'tests', 'corpus', part), path.join(root, part), {
      recursive: true,
      dereference: true,
      filter: (source) => !source.split(path.sep).includes('.semforge')
    });
  }
  const ngsild = path.join(root, 'ontology', 'ngsild.ttl');
  const linked = [];
  const walk = (directory) => fs.readdirSync(directory, { withFileTypes: true })
    .forEach((entry) => {
      const full = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) {
        linked.push(full);
      } else if (entry.isDirectory()) {
        walk(full);
      }
    });
  walk(root);
  if (linked.length) {
    throw new Error(`the test workspace still links outside itself: ${linked.join(', ')}`);
  }
  fs.mkdirSync(path.join(workspace, '.vscode'));
  fs.writeFileSync(path.join(workspace, '.vscode', 'settings.json'), JSON.stringify({
    'semforge.pythonPath': python,
    'semforge.trees.detail': 'summary',
    'semforge.trees.click': 'page'
  }, null, 2));

  // And proof: the source corpus (and the kms package behind its links) is
  // byte-for-byte what it was before the run.
  const source = path.join(sdk, 'tests', 'corpus', 'kms');
  const before = fingerprint(source);

  try {
    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath: path.join(__dirname, 'suite', 'index.js'),
      cachePath: path.join(extensionDevelopmentPath, '.vscode-test'),
      // Packages a test creates declare the default vocabulary: the shared
      // copy, never the network.
      extensionTestsEnv: { SEMFORGE_E2E_WORKSPACE: workspace, SEMFORGE_NGSILD: ngsild,
        SEMFORGE_E2E_OPCUA: path.join(root, 'opcua-pumps') },
      launchArgs: [workspace, '--disable-extensions', '--disable-workspace-trust',
        '--skip-welcome', '--skip-release-notes', '--disable-gpu']
    });
  } finally {
    if (!process.env.SEMFORGE_E2E_KEEP) {
      fs.rmSync(root, { recursive: true, force: true });
    }
    const after = fingerprint(source);
    const changed = Object.keys(before).filter((file) => before[file] !== after[file]);
    if (changed.length) {
      throw new Error(`the run CHANGED the source corpus: ${changed.join(', ')}`);
    }
  }
}

/** {file: sha256} for every file under `directory`, links followed. */
function fingerprint(directory) {
  const crypto = require('crypto');
  const out = {};
  const walk = (at) => fs.readdirSync(at).forEach((name) => {
    const full = path.join(at, name);
    if (name === '.semforge') {
      return;
    }
    if (fs.statSync(full).isDirectory()) {
      walk(full);
    } else {
      out[full] = crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex');
    }
  });
  walk(directory);
  return out;
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
