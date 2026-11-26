# Tasks

Unit tests are in `semantic-model/SemForge-SDK/tests/unit/test_list_values.py`,
the end-to-end test ("e2e:") in `vscode/test/e2e/suite/36-list-values.test.js`, run with
`make test-e2e`.

## 1. SDK

- [ ] 1.1 Read an item as words and kind, with the list reading of #1087; verify "A list of texts" and "Typed, tagged and escaped items"
- [ ] 1.2 Write rows as items, for `sh:in` and `sh:hasValue`; verify "A second value", "A value taken out", "Empty and repeated rows", "Exactly", "Characters Turtle uses" and "A number where the shape asks for a double"
- [ ] 1.3 Keep what was not touched; verify "Items of every kind" by comparing RDF terms
- [ ] 1.4 Refuse what is not of its kind; verify "A word as a number" and "A word as a term", and that the file is unchanged
- [ ] 1.5 Take rows in the language server request, and a Turtle list in a text field; verify a unit test of the request and "Turtle typed"

## 2. Extension

- [ ] 2.1 Rows in the attribute editor, with keyboard and buttons; verify the scenarios of "One value per row" in headless Chromium
- [ ] 2.2 The kind of a row; verify "A number typed", "A number where the shape asks for a text" and "A term offered" in headless Chromium
- [ ] 2.3 End to end in VS Code against the real server: a list set, a value added and taken out, and shown; verify with a new e2e test
- [ ] 2.4 Describe it in the extension's README; verify by reading it

## 3. Checks

- [ ] 3.1 Run the SDK unit suite with coverage (over 80 % of the changed code), flake8 and `openspec validate --all --strict`; verify all pass
