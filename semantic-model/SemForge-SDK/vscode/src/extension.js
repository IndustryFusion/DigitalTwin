/*
 * SemForge VS Code extension.
 *
 * This file starts a language server and gets out of the way. Every semantic
 * decision -- what is a violation, which constraint no example exercises, where
 * a property is declared -- is made by the SDK and reaches here as an ordinary
 * LSP message. That is deliberate: the VS Code layer must not become the
 * semantic engine, or the CLI and CI stop agreeing with the editor.
 */

const childProcess = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { LanguageClient, TransportKind } = require('vscode-languageclient/node');

const { findPackageUri } = require('./locate');
const packages = require('./packages');
const projectTree = require('./project');
const cookedTree = require('./tree');
const modelTree = require('./model');
const knowledgeTree = require('./knowledge');
const initPackage = require('./init');
const deleteProject = require('./delete');
const newAttribute = require('./attribute');
const projectCache = require('./cache');
const typePages = require('./typepage');
const vocabularyPages = require('./vocabpage');
const attributeTests = require('./attributetest');
const testCases = require('./testcases');
const casePages = require('./casepage');
const sparqlPage = require('./sparqlpage');
const healthPage = require('./healthpage');
const shapesTree = require('./shapes');
const shapePages = require('./shapepage');
const rename = require('./rename');
const shapeDelete = require('./shapedelete');
const caseDelete = require('./casedelete');
const severity = require('./severity');
const units = require('./units');
const timestamps = require('./timestamps');
const { showLocation } = require('./reveal');

// Shared so the tree provider always talks to the CURRENT client: restarting
// the server must not leave the view wired to a dead one.
const clientHolder = { client: undefined };
let client;
let lastResolved;

/** Every directory from `start` up to the filesystem root. */
function upwards(start) {
  const out = [];
  let here = start;
  for (;;) {
    out.push(here);
    const parent = path.dirname(here);
    if (parent === here) {
      return out;
    }
    here = parent;
  }
}

// Where an SDK venv sits relative to some ancestor directory.
const VENV_PATHS = [
  ['venv', 'bin', 'python'],
  ['venv', 'Scripts', 'python.exe'],
  ['SemForge-SDK', 'venv', 'bin', 'python'],
  ['SemForge-SDK', 'venv', 'Scripts', 'python.exe'],
  ['semantic-model', 'SemForge-SDK', 'venv', 'bin', 'python'],
  ['semantic-model', 'SemForge-SDK', 'venv', 'Scripts', 'python.exe']
];

/**
 * Find a Python that has semforge importable.
 *
 * Searches UPWARD from the opened folder, which is the case that matters: open
 * `kms` and the SDK is a SIBLING, not a child. Looking only downwards meant
 * that opening the package you actually want to work on fell through to the
 * system python3, which has no semforge -- so the server exited and the view
 * showed nothing, with no way to tell that from "there is nothing here".
 */
function resolvePython(startDir) {
  const configured = vscode.workspace
    .getConfiguration('semforge')
    .get('pythonPath');
  if (configured) {
    return { python: configured, source: 'semforge.pythonPath' };
  }
  if (startDir) {
    for (const dir of upwards(startDir)) {
      for (const relative of VENV_PATHS) {
        const candidate = path.join(dir, ...relative);
        if (fs.existsSync(candidate)) {
          return { python: candidate, source: 'found next to the package' };
        }
      }
    }
  }
  return { python: 'python3', source: 'PATH (no SDK venv found)' };
}

/**
 * The SDK directory for an interpreter at <sdk>/venv/bin/python, or undefined.
 *
 * Used as the server's working directory and PYTHONPATH so that an SDK which
 * has not been `pip install -e .`'d still starts. Without it the server is
 * launched in the folder the user opened, where `semforge` is not importable --
 * which fails silently, because a language server that exits immediately looks
 * exactly like one that found nothing to report.
 */
