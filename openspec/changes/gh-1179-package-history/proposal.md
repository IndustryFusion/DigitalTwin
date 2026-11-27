# Proposal

Issue: #1179

## Why

A KMS package edited in the SemForge editor has no way back: every change, the
editor's own and one made by hand, overwrites the only copy, and an exported
package carries no version control. There is no Undo for the editor's changes.

## What Changes

- **A package keeps its own git history.** Opening a package without one starts
  it in the package folder (also inside another repository, never committing into
  that one); every change the editor writes is committed after it, a change made
  outside is committed before the next read or step.
- **`.semforge-no-history`** in a package folder opts out (the kms example and the
  test corpora of this repository); `SEMFORGE_HISTORY=off` turns it off for all.
- **Publish tags** the version in an existing history and never starts one.
- **Undo, Redo and History…** step along that history: Ctrl+Z / Ctrl+Shift+Z in
  SemForge's views, buttons on Entities & Test Cases, a status bar item, the
  command palette.

## Capabilities

### New Capabilities
- `semforge-sdk/package-history`: the package's history, its steps and where they
  are offered.

### Modified Capabilities

None.

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK`): `semforge/package/history.py`
  (new), the editor session (commit on open, on change), `semforge publish`
  (tag), the requests `semforge/history`, `semforge/undo`, `semforge/redo` and
  `semforge/backTo`, the extension's commands, keybindings, view buttons and
  status bar item. git is used when it is installed; no new dependency.
- The kms example and the test corpora get a `.semforge-no-history` file.
- No change to any other component, image, chart or deployment.

## Out of Scope

- Pushing, branches or remotes of a package's history.
- Undo inside a text editor: that stays the editor's own.
