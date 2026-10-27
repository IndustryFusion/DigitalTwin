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
 * Whether the server is validating, in the status bar.
 *
 * An edit used to be followed by seconds of nothing and then new verdicts:
 * the pages say "evaluating…" only once they are refreshed, and a refresh
 * waits while an edit is open. The server says when a run starts and when it
 * ends (`semforge/verdicts`); this shows it, whatever page is open or none.
 */
const SPIN = '$(sync~spin) SemForge: validating…';

class Validating {
  /** `item` is a status bar item (text, tooltip, show(), hide()). */
  constructor(item, timers = { set: setTimeout, clear: clearTimeout }) {
    this.item = item;
    this.timers = timers;
    this.running = new Set();
    this.timer = undefined;
  }

  notice(notice) {
    if (!notice || !notice.state) {
      return;
    }
    const root = notice.root || '';
    if (notice.state === 'evaluating') {
      this.running.add(root);
      this.show(SPIN, 'The package is being validated in the background');
      return;
    }
    this.running.delete(root);
    if (this.running.size) {
      return;
    }
    if (notice.state === 'failed') {
      this.show('$(error) SemForge: validation failed', notice.error || '', 10000);
    } else {
      const seconds = Number(notice.seconds || 0);
      this.show(`$(check) SemForge: validated${seconds ? ` in ${seconds.toFixed(1)} s` : ''}`,
        'The verdicts are current', 3000);
    }
  }

  show(text, tooltip, hideAfter) {
    if (this.timer !== undefined) {
      this.timers.clear(this.timer);
      this.timer = undefined;
    }
    this.item.text = text;
    this.item.tooltip = tooltip;
    this.item.show();
    if (hideAfter) {
      this.timer = this.timers.set(() => {
        this.timer = undefined;
        this.item.hide();
      }, hideAfter);
    }
  }

  dispose() {
    if (this.timer !== undefined) {
      this.timers.clear(this.timer);
    }
    this.item.dispose && this.item.dispose();
  }
}

/** A Validating on a new status bar item, disposed with the extension. */
function register(vscode, context) {
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 0);
  const validating = new Validating(item);
  context.subscriptions.push(validating);
  return validating;
}

module.exports = { Validating, register };
