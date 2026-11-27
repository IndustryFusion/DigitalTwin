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

// Loaded by VS Code inside its extension host: runs every *.test.js here.

const fs = require('fs');
const path = require('path');
const Mocha = require('mocha');

/**
 * The suite files this run takes: all of them, or with SEMFORGE_E2E_SHARD
 * "k/n" every n-th from the k-th (1-based), so parallel CI jobs share them.
 */
function suiteFiles(directory = __dirname, shard = process.env.SEMFORGE_E2E_SHARD) {
  const all = fs.readdirSync(directory).filter((f) => f.endsWith('.test.js')).sort();
  if (!shard) {
    return all;
  }
  const [k, n] = shard.split('/').map(Number);
  if (!(n >= 1 && k >= 1 && k <= n)) {
    throw new Error(`SEMFORGE_E2E_SHARD "${shard}" is not k/n`);
  }
  return all.filter((_, i) => i % n === k - 1);
}

// Kept as they are when a workspace is put back: SemForge's history of the
// package, its cache, and the editor's settings for the run.
const KEEP = new Set(['.git', '.semforge', '.vscode']);

/** `target` made what `pristine` is: files written back, files added removed. */
function putBack(pristine, target) {
  const want = new Set(fs.readdirSync(pristine));
  for (const name of fs.readdirSync(target)) {
    if (!KEEP.has(name) && !want.has(name)) {
      fs.rmSync(path.join(target, name), { recursive: true, force: true });
    }
  }
  for (const name of want) {
    const from = path.join(pristine, name);
    const to = path.join(target, name);
    if (fs.statSync(from).isDirectory()) {
      if (fs.existsSync(to) && !fs.statSync(to).isDirectory()) {
        fs.rmSync(to, { force: true });
      }
      fs.mkdirSync(to, { recursive: true });
      putBack(from, to);
    } else {
      const content = fs.readFileSync(from);
      if (!fs.existsSync(to) || !content.equals(fs.readFileSync(to))) {
        fs.rmSync(to, { recursive: true, force: true });
        fs.writeFileSync(to, content);
      }
    }
  }
}

/**
 * Every suite file starts from the workspace run.js made: what a suite
 * edited, added or removed and did not put back is put back here, with no
 * editor left open on it. Without this a suite passed alone and failed in
 * the full run, on what one before it had left behind.
 */
async function fresh() {
  const pristine = process.env.SEMFORGE_E2E_PRISTINE;
  if (!pristine) {
    return;
  }
  const vscode = require('vscode');
  await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  const places = { kms: process.env.SEMFORGE_E2E_WORKSPACE, 'opcua-pumps': process.env.SEMFORGE_E2E_OPCUA };
  const targets = [];
  for (const [part, target] of Object.entries(places)) {
    if (target && fs.existsSync(path.join(pristine, part))) {
      putBack(path.join(pristine, part), target);
      targets.push(target);
    }
  }
  await settled(vscode, targets);
}

/** Every file under `directory` with its size and time: whether anything still writes. */
function stamps(directory) {
  const out = [];
  const walk = (at) => fs.readdirSync(at, { withFileTypes: true }).forEach((entry) => {
    const full = path.join(at, entry.name);
    if (entry.isDirectory()) {
      if (!KEEP.has(entry.name)) {
        walk(full);
      }
    } else {
      const stat = fs.statSync(full);
      out.push(`${full}:${stat.size}:${stat.mtimeMs}`);
    }
  });
  walk(directory);
  return out.join('\n');
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * The put-back files taken in before the suite starts: nothing writes any
 * more and the views hold rows again. Otherwise the file events and the
 * server's answers to them arrived during the next suite's first test. (No
 * rescan: an emptied cache made the next suite's first waits time out; the
 * server commits outside changes before its next request anyway.)
 */
async function settled(vscode, targets) {
  const extension = vscode.extensions.getExtension('industryfusion.semforge');
  if (!extension || !extension.isActive) {
    return;                                    // the first suite: nothing ran yet
  }
  // No search left set by a suite before: the views show all their rows. And
  // the views on the workspace's package, not pinned -- a suite before may
  // have opened the OPC UA one, and a search there finds what it holds.
  await vscode.commands.executeCommand('semforge.clearSearch');
  extension.exports.session.set(
    vscode.Uri.file(path.join(process.env.SEMFORGE_E2E_WORKSPACE, 'shacl.ttl')).toString(), { pinned: false });
  let before = targets.map(stamps).join('\n');
  for (let quiet = 0, waited = 0; quiet < 3 && waited < 60; waited += 1) {
    await pause(250);
    const now = targets.map(stamps).join('\n');
    quiet = now === before ? quiet + 1 : 0;
    before = now;
  }
  const model = extension.exports.trees.model;
  const provider = model.provider || model;
  for (let waited = 0; waited < 120; waited += 1) {
    if ((await provider.getChildren()).length) {
      return;
    }
    await pause(250);
  }
}

function run() {
  const mocha = new Mocha({ ui: 'bdd', color: true, timeout: 60000,
    grep: process.env.SEMFORGE_E2E_GREP || undefined });
  const files = suiteFiles();
  for (const file of files) {
    mocha.addFile(path.join(__dirname, file));
  }
  mocha.loadFiles();
  mocha.lazyLoadFiles(true);                 // loaded: run() must not load them again
  // Once per file, before its first suite: a file's suites may build on each
  // other, files may not. First of its hooks, before the suite's own.
  const started = new Set();
  for (const suite of mocha.suite.suites) {
    if (started.has(suite.file)) {
      continue;
    }
    started.add(suite.file);
    suite.beforeAll('a fresh workspace', fresh);
    suite._beforeAll.unshift(suite._beforeAll.pop());
  }
  return new Promise((resolve, reject) => {
    const runner = mocha.run((failures) => {
      // What ran, for run.js to hold against the suite folder: a run that
      // loaded fewer files or ran no test must not pass as green.
      if (process.env.SEMFORGE_E2E_REPORT) {
        const stats = runner.stats || {};
        fs.writeFileSync(process.env.SEMFORGE_E2E_REPORT, JSON.stringify({
          files, tests: stats.tests || 0, passes: stats.passes || 0,
          failures: stats.failures || 0, pending: stats.pending || 0,
          ms: stats.duration || 0 }));
      }
      return failures ? reject(new Error(`${failures} end-to-end test(s) failed`)) : resolve();
    });
  });
}

module.exports = { run, suiteFiles };
