# Tasks

## 1. SDK

- [ ] 1.1 Prune a view's answer to the rows that fit a search and the rows above them, in summary and full form; verify unit tests in `tests/unit/test_search.py` for "An attribute in all four views", "Words in any order and case", "A fitting row without fitting rows" and "Nothing fits", and that an answer without a search is unchanged
- [ ] 1.2 Let a row fit by its statement, its case's description and asserts, and say what was found; verify unit tests for "A value a shape lists", "What a case asserts", "A count" and "An entity's type"
- [ ] 1.3 Name the hidden rows under a partly hidden row; verify a unit test that they are named with what edits need, and only then
- [ ] 1.4 Answer which page a line of a file is about, for the text as shown; verify unit tests for "A line of a shape", "A term of the knowledge", "An entity", "A file that cases include", "A declaration of a case", "A file with unsaved lines", "A line without a page" and "A file outside any package"

## 2. Extension

- [ ] 2.1 Add Search…, its key and buttons, Clear the search, the count above the rows and the rows opened down to what fits; verify unit tests on the contributions and by the end-to-end test
- [ ] 2.2 Decide the taken instances, a type's own shape and the file an entity is added to by the hidden rows too; verify an extension unit test for "An attribute whose row is hidden"
- [ ] 2.3 Add Open in SemForge to the title bar and context menu of the three kinds of files; verify unit tests on the contributions and on the message without a file
- [ ] 2.4 Describe search and Open in SemForge in `vscode/README.md`; verify by reading it

## 3. End to end and checks

- [ ] 3.1 Add an end-to-end test `vscode/test/e2e/suite/28-search.test.js`: Search… filters all four views, shows SemForge Details, says the count, is kept on Enter, put back on Escape and cleared, a found row opens its page, and Open in SemForge opens a shape's page, also with unsaved lines above; verify `make test-e2e` passes it
- [ ] 3.2 Run the SDK unit suite with coverage, flake8 and `openspec validate --all --strict`; verify all pass, with the coverage of the new module above 80 %
