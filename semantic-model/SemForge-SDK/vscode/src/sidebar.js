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

/*
 * The two SemForge columns, and what each view is.
 *
 * The main column holds what a modeller works with: the package and its
 * entities and test cases. The constraints, the shapes as written and the
 * knowledge are the details behind them -- reached from the pages, and needed
 * in a tree only now and then. They live in a second container that stays
 * away until asked for ("Show details"), so the main column keeps its room.
 *
 * What a view is used to be its message, a paragraph at its top on every
 * view, always. It is the hover of an ⓘ in the view's title bar now: the
 * command's title IS the text (package.json), and a click says it again.
 * The message is kept for what is wrong -- no server, no package, an error.
 */

const vscode = require('vscode');

// The same words as the titles of the semforge.about.* commands in
// package.json; a unit test keeps the two equal.
const ABOUT = {
  semforgeProject: 'This package: its settings, its health and what it is made of. ' +
    'A row opens the package page.',
  semforgeModel: 'The data: the Main model’s entities, then the test cases that prove ' +
    'the constraints. A row opens the Main page or its case page.',
  semforgeConstraints: 'Every entity type, with what its shapes require of each attribute ' +
    '— its own and inherited ones together. A type opens its type page.',
  semforgeShapes: 'The SHACL shapes as written, one row per shape with what it targets. ' +
    'A shape opens its shape page.',
  semforgeKnowledge: 'What the terms mean: entity types, attributes, value lists and units, ' +
    'from the knowledge files. A row opens its type or vocabulary page.'
};

// The context key the details views are shown under (package.json `when`).
const DETAILS = 'semforge.details';
const CONTAINER = 'workbench.view.extension.semforgeDetails';

function aboutCommand(view) {
  return `semforge.about.${view.replace(/^semforge/, '').toLowerCase()}`;
}

function register(context) {
  const state = context.workspaceState;
  // What was last set: the context key the details views are shown under.
  let current;
  const setShown = async (shown) => {
    current = shown;
    await vscode.commands.executeCommand('setContext', DETAILS, shown);
    if (state && state.update) {
      await state.update(DETAILS, shown);
    }
  };
  // Remembered per workspace: details opened once stay until hidden again.
  setShown(!!(state && state.get && state.get(DETAILS, false)));

  context.subscriptions.push(
    vscode.commands.registerCommand('semforge.showDetails', async () => {
      await setShown(true);
      await vscode.commands.executeCommand(CONTAINER);
    }),
    vscode.commands.registerCommand('semforge.hideDetails', () => setShown(false)),
    ...Object.keys(ABOUT).map((view) =>
      vscode.commands.registerCommand(aboutCommand(view), () =>
        vscode.window.showInformationMessage(ABOUT[view])))
  );

  // What the details are, as the end-to-end tests read it: the context key
  // last set, and what a reload would restore.
  return {
    shown: () => current,
    stored: () => !!(state && state.get && state.get(DETAILS, false))
  };
}

module.exports = { register, ABOUT, DETAILS, aboutCommand };
