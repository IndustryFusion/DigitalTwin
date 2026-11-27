# Tasks

Unit tests are in `semantic-model/SemForge-SDK/tests/unit/` (`test_new_case.py`,
`test_tree_clicks.py`, `test_add_test_case.py`), the end-to-end tests ("e2e:") in
`vscode/test/e2e/suite/`, run with `make test-e2e`.

## 1. SDK

- [x] 1.1 Write a query's test empty by default, declared without an assert; verify "Written empty", "Not firing yet", and "Silent" with a unit test that pastes entities the query holds on into an empty test that should conform and finds it passing and listed on the shape page as evaluated and not fired
- [x] 1.2 Keep the start from a scene for `scene: copy`, refuse another value; verify "A query of several types", "A type without entities", "What an entity of the model points at", "Out of the query's reach", "Asserted from the start" and "No scene asked for"
- [x] 1.3 Say in the description that the case starts empty; verify a unit test of the declaration
- [x] 1.4 Take `scene` in `semforge/newCase` and answer it; verify a unit test of the request's answers

## 2. Extension

- [x] 2.1 New case… of a shape page asks Should conform or Should fail first, then a free name in that folder; verify "Asked first", "Should fail", "Should conform" and "Not answered" with unit tests of the extension
- [x] 2.2 Word the messages of the shape page and of New test… of a query by the answer's `scene`; verify unit tests of the extension
- [x] 2.3 An empty file first in New test case…; verify "The first start" with a unit test of the extension
- [x] 2.4 e2e: a query's test written empty, its entities pasted from Main, made to fire and asserted; verify "Firing, not yet asserted" and "Made to fire"
- [x] 2.5 e2e: New case… of a shape page answered Should fail, written empty, deleted again from its row, no page left evaluating; verify "Should fail" and "From the shape page"

## 3. Checks

- [x] 3.1 Run the SDK unit suite with coverage (over 80 % of the changed code), flake8 and `openspec validate --all --strict`; verify all pass
