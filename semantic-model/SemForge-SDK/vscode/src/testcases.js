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

/*
 * New test case…: add a test file to a suite.
 *
 * The general way in, beside New test… (one attribute) and New case… (one
 * SPARQL rule): a suite -- existing, or new for a shape -- good or bad, and a
 * start: a copy of a case, the whole main model, an entity from the model, a
 * fresh entity of a type, an empty file, or a .jsonld already under examples/
 * that nothing declares. The SDK writes and declares it and runs it once; the case page
 * opens, where a bad case's firings become asserts with "Assert it".
 */

const path = require('path');
const vscode = require('vscode');

const { showLocation } = require('./reveal');

const SEPARATOR = vscode.QuickPickItemKind
  ? vscode.QuickPickItemKind.Separator : -1;

function base(path) {
  return String(path).split('/').pop().replace(/\.jsonld$/, '');
}

/**
 * A suite's folder name, from what was typed: `test_` in front (that is what
 * marks a folder under examples/ as a suite), spaces as dashes. Undefined
 * when nothing usable is left.
 */
function suiteName(text) {
  const cleaned = String(text || '').trim().replace(/\s+/g, '-');
  if (!/^[A-Za-z0-9_.-]+$/.test(cleaned) || !/[A-Za-z0-9]/.test(cleaned)) {
    return undefined;
  }
  return cleaned.startsWith('test_') ? cleaned : `test_${cleaned}`;
}

/** New suite…: ask for its name. The folder appears with its first case. */
async function askSuiteName(existing) {
  const name = await vscode.window.showInputBox({
    title: 'New suite',
    prompt: 'A folder under examples/ — e.g. "pump-limits" becomes test_pump-limits. ' +
      'Its first test case is asked next.',
    validateInput: (text) => {
      const suite = suiteName(text);
      if (!suite) {
        return 'letters, digits, "_", "-" and "." only';
      }
      return existing.has(suite) ? `${suite} exists already — pick it from the list` : undefined;
    }
  });
  const suite = name === undefined ? undefined : suiteName(name);
  return suite ? { suite, fresh: true } : undefined;
}

async function pickSuite(options, preset) {
  const existing = new Set(options.suites);
  if (preset === NEW_SUITE) {
    return askSuiteName(existing);
  }
  if (preset) {
    return { suite: preset };
  }
  const items = [{ label: 'Suites', kind: SEPARATOR }]
    .concat(options.suites.map((suite) => ({ label: `$(beaker) ${suite}`, suite })));
  const fresh = options.shapes.filter((s) => !existing.has(`test_${s.label}`));
  items.push({ label: 'A new suite for a shape', kind: SEPARATOR });
  items.push(...fresh.map((s) => ({ label: `$(add) test_${s.label}`,
    description: `for ${s.name}`, suite: `test_${s.label}` })));
  // The actions on top: an OPC UA package has a suite, and a shape, per type.
  const picked = await require('./picks').pickWithActions([
    { label: '$(new-folder) New suite…', named: true,
      description: fresh.length ? 'any name' : 'any name — every shape has a suite already' },
    options.undeclared.length ? { label: '$(file-add) Declare a file under examples/ that nothing runs',
      description: `${options.undeclared.length} file(s)`, declare: true } : null
  ], items, { title: 'New test case: in which suite?' });
  return picked && picked.named ? askSuiteName(existing) : picked;
}

// newSuite's preset: ask for a name instead of offering the list.
const NEW_SUITE = Symbol('new suite');

async function pickExpect() {
  const picked = await vscode.window.showQuickPick([
    { label: '$(pass) Should conform', description: 'good/ · expect: valid', expect: 'valid' },
    { label: '$(error) Should violate', description: 'bad/ · expect: invalid — fails until you assert ' +
      'why, on its case page', expect: 'invalid' }
  ], { title: 'New test case: what should it show?' });
  return picked && picked.expect;
}

/**
 * `stem`, or the first of `stem-2`, `stem-3`, … that no case or file of the
 * folder `folder` (suite/good or suite/bad) has yet.
 */
function freeName(options, folder, stem) {
  const taken = new Set((options.cases || []).map((c) => c.path)
    .concat(options.undeclared || []));
  let name = stem;
  for (let n = 2; taken.has(`${folder}/${name}.jsonld`); n += 1) {
    name = `${stem}-${n}`;
  }
  return name;
}

