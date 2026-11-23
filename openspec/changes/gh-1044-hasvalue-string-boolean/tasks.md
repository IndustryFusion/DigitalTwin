# Tasks

## 1. Tests first

- [x] 1.1 Add the kms-constraints fixture `test28`: a shape with `sh:hasValue true`, `false`, `"1"`, `"1.0"`, `"0.5"`, `"1e+21"` and `"true"` on one property each, and one entity per value (plain `true`, `false`, `1`, `0`, `1.0`, `0.5`, `1e21`; declared boolean `true`, `"1"`, `"0"`; declared double `1` and `0.5`; declared integer `1`; the strings `"true"`, `"false"`, `"True"`, `"TRUE"`, `"1"`, `"0"`, `"1.0"`, `"0.5"`, `".5"`, `"1e21"`), each holding the value on every property; write the expected result from the delta specification; verify `tests/sql-tests/tests.sh test28` fails on it before the change
  - Verified: with origin/main's compiler `tests.sh test28` fails (among others, plain `false` and `"True"` meet `true`, plain `1` meets `"1.0"`, `"true"` violates `true`); with the change it passes
- [x] 1.2 In `tests/test_hasvalue_check.py`, run the generated check on SQLite with the rows each side fills (the design's table) for every value of task 1.1 and the constants `true`, `false`, `"1"^^xsd:boolean`, `"true"`, `"1"`, `"1"^^xsd:string`, `"1.0"`, `"0.5"` and `"1e+21"`; verify the tests fail before the change on the Flink rows and on the SQLite rows
  - Verified: 216 cases; with origin/main's check 27 of them fail, on Flink rows and SQLite rows; all pass with the change
- [x] 1.3 Turn the strict expected failure for a string constant against a plain number into a passing test; verify it passes and is no longer reported as xfail
  - Verified: the test passes, no xfail is left in the file, and it fails with origin/main's check
- [x] 1.4 Test that the compiler writes a boolean constant as `true`/`false` with `xsd:boolean`, and marks a string constant only when it is the platform's text of a number; test the number formatting against known outputs of JavaScript; test that neither generated check casts to `INTEGER` or `BOOLEAN`; verify by running the file
  - Verified: `pytest tests/test_hasvalue_check.py` passes (297); the 7 new constraint-table cases and the no-cast assertion fail with origin/main
- [x] 1.5 Extend `test28` and the matrix of task 1.2 with constants of other datatypes (`"2020"^^xsd:gYear`, `"1"^^xsd:token`, `"1"` of a datatype of the model's own, `"2020-05"^^xsd:gYearMonth`) and `"NaN"`, and with the values plain `2020`, the string `"2020"`, a declared `xsd:gYear` `2020`, a declared double written as the string `"1.0"`, the string `"NaN"` and a declared `xsd:string` `"true"` (D1, D6, D7); test that `NaN`, `Infinity` and `-Infinity` are not marked; verify they fail on 31970e50
  - Verified: with 31970e50's compiler and model writer `tests.sh test28` fails (plain `2020` and `"2020"` violate `"2020"^^xsd:gYear`, every number violates `"1"^^xsd:token` and the custom datatype, plain `0` meets `"NaN"`); with the change it passes. `test_hasvalue_check.py` on 31970e50: 14 failures (5 constraint-table cases, 3 NaN/Infinity mark cases, 6 rejection cases of task 1.6)
- [x] 1.6 Test that the build fails, naming the constant, for `"abc"^^xsd:integer`, `"1e3"^^xsd:integer`, `"NaN"^^xsd:double`, `"INF"^^xsd:double`, `"-INF"^^xsd:float` and `"yes"^^xsd:boolean` (D8), and that the SQLite model rows hold a value of another declared datatype by its lexical form (D6); verify by running the file
  - Verified: `pytest tests/test_hasvalue_check.py` passes (535); the six rejection cases fail on 31970e50, which compiled them; its model writer held a declared `xsd:gYear` 2020 as `2020-01-01` (seen in the test28 database)

## 2. shacl2flink

- [x] 2.1 In the compiler, store a boolean constant as `true`/`false` and mark a string constant whose text is the platform's text of a number in `hasValueType` (D1, D2); verify task 1.4 passes
  - Verified: task 1.4 passes
- [x] 2.6 Store a constant of another datatype by its lexical form and mark it like a string constant, mark only finite numbers, write a value of another declared datatype to the SQLite model rows by its lexical form, and reject the constants of D8 as `UnsupportedShape` with the other build problems (D1, D6, D8); verify tasks 1.5 and 1.6 pass
  - Verified: tasks 1.5 and 1.6 pass; `pytest` of shacl2flink without the pyflink UDF tests: 853 passed, coverage 85 %; `flake8` of the test file is clean and finds nothing new in the changed modules; all kms-constraints, sql-cases and kms-rules fixtures pass with no existing expected result changed
- [x] 2.2 Rework the generated `sh:hasValue` check: a boolean constant as in D2, a string constant as in D1 and D3, no cast to a value's declared type (D4), number constants unchanged; verify tasks 1.1 to 1.3 pass, and `flake8` and `pytest` of shacl2flink pass
  - Verified: tasks 1.1 to 1.3 pass; `pytest` of shacl2flink without the pyflink UDF tests passes (634, coverage 85 %, the changed module 93 %); `flake8` finds nothing new in the changed files. The UDF tests need pyflink and run in CI
- [x] 2.3 Run all sql-tests; verify they pass and that no existing expected result had to change (`kms-constraints/test27` and `sql-cases/untyped-hasvalue` unchanged)
  - Verified: every kms-constraints, sql-cases and kms-rules fixture passes and no expected result changed; kms-udf needs pyflink and runs in CI
- [x] 2.4 Add the deliberate divergences of D5 found on `test28` to `tests/pyshacl-compare/expected-divergences.txt` with their reason; verify the pyshacl comparison reports no missed or extra divergence that is not listed
  - Verified: the comparison reported exactly the twelve of D5 before they were listed, and after task 1.5 the fifteen further ones of D5 (D6, D7); with all listed, 0 missed and 0 extra over 96 models
- [x] 2.5 Document both rules in the `sh:hasValue` entry of `docs/supported-features.md`; verify the entry says what the documentation scenario of the delta requires
  - Verified: the entry names every value of the documentation scenario, and also states D6, D7 and D8

## 3. Flink

- [x] 3.1 Add `sh:hasValue "1"` and `sh:hasValue true` to the e2e kms package (`tests/e2e-kms`) and extend the `sh:hasValue` test of `tests/bats/test-shacl-flink-scorpio-e2e` with plain `1` and `1.0`, declared double and integer `1`, the strings `"1"` and `"1.0"` against `"1"` and `"1.0"`, and plain `true` and `false`, declared boolean `1` and `0`, the strings `"true"`, `"True"` and `"1"` and the plain `1` against `true`; verify the package compiles
  - Verified: the e2e package compiles offline (again after task 2.6), `bats --count` parses the suite and `shellcheck` finds nothing; running it needs the cluster (task 3.2)
- [x] 3.3 Add `sh:hasValue "2020"^^xsd:gYear` and `sh:hasValue "NaN"` to the e2e kms package and extend the same bats test: plain `2020`, the string `"2020"` and a declared `xsd:gYear` `2020` meet the gYear constant, plain `0` violates `"NaN"` and the string `"NaN"` meets it (D1, D6); verify the package compiles and the suite parses
  - Verified: the e2e package compiles offline with both constants, `bats --count` parses the suite (9 tests) and `shellcheck` finds nothing; that the cases pass on Flink is shown only by task 3.2
- [x] 3.2 Verify `make test-flink-e2e` (including the cases of task 3.3) passes in the K8s tests workflow of the Pull Request, and report the run and the test's result in the Pull Request
  - K8s e2e run 45093012381 (head d3b266ed), job `e2e (flink)`: `ok 27 sh:hasValue compares numbers, strings and booleans as specified, through scorpio and the bridge`; reported in the pull request.

## 4. Verification

- [x] 4.1 Check every scenario of the delta specification against the tests of tasks 1.1, 1.2 and 3.1 and report the result per scenario in the Pull Request, naming which scenarios are verified on Flink end to end and which only through the Flink rows of task 1.2
  - The pull request reports every scenario of the delta with its tests (unit matrix on SQLite- and Flink-shaped rows, test28 on SQLite, the pyshacl comparison) and names the ones verified on Flink end to end: the string constants `"1"`, `"1.0"`, `"2020"^^xsd:gYear`, `"NaN"` and the boolean `true`, through Scorpio and the bridge.
