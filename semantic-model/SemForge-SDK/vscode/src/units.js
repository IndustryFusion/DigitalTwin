/*
 * Units -- NGSI-LD's unitCode, a UN/CEFACT Rec 20 common code (CEL, BAR).
 *
 * One picker everywhere a unit is chosen: each code with its name, symbol and
 * the quantity it measures, so typing "temperature" or "celsius" finds CEL --
 * the quick pick filters on all three. The units a shape allows come first.
 * A code the curated set lacks is added as one of the package's own (New
 * unit…), a qudt:Unit in its knowledge.
 */

const vscode = require('vscode');
const { pickVocabularyNamespace } = require('./namespacepick');

const SEPARATOR = vscode.QuickPickItemKind ? vscode.QuickPickItemKind.Separator : -1;
const CODE = /^[A-Za-z0-9]{1,3}$/;

async function ask(client, method, params) {
  const answer = await client.sendRequest(method, params);
  if (!answer || !answer.ok) {
    vscode.window.showErrorMessage(`SemForge: ${(answer && answer.error) || 'no answer'}`);
    return undefined;
  }
  return answer;
}

function item(unit, picked) {
  return {
    label: unit.code,
    description: [unit.name, unit.symbol].filter(Boolean).join(' · '),
    detail: `${unit.quantityLabel || 'no quantity'}${unit.builtin ? '' : ' · the package\'s own'}`,
    picked: Boolean(picked), unit
  };
}

/**
 * Pick a unit (or, with `options.many`, several). `options`: title,
 * allowed (codes the shape allows, offered first), current (the code(s) now),
 * none (offer "No unit"). Returns a code, '' for no unit, a list with
 * `many`, or undefined when cancelled.
 */
async function pickUnit(client, packageUri, options) {
  const offered = await ask(client, 'semforge/units', { uri: packageUri });
  if (!offered) {
    return undefined;
  }
  const allowed = options.allowed || [];
  const current = [].concat(options.current || []);
  const items = [];
  if (options.none && !options.many) {
    items.push({ label: 'No unit', description: 'no unitCode', none: true });
  }
  const first = offered.units.filter((u) => allowed.includes(u.code));
  if (first.length) {
    items.push({ label: 'Allowed by the shape', kind: SEPARATOR },
      ...first.map((u) => item(u, current.includes(u.code))));
    items.push({ label: 'Every unit', kind: SEPARATOR });
  }
  items.push(...offered.units.filter((u) => !allowed.includes(u.code))
    .map((u) => item(u, current.includes(u.code))));
  if (!options.many) {
    items.push({ label: '', kind: SEPARATOR },
      { label: '$(add) New unit…', description: 'a code the curated set does not have', create: true });
  }
  const picked = await vscode.window.showQuickPick(items, {
    title: options.title,
    placeHolder: 'Search by code, name or quantity — "temperature", "celsius", "CEL"',
    matchOnDescription: true, matchOnDetail: true, canPickMany: Boolean(options.many)
  });
  if (!picked) {
    return undefined;
  }
  if (options.many) {
    return picked.map((p) => p.unit.code);
  }
  if (picked.none) {
    return '';
  }
  if (picked.create) {
    const made = await newUnit(client, packageUri, {});
    return made ? made.code : undefined;
  }
  return picked.unit.code;
}

/** A unit of the package's own: code, name, symbol, quantity, namespace. */
async function newUnit(client, packageUri, preset) {
  const code = await vscode.window.showInputBox({
    title: 'New unit: its UN/CEFACT common code',
    prompt: 'One to three letters or digits, e.g. CEL', value: (preset && preset.code) || '',
    validateInput: (text) => (CODE.test(text.trim()) ? undefined : 'one to three letters or digits')
  });
  if (!code) {
    return undefined;
  }
  const name = await vscode.window.showInputBox({
    title: `${code.trim().toUpperCase()}: its name`, prompt: 'e.g. degree Celsius',
    validateInput: (text) => (text.trim() ? undefined : 'a unit has a name')
  });
  if (!name) {
    return undefined;
  }
  const symbol = await vscode.window.showInputBox({
    title: `${code.trim().toUpperCase()}: its symbol (optional)`, prompt: 'e.g. °C'
  });
  if (symbol === undefined) {
    return undefined;
  }
  const offered = await ask(client, 'semforge/units', { uri: packageUri });
  if (!offered) {
    return undefined;
  }
  const quantity = await vscode.window.showQuickPick(
    offered.quantities.map((q) => ({ label: q, value: q }))
      .concat([{ label: '$(edit) Another quantity…', other: true }]),
    { title: `${code.trim().toUpperCase()} measures…`, placeHolder: 'the quantity, as QUDT names it' });
  if (!quantity) {
    return undefined;
  }
  let kind = quantity.value;
  if (quantity.other) {
    kind = await vscode.window.showInputBox({
      title: 'The quantity', prompt: 'e.g. Temperature, VolumeFlowRate',
      validateInput: (text) => (/^[A-Za-z][A-Za-z0-9 ]*$/.test(text.trim()) ? undefined
        : 'letters and digits, e.g. VolumeFlowRate')
    });
    if (!kind) {
      return undefined;
    }
  }
  const namespace = await pickVocabularyNamespace(client, packageUri,
    code.trim().toUpperCase(), '');
  if (namespace === undefined) {
    return undefined;
  }
  const made = await ask(client, 'semforge/addUnit', {
    uri: packageUri, code: code.trim().toUpperCase(), name: name.trim(),
    symbol: symbol.trim(), quantity: kind.trim(), namespace: namespace || null
  });
  if (made) {
    vscode.commands.executeCommand('semforge.refreshKnowledge');
  }
  return made;
}

