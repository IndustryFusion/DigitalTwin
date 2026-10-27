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

/**
 * The pages' refresh deferral, driven directly: results that arrive while an
 * edit is open wait for it. Prints one JSON line of what happened.
 *
 *   node defer.js <vscode/src directory>
 */
const Module = require('module');
const path = require('path');

const original = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return new Proxy({}, { get: () => new Proxy(function () {}, { get: () => () => ({}) }) });
  }
  return original(request, parent, isMain);
};

const src = process.argv[2];
const out = {};

async function check(name, Pages) {
  const pages = new Pages({ client: undefined }, undefined);
  let renders = 0;
  pages.render = async () => { renders += 1; pages.editing = false; };
  pages.panel = { visible: true };
  pages.page = { verdicts: { state: 'evaluating' } };

  // 1. An edit of the extension's (a picker) is under way: the refresh waits.
  let finish;
  pages.handle = () => new Promise((resolve) => { finish = resolve; });
  const editing = pages.receive({ command: 'presence' });
  pages.verdictsArrived();
  const duringPicker = renders;
  finish();
  await editing;
  const afterPicker = renders;

  // 2. The page's own editor is open: the refresh waits until it closes.
  pages.page = { verdicts: { state: 'evaluating' } };
  await pages.receive({ command: 'editing', open: true });
  pages.verdictsArrived();
  const duringEditor = renders;
  await pages.receive({ command: 'editing', open: false });
  const afterEditor = renders;

  // 3. Nothing open: at once. 4. A page already final is not redrawn.
  pages.page = { verdicts: { state: 'evaluating' } };
  pages.verdictsArrived();
  const idle = renders;
  pages.page = { verdicts: { state: 'ready' } };
  pages.verdictsArrived();
  const final = renders;

  // 5. Final, but a run for its package finished: an edit made elsewhere
  // (another page writes the file, no editor saves it) -- it asks again.
  pages.page = { root: '/pkg', verdicts: { state: 'ready' } };
  pages.verdictsArrived({ root: '/pkg', state: 'ready' });
  const newer = renders;
  // 6. Another package's run: not this page's business.
  pages.verdictsArrived({ root: '/other', state: 'ready' });
  const other = renders;
  // 7. Hidden: marked, not drawn; drawn when shown (the view-state handler).
  pages.panel = { visible: false };
  pages.verdictsArrived({ root: '/pkg', state: 'ready' });
  const hidden = renders;
  const marked = !!pages.staleWhileHidden;
  out[name] = { duringPicker, afterPicker, duringEditor, afterEditor, idle, final,
                newer, other, hidden, marked };
}

(async () => {
  await check('type', require(path.join(src, 'typepage.js')).TypePages);
  await check('shape', require(path.join(src, 'shapepage.js')).ShapePages);
  await check('case', require(path.join(src, 'casepage.js')).CasePages);
  console.log(JSON.stringify(out));
})().catch((error) => { console.error(error); process.exit(1); });
