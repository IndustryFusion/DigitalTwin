# Tasks

## 1. Tests first

- [x] 1.1 Add the kms-constraints fixtures `test29` (shapes with `sh:datatype` and no `sh:nodeKind`, plain, inside `sh:or` and on a sub-attribute, next to shapes whose verdicts must not change, and entities with strings, numbers, booleans, declared types, IRIs, Relationship, ListProperty, JsonProperty and several datasetIds) and `test30` (a datatype beside and inside connectives, lists with another datatype, list elements, objects and a GeoProperty) and `test31` (spellings of declared literals, `rdf:JSON`, similar type names, branches with a node kind or a path, deactivated shapes and branches); verify `tests/sql-tests/tests.sh` fails on all three before the change
- [x] 1.2 Extend `tests/test_datatype_check.py` with the rows each side fills for a shape without a node kind, the lists with another datatype and the guards for the other node kinds, take the forms of the bridge from `KafkaBridge/test/valueForms.json`, to which `KafkaBridge/test/testLibDebeziumBridgeValueForms.js` holds the bridge, and add `tests/test_datatype_only_checks.py` for what is read out of a shape; verify the new tests of a missing node kind fail before the change

## 2. shacl2flink

- [x] 2.1 Add the constraints of datatypes without a node kind (D1 to D4), the lists of datatypes (D5) and the blank nodes of the model reader (D3); verify tasks 1.1 and 1.2 pass, `make lint` and `make test` pass
- [x] 2.2 Run all sql-tests; verify no existing expected result changes
- [x] 2.3 List the naming divergences of the fixture in `tests/pyshacl-compare/expected-divergences.txt`; verify `make test-pyshacl-compare` reports no missed or extra divergence
- [x] 2.4 Document in the `sh:datatype` entry of `docs/supported-features.md` that the check does not need `sh:nodeKind`; verify the entry says what the documentation scenario requires

## 3. Flink

- [x] 3.1 Add the shapes without `sh:nodeKind` to `tests/e2e-kms` and their cases to `tests/bats/test-shacl-flink-scorpio-e2e`, every verdict of the delta that Flink can show: Scorpio was found to pass all these values on unchanged, except a JSON object, which the bridge drops. Not repeated there are `rdf:JSON`, whose verdicts are the absence of alerts already covered by the unit tests of the bridge's forms, and the branches with a node kind or a path and the deactivated branch, which differ only in the generated rows that `test31` covers; verify the package compiles and its statements equal those without the new shapes
- [ ] 3.2 Verify the Flink e2e test passes in the Pull Request's K8s e2e workflow and report the run

## 4. Verification

- [x] 4.1 Check every scenario of the delta specification against the tests and report the result per scenario in the Pull Request
