// Delete… in a real VS Code: a shape with its asserts and the cases that
// tested only it, from its row -- and the package tests no worse than before.
// Last, since the shape does not come back.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, WORKSPACE, semforge, row, until, answering, read } = require('./helpers');

const BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/';
const EXAMPLES = path.join(WORKSPACE, 'examples');

async function tests(api) {
  return row(api.trees.model, (raw) => raw.kind === 'group' && raw.label === 'Tests', 'Tests');
}

describe('Delete…', () => {
  it('a shape, its asserts and the cases that tested only it', async () => {
    const api = await semforge();
    const before = (await tests(api)).raw;
    // Its page is open: deleting the shape closes it.
    await vscode.commands.executeCommand('semforge.openShapePage',
      { raw: { shape: `${BASE}FilterShape` }, packageUri: PACKAGE_URI });
    await until(() => api.pages.shape.panel && api.pages.shape.page &&
      api.pages.shape.page.iri === `${BASE}FilterShape`, 'its shape page');
    const shapeRow = await row(api.trees.shapes || api.trees.constraints,
      (raw) => raw.shape === `${BASE}FilterShape` && (raw.kind === 'shape' || raw.kind === 'rule'),
      'FilterShape in the view');
    const session = answering([{ kind: 'warning', button: 'Delete it, its asserts and the cases' }]);
    let done;
    try {
      done = await vscode.commands.executeCommand('semforge.deleteShape', shapeRow);
    } finally {
      session.restore();
    }
    assert.ok(done && done.ok, JSON.stringify(done));
    assert.ok(session.asked[0].offered.message.startsWith('Delete iffBaseShacl:FilterShape?'));
    assert.ok(!/iffBaseShacl:FilterShape\b/.test(read('shacl.ttl')));
    assert.ok(!fs.existsSync(path.join(EXAMPLES, 'test_FilterShape')), 'its suite held only its case');
    await until(() => !api.pages.shape.panel, 'its page closed');
    // The Tests summary: one case fewer, and nothing newly failing.
    const after = await until(async () => {
      const raw = (await tests(api)).raw;
      return raw.detail !== before.detail && raw;
    }, 'the Tests view to catch up');
    assert.strictEqual(after.severity || '', before.severity || '', after.detail);
  });
});
