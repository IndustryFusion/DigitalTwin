/*
 * Which datasetId -- picked from the package's namespaces, or one defined on
 * the spot.
 *
 * A datasetId is an IRI in a namespace the package registers: it reads
 * attribute[prefix:name] -- hasHeight[sensors:left] -- and a name needs a
 * prefix. So the package's namespaces are offered, or a new one is defined
 * on the spot; then only the local part is typed (`left`) and the full IRI is
 * written. There is no free-form IRI: one in no registered namespace would
 * have no name to show. Full, not prefixed: a namespace from semforge.yaml is not in a
 * case's @context, and `sensors:left` would then be read as an IRI whose
 * scheme is "sensors" -- valid, and silently another id.
 *
 * Add Attribute, Add instance… and Change datasetId… all ask through here.
 */

const vscode = require('vscode');
const { defineNamespace } = require('./namespacepick');

const SEPARATOR = vscode.QuickPickItemKind ? vscode.QuickPickItemKind.Separator : -1;
const IRI = /^[A-Za-z][A-Za-z0-9+.-]*:[^\s<>"{}|\\^`]+$/;
const LOCAL = /^[^\s<>"{}|\\^`#/?]+$/;

/** What is wrong with a datasetId, or undefined. */
function problem(text, taken) {
  const value = String(text || '').trim();
  if (value === '@none') {
    return '@none is the platform\'s name for the default instance; the default instance has no datasetId';
  }
  if (!IRI.test(value)) {
    return 'an IRI, e.g. urn:sensor:left';
  }
  if ((taken || []).includes(value)) {
    return 'this attribute already has an instance with it; another one there is an observation';
  }
  return undefined;
}

/**
 * Ask for a datasetId. Returns '' for the default instance (only when
 * `options.allowDefault`), the full IRI, or undefined when cancelled.
 *
 * options: { title, taken: [datasetIds the attribute has, '@none' for the
 * default], allowDefault, suggestion: a local name, observations: offer the
 * taken ones too -- another observation of one, which then needs a time }
 */
async function askDatasetId(client, packageUri, options) {
  const taken = options.taken || [];
  const local = options.suggestion || 'instance-2';
  let spaces = [];
  try {
    const answer = await client.sendRequest('semforge/vocabularyNamespaces',
      { uri: packageUri, near: '' });
    spaces = (answer && answer.namespaces) || [];
  } catch (error) {
    spaces = [];      // an older server: typing the IRI still works
  }
  const items = [];
  const again = options.observations ? taken.filter((d) => d !== '@none') : [];
  if (options.allowDefault) {
    items.push({ label: 'Default instance', pick: 'default',
      description: taken.includes('@none') ? 'another observation of it — at another time'
        : 'no datasetId' });
  }
  if (again.length) {
    items.push({ label: 'Another observation of', kind: SEPARATOR },
      ...again.map((d) => ({ label: d, description: 'at another time', pick: 'taken', id: d })));
  }
  if (spaces.length) {
    items.push({ label: 'In a namespace of this package', kind: SEPARATOR });
    for (const space of spaces) {
      items.push({ label: `${space.prefix ? `${space.prefix}:` : ''}${local}`,
        description: 'type the local part', detail: space.namespace, pick: 'space', space });
    }
  }
  items.push({ label: '', kind: SEPARATOR },
    { label: '$(add) New namespace…', description: 'define a prefix and its IRI for the package',
      pick: 'new' });
  const picked = await vscode.window.showQuickPick(items, {
    title: options.title,
    placeHolder: taken.length
      ? `Has ${taken.map((d) => (d === '@none' ? 'default' : d)).join(', ')} — another instance needs its own`
      : 'The datasetId of this instance',
    matchOnDescription: true,
    matchOnDetail: true
  });
  if (!picked) {
    return undefined;
  }
  if (picked.pick === 'default') {
    return '';
  }
  if (picked.pick === 'taken') {
    return picked.id;
  }
  let namespace = picked.space && picked.space.namespace;
  if (picked.pick === 'new') {
    const made = await defineNamespace(client, packageUri);
    if (!made) {
      return undefined;
    }
    namespace = made.namespace;
  }
  const name = await vscode.window.showInputBox({
    title: options.title,
    prompt: `The local part, in ${namespace}`,
    value: local,
    validateInput: (text) => (!LOCAL.test(text.trim()) ? 'no spaces, "/", "#" or "?"'
      : problem(namespace + text.trim(), options.observations ? [] : taken))
  });
  return name === undefined ? undefined : namespace + name.trim();
}

module.exports = { askDatasetId, problem };
