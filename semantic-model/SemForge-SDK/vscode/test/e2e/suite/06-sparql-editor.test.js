// The SPARQL editor in a real VS Code: the query opens as its own document
// (language sparql), and the language server completes, checks, explains and
// formats it; Ctrl+S saves it into shacl.ttl, Ctrl+Enter applies it.

const assert = require('assert');
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { PACKAGE_URI, WORKSPACE, semforge, until, read } = require('./helpers');

const BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/';
const SHAPE = `${BASE}StateOnFilterShape`;
const ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/';

async function openQuery(api) {
  await vscode.commands.executeCommand('semforge.openSparqlBench',
    { raw: { shape: SHAPE }, packageUri: PACKAGE_URI }, {});
  await until(() => api.pages.sparql.page && api.pages.sparql.page.shape === SHAPE,
    'the workbench on StateOnFilterShape');
  return until(() => api.pages.sparql.document(), 'the query document');
}

async function setText(doc, text) {
  const edit = new vscode.WorkspaceEdit();
  edit.replace(doc.uri, new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length)),
    text);
  await vscode.workspace.applyEdit(edit);
}

async function revert(doc) {
  if (doc.isDirty) {
    await vscode.window.showTextDocument(doc, { preview: false });
    await vscode.commands.executeCommand('workbench.action.files.revert');
  }
}

function at(doc, text, needle, shift = 0) {
  return doc.positionAt(text.indexOf(needle) + needle.length + shift);
}

const HEAD = `PREFIX ngsild: <https://uri.etsi.org/ngsi-ld/>\n`;

