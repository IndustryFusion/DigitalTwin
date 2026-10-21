/*
 * Timestamps -- NGSI-LD's observedAt -- picked rather than typed.
 *
 * Never asked by default: an instance without one counts as now, as on the
 * platform, where the bridge stamps it with the time it arrives. When one is
 * wanted -- an imported series, a second observation of one datasetId -- it
 * is chosen here: Now, Just after the latest, or a time of your own (any ISO
 * 8601 with its zone, written in the kms form 2024-02-28T13:52:35.000Z).
 * The case page has a date-and-time picker of its own (casepage.js).
 */

const vscode = require('vscode');

const STAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$/;

/** A Date in the kms form: 2024-02-28T13:52:35.000Z. */
function canonical(date) {
  return date.toISOString();
}

/** What is wrong with a typed timestamp, or undefined. */
function problem(text) {
  const value = String(text || '').trim();
  if (!STAMP.test(value) || Number.isNaN(Date.parse(value))) {
    return 'ISO 8601 with its zone, e.g. 2024-02-28T13:52:35.000Z or 2024-02-28T14:52:35+01:00';
  }
  return undefined;
}

/**
 * Pick a timestamp. options: title, current (the instance's now, if any),
 * latest (its datasetId's latest, for "Just after"), removable. Returns the
 * stamp in the kms form, '' to remove it, or undefined when cancelled.
 */
async function pickStamp(options) {
  const items = [{ label: '$(clock) Now', description: canonical(new Date()), stamp: 'now' }];
  if (options.latest) {
    const after = new Date(Date.parse(options.latest) + 1);
    items.push({ label: '$(arrow-right) Just after the latest', description: canonical(after),
      stamp: canonical(after) });
  }
  items.push({ label: '$(calendar) A time of your own…', description: 'ISO 8601 with its zone',
    custom: true });
  if (options.current && options.removable !== false) {
    items.push({ label: '$(circle-slash) No timestamp',
      description: 'it then counts as now, as on the platform', stamp: '' });
  }
  const picked = await vscode.window.showQuickPick(items, {
    title: options.title || 'observedAt',
    placeHolder: options.current ? `Now ${options.current}` : 'When it was observed (UTC)'
  });
  if (!picked) {
    return undefined;
  }
  if (picked.stamp === 'now') {
    return canonical(new Date());
  }
  if (!picked.custom) {
    return picked.stamp;
  }
  const typed = await vscode.window.showInputBox({
    title: options.title || 'observedAt',
    prompt: 'ISO 8601 with its zone; written as 2024-02-28T13:52:35.000Z (UTC)',
    value: options.current || canonical(new Date()),
    validateInput: problem
  });
  return typed === undefined ? undefined : canonical(new Date(Date.parse(typed.trim())));
}

/** The instance a tree row or a quick fix stands for: {entity,
 *  attributePath, index, file}. A row's `path` ends with its index. */
function instanceOf(raw) {
  const path = raw.path || [];
  const last = path[path.length - 1];
  return {
    entity: raw.entity, file: raw.file,
    attributePath: raw.attributePath || path.slice(0, -1),
    index: raw.index !== undefined ? raw.index : (typeof last === 'number' ? last : 0)
  };
}

function register(context, clientHolder) {
  const refresh = () => {
    for (const command of ['semforge.refreshTree', 'semforge.refreshModel']) {
      vscode.commands.executeCommand(command);
    }
  };
  const send = async (method, params) => {
    const answer = await clientHolder.client.sendRequest(method, params);
    if (!answer || !answer.ok) {
      vscode.window.showErrorMessage(`SemForge: ${(answer && answer.error) || 'not written'}`);
      return undefined;
    }
    refresh();
    return answer;
  };
  context.subscriptions.push(
    // A row's (or a quick fix's) instance: its observedAt set, changed or taken away.
    vscode.commands.registerCommand('semforge.setObservedAt', async (node) => {
      const raw = (node && node.raw) || node || {};
      const where = instanceOf(raw);
      if (!where.entity || !where.attributePath.length) {
        return undefined;
      }
      let stamp = raw.observedAt;
      if (stamp === undefined) {
        const name = String(where.attributePath[where.attributePath.length - 1])
          .split(/[:/#]/).pop();
        stamp = await pickStamp({ title: `observedAt of ${raw.label || name} on ${where.entity}`,
          current: raw.current, latest: raw.latest });
        if (stamp === undefined) {
          return undefined;
        }
      }
      return send('semforge/setObservedAt', Object.assign(
        { uri: (node && node.packageUri) || raw.packageUri, observedAt: stamp }, where));
    }),
    vscode.commands.registerCommand('semforge.sortObservations', async (node) => {
      const raw = (node && node.raw) || node || {};
      return send('semforge/sortObservations', {
        uri: (node && node.packageUri) || raw.packageUri, entity: raw.entity,
        attributePath: raw.attributePath, datasetId: raw.datasetId || '', file: raw.file });
    })
  );
}

module.exports = { register, pickStamp, problem, canonical };
