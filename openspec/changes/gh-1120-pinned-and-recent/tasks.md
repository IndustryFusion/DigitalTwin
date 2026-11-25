# Tasks

## 1. SDK

- [ ] 1.1 Answer whether what each pin names is in the package, for every kind, in the order asked, and that the package is gone; verify unit tests in `tests/unit/test_pins.py` for "A package that is gone" and each kind there and gone

## 2. Extension

- [ ] 2.1 Keep pins and recent places in the workspace state and list them, with "Nothing yet", the taking out and the pinning from the list; verify unit tests and the end-to-end test for "Pinned before recent", "Opening a pinned entity", "A recent place pinned from the list" and "No answer"
- [ ] 2.2 Pin from the star of a page, from rows, and from the ⋯ of an attribute and a query, and contribute the entry for an entity's id; verify unit tests on the contributions and the menus, and for "A row", "An id on a test case's page" and "A row that is no such thing"
- [ ] 2.3 Let renames of shapes, cases and suites take pins along; verify tests for "A renamed test case", "An entity in a renamed suite" and a renamed shape
- [ ] 2.4 Say what is gone, and search for it or take it out; verify the end-to-end test for "A deleted case"
- [ ] 2.5 Describe it in `vscode/README.md`; verify by reading it

## 3. End to end and checks

- [ ] 3.1 Add an end-to-end test `vscode/test/e2e/suite/30-pins.test.js` that pins the page in front and an entity, checks the star, opens from the list, pins through a rename, and takes out what was deleted, and that no file of the package changes by pinning; verify `make test-e2e` passes it
- [ ] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass, with the coverage of the new code above 80 %