/** Which units an attribute's instances may say, in its shape: Unit… on a
 *  type page or shape page row. */
async function editUnits(client, packageUri, row) {
  const now = await ask(client, 'semforge/units',
    { uri: packageUri, shape: row.shape, path: row.path });
  if (!now) {
    return false;
  }
  const codes = await pickUnit(client, packageUri, {
    title: `${row.label}: which units may its instances say? None removes the constraint`,
    allowed: now.allowed, current: now.allowed, many: true
  });
  if (codes === undefined) {
    return false;
  }
  let required = false;
  if (codes.length) {
    const presence = await vscode.window.showQuickPick([
      { label: 'Optional', description: 'an instance may say no unit', value: false },
      { label: 'Required', description: 'every instance says one (sh:minCount 1)', value: true }
    ], { title: `${row.label}: is a unit required?${now.required ? ' Now required' : ''}` });
    if (!presence) {
      return false;
    }
    required = presence.value;
  }
  return Boolean(await ask(client, 'semforge/setUnits',
    { uri: packageUri, shape: row.shape, path: row.path, codes, required }));
}

/** The unitCode of one instance in the data -- a tree or case page row, or
 *  the unit-unknown quick fix. */
async function setUnitCode(client, node) {
  const raw = (node && node.raw) || node || {};
  const packageUri = (node && node.packageUri) || raw.packageUri;
  if (!raw.entity || !raw.attributePath) {
    return false;
  }
  let allowed = [];
  if (raw.entityType) {
    const shaped = await client.sendRequest('semforge/units', { uri: packageUri,
      entityType: raw.entityType, attribute: raw.attributePath[raw.attributePath.length - 1] });
    allowed = (shaped && shaped.allowed) || [];
  }
  const name = String(raw.attributePath[raw.attributePath.length - 1]).split(/[:/#]/).pop();
  const code = await pickUnit(client, packageUri, {
    title: `Unit of ${raw.label || name} on ${raw.entity}`, allowed,
    current: raw.current || raw.unitCode || '', none: true
  });
  if (code === undefined) {
    return false;
  }
  const dataset = raw.datasetId && raw.datasetId !== '@none' ? raw.datasetId : '';
  return Boolean(await ask(client, 'semforge/setUnitCode', {
    uri: packageUri, entity: raw.entity, attributePath: raw.attributePath,
    datasetId: dataset, code, file: raw.file
  }));
}

function register(context, clientHolder, session) {
  const refresh = () => {
    for (const command of ['semforge.refreshTree', 'semforge.refreshModel',
      'semforge.refreshKnowledge', 'semforge.refreshShapes']) {
      vscode.commands.executeCommand(command);
    }
  };
  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.findUnit', async (node) => {
      const packageUri = (node && node.packageUri) || session.uri;
      const code = await pickUnit(clientHolder.client, packageUri, { title: 'Find a unit' });
      if (code) {
        if (vscode.env && vscode.env.clipboard) {
          await vscode.env.clipboard.writeText(code);
        }
        vscode.window.setStatusBarMessage(`SemForge: ${code} copied`, 4000);
      }
    }),
    vscode.commands.registerCommand('semforge.newUnit', async (node) => {
      const made = await newUnit(clientHolder.client,
        (node && node.packageUri) || session.uri, node || {});
      if (made) {
        vscode.window.setStatusBarMessage(`SemForge: ${made.code} — ${made.name}`, 5000);
        refresh();
      }
    }),
    vscode.commands.registerCommand('semforge.setUnitCode', async (node) => {
      if (await setUnitCode(clientHolder.client, node)) {
        refresh();
      }
    })
  );
}

module.exports = { register, pickUnit, newUnit, editUnits, setUnitCode };
