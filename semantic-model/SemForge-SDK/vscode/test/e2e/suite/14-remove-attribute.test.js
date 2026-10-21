// Remove… an attribute from an entity on a test case's page, in a real VS
// Code: the row's ⋯ offers it, the question is asked, and the attribute goes
// from the case's file -- the others stay.

const assert = require('assert');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, WORKSPACE, semforge, until, answering, read } = require('./helpers');

const CASE = path.join(WORKSPACE, 'examples', 'test_WorkpieceShape', 'good', 'at-the-limits.jsonld');

describe('Remove… an attribute from a test case', () => {
  it('from the case page\'s row menu', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openCasePage',
      { raw: { kind: 'example', file: CASE }, packageUri: PACKAGE_URI });
    const page = await until(() => api.pages.case.page && api.pages.case.page.file === CASE &&
      api.pages.case.page, 'the case page');
    const card = page.files[0].cards.findIndex((c) => c.id === 'urn:workpiece:1');
    const row = page.files[0].cards[card].attributes.findIndex((a) => a.name === 'hasWidth');
    assert.ok(card >= 0 && row >= 0, 'the workpiece and its hasWidth on the page');
    const session = answering([
      { kind: 'pick', label: '$(trash) Remove hasWidth…' },
      { kind: 'warning', button: 'Remove' }]);
    try {
      await api.pages.case.receive({ command: 'rowMenu', at: `0.${card}.${row}` });
    } finally {
      session.restore();
    }
    assert.ok(session.asked[1].offered.message.startsWith('Remove hasWidth from urn:workpiece:1?'));
    const text = read('examples/test_WorkpieceShape/good/at-the-limits.jsonld');
    assert.ok(!text.includes('hasWidth'), text);
    assert.ok(text.includes('hasHeight') && text.includes('hasLength'));
    await until(() => api.pages.case.page && !api.pages.case.page.files[0].cards[card].attributes
      .some((a) => a.name === 'hasWidth'), 'the page without it');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
