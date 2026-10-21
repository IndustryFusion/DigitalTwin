// Timestamps in a real VS Code: the case page's picker gives hasLength its
// observedAt; + Attribute adds a second observation of the same (default)
// instance at a later time; the page then marks the earlier one superseded --
// only the latest of a datasetId is validated, as on the platform.

const assert = require('assert');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, WORKSPACE, semforge, until, answering, read } = require('./helpers');

const RELATIVE = 'examples/test_WorkpieceShape/good/at-the-limits.jsonld';
const CASE = path.join(WORKSPACE, RELATIVE);

function lengths() {
  const document = JSON.parse(read(RELATIVE));
  const workpiece = (Array.isArray(document) ? document : [document])
    .find((e) => e.id === 'urn:workpiece:1');
  const key = Object.keys(workpiece).find((k) => k.endsWith('hasLength'));
  return [].concat(workpiece[key]);
}

describe('Timestamps (observedAt)', () => {
  it('the case page picker sets a time; a later observation supersedes it', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openCasePage',
      { raw: { kind: 'example', file: CASE }, packageUri: PACKAGE_URI });
    let page = await until(() => api.pages.case.page && api.pages.case.page.file === CASE &&
      api.pages.case.page, 'the case page');
    const card = page.files[0].cards.findIndex((c) => c.id === 'urn:workpiece:1');
    const row = page.files[0].cards[card].attributes.findIndex((a) => a.name === 'hasLength');
    assert.ok(api.pages.case.panel.webview.html.includes(`data-stamp="0.${card}.${row}"`));

    // The picker sends its value; the page writes it through Timestamp….
    await api.pages.case.receive({ command: 'stamp', at: `0.${card}.${row}`,
      value: '2026-01-01T00:00:00.000Z' });
    await until(() => lengths()[0].observedAt === '2026-01-01T00:00:00.000Z', 'the time written');

    // The same default instance again, later: another observation of it.
    const session = answering([
      { kind: 'pick', labelStarts: 'iffBaseEntities:hasLength' },
      { kind: 'pick', label: 'Default instance' },
      { kind: 'pick', label: '$(calendar) A time of your own…' },
      { kind: 'input', value: '2026-02-01T01:00:00+01:00' },
      { kind: 'input', value: '7' },
      { kind: 'pick', label: 'MMT' }]);
    try {
      await api.pages.case.receive({ command: 'addAttribute', at: `0.${card}` });
    } finally {
      session.restore();
    }
    assert.deepStrictEqual(lengths().map((i) => i.observedAt),
      ['2026-01-01T00:00:00.000Z', '2026-02-01T00:00:00.000Z'], JSON.stringify(session.asked));
    page = await until(() => {
      const rows = api.pages.case.page && api.pages.case.page.files[0].cards[card].attributes
        .filter((a) => a.name === 'hasLength');
      return rows && rows.length === 2 && rows[0].superseded && !rows[1].superseded &&
        api.pages.case.page;
    }, 'the earlier one superseded');
    // Shown: the latest, with "+1 earlier"; the earlier one folded under it.
    const html = api.pages.case.panel.webview.html;
    assert.ok(html.includes('>+1 earlier</a>') && html.includes('class="older"'));
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
