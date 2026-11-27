# Tasks

Unit tests are in `semantic-model/SemForge-SDK/tests/unit/` (`test_package_history.py`,
`test_package_undo.py`, `test_extension_activates.py`), the end-to-end test
("e2e:") in `vscode/test/e2e/suite/`, run with `make test-e2e`.

## 1. SDK

- [x] 1.1 Start a package's history, also inside another repository; verify "No repository" and "Inside another repository"
- [x] 1.2 Commit each editor write and each outside change first; verify "An edit of the editor" and "A change made by hand", through the editor session
- [x] 1.3 Commit as SemForge, unsigned, without hooks; no git keeps the edit; verify "A signing setup" and "No git"
- [x] 1.4 The `.semforge-no-history` marker and `SEMFORGE_HISTORY=off`; the marker is no member and not exported; verify "Marked", "Extracted from a marked package" and "Turned off"
- [x] 1.10 A history is SemForge's only when it started it (a mark in the git folder; for older ones a single SemForge root commit without a remote); git kept in the package (no links, no inherited location, an index lock waited for); verify "A history SemForge started", "A clone of a package repository", "A clone of a history SemForge started", "Linked files" and "A repository named by the environment"
- [x] 1.5 Publish tags in an existing history, never moves a tag, never starts one; verify "Tagged" and "A checkout"
- [x] 1.6 Undo, Redo and the redo stack; verify "Undone and redone", "A new change" and "The starting point"
- [x] 1.7 History… back to a step; verify "Back three steps"
- [x] 1.8 The requests `semforge/history`, `undo`, `redo`, `backTo`; verify unit tests of their answers and refusals
- [x] 1.9 The marker in the kms example and the test corpora; verify a unit test

## 2. Extension

- [x] 2.1 Undo, Redo and History… commands, the status bar item, the buttons and keybindings; verify "The status bar" and "In a view" with unit tests of the extension's contributions
- [x] 2.2 Unsaved edits refused; verify "Unsaved" with a unit test of the extension
- [x] 2.3 e2e: an entity removed, Undo brings it back, Redo removes it again, the status bar names the change; verify "Undone and redone" end to end

## 3. Checks

- [x] 3.1 Run the SDK unit suite with coverage (over 80 % of the changed code), flake8 and `openspec validate --all --strict`; verify all pass
