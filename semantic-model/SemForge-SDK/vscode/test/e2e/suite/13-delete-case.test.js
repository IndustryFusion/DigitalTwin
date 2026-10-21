// Delete… a case and a suite in a real VS Code, from their rows: the file and
// its entry go, the folders left empty go, what is left still tests -- and
// the question named the evidence the deletion costs. Runs after 12-clone,
// whose failing twin is the case deleted here.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { WORKSPACE, semforge, row, until, answering, read } = require('./helpers');

const EXAMPLES = path.join(WORKSPACE, 'examples');

async function suiteRow(api, folder) {
  return row(api.trees.model, (raw) => raw.kind === 'suite' && (raw.term || raw.label) === folder,
    folder);
}

describe('Delete… a test case and a suite', () => {
  it('a case, from its row', async () => {
    const api = await semforge();
    const suite = await suiteRow(api, 'test_WorkpieceShape');
    const children = await api.trees.model.getChildren(suite);
    const twin = children.find((n) => n.raw.kind === 'example' && n.raw.file.endsWith('-violates.jsonld'));
    assert.ok(twin, 'the clone 12-clone made');
    const others = children.filter((n) => n !== twin && n.raw.kind === 'example').map((n) => n.raw.file);
    const session = answering([{ kind: 'warning', button: 'Delete' }]);
    let done;
    try {
      done = await vscode.commands.executeCommand('semforge.deleteTestCase', twin);
    } finally {
      session.restore();
    }
    assert.ok(done && done.ok, JSON.stringify(done));
    assert.ok(session.asked[0].offered.message.startsWith(`Delete ${path.basename(twin.raw.file)}?`));
    assert.ok(!fs.existsSync(twin.raw.file));
    assert.ok(!read('examples/test_WorkpieceShape/bad/expectations.yaml')
      .includes(path.basename(twin.raw.file)));
    for (const file of others) {
      assert.ok(fs.existsSync(file), `${file} stays`);
    }
    await until(async () => (await api.trees.model.getChildren(
      await suiteRow(api, 'test_WorkpieceShape'))).length === children.length - 1,
    'the view without it');
  });

  it('a suite, from its row, naming the evidence it costs', async () => {
    const api = await semforge();
    const suite = await suiteRow(api, 'test_CartridgeShape');
    const session = answering([{ kind: 'warning', button: 'Delete' }]);
    let done;
    try {
      done = await vscode.commands.executeCommand('semforge.deleteSuite', suite);
    } finally {
      session.restore();
    }
    assert.ok(done && done.ok, JSON.stringify(done));
    const asked = session.asked[0].offered.message;
    assert.ok(asked.startsWith('Delete the suite test_CartridgeShape?'), asked);
    assert.ok(done.lost.some((c) => c.includes('CartridgeShape/hasCartridge/MaxCountConstraintComponent')),
      done.lost.join(', '));
    assert.ok(!fs.existsSync(path.join(EXAMPLES, 'test_CartridgeShape')));
    await until(async () => {
      const tests = await row(api.trees.model,
        (raw) => raw.kind === 'group' && raw.label === 'Tests', 'Tests');
      const suites = await api.trees.model.getChildren(tests);
      return !suites.some((n) => (n.raw.term || n.raw.label) === 'test_CartridgeShape');
    }, 'the suite gone from the view');
  });
});
