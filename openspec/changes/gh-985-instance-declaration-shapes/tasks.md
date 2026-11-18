# Tasks

## 1. opcua: declaration shapes

- [ ] 1.1 Detect members that an object child declaration adds beyond its type and supertypes (by browse name), with unit tests for: additions present, none, inherited members not counted as additions. Verified by `make test` in `semantic-model/opcua`.
- [ ] 1.2 Generate the declaration node shape (no target, deterministic IRI from owning type and browse path) from the added members with the same property generation as type shapes, and reference it with `sh:node` on the relationship's `ngsi-ld:hasObject` value shape next to `sh:class`. Verified by a new owl2instances case (direct additions, optional and mandatory members, wrong data type, a declaration without additions) whose expected shapes match and whose instances give the expected pyshacl results.
- [ ] 1.3 Leave child entity types and declarations without additions unchanged. Verified by the full owl2instances suite with unchanged expected files for all existing cases, except the shapes of `test_reference_types_properties`, whose declaration `SubAlphaInstance` adds `SubB2` and now gets its declaration shape (its instances stay identical).
- [ ] 1.4 Collect additions more than one relationship deep and report them once per owning type with count and browse paths. Verified by the new case (an addition two relationships deep: no shape for it, exactly one report line for the owning type).
- [ ] 1.5 Constrain placeholder members that a declaration adds like type-defined placeholders: class per instance, count of distinct datasetIds, at least one instance for a mandatory placeholder; decide membership by the whole name for patterns with a fixed part and by type for fully generic placeholders (D10). Verified by the new owl2instances cases: `Item<no>` with a child of the wrong type (reported) and an unrelated child `Inner` (not taken in), `<Part>` with a child of another type (not counted) and a mandatory `<Part>` without instances (reported), with the expected pyshacl results.
- [ ] 1.6 Document the declaration shapes, the one-relationship limit and its report, and placeholder membership (name-based and type-based, with an example each, and the limitation of fully generic placeholders) in `semantic-model/opcua/README.md`. Verified by review against the documentation requirement.
- [ ] 1.7 Measure the coverage of the changed generator code and keep the component gate. Verified by `pytest --cov` output (above 80 % for the changed modules), stated in the PR.

## 2. shacl2flink: relationship node checks

- [ ] 2.1 Keep attribute instances apart in the offline models: correlate `datasetId`, value and the other sub-attributes through the attribute instance for properties, relationships, list and JSON properties; review the expected results of existing cases with equal values across instances. Verified by SQLite cases for every scenario of the attribute-instances spec (equal values with and without a datasetId for all four kinds, a minimum count of three) and `make test-pyshacl-compare` with no new divergence.
- [ ] 2.2 Exclude `sh:node` references on a `ngsi-ld:hasObject` value shape from substitution and extract them as relationship node checks; keep node-level and same-focus `sh:node` as today. Verified by unit tests for extraction and by the unchanged existing `sh:node` tests.
- [ ] 2.3 Reject at build time, naming the shape: a property shape directly underneath `ngsi-ld:hasObject`, a declaration shape that applies `sh:node` to a further relationship's object, and a declaration shape that produced no constraint. Verified by build-rejection tests.
- [ ] 2.4 Generate the check for SQLite and Flink: the declaration shape compiled as an ordinary shape over the node focus (the entities the relationships refer to, design D6), its circuit tops combined per owning entity and relationship instance with a pinned accumulator, one `NodeConstraintComponent(<path>[<index>])` alert on the owning entity whose text lists the referenced entity and every violated inner constraint in a stable order. Verified by SQLite cases for every scenario of the shacl2flink spec (missing attribute, conforming, two violations one alert, two relationship instances, a placeholder relationship with three datasetIds where only one referenced entity violates, a count of distinct instances inside the node shape, repair clears, deleted referenced entity raises, datatype leaf).
- [ ] 2.5 Compare the SQLite results of the new cases with pyshacl in the pyshacl comparison. Verified by `make test-pyshacl-compare` with no new divergence.
- [ ] 2.6 Compile all shapes in the repository (KMS packages, test fixtures, the opcua shapes test) against the new rejection rules and fix any shape that relied on the silent acceptance. Verified by `make test test-kms test-opcua-shapes` in `semantic-model/shacl2flink`.
- [ ] 2.7 Document the check, the alert, the one-relationship limit and the rejected forms in `docs/supported-features.md`. Verified by review against the spec's documentation requirement.
- [ ] 2.8 Measure the coverage of the changed compiler code and keep the component gate. Verified by `pytest --cov` output (above 80 % for the changed modules), stated in the PR.

## 3. SemForge SDK: cause and reach

- [ ] 3.1 Read `sh:detail` recursively in the validation adapter and attach the inner results as the cause of the outer result, keeping its identity. Verified by unit tests (one outer result, cause lists the inner violations; expectations and coverage unchanged).
- [ ] 3.2 Show the cause in the validation report and in the editor's violation display (entity pages, Problems panel). Verified by unit tests of the report and by an editor test on a corpus package with the nested form.
- [ ] 3.3 Count a declaration shape reached through a relationship's `sh:node` as reached by the referenced entities. Verified by a unit test of the shape page reach (no "never reached / never fired" while such entities exist).
- [ ] 3.4 Add a corpus package with the nested form and an expectation on the owning shape's relationship node constraint. Verified by `make test` (the expectation is met and not stale) and `make kms-check`.
- [ ] 3.5 Measure the coverage of the changed SDK code and keep the component gate. Verified by `pytest --cov` output (above 80 % for the changed modules), stated in the PR.

## 4. End to end

- [ ] 4.1 Generator to compiler: feed the shapes of the new owl2instances case into the opcua shapes test so they compile and their checks run. Verified by `make test-opcua-shapes`.
- [ ] 4.2 Streaming end to end: add an owning type with a declaration shape to the e2e KMS of `make test-flink-e2e`, with bats tests through Kafka and through the NGSI-LD API to Alerta: the alert raises, clears when the referenced entity is repaired, raises when it is deleted, and follows attribute changes; a placeholder relationship with several datasetIds raises one alert only for the violating instance. Verified by `make test-flink-e2e` on a local cluster and in the K8s tests workflow.
- [ ] 4.3 State longevity: add a family for the check to `tools/ttl_test.py` (raise, retract, referenced entity deleted, after three times the state TTL idle). Verified by a ttl_test run on a local cluster with the result recorded in the PR.
- [ ] 4.4 KMS package: build a package from the new owl2instances case and verify it. Verified by `semforge verify` and `semforge check` with no error, and the nested violation shown with its cause by `semforge validate`.

## Workflow follow-up

- Per-scenario verification list in the PR body (scenario → test or platform check), with the coverage numbers.
- After the merge: archive the change in a follow-up PR (`Closes #985`).
