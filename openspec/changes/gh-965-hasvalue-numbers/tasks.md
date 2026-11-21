# Tasks

## 1. Tests first

- [ ] 1.1 Add the kms-constraints fixture `test27`: a shape with `sh:hasValue 80.0` on one property and `sh:hasValue 80` on another, and one entity per value (plain `80`, `80.0`, `80.5`, declared double `80` and `80.5`, declared integer `80`, the strings `"80.0"`, `"80"` and `"eighty"`), each holding the value on both properties; write the expected result from the delta specification; verify `tests/sql-tests/tests.sh` fails on it before the change
- [ ] 1.2 Add unit tests of the generated `sh:hasValue` check (`tests/test_hasvalue_check.py`) that run it on SQLite with rows as each side fills them (the design's table), for the constants `80.0`, `80`, `"80.0"^^xsd:double` and the string `"1.0"`; verify they fail before the change on the Flink rows and on the declared integer against `80.5`
- [ ] 1.3 In the same file, test that the compiler writes each constant and its datatype into the constraint table, and that the Flink check casts only with a cast that cannot fail and uses the number pattern of the `sh:datatype` check; verify by running the file
- [ ] 1.4 Record the string constant against a plain number (design, *Known divergences left open*) as an expected failure in the same file; verify it is reported as xfail, not as a pass

## 2. shacl2flink

- [ ] 2.1 Add the column for the constant's datatype to the constraint table and fill it in the compiler, NULL for a constant without one and for every other constraint (D4); verify task 1.3 passes
- [ ] 2.2 Compare a number constant by its value when the value's type is numeric or missing and its text is a number (D1 to D3), and keep today's comparison otherwise; verify tasks 1.1 and 1.2 pass, and `make lint` and `make test` pass
- [ ] 2.3 Run all sql-tests; verify they pass, `sql-cases/untyped-hasvalue` and `kms-constraints/test18` unchanged, and list in the Pull Request every existing expected result that had to change
- [ ] 2.4 Add the nine deliberate divergences of D5 to `tests/pyshacl-compare/expected-divergences.txt` with their reason; verify `make test-pyshacl-compare` reports no missed or extra divergence
- [ ] 2.5 Document the rule in the `sh:hasValue` entry of `docs/supported-features.md`; verify the entry says what the documentation scenario of the delta requires

## 3. Flink

- [ ] 3.1 Add a shape with `sh:hasValue 80.0`, `sh:hasValue 80`, `sh:hasValue 80.5` and a string constant `sh:hasValue "1.0"` to the e2e kms package (`tests/e2e-kms`) and a test to `tests/bats/test-shacl-flink-scorpio-e2e` that writes every value of the scenarios to Scorpio (plain `80` and `80.0`, declared double `80` and `80.5`, declared integer `80`, `80.5`, the strings `"80.0"`, `"80"`, `"eighty"`, `"1.0"` and `"1"`) and checks each scenario's verdict on Flink, including the declared integer `80` against `sh:hasValue 80.5`; verify the package compiles
- [ ] 3.2 Verify `make test-flink-e2e` passes in the K8s tests workflow of the Pull Request, and report the run and the test's result in the Pull Request

## 4. Verification

- [ ] 4.1 Check every scenario of the delta specification against the tests of tasks 1.1, 1.2 and 3.1 and report the result per scenario in the Pull Request, naming which scenarios are verified on Flink end to end and which only through the Flink rows of task 1.2
- [ ] 4.2 Open the two issues of the design's *Known divergences left open* (string constant against a plain number, boolean constants); verify they are linked from the Pull Request
