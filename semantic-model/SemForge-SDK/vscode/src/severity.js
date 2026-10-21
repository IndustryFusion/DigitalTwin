/*
 * Severity… on any constraint, in SHACL's own vocabulary.
 *
 * `sh:Severity` is the class: its three levels -- violation (the default),
 * warning, info -- are always offered; a package's own levels are
 * individuals of sh:Severity or of a class derived from it, listed by class.
 * New levels and new derived classes are made from the same picker, and a
 * new level is set on the constraint straight away.
 */

const vscode = require('vscode');

const SEPARATOR = vscode.QuickPickItemKind ? vscode.QuickPickItemKind.Separator : -1;
const { pickVocabularyNamespace } = require('./namespacepick');

const NAME = /^(?:[A-Za-z_][\w.-]*:)?[A-Za-z_][A-Za-z0-9_-]*$/;
const CLASS_NAME = /^(?:[A-Za-z_][\w.-]*:)?[A-Z][A-Za-z0-9_-]*$/;
const REFRESH = ['semforge.refreshShapes', 'semforge.refreshTree', 'semforge.refreshKnowledge'];

async function ask(client, method, params) {
  const answer = await client.sendRequest(method, params);
  if (!answer.ok) {
    vscode.window.showErrorMessage(`SemForge: ${answer.error}`);
    return undefined;
  }
  return answer;
}

function refresh() {
  for (const command of REFRESH) {
    vscode.commands.executeCommand(command);
  }
}

/** A new class derived from sh:Severity (or from one derived from it). */
async function newClass(client, packageUri, classes) {
  const linked = classes.filter((c) => c.linked);
  const parent = linked.length === 1 ? linked[0] : await vscode.window.showQuickPick(
    linked.map((c) => ({ label: c.term, description: c.parent ? `derived from ${c.parent}` : '',
      cls: c })), { title: 'New severity class: derived from which?' }).then((p) => p && p.cls);
  if (!parent) {
    return undefined;
  }
  const name = await vscode.window.showInputBox({
    title: `New severity class, a kind of ${parent.term}`,
    prompt: 'Its name, e.g. AlarmLevel — or prefix:AlarmLevel to choose its namespace',
    validateInput: (text) => (CLASS_NAME.test(text.trim())
      ? undefined : 'a capital first, then letters, digits, "_" and "-"')
  });
  if (!name) {
    return undefined;
  }
  const namespace = await pickVocabularyNamespace(client, packageUri, name.trim(), parent.iri);
  if (namespace === undefined) {
    return undefined;
  }
  return ask(client, 'semforge/addSeverityClass',
    { uri: packageUri, name: name.trim(), parent: parent.term, namespace: namespace || null });
}

/** A new level: an individual of sh:Severity or of a class derived from it. */
async function newLevel(client, packageUri, classes, cls) {
  const linked = classes.filter((c) => c.linked);
  const owner = cls || (linked.length === 1 ? linked[0] : await vscode.window.showQuickPick(
    linked.map((c) => ({ label: c.term, description: c.parent ? `derived from ${c.parent}` : '',
      cls: c })), { title: 'New severity level: of which class?' }).then((p) => p && p.cls));
  if (!owner) {
    return undefined;
  }
  const name = await vscode.window.showInputBox({
    title: `New severity level of ${owner.term}`,
    prompt: 'Its name, e.g. severityMajor — or prefix:severityMajor to choose its namespace',
    validateInput: (text) => (NAME.test(text.trim()) ? undefined
      : 'a letter first, then letters, digits, "_" and "-"')
  });
  if (!name) {
    return undefined;
  }
  const namespace = await pickVocabularyNamespace(client, packageUri, name.trim(), owner.iri);
  if (namespace === undefined) {
    return undefined;
  }
  const label = await vscode.window.showInputBox({
    title: `${name.trim()}: its label`,
    prompt: 'The word it is said by, e.g. "major"', value: name.trim().split(':').pop()
      .replace(/^severity/i, '')
      .replace(/^./, (c) => c.toLowerCase())
  });
  if (label === undefined) {
    return undefined;
  }
  return ask(client, 'semforge/addSeverityLevel',
    { uri: packageUri, cls: owner.term, name: name.trim(), label: label.trim(),
      namespace: namespace || null });
}

/**
 * Pick a severity for one constraint and write it. `target` is
 * {shape, path} for an attribute constraint or {shape, holder | query} for a
 * SPARQL constraint, with `label` and `current` (its severity label) to say.
 */
async function chooseSeverity(client, packageUri, target) {
  const offered = await ask(client, 'semforge/severityLevels', { uri: packageUri });
  if (!offered) {
    return undefined;
  }
  const items = [{ label: 'SHACL', kind: SEPARATOR }];
  let group = 'sh:Severity';
  for (const level of offered.levels) {
    if (level.class !== group) {
      group = level.class;
      items.push({ label: level.class, kind: SEPARATOR });
    }
    items.push({ label: level.label, description: level.term,
      detail: level.note || (level.used ? `used ${level.used} time(s)` : ''), level });
  }
  items.push({ label: '', kind: SEPARATOR },
    { label: '$(circle-slash) No severity', description: 'SHACL\'s default applies: violation',
      clear: true },
    { label: '$(add) New severity level…', description: 'an individual of sh:Severity or a class derived from it',
      create: 'level' },
    { label: '$(type-hierarchy-sub) New severity class…', description: 'derived from sh:Severity',
      create: 'class' });
  const picked = await vscode.window.showQuickPick(items, {
    title: `Severity of ${target.label}${target.current ? ` — now ${target.current}` : ''}`,
    matchOnDescription: true });
  if (!picked) {
    return undefined;
  }
  let severity = picked.level ? picked.level.term : '';
  if (picked.create === 'class') {
    const made = await newClass(client, packageUri, offered.classes);
    if (!made) {
      return undefined;
    }
    refresh();
    // A class is not a level: its first level is made next, and set.
    const level = await newLevel(client, packageUri, offered.classes.concat(
      [{ iri: made.iri, term: made.term, linked: true, parent: '' }]),
    { iri: made.iri, term: made.term, linked: true });
    if (!level) {
      return made;
    }
    severity = level.term;
  } else if (picked.create === 'level') {
    const level = await newLevel(client, packageUri, offered.classes);
    if (!level) {
      return undefined;
    }
    severity = level.term;
  }
  const done = await ask(client, 'semforge/setSeverity', Object.assign(
    { uri: packageUri, severity: picked.clear ? '' : severity }, target.shape ? {
      shape: target.shape, path: target.path, holder: target.holder, query: target.query } : {}));
  if (!done) {
    return undefined;
  }
  refresh();
  vscode.window.setStatusBarMessage(`SemForge: severity of ${target.label} — ` +
    `${picked.clear ? 'SHACL\'s default (violation)' : picked.label || severity}`, 5000);
  return done;
}

function register(context, clientHolder, session) {
  context.subscriptions.push(
    // The Problems panel's fix for a class of levels not linked to sh:Severity.
    vscode.commands.registerCommand('semforge.linkSeverityClass', async (fix) => {
      const client = clientHolder.client;
      if (!client || !fix) {
        return undefined;
      }
      const done = await ask(client, 'semforge/linkSeverityClass',
        { uri: fix.packageUri || session.uri, cls: fix.cls });
      if (done) {
        refresh();
        vscode.window.setStatusBarMessage(
          `SemForge: ${String(fix.cls).split(/[/#]/).pop()} is now a kind of sh:Severity`, 5000);
      }
      return done;
    }));
}

module.exports = { register, chooseSeverity };
