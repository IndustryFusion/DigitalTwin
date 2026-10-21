/*
 * New test case…: add a test file to a suite.
 *
 * The general way in, beside New test… (one attribute) and New case… (one
 * SPARQL rule): a suite -- existing, or new for a shape -- good or bad, and a
 * start: a copy of a case, an entity from the model, a fresh entity of a
 * type, an empty file, or a .jsonld already under examples/ that nothing
 * declares. The SDK writes and declares it and runs it once; the case page
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
  const items = options.suites.map((suite) => ({ label: `$(beaker) ${suite}`, suite }));
  const fresh = options.shapes.filter((s) => !existing.has(`test_${s.label}`));
  items.push({ label: 'A new suite', kind: SEPARATOR });
  items.push(...fresh.map((s) => ({ label: `$(add) test_${s.label}`,
    description: `for ${s.name}`, suite: `test_${s.label}` })));
  items.push({ label: '$(new-folder) New suite…', alwaysShow: true, named: true,
    description: fresh.length ? 'any name'
      : 'any name — every shape has a suite already' });
  if (options.undeclared.length) {
    items.push({ label: 'Already written', kind: SEPARATOR });
    items.push({ label: '$(file-add) Declare a file under examples/ that nothing runs',
      description: `${options.undeclared.length} file(s)`, declare: true });
  }
  const picked = await vscode.window.showQuickPick(items,
    { title: 'New test case: in which suite?' });
  return picked && picked.named ? askSuiteName(existing) : picked;
}

// newSuite's preset: ask for a name instead of offering the list.
const NEW_SUITE = Symbol('new suite');

async function pickExpect() {
  const picked = await vscode.window.showQuickPick([
    { label: '$(pass) Should conform', description: 'good/ · expect: valid', expect: 'valid' },
    { label: '$(error) Should violate', description: 'bad/ · expect: invalid — assert what ' +
      'fires on its case page', expect: 'invalid' }
  ], { title: 'New test case: what should it show?' });
  return picked && picked.expect;
}

async function pickStart(options) {
  const items = [];
  if (options.cases.length) {
    items.push({ label: '$(copy) A copy of a case', start: 'copy',
      description: 'its includes written into the new file' });
  }
  if (options.entities.length) {
    items.push({ label: '$(symbol-object) An entity from the model', start: 'model' });
  }
  if (options.types.length) {
    items.push({ label: '$(symbol-class) A new entity of a type', start: 'type',
      description: 'its required attributes given valid values' });
  }
  items.push({ label: '$(file) An empty file', start: 'empty' });
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
  return { start: 'empty', source: '', name: 'new-case' };
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
    const start = await pickStart(options);
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
        : `SemForge: ${made.case} written; it does not pass yet: ${made.failures.join('; ')}`;
  const open = await (made.passes ? vscode.window.showInformationMessage(said, 'Open .jsonld')
    : vscode.window.showWarningMessage(said, 'Open .jsonld'));
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

module.exports = { register, newTestCase, suiteName, cloneTestCase, expectOf };
