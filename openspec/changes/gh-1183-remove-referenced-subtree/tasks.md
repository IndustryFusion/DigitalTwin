# Tasks

Unit tests are in `semantic-model/SemForge-SDK/tests/unit/` (`test_remove_referenced_subtree.py`,
`test_remove_subtree.py`, `test_casepage.py`, `test_extension_activates.py`, `test_extension_commands.py`), the
end-to-end test ("e2e:") in `vscode/test/e2e/suite/`, run with `make test-e2e` (CI does not run
these yet, so 2.6 is the end-to-end test it runs).

## 1. SDK

- [x] 1.1 Rows of a Relationship's instance, `datasetId` or single-instance attribute name the entity they point at and their file's digest; an object list names none; verify unit tests of the tree payload
- [x] 1.2 The case page's rows of a Relationship name the entity they point at (their `target`) and their card the file's digest; verify a unit test of the case page payload
- [x] 1.3 Remove with subtree on the entity a reference names keeps the attribute's other instances; verify "From a reference row" with a unit test of `remove_subtree`

## 2. Extension

- [x] 2.1 The `…Ref` context values; every menu of the kind still applies; Remove with subtree… on reference rows and entity rows only; verify "Not an entity" with the extension's menu tests
- [x] 2.2 Remove with subtree… from a reference row sends the entity it points at, its file and the digest; verify a unit test of the extension
- [x] 2.3 The case page's row menu: "Remove what … points at, with its subtree", "only this reference; the entity stays", "ALL n instances"; verify "From the case page" and "Only this reference" with unit tests of the extension
- [x] 2.4 The attribute's question names the number of its instances; verify "Several instances" with a unit test of the extension
- [x] 2.5 e2e: a package with a parent pointing at several children, one removed with its subtree from its reference row; the others and their references stay; verify "From a reference row" end to end
- [x] 2.6 e2e that CI runs (`tests/unit/`): on a real package with a parent pointing at several children, a reference row taken from the tree payload, its entity removed with its subtree through the request the extension sends; the others and their references stay; verify "From a reference row" through the server

## 3. Checks

- [x] 3.1 Run the SDK unit suite with coverage (over 80 % of the changed code), flake8 and `openspec validate --all --strict`; verify all pass
