// A new vocabulary term in a namespace of its own, in a real VS Code: New
// vocabulary class… → "New namespace…" defines alerts: on the spot, the class
// is written as alerts:Leak with the file's @prefix line; + Value on its page
// takes `alerts:smallLeak` as typed, without asking.

const assert = require('assert');
const vscode = require('vscode');
const { PACKAGE_URI, semforge, until, answering, read } = require('./helpers');

const ALERTS = 'https://example.org/alerts/';

describe('A namespace for a new vocabulary term', () => {
  it('New namespace… from the class dialog, then a prefixed value', async () => {
    const api = await semforge();
    let session = answering([
      { kind: 'pick', label: '(none)' },
      { kind: 'input', value: 'Leak' },
      { kind: 'pick', label: '$(add) New namespace…' },
      { kind: 'input', value: 'alerts' },
      { kind: 'input', value: ALERTS }]);
    try {
      await vscode.commands.executeCommand('semforge.newVocabularyClass', { packageUri: PACKAGE_URI });
    } finally {
      session.restore();
    }
    assert.ok(/alerts:\s*https:\/\/example\.org\/alerts\//.test(read('semforge.yaml')),
      read('semforge.yaml').slice(-300));
    let knowledge = read('knowledge.ttl');
    assert.strictEqual(knowledge.split(`@prefix alerts: <${ALERTS}> .`).length - 1, 1);
    assert.ok(knowledge.includes('\nalerts:Leak a owl:Class'), knowledge.slice(-300));

    const page = await until(() => api.pages.vocabulary.page &&
      api.pages.vocabulary.page.iri === `${ALERTS}Leak` && api.pages.vocabulary.page, 'its page');
    session = answering([{ kind: 'input', value: 'alerts:smallLeak' },
      { kind: 'input', value: 'small' }]);
    try {
      await api.pages.vocabulary.receive({ command: 'addValue', row: -1 });
    } finally {
      session.restore();
    }
    knowledge = read('knowledge.ttl');
    assert.ok(/alerts:smallLeak a owl:NamedIndividual,\s+alerts:Leak/.test(knowledge),
      knowledge.slice(-300));
    assert.strictEqual(knowledge.split('@prefix alerts:').length - 1, 1);
    await until(() => api.pages.vocabulary.page && api.pages.vocabulary.page.values
      .some((v) => v.iri === `${ALERTS}smallLeak`), 'the value on the page');
    assert.strictEqual(page.term.endsWith('Leak'), true);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
