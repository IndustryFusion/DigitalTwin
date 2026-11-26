# Tasks

Unit tests are in `semantic-model/SemForge-SDK/tests/unit/test_sparql_message.py`
(with `test_sparqlbench.py`, `test_sparqlpage.py` and `test_lsp_sweep.py`), the
page's script in headless Chromium; the end-to-end test is
`vscode/test/e2e/suite/04a-sparql-message.test.js`, run with `make test-e2e`. No
workflow runs the VS Code end-to-end suite (the `semforge-sdk` job of
`build.yaml` runs `make lint test kms-check`): it is run locally, and its result
goes into the pull request's body.

## 1. SDK

- [x] 1.1 The message's variables, filling and checks in one place; verify "A variable the query does not select", "Only the case differs", "Text that looks like a variable", "An apostrophe" and "A value the row lacks" with unit tests
- [x] 1.2 The workbench page and its run carry the message's check, and the type page's row says a message with variables; verify "A constraint with a message", "A constraint without a message", "A rule" and "A message with variables" (type page) with unit tests
- [x] 1.3 Write one message: change, add, remove, keep the language tag, refuse what changed meanwhile, several values or no text; verify "Changed", "Its language kept", "Added", "Changed in the file meanwhile", "Emptied", "Several messages", "No text" and "A line break and quotes" with unit tests that parse the file
- [x] 1.4 The sanity checks for the Problems panel and `semforge check`, and the warning on a query document's SELECT; verify "No message" and "The query edited away from its message" with unit tests
- [x] 1.5 The two language server requests; verify their answers and errors with unit tests and the protocol sweep

## 2. Extension

- [x] 2.1 The field on the workbench: variables, Tab, preview, warnings, Enter/Shift+Enter/Esc, a draft kept across a redraw; verify "The variables listed", "Inserted by a click", "Inserted by Tab", "Keys", "A redraw", "Filled", "A value the row lacks" and "No violating row" with page tests in headless Chromium
- [x] 2.2 Edit message… and + Message from the shape, type and workbench pages, and the confirmation before removing; verify "From the shape page", "From the type page", "A row without a message", "No message for a rule" and "Declined" with harness tests
- [x] 2.3 End to end in VS Code against the real server: opened from the shape page, edited with a variable, saved with an unsaved query edit kept, filled in the result, the SELECT warning, a stale save refused, removed after asking with the Problems panel warning, and added again; verify "From the shape page", "Changed", "Unsaved query edits", "The query edited away from its message", "Changed in the file meanwhile", "Emptied" and "Added" with the new e2e test, run locally with `make test-e2e`
- [x] 2.4 Describe it in the extension's README; verify by reading it

## 3. Checks

- [x] 3.1 Run the SDK unit suite with coverage (over 80 % of the changed code), flake8 and `openspec validate --all --strict`; verify all pass
