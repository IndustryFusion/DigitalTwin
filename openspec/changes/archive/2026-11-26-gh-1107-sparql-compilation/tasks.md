# Tasks

## 1. Tests first

- [x] 1.1 Add a test that evaluates each supported form as SPARQL on a model and its knowledge, and as the SQL it compiles to on SQLite, and requires the same entities (every form of the delta, each with entities that are found and entities that are not); verify the forms that the issue lists fail without the change
  - Verified: `tests/test_sparql_semantics.py`: 99 forms and 6 from the other end of a relationship, all pass; of the first 77, 74 fail with origin/main's compiler
- [x] 1.2 Add a test that each form that is not supported is refused, with the reason naming it; verify by running it
  - Verified: `REFUSED` in the same file: 45 forms, each with the reason that names it
- [x] 1.3 Add tests of the report: two expressions of two shapes, a rule, the pattern, the file and line, an unforeseen failure, no stack trace, nothing written; and of the check without a build, with a draft and machine-readable; verify they fail without the change
  - Verified: `tests/test_query_check.py`; the build of origin/main ends with a traceback and names nothing, and the check does not exist there
- [x] 1.4 Test that a text a program might read as a number is none, in the SQL of both targets; verify by running it
  - Verified: `test_what_is_a_number`: 12 texts; both targets use the one pattern

## 2. shacl2flink

- [x] 2.1 Recognise attributes by their patterns and bring every way of writing one into one form (D1, D2); verify the scenarios of "An attribute is recognised by the pattern that reads it" pass
  - Verified: the forms "blank node" to "in no shape, compared" of task 1.1 pass
- [x] 2.2 Read a variable predicate (D3); verify its scenarios pass
  - Verified: the forms "any …" of task 1.1 pass
- [x] 2.3 Compare numbers as numbers and entities as IRIs (D4); verify their scenarios pass
  - Verified: the forms of numbers, texts and entities of task 1.1 pass
- [x] 2.4 Let `$this` be an entity from the first pattern on, keep every condition, give subqueries their own tables, join groups and keep the `FILTER` of an `OPTIONAL` (D5, D6), and refuse a second value of an attribute (D6); verify the scenarios of "A compiled expression answers what SPARQL answers" pass
  - Verified: the forms of EXISTS, OPTIONAL and one value in two places of task 1.1 pass, the second values are refused (task 1.2)
- [x] 2.5 Report every problem in one run, and offer the check without a build (D7, D8); verify task 1.3 passes
  - Verified: task 1.3 passes
- [x] 2.6 Run the unit tests, the linter and all SQL fixtures; verify they pass and no expected result of a fixture changed (a model whose result rests on an invented time gets a real one)
  - Verified: 1166 passed (with #1097's tests); `flake8` is clean; the 135 models of the kms-constraints, kms-rules and sql-cases fixtures pass with no expected result changed; `kms-rules/test4/model4` has an `observedAt` now, as its siblings do; coverage of the changed lines 92 %. The kms-udf fixtures run in CI

## 3. Flink

- [x] 3.1 Add SPARQL constraints of the changed kinds to the end-to-end package (an attribute declared without a target, a variable predicate, numbers without a cast, `OPTIONAL` first, the same attribute in a `NOT EXISTS`) and a test that writes entities through the context broker and reads the alerts; verify it passes on a cluster and fails without the change
  - Verified: the test "sparql constraints of every supported kind answer as SPARQL does, through scorpio and the bridge" passes in the Flink end-to-end run of the pull request; the compiler of origin/main cannot build the package
- [x] 3.2 Run every form of task 1.1 as a constraint on Flink and compare the alerts with SPARQL; record the result in the pull request
  - Verified: run on Flink 1.20 in streaming mode, over tables with the rows of the test model: the 99 forms and the 6 from the other end, 0 differences to SPARQL (the queries themselves; the alerts around them are those of task 3.1)

## 4. Documentation

- [x] 4.1 Document the supported forms, the comparison of numbers and the check in `docs/supported-features.md` and the README; verify it says what the delta requires
  - Verified: `docs/supported-features.md` has the forms, the comparison and what is not supported; the README names the check
