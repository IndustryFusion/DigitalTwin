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
 * Render a case/model page payload to HTML, with a stub `vscode`, for a
 * browser to run: node render_casepage.js <vscode/src> <page.json> <out.html> [after.js]
 *
 * The page's own script needs acquireVsCodeApi, which only a webview has: a
 * stub is put in front of it. `after.js`, if given, runs once the page is up.
 */
const Module = require('module');
const fs = require('fs');
const path = require('path');

const original = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return new Proxy({}, { get: () => new Proxy(function () {}, { get: () => () => ({}) }) });
  }
  return original(request, parent, isMain);
};

const { renderCasePage } = require(path.join(process.argv[2], 'casepage.js'));
const page = JSON.parse(fs.readFileSync(process.argv[3], 'utf-8'));
// `__options` on the payload: what the extension passes besides the nonce
// (focus, the attribute to mark, only what violates); `__state`, what the
// webview remembered from an earlier visit (its filter, its view).
let html = renderCasePage(page, Object.assign({}, page.__options || {}, { nonce: 'n' }));
// What the page posts is kept on <html data-posted="[…]">, for a dumped DOM to show.
const stub = '<script nonce="n">function acquireVsCodeApi() { return { postMessage(m) { ' +
  'var all = JSON.parse(document.documentElement.dataset.posted || "[]"); all.push(m); ' +
  'document.documentElement.dataset.posted = JSON.stringify(all); }, ' +
  'getState() { return ' + JSON.stringify(page.__state || null).replace(/</g, '\\u003c') +
  '; }, setState() {} }; }</script>';
html = html.replace('<script nonce="n">', stub + '<script nonce="n">');
if (process.argv[5]) {
  html = html.replace('</body>', '<script nonce="n">' + fs.readFileSync(process.argv[5], 'utf-8') +
    '</script></body>');
}
fs.writeFileSync(process.argv[4], html);