async function pickStart(options, folder) {
  // Empty first: a case's entities are best pasted in from Main (Copy
  // entity / Copy subtree, then Paste) -- exactly the scene the author means.
  const items = [{ label: '$(file) An empty file', start: 'empty',
    description: 'paste the entities it needs from Main' }];
  if (options.cases.length) {
    items.push({ label: '$(copy) A copy of a case', start: 'copy',
      description: 'its includes written into the new file' });
  }
  const modelFiles = options.modelFiles || [];
  if (modelFiles.length) {
    items.push({ label: '$(symbol-namespace) The whole main model', start: 'whole-model',
      description: `${modelFiles.length === 1 ? modelFiles[0] : `${modelFiles.length} files`} ` +
        'written into the new file',
      detail: 'A snapshot to vary: remove entities, change values; the model stays as it is.' });
  }
  if (options.entities.length) {
    items.push({ label: '$(symbol-object) An entity from the model', start: 'model' });
  }
  if (options.types.length) {
    items.push({ label: '$(symbol-class) A new entity of a type', start: 'type',
      description: 'its required attributes given valid values' });
  }
  const picked = await vscode.window.showQuickPick(items,
    { title: 'New test case: start from?' });
  if (!picked) {
    return undefined;
  }
  if (picked.start === 'copy') {
    const chosen = await vscode.window.showQuickPick(options.cases.map((c) => ({
      label: c.path, description: c.expect, detail: c.description, source: c.path })),
    { title: 'Copy which case?', matchOnDescription: true });
    return chosen && { start: 'copy', source: chosen.source, name: `${base(chosen.source)}-copy` };
  }
  if (picked.start === 'model') {
    const chosen = await vscode.window.showQuickPick(
      options.entities.map((id) => ({ label: id, source: id })),
      { title: 'Which entity from the model?' });
    return chosen && { start: 'model', source: chosen.source,
      name: chosen.source.split(/[:/#]/).filter(Boolean).slice(-2).join('-') };
  }
  if (picked.start === 'type') {
    const chosen = await vscode.window.showQuickPick(options.types.map((t) => ({
      label: t.label, description: t.term, source: t.iri })),
    { title: 'A new entity of which type?', matchOnDescription: true });
    return chosen && { start: 'type', source: chosen.source,
      name: `${chosen.label.toLowerCase()}-case` };
  }
  if (picked.start === 'whole-model') {
    return { start: 'whole-model', source: '', name: freeName(options, folder, 'whole-model') };
  }
  return { start: 'empty', source: '', name: freeName(options, folder, 'new-case') };
}

async function newTestCase(clientHolder, session, node, newSuite) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  if (!client || !packageUri) {
    vscode.window.showWarningMessage(
      'SemForge: no package is open, or the language server is not running.');
    return false;
  }
  const options = await client.sendRequest('semforge/testCaseOptions', { uri: packageUri });
  if (!options.ok) {
    vscode.window.showErrorMessage(`SemForge: ${options.error}`);
    return false;
  }
  const raw = (node && node.raw) || {};
  const preset = newSuite ? NEW_SUITE : raw.kind === 'suite' ? (raw.term || raw.label) : '';
  const where = await pickSuite(options, preset);
  if (!where) {
    return false;
  }
  let request;
  if (where.declare) {
    const file = await vscode.window.showQuickPick(
      options.undeclared.map((path) => ({ label: path, path })),
      { title: 'Declare which file?' });
    if (!file) {
      return false;
    }
    const expect = await pickExpect();
    if (!expect) {
      return false;
    }
    request = { suite: '', expect, start: 'existing', source: file.path, name: '' };
  } else {
    const expect = await pickExpect();
    if (!expect) {
      return false;
    }
    const start = await pickStart(options,
      `${where.suite}/${expect === 'valid' ? 'good' : 'bad'}`);
    if (!start) {
      return false;
    }
    const name = await vscode.window.showInputBox({
      title: `New test case in ${where.suite}`,
      prompt: 'A name for the file (letters, digits, dashes)',
      value: start.name,
      validateInput: (text) => (/[A-Za-z0-9]/.test(text) ? undefined : 'a name is required')
    });
    if (!name) {
      return false;
    }
    request = { suite: where.suite, expect, start: start.start, source: start.source, name };
  }
  const made = await client.sendRequest('semforge/addTestCase',
    Object.assign({ uri: packageUri }, request));
  if (!made.ok) {
    vscode.window.showErrorMessage(`SemForge: ${made.error}`);
    return false;
  }
  return announce(made, packageUri);
}

/** A case just written: shown on its page, and said whether it passes yet. */
async function announce(made, packageUri) {
  vscode.commands.executeCommand('semforge.refreshModel');
  await vscode.commands.executeCommand('semforge.openCasePage',
    { raw: { kind: 'example', file: made.file }, packageUri });
  const said = made.passes
    ? `SemForge: ${made.case} written, and it passes.`
    : made.expect === 'invalid' && made.violations === 0
      ? `SemForge: ${made.case} written. Nothing fires yet: edit its data until it ` +
        'violates, then assert what fires on its case page.'
      : made.expect === 'valid' && made.sourceExpect === 'invalid'
        ? `SemForge: ${made.case} written. It still violates, as the case it was cloned ` +
          'from does: edit its data until it conforms.'
        : made.expect === 'valid' && made.start === 'whole-model' && made.violations > 0
          ? `SemForge: ${made.case} written. It still violates, as the main model does: ` +
            'edit its data until it conforms.'
          : `SemForge: ${made.case} written; it does not pass yet: ${made.failures.join('; ')}`;
  const shared = made.sharedIds || [];
  const told = shared.length
    ? `${said} Defined by more than one model file, so twice in it (one entity with ` +
      `the attributes of both): ${shared.join(', ')}.`
    : said;
  const open = await (made.passes ? vscode.window.showInformationMessage(told, 'Open .jsonld')
    : vscode.window.showWarningMessage(told, 'Open .jsonld'));
  if (open) {
    await showLocation(`${made.file}:1`, true);
  }
  return made;
}

/** What a case expects, from the folder it is in: good/ conforms, bad/ violates. */
function expectOf(file) {
  const parts = String(file).split(/[\\/]/);
  return parts.includes('bad') ? 'invalid' : parts.includes('good') ? 'valid' : '';
}

/**
 * Clone… a case: its data, in its suite, expecting the opposite -- a valid
 * case's invalid twin, to be broken on purpose, or the other way round -- or
 * the same. The data is copied with its includes written in, so nothing
 * shared is touched; an opposite clone fails until its data is edited, which
 * is the point.
 */
async function cloneTestCase(clientHolder, session, node) {
  const client = clientHolder.client;
  const packageUri = (node && node.packageUri) || session.uri;
  const file = node && node.raw && node.raw.file;
  if (!client || !packageUri || !file) {
    vscode.window.showWarningMessage('SemForge: Clone… works on a test case.');
    return undefined;
  }
  const from = (node.raw.expect || expectOf(file));
  const stem = path.basename(file).replace(/\.jsonld$/, '');
  const opposite = from === 'valid' ? 'invalid' : from === 'invalid' ? 'valid' : '';
  const said = { valid: 'conforms, in good/', invalid: 'violates, in bad/' };
  const picked = await vscode.window.showQuickPick([
    { label: '$(arrow-swap) Expect the opposite', expect: 'opposite',
      description: opposite ? said[opposite] : 'valid ↔ invalid',
      detail: opposite === 'invalid'
        ? 'A twin to break on purpose: it fails until its data violates, and you assert what fires.'
        : opposite === 'valid' ? 'A twin to repair: it fails until its data conforms; its asserts are not copied.'
          : '' },
    { label: '$(copy) Expect the same', expect: 'same',
      description: from ? said[from] : 'the same folder',
      detail: 'A copy to vary: its asserts and description come along, and it passes as the original does.' }
  ], { title: `Clone ${stem}` });
  if (!picked) {
    return undefined;
  }
  const target = picked.expect === 'same' ? from : opposite;
  const suggested = picked.expect === 'same' || !target ? `${stem}-copy`
    : `${stem}-${target === 'invalid' ? 'violates' : 'conforms'}`;
  const name = await vscode.window.showInputBox({
    title: `Clone ${stem}`, prompt: 'A name for the new file (letters, digits, dashes)',
    value: suggested, valueSelection: [0, suggested.length],
    validateInput: (text) => (/[A-Za-z0-9]/.test(text) ? undefined : 'a name is required')
  });
  if (!name) {
    return undefined;
  }
  const made = await client.sendRequest('semforge/cloneCase',
    { uri: packageUri, case: file, expect: picked.expect, name });
  if (!made.ok) {
    vscode.window.showErrorMessage(`SemForge: ${made.error}`);
    return undefined;
  }
  return announce(made, packageUri);
}

function register(context, clientHolder, session) {
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.newTestCase',
      (node) => newTestCase(clientHolder, session, node)),
    // A suite is a folder with cases in it, so it is made with its first one.
    vscode.commands.registerCommand('semforge.newSuite',
      (node) => newTestCase(clientHolder, session, node, true)),
    vscode.commands.registerCommand('semforge.cloneTestCase',
      (node) => cloneTestCase(clientHolder, session, node)));
}

module.exports = { register, newTestCase, freeName, suiteName, cloneTestCase, expectOf };