function sdkDirectory(python) {
  const parts = python.split(path.sep);
  const index = parts.lastIndexOf('venv');
  if (index <= 0) {
    return undefined;
  }
  const candidate = parts.slice(0, index).join(path.sep);
  return fs.existsSync(path.join(candidate, 'semforge')) ? candidate : undefined;
}

/**
 * Can this interpreter actually import semforge?
 *
 * Asked before starting the server, because a language server that exits
 * immediately is indistinguishable from one that found nothing to report --
 * which is exactly how this failed.
 */
function canImport(python) {
  try {
    childProcess.execFileSync(python, ['-c', 'import semforge'], {
      stdio: 'ignore',
      timeout: 20000
    });
    return true;
  } catch (error) {
    return false;
  }
}

function startClient(context) {
  const folders = vscode.workspace.workspaceFolders;
  const root = folders && folders.length ? folders[0].uri.fsPath : undefined;
  const resolved = resolvePython(root);
  const python = resolved.python;
  lastResolved = resolved;
  const sdk = sdkDirectory(python);

  if (!canImport(python)) {
    const hint = sdk || '<SemForge-SDK>';
    vscode.window
      .showErrorMessage(
        `SemForge cannot start: ${python} (${resolved.source}) has no ` +
          `\`semforge\` module. Run \`make setup\` in the SDK, or set ` +
          '`semforge.pythonPath`.',
        'Run SemForge: Doctor',
        'Open Settings'
      )
      .then((choice) => {
        if (choice === 'Run SemForge: Doctor') {
          vscode.commands.executeCommand('semforge.doctor');
        } else if (choice === 'Open Settings') {
          vscode.commands.executeCommand(
            'workbench.action.openSettings',
            'semforge.pythonPath'
          );
        }
      });
    return;
  }

  const environment = Object.assign({}, process.env);
  if (sdk) {
    environment.PYTHONPATH = environment.PYTHONPATH
      ? `${sdk}${path.delimiter}${environment.PYTHONPATH}`
      : sdk;
  }

  const serverOptions = {
    command: python,
    args: ['-m', 'semforge.editor.server'],
    transport: TransportKind.stdio,
    options: { cwd: sdk || root, env: environment }
  };

  const clientOptions = {
    // Turtle carries the shapes and the ontology; the model instance is
    // JSON-LD. Opening any of them should activate the package.
    documentSelector: [
      { scheme: 'file', language: 'turtle' },
      { scheme: 'file', pattern: '**/*.ttl' },
      { scheme: 'file', pattern: '**/*.jsonld' },
      // A test case's claims: a stale assert is reported there, and its
      // quick fixes (rename it to what it meant, remove it) are only asked
      // of the server for documents this selector names.
      { scheme: 'file', pattern: '**/expectations.yaml' },
      // The SPARQL workbench's query documents: completion, diagnostics,
      // hover, formatting and quick fixes, from the package's own terms.
      { scheme: 'semforge-sparql', language: 'sparql' }
    ],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher(
        '**/*.{ttl,jsonld,yaml}'
      )
    },
    outputChannelName: 'SemForge'
  };

  client = new LanguageClient(
    'semforge',
    'SemForge Language Server',
    serverOptions,
    clientOptions
  );
  // A shape renamed by typing in the .ttl: the server noticed on save, and
  // what still names the old shape is offered to be carried along.
  if (typeof client.onNotification === 'function') {
    client.onNotification('semforge/shapeRenamed',
      (notice) => rename.offerFollow(clientHolder, notice));
  }
  client.start();
  clientHolder.client = client;
  context.subscriptions.push(client);
}

