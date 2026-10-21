// The Types view and the type page: a subtype with no shape of its own is a
// type too, with what it inherits.

const assert = require('assert');
const vscode = require('vscode');
const { semforge, row, until, answering } = require('./helpers');

/** What the page's ⋯ offers, dismissed without choosing. */
async function menu(api) {
  const session = answering([{ kind: 'pick' }]);
  try {
    await api.pages.type.receive({ command: 'pageMenu', row: -1 });
  } finally {
    session.restore();
  }
  return session.asked[0].offered;
}

async function typePage(api, label) {
  return until(() => {
    const panel = api.pages.type.panel;
    return panel && panel.title === `${label} · type` && api.pages.type.page &&
      api.pages.type.page.label === label && panel;
  }, `the ${label} page`);
}

describe('Types view', () => {
  it('lists a subtype without a shape of its own, with its inherited shapes', async () => {
    const api = await semforge();
    // Summary: the row is there (inherited attributes are on its page).
    await row(api.trees.constraints,
      (raw) => raw.kind === 'type' && raw.label === 'Plasmacutter', 'Plasmacutter');
    // Full: under it, the shapes that judge it -- every one inherited.
    const settings = vscode.workspace.getConfiguration('semforge');
    await settings.update('trees.detail', 'full', vscode.ConfigurationTarget.Workspace);
    try {
      const shapes = await until(async () => {
        const plasma = await row(api.trees.constraints,
          (raw) => raw.kind === 'type' && raw.label === 'Plasmacutter');
        const found = (await api.trees.constraints.getChildren(plasma)).map((n) => n.raw);
        return found.length && found.every((raw) => raw.kind === 'shape') && found;
      }, 'Plasmacutter\'s shapes in full mode');
      assert.ok(shapes.every((raw) => raw.inheritedFrom), 'none is its own');
      assert.ok(shapes.some((raw) => raw.label.endsWith('CutterShape')));
    } finally {
      await settings.update('trees.detail', 'summary', vscode.ConfigurationTarget.Workspace);
    }
  });

  it('opens its type page with the attributes it inherits', async () => {
    const api = await semforge();
    const plasma = await row(api.trees.constraints,
      (raw) => raw.kind === 'type' && raw.label === 'Plasmacutter');
    await vscode.commands.executeCommand('semforge.openTypePage', plasma);
    const panel = await typePage(api, 'Plasmacutter');
    const page = api.pages.type.page;
    assert.strictEqual(page.ownShape, '');
    assert.ok(page.attributes.length, 'CutterShape\'s attributes are listed');
    assert.ok(page.attributes.every((attribute) => attribute.inherited));
    const html = panel.webview.html;
    assert.ok(html.includes('class="primary" data-action="addAttribute"'),
      '+ Attribute, though it has no shape');
    assert.ok(html.includes('From Cutter'), 'its attributes grouped by where they come from');
    const offered = await menu(api);
    assert.ok(offered.includes('$(type-hierarchy-sub) New subtype…'), offered.join(', '));
    assert.ok(offered.includes('$(new-file) Create its shape'), offered.join(', '));
  });

  it('a type with its own shape adds to it', async () => {
    const api = await semforge();
    const cutter = await row(api.trees.constraints,
      (raw) => raw.kind === 'type' && raw.label === 'Cutter');
    await vscode.commands.executeCommand('semforge.openTypePage', cutter);
    const panel = await typePage(api, 'Cutter');
    assert.ok(api.pages.type.page.ownShape.endsWith('CutterShape'));
    assert.ok(panel.webview.html.includes('data-action="addSparql"'), '+ SPARQL constraint');
    assert.ok(!(await menu(api)).includes('$(new-file) Create its shape'));
  });
});
