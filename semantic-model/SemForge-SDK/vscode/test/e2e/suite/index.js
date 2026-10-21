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
