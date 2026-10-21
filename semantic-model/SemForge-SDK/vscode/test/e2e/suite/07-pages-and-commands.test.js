// Every page opens and renders in a real VS Code, the server can be
// restarted and the package revalidated, and the SPARQL workbench's own
// flows -- Inspect from its key, Revert, a snapshot loaded back -- work on
// the real editor.

const assert = require('assert');
const path = require('path');
const vscode = require('vscode');
const { PACKAGE_URI, WORKSPACE, semforge, request, until, answering } = require('./helpers');

const BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/';
const KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/';

/** The page's body text, without its markup: an error page says "SemForge:". */
function body(panel) {
  return panel.webview.html.replace(/<style[\s\S]*?<\/style>|<script[\s\S]*?<\/script>/g, '')
    .replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
}

async function rendered(pages, what) {
  return until(() => pages.panel && pages.panel.webview.html.includes('<h1') && pages.panel,
    what);
}

describe('every page, in a real VS Code', () => {
  it('a shape page', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openShapePage',
      { raw: { shape: `${BASE}WorkpieceShape` }, packageUri: PACKAGE_URI });
    const panel = await rendered(api.pages.shape, 'the shape page');
    assert.strictEqual(panel.title, 'WorkpieceShape · shape');
    const text = body(panel);
    for (const part of ['Checks', 'Applies to', 'Tested by', '+ Add check ▾', 'Edit targets']) {
      assert.ok(text.includes(part), part);
    }
  });

  it("a shape page's ⋯ opens its .ttl", async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openShapePage',
      { raw: { shape: `${BASE}WorkpieceShape` }, packageUri: PACKAGE_URI });
    await rendered(api.pages.shape, 'the shape page');
    const session = answering([{ kind: 'pick', labelStarts: '$(go-to-file) Open in .ttl' }]);
    try {
      await api.pages.shape.receive({ command: 'pageMenu', row: -1 });
    } finally {
      session.restore();
    }
    assert.ok(session.asked[0].offered.some((label) => label.includes('Merge into…')));
    const editor = await until(() => vscode.window.activeTextEditor &&
      vscode.window.activeTextEditor.document.fileName.endsWith('shacl.ttl') &&
      vscode.window.activeTextEditor, 'shacl.ttl');
    assert.ok(editor.document.lineAt(editor.selection.active.line).text.includes('WorkpieceShape'),
      editor.document.lineAt(editor.selection.active.line).text);
  });

  it('the package health page', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openHealthPage', { packageUri: PACKAGE_URI });
    const panel = await until(() => api.pages.health.panel &&
      api.pages.health.panel.webview.html.length > 500 && api.pages.health.panel, 'health');
    assert.ok(!/SemForge: (?!.*health)/i.test(body(panel).slice(0, 80)), body(panel).slice(0, 200));
  });

  it('a vocabulary page', async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openVocabularyPage',
      { packageUri: PACKAGE_URI }, { cls: `${KNOW}MachineState` });
    const panel = await rendered(api.pages.vocabulary, 'the vocabulary page');
    const text = body(panel);
    assert.ok(text.includes('state_ON'), text.slice(0, 300));
    assert.ok(text.includes('valid for Machine'), 'a property as a reader says it');
    assert.ok(text.includes('drawn from by'), text.slice(0, 300));
  });

  it("a vocabulary value's type opens its type page", async () => {
    const api = await semforge();
    await vscode.commands.executeCommand('semforge.openVocabularyPage',
      { packageUri: PACKAGE_URI }, { cls: `${KNOW}MachineState` });
    await rendered(api.pages.vocabulary, 'the vocabulary page');
    const on = api.pages.vocabulary.page.values.find((v) => v.name === 'state_ON');
    const type = on.properties.find((p) => p.type).type;
    await api.pages.vocabulary.receive({ command: 'type', iri: type });
    await until(() => api.pages.type.page && api.pages.type.page.iri === type, 'its type page');
  });
});

