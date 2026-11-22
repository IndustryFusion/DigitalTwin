# Tasks

## 1. Tests first

- [ ] 1.1 Add `tests/unit/test_crosscheck_expected.py` with the probe package of #958's task 4.2, built from `shacl2flink/tests/jsonld-number-vectors.json` (one Filter per row, on an `xsd:double`, an `xsd:integer` and an `sh:or` attribute). Assert that the cross-check reports no missed or extra difference on it and lists exactly the strings and `true` on the `sh:or` attribute as expected, each with its reason. Verify that it fails before the change (1 missed and 7 extra) and is not skipped where the cross-check's dependencies are installed.
- [ ] 1.2 In the same file, add unit tests of the comparison for the scenarios: the `sh:or` merge (one to one, same entity and attribute, only for an `sh:or` of datatypes), strings read as an admitted datatype, and differences that must stay unexpected (numbers, a string whose text is not admitted, text that is no number, other constraint types, a datatype alert pyshacl does not raise). Verify that they fail before the change where they test a new expected entry, and pass after it.
- [ ] 1.3 Add tests that the command prints the agreement line when every difference is expected and omits it otherwise, that a missing shacl2flink names `--shacl2flink <path>`, and that a relative `--shacl2flink` resolves where it was given. Verify by running the file.
- [ ] 1.4 Add a test to `tests/unit/test_profile_drift.py` that reads the text patterns of shacl2flink's `sh:datatype` check and compares them with the cross-check's copy. Verify that it fails when either pattern is changed.

## 2. SemForge SDK

- [ ] 2.1 Record the rejected value, its datatype and the admitted datatypes on a pyshacl result, outside its identity and equality, and keep them through the editor's verdict cache (D1). Verify the adapter test of task 1.1 and `tests/unit/test_verdicts.py` pass.
- [ ] 2.2 Categorise the two divergences as expected in the cross-check, with their reasons, and print the agreement line when every difference is expected (D2 to D4). Verify that tasks 1.1 to 1.4 pass.
- [ ] 2.3 Name `--shacl2flink <path>` in the message for a missing shacl2flink, and resolve the path before the build changes directory. Verify task 1.3.
- [ ] 2.4 State in the README that the cross-check compiles the model, not the examples, what it lists as expected, and how to point it at shacl2flink. Verify by reading the `--cross-check sqlite` row against the documentation requirement.

## 3. CI and verification

- [ ] 3.1 Install sqlite3 with its PCRE extension and `requirements-crosscheck.txt` in the SemForge SDK job of `.github/workflows/build.yaml`. Verify in the Pull Request's Build run that the probe test of task 1.1 runs and passes rather than skipping.
- [ ] 3.2 Run `make lint test` of the SDK and `openspec validate --all --strict`. Verify that both pass, and report per scenario of the delta specification which test covers it in the Pull Request.
