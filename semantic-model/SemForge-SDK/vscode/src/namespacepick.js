/*
 * Which namespace a new vocabulary term goes in -- and a new one, defined on
 * the spot.
 *
 * Every vocabulary "New …" dialog (class, value, severity level, severity
 * class) asks this after the name. The usual place comes first, so the common
 * case is one Enter; the package's other namespaces follow; "New namespace…"
 * defines a prefix and its IRI right there and continues with it. Before this
 * a term silently went into whatever namespace its neighbours used, and a new
 * namespace meant a trip to the Project view -- after which nothing here
 * offered it anyway.
 */

const vscode = require('vscode');

const SEPARATOR = vscode.QuickPickItemKind ? vscode.QuickPickItemKind.Separator : -1;

/** A name, optionally with the prefix that chooses its namespace. */
const PREFIXED = '(?:[A-Za-z_][\\w.-]*:)?';
const NAME = new RegExp(`^${PREFIXED}[A-Za-z_][A-Za-z0-9_.-]*$`);
const CLASS_NAME = new RegExp(`^${PREFIXED}[A-Z][A-Za-z0-9_-]*$`);

/**
 * Ask for a prefix and its IRI and define it for the whole package. Returns
 * the server's answer ({prefix, namespace, file, line}) or undefined.
 */
async function defineNamespace(client, packageUri, namespaceIri) {
  const prefix = await vscode.window.showInputBox({
    title: 'New namespace prefix',
    prompt: 'The name this package uses for it, e.g. plant',
    validateInput: (text) =>
      /^[A-Za-z_][\w.-]*$/.test((text || '').replace(/:$/, ''))
        ? undefined
        : 'A letter or underscore, then letters, digits, dots, ' +
          'underscores or hyphens.'
  });
  if (!prefix) {
    return undefined;
  }
  const namespace = await vscode.window.showInputBox({
    title: `What does ${prefix.replace(/:$/, '')}: mean?`,
    prompt: 'The namespace IRI. It has to end in "/", "#" or ":", or a ' +
      'term appended to it runs into the last segment.',
    value: namespaceIri || 'https://'
  });
  if (!namespace) {
    return undefined;
  }
  const made = await client.sendRequest('semforge/addNamespace',
    { uri: packageUri, prefix: prefix.replace(/:$/, ''), namespace: namespace.trim() });
  if (!made || !made.ok) {
    vscode.window.showErrorMessage(
      `SemForge: ${(made && made.error) || 'the prefix was not defined'}`);
    return undefined;
  }
  vscode.commands.executeCommand('semforge.refreshProject');
  return made;
}

/**
 * The namespace for a new vocabulary term `name`: '' for the usual place
 * (the server's default), a prefix otherwise, undefined when cancelled.
 * `near` is the class the term belongs to or derives from, if any. A name
 * that already says (`alerts:Leak`) is not asked about.
 */
async function pickVocabularyNamespace(client, packageUri, name, near) {
  if (name.includes(':')) {
    return '';
  }
  let spaces = [];
  try {
    const answer = await client.sendRequest('semforge/vocabularyNamespaces',
      { uri: packageUri, near: near || '' });
    spaces = (answer && answer.namespaces) || [];
  } catch (error) {
    return '';            // an older server: its default is the only place
  }
  const items = [];
  let section;
  for (const space of spaces) {
    const heading = space.default ? 'The usual place'
      : space.terms ? 'Where this package keeps vocabulary' : 'Other namespaces in this package';
    if (heading !== section) {
      items.push({ label: heading, kind: SEPARATOR });
      section = heading;
    }
    items.push({
      label: space.prefix ? `${space.prefix}:${name}` : `<${space.namespace}${name}>`,
      description: space.default ? 'default' : space.terms ? `holds ${space.terms} term(s)` : '',
      detail: space.namespace,
      value: space.default ? '' : (space.prefix || space.namespace)
    });
  }
  items.push({ label: '', kind: SEPARATOR },
    { label: '$(add) New namespace…', description: 'define a prefix and its IRI for the package',
      create: true });
  const picked = await vscode.window.showQuickPick(items, {
    title: `Namespace for ${name}`,
    placeHolder: 'Enter keeps the usual place',
    matchOnDescription: true,
    matchOnDetail: true
  });
  if (!picked) {
    return undefined;
  }
  if (picked.create) {
    const made = await defineNamespace(client, packageUri);
    return made ? made.prefix : undefined;
  }
  return picked.value;
}

module.exports = { pickVocabularyNamespace, defineNamespace, NAME, CLASS_NAME };
