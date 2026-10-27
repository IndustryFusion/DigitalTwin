/**
* Copyright (c) 2026 IndustryFusion Foundation
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*    http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/

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

      // Summary leads with the model's violations, one row each; full keeps
      // the two kinds of data only.
      const groups = detail === 'summary' ? ['Violations', 'Main', 'Tests'] : ['Main', 'Tests'];

      it(`holds ${groups.join(', then ')}`, async () => {
        const api = await semforge();
        const top = await until(async () => {
          const found = (await api.trees.model.getChildren()).map((n) => n.raw.label);
          return found.length === groups.length && found;
        }, `${groups.length} groups`);
        assert.deepStrictEqual(top, groups);
        const tests = (await api.trees.model.getChildren())[groups.length - 1];
        const suites = (await api.trees.model.getChildren(tests)).map((n) => n.raw.kind);
        assert.ok(suites.length && suites.every((kind) => kind === 'suite'));
      });

      it('opens the Main page from Main, its file and an entity in it', async () => {
        const api = await semforge();
        const main = await row(api.trees.model, (raw) => raw.label === 'Main', 'Main');
        await click(api, main);
        let panel = await pageTitled(api, 'Entities: Main');
        assert.ok(panel.webview.html.includes('Open the model file'));
        assert.ok(!panel.webview.html.includes('<h2>Claims</h2>'), 'the model has no claims');

        const file = (await api.trees.model.getChildren(main))[0];
        await click(api, file);
        await pageTitled(api, 'Entities: Main');

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

      if (detail === 'summary') {
        it('opens a violation on the Main page, at its entity, and no file', async () => {
          const api = await semforge();
          const group = await row(api.trees.model, (raw) => raw.kind === 'violations',
            'the Violations group');
          const violation = (await api.trees.model.getChildren(group))
            .find((node) => node.raw.entity === 'urn:cutter:1');
          assert.ok(violation, 'urn:cutter:1 violates MachineShape');
          assert.ok(violation.raw.detail.includes('hasXXXWorkpiece'));
          // From a page with no mark: the click, not an earlier one, sets it.
          await click(api, await row(api.trees.model, (raw) => raw.label === 'Main', 'Main'));
          await until(() => api.pages.case.panel && api.pages.case.panel.title === 'Entities: Main' &&
            !api.pages.case.panel.webview.html.includes('id="focus"'), 'the Main page unmarked');
          const editors = vscode.window.visibleTextEditors.map((e) => e.document.uri.toString());
          api.pages.case.landed = undefined;
          await click(api, violation);
          await until(() => {
            const panel = api.pages.case.panel;
            const html = panel && panel.webview.html;
            return html && panel.title === 'Entities: Main' && html.includes('id="focus"') &&
              html.split('id="focus"')[1].slice(0, 600).includes('urn:cutter:1');
          }, 'urn:cutter:1 marked on the Main page');
          // In sight in the real webview, which puts back its old scroll position.
          const landed = await until(() => api.pages.case.landed, 'the page to say where it landed');
          assert.strictEqual(landed.entity, 'urn:cutter:1');
          assert.ok(landed.inView, JSON.stringify(landed));
          // And each other violation, one after the other, from wherever the last left it.
          for (const other of (await api.trees.model.getChildren(group))) {
            api.pages.case.landed = undefined;
            // As the mouse does: the row's command -- a selection of the row
            // already selected changes nothing, and so does nothing.
            const { command } = await api.trees.model.getTreeItem(other);
            await vscode.commands.executeCommand(command.command, ...command.arguments);
            const there = await until(() => api.pages.case.landed &&
              api.pages.case.landed.entity === other.raw.entity && api.pages.case.landed,
              `${other.raw.entity} landed`);
            assert.ok(there.inView, JSON.stringify(there));
          }
          assert.deepStrictEqual(
            vscode.window.visibleTextEditors.map((e) => e.document.uri.toString()), editors,
            'a click stays in the pages');
        });
      }

      it('opens a case page from a case', async () => {
        const api = await semforge();
        const found = await row(api.trees.model,
          (raw) => raw.kind === 'example' && raw.file, 'a case');
        await click(api, found);
        const panel = await until(() => api.pages.case.panel &&
          api.pages.case.panel.title.startsWith('Test case: ') && api.pages.case.panel, 'a case page');
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
    const panel = await pageTitled(api, 'Entities: Main');
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
