// An attribute the knowledge gives one type, added to an unrelated one from
// its shape's row in a real VS Code: the picker offers it under "Declared for
// other types", asks, and the knowledge's rdfs:domain becomes the union.

const assert = require('assert');
const vscode = require('vscode');
const { semforge, row, until, answering, read } = require('./helpers');

const BASE = 'https://industryfusion.github.io/contexts/example/v0/';

describe('Sharing an attribute with another type', () => {
  it('+ Attribute on Workpiece gives it hasStrength, a Filter attribute', async () => {
    const api = await semforge();
    const tests = async () => (await row(api.trees.model,
      (raw) => raw.kind === 'group' && raw.label === 'Tests', 'Tests')).raw;
    const before = await tests();
    const shapeRow = await row(api.trees.shapes,
      (raw) => raw.shape === `${BASE}base_shacl/WorkpieceShape`, 'WorkpieceShape');
    const session = answering([
      { kind: 'pick', label: 'hasStrength' },
      { kind: 'warning', button: 'Give it to this type too' },
      { kind: 'pick', label: 'Optional' },
      { kind: 'pick', label: 'Any value' }]);
    try {
      await vscode.commands.executeCommand('semforge.addAttributeConstraint', shapeRow);
    } finally {
      session.restore();
    }
    const offered = session.asked[0].offered;
    const section = offered.indexOf('Declared for other types — adding one gives it to this type too');
    assert.ok(section >= 0 && section < offered.indexOf('hasStrength'), offered.join(' | '));
    assert.ok(session.asked[1].offered.message.startsWith('Give hasStrength to Workpiece too?'));

    const knowledge = read('knowledge.ttl');
    const statement = knowledge.slice(knowledge.indexOf('iffBaseEntities:hasStrength a'));
    assert.ok(/owl:unionOf \( iffBaseEntities:Filter iffBaseEntities:Workpiece \)/
      .test(statement.slice(0, 600)), statement.slice(0, 600));
    // Workpiece's shape now constrains it -- asked of the server, since the
    // suites before this one have edited that statement too.
    const options = await api.clientHolder.client.sendRequest('semforge/attributeOptions',
      { uri: shapeRow.packageUri, shape: `${BASE}base_shacl/WorkpieceShape` });
    assert.strictEqual(options.options.find((o) => o.label === 'hasStrength').status, 'here');
    // And nothing newly fails.
    const after = await until(async () => {
      const raw = await tests();
      return raw.detail && raw;
    }, 'the Tests summary');
    assert.strictEqual(after.severity || '', before.severity || '', after.detail);
  });
});
