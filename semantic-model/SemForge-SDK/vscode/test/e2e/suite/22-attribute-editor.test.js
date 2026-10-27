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

// The attribute editor in a real VS Code: a click on a type page's row opens
// it beside the page, and every change made in it -- a condition, a list, a
// form, presence, severity -- is written to shacl.ttl by the server
// (semforge/editValueForms, semforge/editAttribute) and shown by the page.
// Cutter's hasTrust, an optional number no other suite touches.

const assert = require('assert');
const vscode = require('vscode');
const { PACKAGE_URI, semforge, until, answering, request } = require('./helpers');

const ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/';

async function cutter(api) {
  await vscode.commands.executeCommand('semforge.openTypePage',
    { raw: { kind: 'type', targetClass: `${ENT}Cutter`, label: 'Cutter', children: [] },
      packageUri: PACKAGE_URI });
  return until(() => api.pages.type.page && api.pages.type.page.label === 'Cutter' &&
    api.pages.type.page, 'the Cutter page');
}

function trust(api) {
  return (api.pages.type.page.attributes || []).find((a) => a.label === 'hasTrust');
}

/** What the server reads back for hasTrust's value now. */
async function forms(api) {
  const row = trust(api);
  return request(api, 'semforge/valueForms', { shape: row.shape, path: row.path });
}

describe('The attribute editor', () => {
  it('opens beside the page on a click on its row', async () => {
    const api = await semforge();
    const page = await cutter(api);
    const row = page.attributes.findIndex((a) => a.label === 'hasTrust');
    await api.pages.type.receive({ command: 'attribute', row });
    const editor = await until(() => api.pages.attribute && api.pages.attribute.panel &&
      api.pages.attribute, 'the attribute editor');
    assert.strictEqual(editor.panel.title, 'Attribute: hasTrust');
    const html = editor.panel.webview.html;
    assert.ok(html.includes('<h1>Attribute: hasTrust</h1>'), 'its heading');
    for (const button of ['data-cmd="presence"', 'data-cmd="severity"', 'data-cmd="unit"',
      'data-cmd="test"', 'data-cmd="open"']) {
      assert.ok(html.includes(button), button);
    }
    assert.ok(html.includes('data-act="lists-on"'), 'one value: a list may be allowed');
  });

  it('a condition set in a form is written, and the page says it', async () => {
    const api = await semforge();
    await api.pages.attribute.receive({ command: 'edit',
      action: { op: 'set', form: 0, node: [0], parameter: 'sh:maxInclusive', value: '10' } });
    assert.strictEqual(api.pages.attribute.error, '', api.pages.attribute.error);
    const read = await until(async () => {
      const now = await forms(api);
      return now.ok && /10/.test(now.said) && now;
    }, 'the server to read the new condition back');
    assert.ok(/at most 10|– 10|≤ 10/.test(read.said), read.said);
    await until(() => /10/.test(trust(api).value), 'the page to show it');
  });

  it('"Allow a list too" adds the list form, and "One value only" takes it away', async () => {
    const api = await semforge();
    await api.pages.attribute.receive({ command: 'edit', action: { op: 'lists', value: true } });
    await until(async () => (await forms(api)).lists === 'allowed', 'the list form');
    await until(() => (trust(api).kinds || []).join() === 'Property,ListProperty',
      'the page to say Property or ListProperty');
    assert.ok(api.pages.attribute.panel.webview.html.includes('data-act="lists-off"'));

    await api.pages.attribute.receive({ command: 'edit', action: { op: 'lists', value: false } });
    await until(async () => (await forms(api)).lists === 'single', 'one value again');
    await until(() => (trust(api).kinds || []).join() === 'Property', 'the page to say Property');
  });

  it('+ Form adds a kind the value may take, and it can go again', async () => {
    const api = await semforge();
    await api.pages.attribute.receive({ command: 'edit',
      action: { op: 'addform', kind: 'JsonProperty' } });
    const added = await until(async () => {
      const now = await forms(api);
      return now.forms.length === 2 && now;
    }, 'a second form');
    assert.deepStrictEqual(added.forms.map((f) => f.kind), ['Property', 'JsonProperty']);
    await api.pages.attribute.receive({ command: 'edit', action: { op: 'removeform', form: 1 } });
    await until(async () => (await forms(api)).forms.length === 1, 'one form again');
  });

  it('Presence and Severity run the page’s own pickers on its row', async () => {
    const api = await semforge();
    let session = answering([{ kind: 'pick', label: 'Required' }]);
    try {
      await api.pages.attribute.receive({ command: 'row', name: 'presence' });
    } finally {
      session.restore();
    }
    assert.strictEqual(session.left(), 0, JSON.stringify(session.asked));
    await until(() => trust(api).presence !== 'optional', 'the page to say it is required');

    session = answering([{ kind: 'pick', label: 'warning' }]);
    try {
      await api.pages.attribute.receive({ command: 'row', name: 'severity' });
    } finally {
      session.restore();
    }
    assert.strictEqual(session.left(), 0, JSON.stringify(session.asked));
    await until(() => trust(api).severityDeclared && /warning/i.test(trust(api).severity),
      'the page to say warning');
    // The editor shows what the page now says.
    await until(() => /warning/i.test(api.pages.attribute.panel.webview.html),
      'the editor to show the severity');
    await vscode.commands.executeCommand('workbench.action.closeAllEditors');
  });
});