describe('the server and the package', () => {
  it('Restart Language Server brings a server that answers', async () => {
    const api = await semforge();
    const before = api.clientHolder.client;
    await vscode.commands.executeCommand('semforge.restart');
    await until(() => api.clientHolder.client && api.clientHolder.client !== before,
      'a new client');
    const answer = await until(() => request(api, 'semforge/methods', {}).then((a) => a.methods),
      'the restarted server to answer');
    assert.ok(answer.includes('semforge/sparqlBench'));
  });

  it('Revalidate saves the active file, and nothing breaks', async () => {
    const api = await semforge();
    const doc = await vscode.workspace.openTextDocument(path.join(WORKSPACE, 'shacl.ttl'));
    await vscode.window.showTextDocument(doc, { preview: false });
    await vscode.commands.executeCommand('semforge.revalidate');
    assert.strictEqual(doc.isDirty, false);
    assert.ok((await request(api, 'semforge/methods', {})).methods);
  });
});

describe('the SPARQL workbench on the real editor', () => {
  const SHAPE = `${BASE}StateOnFilterShape`;

  async function open(api) {
    await vscode.commands.executeCommand('semforge.openSparqlBench',
      { raw: { shape: SHAPE }, packageUri: PACKAGE_URI }, {});
    await until(() => api.pages.sparql.page && api.pages.sparql.page.shape === SHAPE, 'bench');
    const doc = await until(() => api.pages.sparql.document(), 'its document');
    await vscode.window.showTextDocument(doc, { preview: false });
    return doc;
  }

  async function setText(doc, text) {
    const edit = new vscode.WorkspaceEdit();
    edit.replace(doc.uri, new vscode.Range(doc.positionAt(0),
      doc.positionAt(doc.getText().length)), text);
    await vscode.workspace.applyEdit(edit);
  }

  function recording(bench) {
    const posted = [];
    const post = bench.post.bind(bench);
    bench.post = (message) => { posted.push(message); post(message); };
    return { posted, stop: () => { bench.post = post; } };
  }

  it('Ctrl+Shift+Enter inspects the query in the editor', async () => {
    const api = await semforge();
    await open(api);
    const watch = recording(api.pages.sparql);
    try {
      await vscode.commands.executeCommand('semforge.sparqlInspect');
      const got = await until(() => watch.posted.find((m) => m.type === 'inspect'), 'Inspect');
      assert.ok(got.result.ok, JSON.stringify(got.result));
      assert.ok(got.result.columns.includes('this'));
    } finally {
      watch.stop();
    }
  });

  it("the ⋯ shows the query's place in shacl.ttl", async () => {
    const api = await semforge();
    await open(api);
    const session = answering([{ kind: 'pick', labelStarts: '$(go-to-file) Show it in shacl.ttl' }]);
    try {
      await api.pages.sparql.receive({ command: 'menu' });
    } finally {
      session.restore();
    }
    const labels = session.asked[0].offered;
    assert.ok(labels[labels.length - 1].startsWith('$(trash) Remove this'), labels.join(', '));
    const holder = api.pages.sparql.page.holder;
    const editor = await until(() => vscode.window.activeTextEditor &&
      vscode.window.activeTextEditor.document.fileName.endsWith('shacl.ttl') &&
      vscode.window.activeTextEditor, 'shacl.ttl');
    assert.strictEqual(editor.selection.active.line, holder.line - 1);
  });

  it('Cancel reverts the editor to what shacl.ttl holds', async () => {
    const api = await semforge();
    const doc = await open(api);
    const saved = doc.getText();
    await setText(doc, `${saved}\n# an experiment`);
    assert.ok(doc.isDirty);
    assert.strictEqual(await api.pages.sparql.receive({ command: 'cancel' }), true);
    await until(() => !doc.isDirty, 'clean again');
    assert.strictEqual(doc.getText(), saved);
  });

  it('a snapshot loads back into the editor', async () => {
    const api = await semforge();
    const doc = await open(api);
    const saved = doc.getText();
    const session = answering([{ kind: 'input', value: 'kept' }]);
    let entry;
    try {
      entry = await api.pages.sparql.receive({ command: 'snapshot' });
    } finally {
      session.restore();
    }
    await setText(doc, `${saved}\n# changed after the snapshot`);
    await api.pages.sparql.receive({ command: 'loadSnapshot', id: entry.id });
    assert.strictEqual(doc.getText(), saved);
    await api.pages.sparql.receive({ command: 'cancel' });
    api.pages.sparql.deleteSnapshot(entry.id);
  });
});
