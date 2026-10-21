// Another instance of an attribute -- the same name under a new datasetId --
// in a real VS Code: Add instance… from a case page's row menu writes it, and
// the case's sh:maxCount 1 now fires on it. Then an "@none" written out is
// reported on its line, and the quick fix removes it.

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, WORKSPACE, semforge, until, answering, read } = require('./helpers');

const RELATIVE = 'examples/test_WorkpieceShape/good/at-the-limits.jsonld';
const CASE = path.join(WORKSPACE, RELATIVE);

function code(diagnostic) {
  return typeof diagnostic.code === 'object' && diagnostic.code ? diagnostic.code.value
    : diagnostic.code;
}

describe('Multi-instance attributes (datasetId)', () => {
  it('Add instance… on a case page; sh:maxCount sees it', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openCasePage',
      { raw: { kind: 'example', file: CASE }, packageUri: PACKAGE_URI });
    const page = await until(() => api.pages.case.page && api.pages.case.page.file === CASE &&
      api.pages.case.page, 'the case page');
    const card = page.files[0].cards.findIndex((c) => c.id === 'urn:workpiece:1');
    const row = page.files[0].cards[card].attributes.findIndex((a) => a.name === 'hasHeight');
    assert.ok(card >= 0 && row >= 0, 'the workpiece and its hasHeight on the page');
    const session = answering([
      // A datasetId lives in a registered namespace: define sensor: here.
      { kind: 'pick', label: '$(layers) Add instance…' },
      { kind: 'pick', label: '$(add) New namespace…' },
      { kind: 'input', value: 'sensor' },
      { kind: 'input', value: 'urn:sensor:' },
      { kind: 'input', value: 'second' }]);
    try {
      await api.pages.case.receive({ command: 'rowMenu', at: `0.${card}.${row}` });
    } finally {
      session.restore();
    }
    const document = JSON.parse(read(RELATIVE));
    const workpiece = (Array.isArray(document) ? document : [document])
      .find((e) => e.id === 'urn:workpiece:1');
    const height = Object.keys(workpiece).find((k) => k.endsWith('hasHeight'));
    assert.ok(Array.isArray(workpiece[height]), JSON.stringify(workpiece[height]));
    assert.deepStrictEqual(workpiece[height].map((i) => i.datasetId),
      [undefined, 'urn:sensor:second']);
    assert.match(read('semforge.yaml'), /sensor:\s*['"]?urn:sensor:/);
    await until(() => api.pages.case.page && api.pages.case.page.files[0].cards[card].attributes
      .some((a) => a.name === 'hasHeight' && a.violations
        .some((v) => JSON.stringify(v).includes('MaxCount'))), 'MaxCount firing on hasHeight');
    await until(() => api.pages.case.page.files[0].cards[card].attributes
      .some((a) => a.display === 'hasHeight[sensor:second]'), 'the row named hasHeight[sensor:second]');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('+ Attribute on an entity that has it adds another instance, by datasetId', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openCasePage',
      { raw: { kind: 'example', file: CASE }, packageUri: PACKAGE_URI });
    const page = await until(() => api.pages.case.page && api.pages.case.page.file === CASE &&
      api.pages.case.page, 'the case page');
    const card = page.files[0].cards.findIndex((c) => c.id === 'urn:workpiece:1');
    // The datasetId from one of the package's namespaces: pick it, type the
    // local part, and the full IRI is written.
    let namespace;
    const session = answering([
      { kind: 'pick', labelStarts: 'iffBaseEntities:hasHeight' },
      { kind: 'pick', choose: (items) => {
        const space = items.find((item) => item.space);
        namespace = space && space.space.namespace;
        return space;
      } },
      { kind: 'input', value: 'third' },
      { kind: 'input', value: '2.5' }]);
    try {
      await api.pages.case.receive({ command: 'addAttribute', at: `0.${card}` });
    } finally {
      session.restore();
    }
    const document = JSON.parse(read(RELATIVE));
    const workpiece = (Array.isArray(document) ? document : [document])
      .find((e) => e.id === 'urn:workpiece:1');
    const height = Object.keys(workpiece).find((k) => k.endsWith('hasHeight'));
    assert.ok(namespace, 'a namespace of the package was offered');
    assert.deepStrictEqual(workpiece[height].map((i) => i.datasetId),
      [undefined, 'urn:sensor:second', `${namespace}third`], JSON.stringify(session.asked));
    assert.strictEqual(workpiece[height][2].value, 2.5);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('"datasetId": "@none" written out is reported, and the quick fix removes it', async () => {
    await semforge();
    const text = read(RELATIVE).replace('"datasetId": "urn:sensor:second"', '"datasetId": "@none"');
    fs.writeFileSync(CASE, text);
    const uri = vscode.Uri.file(CASE);
    await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(uri));
    const found = await until(() => vscode.languages.getDiagnostics(uri)
      .find((d) => code(d) === 'dataset-none'), 'the dataset-none diagnostic');
    assert.ok(text.split('\n')[found.range.start.line].includes('"@none"'));
    const actions = await vscode.commands.executeCommand('vscode.executeCodeActionProvider',
      uri, found.range);
    const fix = actions.find((a) => a.title.startsWith('Remove "datasetId": "@none"'));
    assert.ok(fix, actions.map((a) => a.title).join(' | '));
    await vscode.commands.executeCommand(fix.command.command, ...fix.command.arguments);
    await until(() => !read(RELATIVE).includes('@none'), 'the @none gone from the file');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('Remove on one instance\'s row takes just that instance', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openCasePage',
      { raw: { kind: 'example', file: CASE }, packageUri: PACKAGE_URI });
    const page = await until(() => api.pages.case.page && api.pages.case.page.file === CASE &&
      api.pages.case.page, 'the case page');
    const card = page.files[0].cards.findIndex((c) => c.id === 'urn:workpiece:1');
    const rows = page.files[0].cards[card].attributes;
    const row = rows.findIndex((a) => a.name === 'hasHeight' && a.dataset &&
      a.dataset.endsWith('third'));
    assert.ok(row >= 0, rows.map((a) => a.display).join(', '));
    const before = JSON.parse(read(RELATIVE));
    const count = (document) => {
      const workpiece = (Array.isArray(document) ? document : [document])
        .find((e) => e.id === 'urn:workpiece:1');
      const height = Object.keys(workpiece).find((k) => k.endsWith('hasHeight'));
      return [].concat(workpiece[height]);
    };
    const session = answering([
      { kind: 'pick', labelStarts: `$(trash) Remove ${rows[row].display}` },
      { kind: 'warning', button: 'Remove' }]);
    try {
      await api.pages.case.receive({ command: 'rowMenu', at: `0.${card}.${row}` });
    } finally {
      session.restore();
    }
    const left = count(JSON.parse(read(RELATIVE)));
    assert.strictEqual(left.length, count(before).length - 1, JSON.stringify(session.asked));
    assert.ok(!left.some((i) => String(i.datasetId || '').endsWith('third')));
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
