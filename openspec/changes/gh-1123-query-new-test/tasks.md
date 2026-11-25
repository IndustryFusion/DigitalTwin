# Tasks

Unit tests are in `semantic-model/SemForge-SDK/tests/unit/test_new_case.py`, the
end-to-end test ("e2e:") in `vscode/test/e2e/suite/`, run with `make test-e2e`.

## 1. SDK

- [ ] 1.1 Write a test that should conform or fail; verify "Silent", "Not firing yet" and "Made to fire"
- [ ] 1.2 Choose the scene by the type, with what a model's entity points at, or a new entity; verify "A query of several types", "A type without entities", "What an entity of the model points at" and "Out of the query's reach"
- [ ] 1.3 Run it once, and write it whole or not at all; verify "The outcome", "A failure after declaring" and "A name that is taken"
- [ ] 1.6 Move a relative context; verify "From a model with a relative context", and that the test fails without the move
- [ ] 1.4 Keep New case… as it is; verify "From the shape page" and the existing tests of New case…
- [ ] 1.5 Take the two inputs in the language server request; verify a unit test of its answers

## 2. Extension

- [ ] 2.1 New test… in the menu of a query's row, its two questions and its message; verify "A constraint", "A rule" and "Not answered" with unit tests of the extension
- [ ] 2.2 End to end in VS Code against the real server: from the row's menu to the case page, and made to fire; verify with a new e2e test
- [ ] 2.3 Describe it in the extension's README; verify by reading it

## 3. Checks

- [ ] 3.1 Run the SDK unit suite with coverage (over 80 % of the changed code), flake8 and `openspec validate --all --strict`; verify all pass
