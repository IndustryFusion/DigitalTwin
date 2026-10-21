// The Instances view and the pages a click opens on it, with the rows the
// real server sends -- in both tree modes.

const assert = require('assert');
const vscode = require('vscode');
const { semforge, row, rows, until } = require('./helpers');

async function click(api, node) {
  await api.trees.model.view.reveal(node, { select: true, focus: false, expand: false });
}

async function pageTitled(api, title) {
  return until(() => {
    const panel = api.pages.case.panel;
    return panel && panel.title === title && panel.webview.html.includes('<h1>') && panel;
  }, `a page titled "${title}"`);
}

describe('Instances view', () => {
  for (const detail of ['summary', 'full']) {
    describe(`in ${detail} mode`, () => {
      before(async () => {
        const api = await semforge();
        await vscode.workspace.getConfiguration('semforge').update('trees.detail', detail,
          vscode.ConfigurationTarget.Workspace);
        await until(async () => {
          const top = await api.trees.model.getChildren();
          return top && top.length && top[0].raw.detail !== undefined;
        }, 'the tree to redraw');
      });

      it('holds Main first, then Tests', async () => {
        const api = await semforge();
        const top = await until(async () => {
          const found = (await api.trees.model.getChildren()).map((n) => n.raw.label);
          return found.length === 2 && found;
        }, 'two groups');
        assert.deepStrictEqual(top, ['Main', 'Tests']);
        const tests = (await api.trees.model.getChildren())[1];
        const suites = (await api.trees.model.getChildren(tests)).map((n) => n.raw.kind);
        assert.ok(suites.length && suites.every((kind) => kind === 'suite'));
      });

      it('opens the Main page from Main, its file and an entity in it', async () => {
        const api = await semforge();
        const main = await row(api.trees.model, (raw) => raw.label === 'Main', 'Main');
        await click(api, main);
        let panel = await pageTitled(api, 'Main · instances');
        assert.ok(panel.webview.html.includes('Open the model file'));
        assert.ok(!panel.webview.html.includes('<h2>Claims</h2>'), 'the model has no claims');

        const file = (await api.trees.model.getChildren(main))[0];
        await click(api, file);
        await pageTitled(api, 'Main · instances');

        const entity = (await rows(api.trees.model)).find((node) =>
          node.raw.kind === 'entity' && api.trees.model.getParent(node) &&
          api.trees.model.getParent(node).raw.label === file.raw.label);
        await click(api, entity);
        panel = await until(() => {
          const html = api.pages.case.panel.webview.html;
          return html.includes('id="focus"') && html.split('id="focus"')[1]
            .slice(0, 600).includes(entity.raw.entity) && api.pages.case.panel;
        }, `${entity.raw.entity} marked on the page`);
      });

      it('opens a case page from a case', async () => {
        const api = await semforge();
        const found = await row(api.trees.model,
          (raw) => raw.kind === 'example' && raw.file, 'a case');
        await click(api, found);
        const panel = await until(() => api.pages.case.panel &&
          api.pages.case.panel.title.endsWith('· test case') && api.pages.case.panel, 'a case page');
        assert.ok(panel.webview.html.includes('<h2>Claims</h2>'));
      });
    });
  }

  after(async () => {
    await vscode.workspace.getConfiguration('semforge').update('trees.detail', 'summary',
      vscode.ConfigurationTarget.Workspace);
  });
});

describe('the Main page', () => {
  it('offers editing on every card and file', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openModelPage');
    const panel = await pageTitled(api, 'Main · instances');
    const page = api.pages.case.page;
    const html = panel.webview.html;
    assert.strictEqual(page.kind, 'model');
    page.files.forEach((file, f) => {
      assert.ok(html.includes(`data-addentity="${f}"`), `+ Entity on ${file.relative}`);
      file.cards.forEach((card, c) => {
        assert.ok(card.node, `${card.id} carries its tree row`);
        assert.ok(html.includes(`data-addattr="${f}.${c}"`), `+ Attribute on ${card.id}`);
      });
    });
    const editable = page.files[0].cards.flatMap((card) => card.attributes)
      .filter((attribute) => attribute.node && attribute.node.editable);
    assert.ok(editable.length, 'some value can be edited');
    assert.ok(html.includes('data-edit="0.'), 'a value is a link');
    assert.ok(html.includes('data-rowmenu="0.'), 'a row has its ⋯');
  });
});
