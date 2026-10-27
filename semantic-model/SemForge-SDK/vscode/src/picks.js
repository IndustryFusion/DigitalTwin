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
 * Quick picks with their actions first.
 *
 * "New attribute…", "Enter a different value…", "Combine with another
 * condition…" used to follow the list they belong to. On the OPC UA packages
 * that list is hundreds of datatypes, classes or attributes long, and an
 * action after it is never seen. So every picker that offers actions beside
 * a list puts them on top, then the list under its own heading.
 *
 * Where Enter has a meaning -- "Enter keeps the usual place" -- the highlight
 * starts on that item, not on the first action.
 */
const vscode = require('vscode');

const SEPARATOR = vscode.QuickPickItemKind ? vscode.QuickPickItemKind.Separator : -1;

/** `actions`, then the list under `heading` (a separator). */
function withActions(actions, items, heading) {
  const shown = (actions || []).filter(Boolean);
  if (!shown.length) {
    return items;
  }
  const list = items.length && items[0].kind === SEPARATOR ? items
    : [{ label: heading || '', kind: SEPARATOR }].concat(items);
  return shown.map((action) => Object.assign({ alwaysShow: true }, action)).concat(list);
}

/**
 * Pick from `items` with `actions` on top. `options` as for showQuickPick;
 * `active`, when given, is the item highlighted first. Resolves to the
 * picked item, or undefined.
 */
function pickWithActions(actions, items, options, active) {
  const all = withActions(actions, items, options && options.heading);
  if (!active) {
    return vscode.window.showQuickPick(all, options);
  }
  return new Promise((resolve) => {
    const quick = vscode.window.createQuickPick();
    quick.items = all;
    quick.activeItems = [active];
    quick.title = options && options.title;
    quick.placeholder = options && options.placeHolder;
    quick.matchOnDescription = !!(options && options.matchOnDescription);
    quick.matchOnDetail = !!(options && options.matchOnDetail);
    let picked;
    quick.onDidAccept(() => {
      picked = quick.selectedItems[0];
      quick.hide();
    });
    quick.onDidHide(() => {
      quick.dispose();
      resolve(picked);
    });
    quick.show();
  });
}

module.exports = { withActions, pickWithActions, SEPARATOR };
