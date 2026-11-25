# Tasks

## 1. Tests first

- [ ] 1.1 Add the kms-constraints fixture `test29`: shapes with `sh:datatype` and no `sh:nodeKind` (plain, inside `sh:or`, `sh:not` and `sh:xone`, on a sub-attribute), next to shapes whose verdicts must not change, and entities with strings, numbers, booleans, declared types, IRIs, Relationship, ListProperty, JsonProperty and several datasetIds; verify `tests/sql-tests/tests.sh test29` fails before the change
- [ ] 1.2 Extend `tests/test_datatype_check.py` with the rows each side fills for a shape without a node kind and with the guards for the other node kinds; verify the new tests of a missing node kind fail before the change

## 2. shacl2flink

- [ ] 2.1 Let the datatype check read a value shape with a datatype and no node kind (D1 to D4); verify tasks 1.1 and 1.2 pass, `make lint` and `make test` pass
- [ ] 2.2 Run all sql-tests; verify no existing expected result changes
- [ ] 2.3 List the naming divergences of the fixture in `tests/pyshacl-compare/expected-divergences.txt`; verify `make test-pyshacl-compare` reports no missed or extra divergence
- [ ] 2.4 Document in the `sh:datatype` entry of `docs/supported-features.md` that the check does not need `sh:nodeKind`; verify the entry says what the documentation scenario requires

## 3. Flink

- [ ] 3.1 Add the shapes without `sh:nodeKind` to `tests/e2e-kms` and their cases to `tests/bats/test-shacl-flink-scorpio-e2e`; verify the package compiles
- [ ] 3.2 Verify the Flink e2e test passes in the Pull Request's K8s e2e workflow and report the run

## 4. Verification

- [ ] 4.1 Check every scenario of the delta specification against the tests and report the result per scenario in the Pull Request
