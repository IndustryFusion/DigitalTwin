# Tasks

Unit tests are in `semantic-model/SemForge-SDK/tests/unit/` (`test_remove_subtree.py`,
`test_extension_activates.py`, `test_extension_commands.py`), the end-to-end test
("e2e:") in `vscode/test/e2e/suite/`, run with `make test-e2e`.

## 1. SDK

- [ ] 1.1 `remove_subtree`: the members of the copied subtree in the row's file; verify "Children and theirs" and that a plan writes nothing
- [ ] 1.2 Keep members written elsewhere and children used outside the subtree; verify "Written in another file" and "Used by another entity"
- [ ] 1.3 Take out the references to removed entities, by IRI, one object of several, object lists; verify "The parent's reference", "However it is written", "An object list" and "Still defined"
- [ ] 1.4 The refusals and the whole-file write of Remove entity, the plan over members, file and asserts; verify "Changed during the question", "Changed since it was read", "Another file" and "Written twice"
- [ ] 1.5 `subtree` in `semforge/removeEntity`; verify a unit test of the request with and without it

## 2. Extension

- [ ] 2.1 The command, its menu entry below Remove entity…, not in the palette; verify "Not an entity" with the extension's command and menu tests
- [ ] 2.2 The question: what goes, the references, what stays and why, the cases and the asserts; dismissed nothing is written, unsaved edits refused; verify "Asked first", "Dismissed" and "Unsaved edits" with unit tests of the extension
- [ ] 2.3 e2e: a subtree pasted into a case and removed from it, its count asked, the main model untouched; verify "From a row"

## 3. Checks

- [ ] 3.1 Run the SDK unit suite with coverage (over 80 % of the changed code), flake8 and `openspec validate --all --strict`; verify all pass