describe('the SPARQL editor', () => {
  it('opens the query as a SPARQL document with the saved text', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    assert.strictEqual(doc.uri.scheme, 'semforge-sparql');
    assert.strictEqual(doc.languageId, 'sparql');
    assert.strictEqual(doc.getText(), api.pages.sparql.page.holder.query);
    assert.ok(vscode.window.visibleTextEditors.some((e) => e.document === doc),
      'shown in an editor beside the page');
    assert.strictEqual(doc.isDirty, false);
  });

  it('completes a namespace\'s terms, and declares the prefix', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    const text = `${HEAD}SELECT $this WHERE {\n    $this iffBaseEntities:has`;
    await setText(doc, text);
    try {
      const list = await until(async () => {
        const got = await vscode.commands.executeCommand('vscode.executeCompletionItemProvider',
          doc.uri, doc.positionAt(text.length));
        return got && got.items.length && got;
      }, 'completion');
      const state = list.items.find((i) => (i.label.label || i.label) === 'iffBaseEntities:hasState');
      assert.ok(state, list.items.map((i) => i.label.label || i.label).slice(0, 20).join(', '));
      assert.strictEqual(state.detail, 'Property · on iffBaseEntities:Machine');
      assert.ok((state.additionalTextEdits || []).some((e) =>
        e.newText.startsWith('PREFIX iffBaseEntities:')), 'the prefix gets declared');
      const step = list.items.find((i) =>
        String(i.label.label || i.label).startsWith('iffBaseEntities:hasCartridge ['));
      assert.ok(step, 'the NGSI-LD step for a Relationship');
      assert.match(step.insertText.value || String(step.insertText), /ngsild:hasObject/);
    } finally {
      await revert(doc);
    }
  });

  it('marks a typo, says what was meant, and fixes it', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    const text = `${HEAD}PREFIX iffBaseEntities: <${ENT}>\n` +
      'SELECT $this WHERE { $this iffBaseEntities:hasStat [ ngsild:hasValue ?v ] }';
    await setText(doc, text);
    try {
      const found = await until(() => vscode.languages.getDiagnostics(doc.uri)
        .find((d) => d.message.includes('did you mean')), 'the typo diagnostic');
      assert.match(found.message, /did you mean iffBaseEntities:hasState\?/);
      assert.strictEqual(found.severity, vscode.DiagnosticSeverity.Warning);
      const actions = await vscode.commands.executeCommand('vscode.executeCodeActionProvider',
        doc.uri, found.range);
      const fix = actions.find((a) => a.title === 'Change to iffBaseEntities:hasState');
      assert.ok(fix, actions.map((a) => a.title).join(', '));
      await vscode.workspace.applyEdit(fix.edit);
      assert.ok(doc.getText().includes('iffBaseEntities:hasState ['));
      await until(() => !vscode.languages.getDiagnostics(doc.uri)
        .some((d) => d.message.includes('did you mean')), 'the squiggle to go');
    } finally {
      await revert(doc);
    }
  });

  it('a missing PREFIX is an error with a quick fix', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    const text = 'SELECT $this WHERE { $this base:x ?y }';
    await setText(doc, text);
    try {
      const found = await until(() => vscode.languages.getDiagnostics(doc.uri)
        .find((d) => d.message.includes('base: is not declared')), 'the prefix diagnostic');
      assert.strictEqual(found.severity, vscode.DiagnosticSeverity.Error);
      const actions = await vscode.commands.executeCommand('vscode.executeCodeActionProvider',
        doc.uri, found.range);
      const add = actions.find((a) => a.title.startsWith('Add PREFIX base:'));
      await vscode.workspace.applyEdit(add.edit);
      assert.match(doc.getText(), /^PREFIX base: <https:\/\/industryfusion/);
    } finally {
      await revert(doc);
    }
  });

  it('hover shows a name\'s IRI and what it is', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    const text = doc.getText();
    const needle = 'iffBaseEntities:hasState';
    assert.ok(text.includes(needle), 'the saved query reads hasState');
    const hovers = await vscode.commands.executeCommand('vscode.executeHoverProvider',
      doc.uri, at(doc, text, needle, -3));
    const said = hovers.flatMap((h) => h.contents.map((c) => c.value || String(c))).join('\n');
    assert.match(said, /\*\*hasState\*\* · Property/);
    assert.ok(said.includes(`<${ENT}hasState>`));
  });

  it('Format Document lays the query out, and keeps its meaning', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    const squashed = `${HEAD}select $this where{$this ?p ?o.filter(?o!=1)}`;
    await setText(doc, squashed);
    try {
      const edits = await vscode.commands.executeCommand('vscode.executeFormatDocumentProvider',
        doc.uri, { tabSize: 4, insertSpaces: true });
      assert.ok(edits && edits.length, 'the formatter answered');
      const edit = new vscode.WorkspaceEdit();
      edit.set(doc.uri, edits);
      await vscode.workspace.applyEdit(edit);
      assert.strictEqual(doc.getText(), `${HEAD}\nSELECT $this\nWHERE {\n    $this ?p ?o .\n` +
        '    FILTER(?o != 1)\n}\n');
    } finally {
      await revert(doc);
    }
  });

  it('Ctrl+Enter applies the editor\'s text; Ctrl+S saves it into shacl.ttl', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    await vscode.window.showTextDocument(doc, { preview: false });
    const posted = [];
    const post = api.pages.sparql.post.bind(api.pages.sparql);
    api.pages.sparql.post = (message) => { posted.push(message); post(message); };
    try {
      const saved = doc.getText();
      const edited = saved.replace('FILTER(', '# kept by the editor\n    FILTER(');
      await setText(doc, edited);
      await vscode.commands.executeCommand('semforge.sparqlApply');
      const result = await until(() => posted.find((m) => m.type === 'result'), 'Apply');
      assert.ok(result.result.ok, JSON.stringify(result.result));
      assert.ok(await doc.save(), 'saved');
      assert.match(read('shacl.ttl'), /# kept by the editor/);
      assert.strictEqual(doc.isDirty, false);
      await until(() => posted.find((m) => m.type === 'saved'), 'the page told');
    } finally {
      api.pages.sparql.post = post;
    }
  });

  it('inside an attribute\'s [ ] the payload of its kind comes first', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    const text = `${HEAD}PREFIX iffBaseEntities: <${ENT}>\n` +
      'SELECT $this WHERE { $this iffBaseEntities:hasFilter [ ';
    await setText(doc, text);
    try {
      const list = await vscode.commands.executeCommand('vscode.executeCompletionItemProvider',
        doc.uri, doc.positionAt(text.length));
      const labels = list.items.map((i) => i.label.label || i.label);
      assert.ok(labels.includes('ngsild:hasObject ?filter'), labels.slice(0, 8).join(', '));
      const first = list.items.find((i) => (i.label.label || i.label) === 'ngsild:hasObject ?filter');
      assert.strictEqual(first.sortText.slice(0, 1), '0', 'ranked first');
      assert.ok(labels.some((l) => String(l).startsWith('iffBaseEntities:hasTrust [')),
        'its sub-attribute, as a step');
    } finally {
      await revert(doc);
    }
  });

  it('a value read without its instance is marked, and fixed in one click', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    const text = `${HEAD}PREFIX iffBaseEntities: <${ENT}>\n` +
      'SELECT $this WHERE { $this iffBaseEntities:hasStrength ?s . FILTER(?s > 1) }';
    await setText(doc, text);
    try {
      const found = await until(() => vscode.languages.getDiagnostics(doc.uri)
        .find((d) => d.code === 'skipped-layer'), 'the skipped-layer warning');
      assert.match(found.message, /\?s is the attribute instance of iffBaseEntities:hasStrength/);
      const actions = await vscode.commands.executeCommand('vscode.executeCodeActionProvider',
        doc.uri, found.range);
      const fix = actions.find((a) => a.title === 'Read the value: [ ngsild:hasValue ?s ]');
      assert.ok(fix, actions.map((a) => a.title).join(', '));
      await vscode.workspace.applyEdit(fix.edit);
      assert.ok(doc.getText().includes('iffBaseEntities:hasStrength [ ngsild:hasValue ?s ] .'));
      await until(() => !vscode.languages.getDiagnostics(doc.uri)
        .some((d) => d.code === 'skipped-layer'), 'the warning to go');
    } finally {
      await revert(doc);
    }
  });

  it('a new attribute Flink cannot read yet gets its shape, and the warning goes', async () => {
    const api = await semforge();
    // Declared in the knowledge, as a Property of Cutter -- with no shape yet.
    fs.appendFileSync(path.join(WORKSPACE, 'knowledge.ttl'),
      '\niffBaseEntities:hasHumidity a owl:DatatypeProperty ;\n' +
      '    rdfs:domain iffBaseEntities:Cutter ;\n' +
      '    rdfs:range <https://uri.etsi.org/ngsi-ld/Property> .\n');
    const doc = await openQuery(api);
    const text = `${HEAD}PREFIX iffBaseEntities: <${ENT}>\n` +
      'SELECT $this WHERE { $this iffBaseEntities:hasHumidity [ ngsild:hasValue ?h ] }';
    await setText(doc, text);
    try {
      const found = await until(() => vscode.languages.getDiagnostics(doc.uri)
        .find((d) => d.code === 'not-compiled'), 'the not-compiled warning');
      const actions = await vscode.commands.executeCommand('vscode.executeCodeActionProvider',
        doc.uri, found.range);
      const fix = actions.find((a) => a.command && a.command.command === 'semforge.nestForFlink');
      assert.ok(fix, actions.map((a) => a.title).join(', '));
      const made = await vscode.commands.executeCommand(fix.command.command,
        ...fix.command.arguments);
      assert.ok(made && made.ok, JSON.stringify(made));
      assert.match(read('shacl.ttl'), /sh:path iffBaseEntities:hasHumidity[^\]]*ngsild:hasValue/s);
      await until(() => !vscode.languages.getDiagnostics(doc.uri)
        .some((d) => d.code === 'not-compiled'), 'the warning to go once the shape is there');
    } finally {
      await revert(doc);
    }
  });

  it('a save over a changed literal fails, and the edit stays', async () => {
    const api = await semforge();
    const doc = await openQuery(api);
    // Someone else changes the query in shacl.ttl behind the editor's back.
    const behind = api.pages.sparql.files.saved.get(doc.uri.toString());
    api.pages.sparql.files.saved.set(doc.uri.toString(), `${behind}# not what the file says`);
    await setText(doc, `${doc.getText()}\n# mine`);
    try {
      const ok = await doc.save().then((r) => r, () => false);
      assert.strictEqual(ok, false, 'refused');
      assert.strictEqual(doc.isDirty, true, 'the edit is kept');
      assert.ok(!read('shacl.ttl').includes('# mine'));
    } finally {
      api.pages.sparql.files.saved.set(doc.uri.toString(), behind);
      await revert(doc);
    }
  });
});
