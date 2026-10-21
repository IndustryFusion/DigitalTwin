// Rename… in a real VS Code: a shape with its suite, then a case and a suite,
// each from the row a person right-clicks -- and the package tests exactly as
// it did before. The suites before this one have edited the workspace, so
// everything is compared with how it was, not with the pristine corpus; and
// everything is named back at the end.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, WORKSPACE, semforge, row, until, answering, read,
  restoreShapeName } = require('./helpers');

const BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/';
const EXAMPLES = path.join(WORKSPACE, 'examples');
const FROM = 'FilterShape';
const TYPED = 'FilterCheckShape';
// What Rename… made of it: the typed name with a random part.
let TO;

/** Every assert in every expectations.yaml naming `name`'s constraints. */
function asserts(name) {
  let count = 0;
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.name === 'expectations.yaml') {
        count += (fs.readFileSync(full, 'utf-8').match(
          new RegExp(`iffBaseShacl:${name}/`, 'g')) || []).length;
      }
    }
  };
  walk(EXAMPLES);
  return count;
}

/** The Tests row's summary, once the view has caught up with `ready`. */
async function summary(api, ready) {
  return until(async () => {
    const tests = await row(api.trees.model,
      (raw) => raw.kind === 'group' && raw.label === 'Tests', 'Tests');
    const suites = await api.trees.model.getChildren(tests);
    return (!ready || ready(suites.map((n) => n.raw.term || n.raw.label))) &&
      `${tests.raw.detail} ${tests.raw.severity || ''}`;
  }, 'the Tests summary');
}

describe('Rename…', () => {
  let before;

  it('a shape: its references, asserts and suite follow, and the cases test as before',
    async () => {
      const api = await semforge();
      before = await summary(api);
      const named = asserts(FROM);
      assert.ok(named > 0, 'the shape has asserts to carry along');
      const session = answering([{ kind: 'input', value: TYPED },
        { kind: 'warning', button: `Rename it and test_${FROM}` }]);
      let done;
      try {
        done = await vscode.commands.executeCommand('semforge.renameShape',
          { raw: { kind: 'shape', shape: BASE + FROM }, packageUri: PACKAGE_URI });
      } finally {
        session.restore();
      }
      assert.ok(done && done.ok, JSON.stringify(done));
      TO = done.newName;
      assert.ok(new RegExp(`^${TYPED}-[0-9a-f]{8}$`).test(TO), TO);
      const shacl = read('shacl.ttl');
      assert.ok(shacl.includes(`iffBaseShacl:${TO}`));
      assert.ok(!new RegExp(`iffBaseShacl:${FROM}\\b`).test(shacl));
      assert.strictEqual(asserts(TO), named, 'every assert renamed');
      assert.strictEqual(asserts(FROM), 0);
      assert.ok(fs.existsSync(path.join(EXAMPLES, `test_${TO}`)));
      await until(() => api.pages.shape.page && api.pages.shape.page.iri === BASE + TO,
        'the renamed shape page');
      assert.strictEqual(await summary(api, (suites) => suites.includes(`test_${TO}`)), before);
    });

  it('a case and a suite, from their rows', async () => {
    const api = await semforge();
    const suiteRow = await row(api.trees.model, (raw) => raw.kind === 'suite' &&
      (raw.term || raw.label) === `test_${TO}`, 'the renamed suite');
    const caseRow = (await api.trees.model.getChildren(suiteRow))
      .find((n) => n.raw.kind === 'example' && n.raw.file);
    const old = path.basename(caseRow.raw.file);
    let session = answering([{ kind: 'input', value: 'renamed-case' }]);
    try {
      const done = await vscode.commands.executeCommand('semforge.renameTestCase', caseRow);
      assert.ok(done && done.ok, JSON.stringify(done));
    } finally {
      session.restore();
    }
    const moved = path.join(path.dirname(caseRow.raw.file), 'renamed-case.jsonld');
    assert.ok(fs.existsSync(moved) && !fs.existsSync(caseRow.raw.file), old);
    await until(() => api.pages.case.page && api.pages.case.page.file === moved, 'its case page');

    session = answering([{ kind: 'input', value: 'filter_suite' }]);
    try {
      const done = await vscode.commands.executeCommand('semforge.renameSuite', suiteRow);
      assert.ok(done && done.ok, JSON.stringify(done));
    } finally {
      session.restore();
    }
    assert.ok(fs.existsSync(path.join(EXAMPLES, 'filter_suite')));
    assert.strictEqual(await summary(api, (suites) => suites.includes('filter_suite')), before);

    // Named back, from the rows again, for the suites after this one.
    session = answering([{ kind: 'input', value: `test_${TO}` }]);
    try {
      const back = await row(api.trees.model, (raw) => raw.kind === 'suite' &&
        (raw.term || raw.label) === 'filter_suite', 'filter_suite');
      await vscode.commands.executeCommand('semforge.renameSuite', back);
    } finally {
      session.restore();
    }
    const { client } = api.clientHolder;
    await client.sendRequest('semforge/renameCase', { uri: PACKAGE_URI,
      case: `test_${TO}/${path.basename(path.dirname(moved))}/renamed-case.jsonld`,
      name: old });
    await restoreShapeName(api, TO, FROM, true);
    assert.ok(fs.existsSync(path.join(EXAMPLES, `test_${FROM}`, path.basename(path.dirname(moved)),
      old)));
    assert.strictEqual(await summary(api, (suites) => suites.includes(`test_${FROM}`)), before);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
