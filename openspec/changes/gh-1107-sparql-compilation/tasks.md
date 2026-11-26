# Tasks

## 1. Tests first

- [ ] 1.1 Add a test that evaluates each supported form as SPARQL on a model and its knowledge, and as the SQL it compiles to on SQLite, and requires the same entities (every form of the delta, each with entities that are found and entities that are not); verify the forms that the issue lists fail without the change
- [ ] 1.2 Add a test that each form that is not supported is refused, with the reason naming it; verify by running it
- [ ] 1.3 Add tests of the report: two expressions of two shapes, a rule, the pattern, the file and line, an unforeseen failure, no stack trace, nothing written; and of the check without a build, with a draft and machine-readable; verify they fail without the change
- [ ] 1.4 Test that a text a program might read as a number is none, in the SQL of both targets; verify by running it

## 2. shacl2flink

- [ ] 2.1 Recognise attributes by their patterns and bring every way of writing one into one form (D1, D2); verify the scenarios of "An attribute is recognised by the pattern that reads it" pass
- [ ] 2.2 Read a variable predicate (D3); verify its scenarios pass
- [ ] 2.3 Compare numbers as numbers and entities as IRIs (D4); verify their scenarios pass
- [ ] 2.4 Let `$this` be an entity from the first pattern on, keep every condition, give subqueries their own tables, join groups and keep the `FILTER` of an `OPTIONAL` (D5, D6), and refuse a second value of an attribute (D6); verify the scenarios of "A compiled expression answers what SPARQL answers" pass
- [ ] 2.5 Report every problem in one run, and offer the check without a build (D7, D8); verify task 1.3 passes
- [ ] 2.6 Run the unit tests, the linter and all SQL fixtures; verify they pass and no expected result of a fixture changed (a model whose result rests on an invented time gets a real one)

## 3. Flink

- [ ] 3.1 Add SPARQL constraints of the changed kinds to the end-to-end package (an attribute declared without a target, a variable predicate, numbers without a cast, `OPTIONAL` first, the same attribute in a `NOT EXISTS`) and a test that writes entities through the context broker and reads the alerts; verify it passes on a cluster and fails without the change
- [ ] 3.2 Run every form of task 1.1 as a constraint on Flink and compare the alerts with SPARQL; record the result in the pull request

## 4. Documentation

- [ ] 4.1 Document the supported forms, the comparison of numbers and the check in `docs/supported-features.md` and the README; verify it says what the delta requires
