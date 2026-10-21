const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');
const { semforge, request } = require('./helpers');

describe('activation', () => {
  it('starts its language server on the package', async () => {
    const api = await semforge();
    const answer = await request(api, 'semforge/methods', {});
    for (const method of ['semforge/model', 'semforge/casePage', 'semforge/modelPage',
      'semforge/typePage', 'semforge/valueChoices', 'semforge/addEntityType']) {
      assert.ok(answer.methods.includes(method), `the server cannot answer ${method}`);
    }
  });

  it('registers every command it contributes', async () => {
    await semforge();
    const manifest = JSON.parse(fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'package.json'), 'utf-8'));
    const registered = new Set(await vscode.commands.getCommands(true));
    const missing = manifest.contributes.commands.map((c) => c.command)
      .filter((command) => !registered.has(command));
    assert.deepStrictEqual(missing, []);
  });
});
