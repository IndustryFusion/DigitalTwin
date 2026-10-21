// Units in a real VS Code: Unit… on Workpiece's hasLength allows mm and
// requires it, the case that says no unit then fails on
// hasLength.unitCode, and Unit… on its case page row makes it say mm. The
// Vocabulary view lists the units by quantity under qudt:Unit.

const assert = require('assert');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, WORKSPACE, semforge, until, answering, read } = require('./helpers');

const ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/';
const RELATIVE = 'examples/test_WorkpieceShape/good/at-the-limits.jsonld';
const CASE = path.join(WORKSPACE, RELATIVE);

function lengthStatement(shacl) {
  const shape = shacl.slice(shacl.indexOf('iffBaseShacl:WorkpieceShape a'));
  const at = shape.indexOf('sh:path iffBaseEntities:hasLength');
  const next = shape.indexOf('sh:path iffBaseEntities:', at + 1);
  return shape.slice(shape.lastIndexOf('[', at), next > 0 ? next : at + 800);
}

describe('Units (unitCode)', () => {
  it('Unit… on the type page: hasLength in mm, required', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openTypePage',
      { raw: { kind: 'type', targetClass: `${ENT}Workpiece`, label: 'Workpiece', children: [] },
        packageUri: PACKAGE_URI });
    const page = await until(() => api.pages.type.page && api.pages.type.page.label === 'Workpiece' &&
      api.pages.type.page, 'the Workpiece page');
    const row = page.attributes.findIndex((a) => a.label === 'hasLength');
    const session = answering([
      { kind: 'pick', label: '$(symbol-ruler) Unit…' },
      { kind: 'pick', choose: (items) => items.filter((i) => i.label === 'MMT') },
      { kind: 'pick', label: 'Required' }]);
    try {
      await api.pages.type.receive({ command: 'menu', row });
    } finally {
      session.restore();
    }
    await until(() => /sh:path ngsild:unitCode ; sh:in \( "MMT" \) ; sh:minCount 1/
      .test(lengthStatement(read('shacl.ttl'))), 'the unit constraint on hasLength');
    await until(() => api.pages.type.page.attributes.find((a) => a.label === 'hasLength' &&
      a.value.includes('in mm') && a.value.includes('unit required')), 'the row to say in mm');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('a case without the unit fails on it, and Unit… on its row fixes it', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openCasePage',
      { raw: { kind: 'example', file: CASE }, packageUri: PACKAGE_URI });
    const lengthRow = () => {
      const page = api.pages.case.page;
      const card = page && page.files[0].cards.find((c) => c.id === 'urn:workpiece:1');
      return card && card.attributes.find((a) => a.name === 'hasLength');
    };
    await until(() => lengthRow() && lengthRow().violations
      .some((v) => JSON.stringify(v).includes('unitCode')), 'hasLength.unitCode firing');
    const page = api.pages.case.page;
    const card = page.files[0].cards.findIndex((c) => c.id === 'urn:workpiece:1');
    const row = page.files[0].cards[card].attributes.findIndex((a) => a.name === 'hasLength');
    const session = answering([
      { kind: 'pick', label: '$(symbol-ruler) Unit…' },
      { kind: 'pick', label: 'MMT' }]);
    try {
      await api.pages.case.receive({ command: 'rowMenu', at: `0.${card}.${row}` });
    } finally {
      session.restore();
    }
    const document = JSON.parse(read(RELATIVE));
    const workpiece = (Array.isArray(document) ? document : [document])
      .find((e) => e.id === 'urn:workpiece:1');
    const length = Object.keys(workpiece).find((k) => k.endsWith('hasLength'));
    assert.strictEqual([].concat(workpiece[length])[0].unitCode, 'MMT', JSON.stringify(session.asked));
    await until(() => lengthRow() && lengthRow().unitText === 'mm' &&
      !lengthRow().violations.some((v) => JSON.stringify(v).includes('unitCode')), 'mm, and clean');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });

  it('the Vocabulary view lists the units by quantity', async () => {
    const api = await semforge();
    const vocabulary = await until(async () => (await api.trees.knowledge.getChildren())
      .find((n) => n.raw.label === 'Vocabulary classes'), 'the Vocabulary classes');
    const units = (await api.trees.knowledge.getChildren(vocabulary))
      .find((n) => n.raw.kind === 'units');
    assert.ok(units, 'qudt:Unit in the view');
    const temperature = (await api.trees.knowledge.getChildren(units))
      .find((n) => n.raw.label === 'temperature');
    const codes = (await api.trees.knowledge.getChildren(temperature)).map((n) => n.raw.label);
    assert.deepStrictEqual(codes, ['CEL', 'FAH', 'KEL']);
  });
});
