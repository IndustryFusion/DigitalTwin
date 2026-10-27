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

// Loaded by VS Code inside its extension host: runs every *.test.js here.

const fs = require('fs');
const path = require('path');
const Mocha = require('mocha');

function run() {
  const mocha = new Mocha({ ui: 'bdd', color: true, timeout: 60000,
    grep: process.env.SEMFORGE_E2E_GREP || undefined });
  for (const file of fs.readdirSync(__dirname).filter((f) => f.endsWith('.test.js')).sort()) {
    mocha.addFile(path.join(__dirname, file));
  }
  return new Promise((resolve, reject) => {
    mocha.run((failures) => (failures
      ? reject(new Error(`${failures} end-to-end test(s) failed`)) : resolve()));
  });
}

module.exports = { run };
