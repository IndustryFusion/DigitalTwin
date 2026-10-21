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
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'semforge-e2e-'));
  fs.cpSync(path.join(sdk, 'tests', 'corpus', 'kms'), workspace, {
    recursive: true,
    dereference: true,
    filter: (source) => !source.split(path.sep).includes('.semforge')
  });
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
  walk(workspace);
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
      extensionTestsEnv: { SEMFORGE_E2E_WORKSPACE: workspace },
      launchArgs: [workspace, '--disable-extensions', '--disable-workspace-trust',
        '--skip-welcome', '--skip-release-notes', '--disable-gpu']
    });
  } finally {
    if (!process.env.SEMFORGE_E2E_KEEP) {
      fs.rmSync(workspace, { recursive: true, force: true });
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
