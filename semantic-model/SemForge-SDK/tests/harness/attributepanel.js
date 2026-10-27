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
 * The expression editor's panel as HTML, for a browser to run:
 *
 *   node attributepanel.js <vscode/src> <state.json> <out.html> [after.js]
 *
 * acquireVsCodeApi is stubbed; what the panel posts is kept on
 * <html data-posted="[…]">. `after.js`, if given, runs once the panel is up.
 */
const fs = require('fs');
const Module = require('module');
const path = require('path');

const original = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return {};
  }
  return original(request, parent, isMain);
};

const { renderAttributePanel } = require(path.resolve(process.argv[2], 'attributepanel.js'));
const state = JSON.parse(fs.readFileSync(process.argv[3], 'utf-8'));
let html = renderAttributePanel(state, { nonce: 'n' });
const stub = '<script nonce="n">function acquireVsCodeApi() { return { postMessage(m) { ' +
  'var all = JSON.parse(document.documentElement.dataset.posted || "[]"); all.push(m); ' +
  'document.documentElement.dataset.posted = JSON.stringify(all); } }; }</script>';
html = html.replace('<script nonce="n">', stub + '<script nonce="n">');
if (process.argv[5]) {
  html = html.replace('</body>', '<script nonce="n">' + fs.readFileSync(process.argv[5], 'utf-8') +
    '</script></body>');
}
fs.writeFileSync(process.argv[4], html);