function activate(context) {
  startClient(context);

  // One answer to "which package is this?", shared by all three views and
  // shown in the status bar. Settled BEFORE the views are built, so each one
  // opens on the same package rather than discovering its own.
  const session = new packages.PackageSession();
  session.discover();
  if (!session.uri) {
    session.follow(vscode.window.activeTextEditor);
  }

  // The constraint view and the model view are two halves of one loop: editing
  // data should refresh the shapes' verdicts and vice versa.
  const constraints = cookedTree.register(context, clientHolder, session);
  const model = modelTree.register(context, clientHolder, session, () =>
    constraints.refresh()
  );
  // The third ingredient, joined to the other two: the shape icon on a class
  // row opens shacl.ttl and shows that shape in the constraint tree, and a
  // usage row shows the entity doing the using in the model tree.
  const knowledge = knowledgeTree.register(
    context,
    clientHolder,
    session,
    (shape) => constraints.revealShape(shape),
    (entity, file) => model.revealEntity(entity, file)
  );

  // Every shape, whatever it targets: a shape is not tied to one type.
  const shapes = shapesTree.register(context, clientHolder, session);

  // What the package IS, above what it says. A setting here changes what the
  // other three mean -- the context decides how a term expands, the entity
  // root decides what counts as an entity -- so a write re-reads them.
  const project = projectTree.register(context, clientHolder, session, () => {
    constraints.refresh();
    shapes.refresh();
    model.refresh();
    knowledge.refresh();
  });

  const refreshAll = () => {
    project.refresh();
    constraints.refresh();
    shapes.refresh();
    model.refresh();
    knowledge.refresh();
  };
  packages.register(
    context, session,
    [project.view, constraints.view, shapes.view, model.view, knowledge.view],
    refreshAll
  );

  // A folder that is not a package yet needs an answer other than three empty
  // trees. Creating one refreshes all three, because it is the first thing
  // they have to show.
  initPackage.register(context, clientHolder, () => {
    session.discover();
    refreshAll();
  });
  // The one gesture that cannot be undone by another gesture.
  deleteProject.register(context, clientHolder, session, refreshAll);
  // Rescan and delete the per-package cache of what the views show.
  projectCache.register(context, clientHolder, session, refreshAll);
  // One page per entity type, in the editor area: read there, find in the trees.
  const typeViews = typePages.register(context, clientHolder, session);
  // One page per vocabulary class: its values, their uses, and their care.
  const vocabularyViews = vocabularyPages.register(context, clientHolder, session);
  // New test… for one attribute: valid, or one of its constraints firing.
  attributeTests.register(context, clientHolder, session);
  // New test case…: add a test file to a suite, from wherever it should start.
  testCases.register(context, clientHolder, session);
  // One page per test case: its claims, whether they hold, its data.
  const caseViews = casePages.register(context, clientHolder, session);
  caseDelete.register(context, clientHolder, session, { case: caseViews });
  severity.register(context, clientHolder, session);
  units.register(context, clientHolder, session);
  timestamps.register(context, clientHolder);
  // A shape's SPARQL query, run over a case's data: where SPARQL constraints
  // are developed.
  const sparqlBench = sparqlPage.register(context, clientHolder, session);
  rename.register(context, clientHolder, session, sparqlBench);
  // The package at a glance: what needs attention first.
  const healthView = healthPage.register(context, clientHolder, session);
  // One page per shape: its target in words, what it checks, what it reaches.
  const shapeViews = shapePages.register(context, clientHolder, session);
  shapeDelete.register(context, clientHolder, session,
    { bench: sparqlBench, shape: shapeViews });

  // Summary or full trees: switching re-asks every tree at once.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('semforge.trees.detail')) {
        refreshAll();
      }
    }),
    // A click opens a row's page; its place in the .ttl/.jsonld is here.
    vscode.commands.registerCommand('semforge.openSource', async (node) => {
      const raw = node && node.raw;
      const at = raw && (raw.definedAt || raw.shapeAt || (raw.file && `${raw.file}:1`));
      if (at) {
        await showLocation(at, true);
      } else if (raw) {
        vscode.window.showInformationMessage(
          `SemForge: ${raw.label} is not written in any one file.`);
      }
    }));
  // Declare an attribute and constrain it, from wherever an extension may put
  // a menu entry -- VS Code gives extensions no top-level menu of their own.
  newAttribute.register(context, clientHolder, session, () => {
    constraints.refresh();
    knowledge.refresh();
    // A deletion takes keys out of the data too.
    model.refresh();
  });

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.doctor', async () => {
      // "I have no clue how to start it" deserves a self-diagnosis, not a
      // search through an output channel.
      const folders = vscode.workspace.workspaceFolders;
      const root = folders && folders.length ? folders[0].uri.fsPath : '(none)';
      const resolved = lastResolved || resolvePython(root === '(none)' ? undefined : root);
      const sdk = sdkDirectory(resolved.python);
      const importable = canImport(resolved.python);

      const channel = vscode.window.createOutputChannel('SemForge Doctor');
      channel.appendLine('SemForge doctor');
      channel.appendLine('');
      channel.appendLine(`opened folder   ${root}`);
      channel.appendLine(`interpreter     ${resolved.python}`);
      channel.appendLine(`  chosen via    ${resolved.source}`);
      channel.appendLine(`  imports semforge: ${importable ? 'yes' : 'NO'}`);
      channel.appendLine(`SDK directory   ${sdk || '(not found)'}`);
      channel.appendLine(`language client ${client ? 'started' : 'not started'}`);
      const found = session.uri || findPackageUri();
      channel.appendLine(`package         ${found || '(none found in this folder or one level below)'}`);
      channel.appendLine(`  chosen by     ${session.pinned ? 'you (pinned)' : 'the opened folder / active editor'}`);
      for (const entry of require('./locate').listPackages()) {
        channel.appendLine(`  also here     ${entry.directory}`);
      }

      // What the RUNNING server can answer. An extension newer than the server
      // shows its new icons and its new view, and every one of them does
      // nothing -- which is indistinguishable from the feature being broken.
      if (client) {
        try {
          const reported = await client.sendRequest('semforge/methods', {});
          channel.appendLine(`server code     ${reported.module}`);
          channel.appendLine(`server methods  ${(reported.methods || []).join(', ')}`);
          const missing = ['semforge/knowledge', 'semforge/shapeFor',
                           'semforge/valueChoices', 'semforge/project',
                           'semforge/entityTypes', 'semforge/attributes']
            .filter((name) => !(reported.methods || []).includes(name));
          if (missing.length) {
            channel.appendLine('');
            channel.appendLine(`This server is OLDER than the extension: it cannot answer ${missing.join(', ')}.`);
            channel.appendLine('Run "SemForge: Restart Language Server", or reload the window.');
          }
        } catch (error) {
          channel.appendLine('server methods  (the server did not answer ' +
            'semforge/methods — it predates this extension entirely)');
        }
      }
      channel.appendLine('');
      if (!importable) {
        channel.appendLine('To fix:');
        channel.appendLine(`  cd ${sdk || '<repo>/semantic-model/SemForge-SDK'}`);
        channel.appendLine('  make setup');
        channel.appendLine('  then: Developer: Reload Window');
      } else {
        channel.appendLine('A package is any directory holding knowledge.ttl,');
        channel.appendLine('shacl.ttl and model-instance.jsonld. Open a file');
        channel.appendLine('inside one; diagnostics arrive on open and on save.');
      }
      channel.show(true);
    }),

    vscode.commands.registerCommand('semforge.restart', async () => {
      if (client) {
        await client.stop();
      }
      startClient(context);
      vscode.window.showInformationMessage('SemForge language server restarted');
    })
  );

  // Revalidation is a save in disguise: the server analyses the whole package
  // on save, so this just re-triggers it for the active file.
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.revalidate', async () => {
      const editor = vscode.window.activeTextEditor;
      if (editor) {
        await editor.document.save();
      }
    })
  );

  // For the end-to-end tests (test/e2e), which run in a real VS Code: what
  // they inspect after driving it. Nothing in the extension reads this.
  return {
    clientHolder,
    session,
    trees: { project, constraints, shapes, model, knowledge },
    pages: { type: typeViews, case: caseViews, sparql: sparqlBench, shape: shapeViews,
      vocabulary: vocabularyViews, health: healthView }
  };
}

function deactivate() {
  return client ? client.stop() : undefined;
}

module.exports = { activate, deactivate };
