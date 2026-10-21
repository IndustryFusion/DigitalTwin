// Counts other than 0 and 1, in a real VS Code: the Presence cell's
// Between… writes sh:minCount 2 and sh:maxCount 3 into the property shape,
// the page says "2 to 3", and Required afterwards keeps the 2.

const assert = require('assert');
const vscode = require('vscode');
const { PACKAGE_URI, semforge, until, answering, read } = require('./helpers');

const ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/';

async function workpiece(api) {
  await vscode.commands.executeCommand('semforge.openTypePage',
    { raw: { kind: 'type', targetClass: `${ENT}Workpiece`, label: 'Workpiece', children: [] },
      packageUri: PACKAGE_URI });
  return until(() => api.pages.type.page && api.pages.type.page.label === 'Workpiece' &&
    api.pages.type.page, 'the Workpiece page');
}

/** hasHeight's property shape: from its `[` -- the corpus writes the counts
 *  before sh:path -- to the next attribute's sh:path. */
function heightStatement(shacl) {
  const shape = shacl.slice(shacl.indexOf('iffBaseShacl:WorkpieceShape a'));
  const at = shape.indexOf('sh:path iffBaseEntities:hasHeight');
  const next = shape.indexOf('sh:path iffBaseEntities:', at + 1);
  return shape.slice(shape.lastIndexOf('[', at), next > 0 ? next : at + 800);
}

describe('Counts beyond one', () => {
  it('Between… 2 and 3 from the Presence cell; Required keeps the 2', async () => {
    const api = await semforge();
    let page = await workpiece(api);
    let row = page.attributes.findIndex((a) => a.label === 'hasHeight');
    let session = answering([{ kind: 'pick', label: 'Between…' },
      { kind: 'input', value: '2' }, { kind: 'input', value: '3' }]);
    const errors = [];
    const showError = vscode.window.showErrorMessage;
    vscode.window.showErrorMessage = async (message) => { errors.push(message); };
    try {
      await api.pages.type.receive({ command: 'presence', row });
    } finally {
      session.restore();
      vscode.window.showErrorMessage = showError;
    }
    assert.deepStrictEqual(errors, []);
    assert.strictEqual(session.left(), 0, JSON.stringify(session.asked));
    await until(() => /sh:minCount 2/.test(heightStatement(read('shacl.ttl'))) &&
      /sh:maxCount 3/.test(heightStatement(read('shacl.ttl'))), 'minCount 2 and maxCount 3');
    page = await until(() => api.pages.type.page && api.pages.type.page.attributes
      .find((a) => a.label === 'hasHeight' && a.presence === '2 to 3') && api.pages.type.page,
    'the page to say 2 to 3');

    row = page.attributes.findIndex((a) => a.label === 'hasHeight');
    session = answering([{ kind: 'pick', label: 'Required' }]);
    try {
      await api.pages.type.receive({ command: 'presence', row });
    } finally {
      session.restore();
    }
    await until(() => api.pages.type.page && api.pages.type.page.attributes
      .find((a) => a.label === 'hasHeight' && a.presence === '2 to 3'), 'still 2 to 3');
    assert.match(heightStatement(read('shacl.ttl')), /sh:minCount 2/);
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
