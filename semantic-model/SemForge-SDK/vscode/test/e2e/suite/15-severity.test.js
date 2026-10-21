// Severity… on an attribute constraint in a real VS Code: SHACL's own level,
// then a new level made from the same picker -- an individual of sh:Severity
// written into the knowledge -- and set on the constraint.

const assert = require('assert');
const vscode = require('vscode');
const { PACKAGE_URI, semforge, until, answering, read } = require('./helpers');

const ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/';

async function workpiecePage(api) {
  await vscode.commands.executeCommand('semforge.openTypePage',
    { raw: { kind: 'type', targetClass: `${ENT}Workpiece`, label: 'Workpiece', children: [] },
      packageUri: PACKAGE_URI });
  return until(() => api.pages.type.page && api.pages.type.page.label === 'Workpiece' &&
    api.pages.type.page, 'the Workpiece page');
}

/** hasHeight's property shape: from its sh:path to the next attribute's. */
function heightStatement(shacl) {
  const shape = shacl.slice(shacl.indexOf('iffBaseShacl:WorkpieceShape a'));
  const at = shape.indexOf('sh:path iffBaseEntities:hasHeight');
  const next = shape.indexOf('sh:path iffBaseEntities:', at + 1);
  return shape.slice(at, next > 0 ? next : at + 800);
}

describe('Severity… on a constraint', () => {
  it('SHACL\'s warning, then a new level of sh:Severity', async () => {
    const api = await semforge();
    let page = await workpiecePage(api);
    let row = page.attributes.findIndex((a) => a.label === 'hasHeight');
    // Its own column: a click on the cell opens the picker.
    assert.ok(api.pages.type.panel.webview.html.includes('>Severity</th>'));
    let session = answering([{ kind: 'pick', label: 'warning' }]);
    try {
      await api.pages.type.receive({ command: 'severity', row });
    } finally {
      session.restore();
    }
    await until(() => heightStatement(read('shacl.ttl')).includes('sh:severity sh:Warning'),
      'sh:severity sh:Warning on hasHeight');

    page = await until(() => api.pages.type.page && api.pages.type.page.attributes
      .find((a) => a.label === 'hasHeight' && a.severityDeclared) && api.pages.type.page,
    'the page to say it');
    row = page.attributes.findIndex((a) => a.label === 'hasHeight');
    session = answering([{ kind: 'pick', label: '$(warning) Severity…' },
      { kind: 'pick', label: '$(add) New severity level…' },
      { kind: 'input', value: 'severityMajor' },
      // The namespace: Enter keeps the usual place, the first entry.
      { kind: 'pick', choose: (items) => items[0] },
      { kind: 'input', value: 'major' }]);
    try {
      await api.pages.type.receive({ command: 'menu', row });
    } finally {
      session.restore();
    }
    const knowledge = read('knowledge.ttl');
    assert.ok(/severityMajor a owl:NamedIndividual, sh:Severity ;\s+rdfs:label "major"/.test(knowledge) ||
      /severityMajor a owl:NamedIndividual,\s*<http:\/\/www\.w3\.org\/ns\/shacl#Severity>/.test(knowledge),
    knowledge.slice(-400));
    await until(() => /sh:severity \S*severityMajor/.test(heightStatement(read('shacl.ttl'))),
      'the new level on hasHeight');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('sh:Severity is in the vocabulary, its levels SHACL\'s, the new level beside them', async () => {
    const api = await semforge();
    const vocabulary = await until(async () => {
      const roots = await api.trees.knowledge.getChildren();
      const group = roots.find((n) => n.raw.label === 'Vocabulary classes');
      return group && group;
    }, 'the Vocabulary classes');
    // By its IRI: the summary view drops prefixes from labels.
    const severity = (await api.trees.knowledge.getChildren(vocabulary))
      .find((n) => n.raw.iri === 'http://www.w3.org/ns/shacl#Severity');
    assert.ok(severity, 'sh:Severity in the view');
    const levels = (await api.trees.knowledge.getChildren(severity)).map((n) => n.raw.label);
    assert.deepStrictEqual(levels.slice(0, 3), ['Violation', 'Warning', 'Info']);
    assert.ok(levels.includes('severityMajor'), levels.join(', '));
    await vscode.commands.executeCommand('semforge.openVocabularyPage', severity);
    const page = await until(() => api.pages.vocabulary.page &&
      api.pages.vocabulary.page.term === 'sh:Severity' && api.pages.vocabulary.page, 'its page');
    assert.deepStrictEqual(page.values.filter((v) => v.builtin).map((v) => v.label),
      ['violation', 'warning', 'info']);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
