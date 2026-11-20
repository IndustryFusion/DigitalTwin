# Tasks

## 1. Test model

- [ ] 1.1 Add `semantic-model/opcua/tests/owl2instances/test_declaration_types.NodeSet2.xml`: a type `AlphaType`
  with a mandatory child `Blocks` of type `FolderType` whose declaration adds, with `HasAddIn`, a child `State` of
  type `BetaType`; `BetaType` defines a mandatory variable `Level`. `AlphaType` also declares a child `Delta` of
  type `DeltaType` (with a mandatory variable) whose instance uses `DeltaSubType`, a subtype without members of its
  own. One instance of `AlphaType` whose `State` lacks `Level` and whose `Blocks` carries an extra variable that
  only the instance adds. Verified: `nodeset2owl.py` translates it without error.
- [ ] 1.2 A type without a definition: `nodeset2owl.py` refuses a nodeset whose instance names an undefined type
  definition, so such a type only reaches `owl2instances.py` through an ontology not written by `nodeset2owl.py`.
  Covered by unit tests of the coverage helpers instead of a nodeset. Verified: the unit test for a type without a
  definition passes (reported as having no shape).

## 2. Types of the instance nodes have their shapes (met by the type pass since #985)

- [ ] 2.1 Measure whether a pre-pass over the types of the instance nodes (design D1) adds any shape on main after
  #985. Verified: `shacl.ttl` with and without the pre-pass is the same for all 26 cases of
  `tests/owl2instances/test.bash` and for the pump, laser and simple example packages; the pre-pass is not
  implemented.

## 3. Attributes of the entities are declared

- [ ] 3.1 When an entity is written, declare every attribute without a domain among the entity's type and its
  supertypes, in the written or the loaded ontologies, with the entity's type as domain (design D2). Verified by 5.3.

## 4. Coverage warning

- [ ] 4.1 After the outputs are written, write one `UNCOVERED_INSTANCE_TERMS` warning grouped per type, listing types
  without a node shape, attributes without a covering domain and attributes that neither a shape of the entity's type
  nor a declaration shape applied to it through a relationship constrains; suppressible with `-sw`; exit status
  unchanged (design D3). Verified by 5.4 and 5.5.

## 5. Tests

- [ ] 5.1 Add the case of 1.1 to `TESTNODESETS` in `tests/owl2instances/test.bash` with expected `.shacl`,
  `.instances` and `.pyshacl` (one violation, on the `State` entity, for `Level`). Verified: passes; on main the
  shapes contain the same type shapes (2.1) and the case fails on the ontology queries of 5.3.
- [ ] 5.2 Path independence: in `test.bash`, generate the shapes once with `-t BetaType` and compare the node shape
  targeting `BetaType` with the one from 5.1 for isomorphism. Verified: passes.
- [ ] 5.3 `.query1`/`.query2` for the case of 1.1: the ontology declares the attributes of the `State` entity with
  `BetaType` (or a supertype) as domain, and the relationship from `Blocks` to `State` with `FolderType` (or a
  supertype) as domain; and that the written ontology has no declaration of the node reference attribute (declared
  by the base ontology). Verified: `.query2` fails on main (`hasState`, `hasExtra` undeclared), all pass with the
  change.
- [ ] 5.4 Warning: the case of 1.1 expects `UNCOVERED_INSTANCE_TERMS` naming the instance-only variable; unit tests
  cover the type without a definition (1.2), a declaration shape constraining the referred entity, and a declaration
  shape not applying to an entity that no relationship refers to. Verified with the warning check of `test.bash` and
  `tests/test_libinstance_coverage.py`.
- [ ] 5.5 No warning on covered models: `test.bash` asserts that `UNCOVERED_INSTANCE_TERMS` does not appear for the
  existing cases, except those listed in the script because their instances carry members no type or declaration
  rule covers (e.g. a reference to a fixed object without a modelling rule, or #985's additions more than one
  relationship deep). Verified: passes.
- [ ] 5.6 No bloat: for `test_pumps_instanceexample` (imports Machinery, uses none of its state machines), a query
  asserts that no node shape targets a Machinery state machine type. Verified: passes.
- [ ] 5.7 Examples: run `make kms-packages kms-packages-check` in `semantic-model/opcua`; compare `instances.jsonld`
  and `shacl.ttl` of the pump, laser and simple examples with main (identical / isomorphic) and list the attribute
  declarations `entities.ttl` gains. Verified: result stated in the Pull Request.
- [ ] 5.8 End-to-end: build the case of 1.1 into a KMS package with `owl2kms.py`, run it through shacl2flink with
  `make build KMS=<package>` and the SQLite check, and assert an alert on the `State` entity for `Level`; the script
  beside `test.bash` is part of the opcua `test` target. Verified: passes.
- [ ] 5.9 shacl2flink compiles the expected shapes: `make test-opcua-shapes` in `semantic-model/shacl2flink`.
  Verified: passes.
- [ ] 5.10 Coverage: measure the coverage of the changed lines of `owl2instances.py` across `test.bash` (coverage
  run) and the pytest suite; above 80 %; state the number in the Pull Request.

## 6. Finish

- [ ] 6.1 `make lint` and `make test` in `semantic-model/opcua` pass.
- [ ] 6.2 Report every scenario of `specs/opcua/instance-coverage/spec.md` with its test in the Pull Request.
