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
 * The status bar's "validating…", driven by the notices the server sends.
 * Prints one JSON line: what the item showed after each notice.
 *
 *   node validating.js <vscode/src directory>
 */
const path = require('path');

const { Validating } = require(path.resolve(process.argv[2], 'validating.js'));

const item = { text: '', tooltip: '', visible: false,
  show() { this.visible = true; }, hide() { this.visible = false; } };
let pending;
const validating = new Validating(item, {
  set: (fn) => { pending = () => { pending = undefined; fn(); }; return 1; },
  clear: () => { pending = undefined; } });

const seen = [];
function after(notice) {
  validating.notice(notice);
  seen.push({ text: item.text, visible: item.visible, timer: pending !== undefined });
}

after({ root: '/a', state: 'evaluating', started: true });
after({ root: '/b', state: 'evaluating', started: true });
after({ root: '/a', state: 'ready', seconds: 0.42 });      // /b still running
after({ root: '/b', state: 'ready', seconds: 1.25 });
pending();
seen.push({ text: item.text, visible: item.visible, timer: pending !== undefined });
after({ root: '/a', state: 'evaluating', started: true });
after({ root: '/a', state: 'failed', error: 'boom' });
seen.push({ tooltip: item.tooltip });
console.log(JSON.stringify(seen));
