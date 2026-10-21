// Clone… a case in a real VS Code: a valid case's invalid twin, from its row,
// lands in bad/ with the same data, fails until that data is broken, and
// leaves the original passing.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, semforge, row, until, answering, read } = require('./helpers');

const EXAMPLES = path.join(WORKSPACE, 'examples');

describe('Clone… a test case', () => {
  it('a valid case\'s invalid twin, from its row', async () => {
    const api = await semforge();
    const suite = await row(api.trees.model, (raw) => raw.kind === 'suite' &&
      (raw.term || raw.label) === 'test_WorkpieceShape', 'test_WorkpieceShape');
    const original = (await api.trees.model.getChildren(suite))
      .find((n) => n.raw.kind === 'example' && n.raw.file.includes(`${path.sep}good${path.sep}`));
    const stem = path.basename(original.raw.file, '.jsonld');
    const session = answering([
      { kind: 'pick', label: '$(arrow-swap) Expect the opposite' },
      { kind: 'input', value: `${stem}-violates` },
      { kind: 'warning' }]);           // "… nothing fires yet" -- dismissed
    let made;
    try {
      made = await vscode.commands.executeCommand('semforge.cloneTestCase', original);
    } finally {
      session.restore();
    }
    assert.ok(made && made.ok, JSON.stringify(made));
    const twin = path.join(EXAMPLES, 'test_WorkpieceShape', 'bad', `${stem}-violates.jsonld`);
    assert.strictEqual(made.file, twin);
    assert.ok(fs.existsSync(twin));
    assert.strictEqual(made.expect, 'invalid');
    assert.strictEqual(made.passes, false, 'identical data does not violate yet');
    assert.ok(read('examples/test_WorkpieceShape/bad/expectations.yaml')
      .includes(`path: ${stem}-violates.jsonld`));
    await until(() => api.pages.case.page && api.pages.case.page.file === twin, 'its case page');
    // The original is untouched and still passes.
    const rows = await until(async () => {
      const children = await api.trees.model.getChildren(await row(api.trees.model,
        (raw) => raw.kind === 'suite' && (raw.term || raw.label) === 'test_WorkpieceShape'));
      return children.length === 3 && children;
    }, 'the suite to show the clone');
    const again = rows.find((n) => n.raw.file === original.raw.file);
    assert.ok(!again.raw.severity, again.raw.detail);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
