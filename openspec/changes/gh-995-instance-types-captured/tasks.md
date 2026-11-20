# Tasks

## 1. Test models

- [ ] 1.1 `semantic-model/opcua/tests/owl2instances/test_declaration_types.NodeSet2.xml`: a type `AlphaType` with a
  mandatory child `Blocks` of type `FolderType` whose declaration adds, with `HasAddIn`, a child `State` of type
  `BetaType`; `BetaType` defines a mandatory variable `Level`. `AlphaType` also declares a child `Delta` of type
  `DeltaType` (with a mandatory variable) whose instance uses `DeltaSubType`, a subtype without members of its own.
  One instance of `AlphaType` whose `State` lacks `Level` and whose `Blocks` carries an extra variable that only the
  instance adds. Verified: `nodeset2owl.py` translates it without error.
- [ ] 1.2 `test_instance_types.NodeSet2.xml`: `AlphaType` declares a mandatory child `Unit` of `UnitType` (mandatory
  `Count`); the instance's `Unit` uses `UnitSubType`, which adds a mandatory `Extra`, and lacks it. The instance
  organizes an object of `ZetaType` (mandatory `Level`, referenced by no type) that lacks `Level`, and an object of
  plain `BaseObjectType`. Verified: `nodeset2owl.py` translates it without error.
- [ ] 1.3 A type without a definition: `nodeset2owl.py` refuses a nodeset whose instance names an undefined type
  definition, so such a type only reaches `owl2instances.py` through an ontology not written by `nodeset2owl.py`.
  Covered by a unit test of the coverage helpers instead of a nodeset.

## 2. Types of the instance nodes get their shapes

- [ ] 2.1 Determine the root entities before the shapes are written, and before writing them scan, with the existing
  type scan, every object type of the instance nodes reachable from the root entities that needs a shape and has
  none (design D1). Verified by 5.1 and 5.2: on main, `test_instance_types` has no shape for `UnitSubType` and
  `ZetaType` and pyshacl reports it conformant; with the change both shapes exist and both violations are reported.
- [ ] 2.2 Keep `--shacl-only`, `--type-all`, `-eid` and `--maximalshacl` working with the earlier root entities.
  Verified: all existing cases in `tests/owl2instances/test.bash` pass unchanged.

## 3. Attributes of the entities are declared

- [ ] 3.1 When an entity is written, declare every attribute without a domain among the entity's type and its
  supertypes, in the written or the loaded ontologies, with the entity's type as domain (design D2). Verified by 5.3.

## 4. Coverage warning

- [ ] 4.1 After the outputs are written, write one `UNCOVERED_INSTANCE_TERMS` warning grouped per type, with the
  definitions of design D3; suppressible with `-sw`; exit status unchanged. Verified by 5.4 and 5.5.

## 5. Tests (one per scenario of `specs/opcua/instance-coverage/spec.md`)

- [ ] 5.1 Shapes. `test.bash` cases with expected `.shacl`, `.instances` and `.pyshacl`, and `.shaclquery` files:
  - *Type added in a folder's declaration*: `test_declaration_types.NodeSet2.shaclquery1` (shape of `BetaType`
    requiring `hasLevel`).
  - *Instance of a subtype that adds a member*, *Type reached only through Organizes*, *Type without rules*:
    `test_instance_types.NodeSet2.shaclquery1` (shapes of `UnitSubType` requiring `hasExtra` and of `ZetaType`
    requiring `hasLevel`; no shape targeting `BaseObjectType`).
  - *Subtype without own members*: `test_declaration_types.NodeSet2.shaclquery1` (no shape targeting
    `DeltaSubType`).
  - *Missing mandatory members found*: the `.pyshacl` files of both cases (one violation each for `State`, `Unit`,
    `Zeta`).
- [ ] 5.2 *Same shape on both paths*: in `test.bash`, generate the shapes with `-t BetaType` and compare the node
  shape targeting `BetaType` with the one from `test_declaration_types` for isomorphism.
- [ ] 5.3 Ontology. `.query` files on `entities.ttl`:
  - *Types reached only through instance nodes*: `test_instance_types.NodeSet2.query1` (classes `UnitSubType` and
    `ZetaType` with their superclasses).
  - *Attribute of a type reached only through instance nodes*: `test_declaration_types.NodeSet2.query1` and
    `test_instance_types.NodeSet2.query1`.
  - *Attribute added by a declaration*: `test_declaration_types.NodeSet2.query2` (`hasState`, `hasExtra` with domain
    `FolderType`).
  - *Attribute declared in an imported ontology*: unit test `test_covering_domain_over_graphs`, and the pump
    package's `entities.ttl` is unchanged (5.7) although its instances carry attributes of the Pumps and Machinery
    ontologies.
  - *Node reference*: the node reference check at the end of `test.bash` (`-nr`: the entities carry
    `base:hasNodeRef`, `entities_node_reference.query` finds it declared with the domain `BaseObjectType` only, the
    warning does not name it).
- [ ] 5.4 Warning, in `test.bash` (`UNCOVERED_EXPECTED`) and `tests/test_libinstance_coverage.py`:
  - *Member added only by the instance*: `test_declaration_types` names `test:hasExtra`.
  - *Member added more than one relationship deep*: `test_declaration_additions` names `test:hasDeep`.
  - *Member added by a declaration*: unit test `test_declaration_shape_constrains_the_referred_entity`, and
    `test_declaration_additions` does not name the members its declaration shapes constrain.
  - *Subtype with members of its own without a shape*: unit test
    `test_subtype_with_own_members_without_shape_is_named`.
  - *Type without a definition*: unit test of `uncovered_terms` for an undefined type.
  - *Gaps reported once*: the node reference check at the end of `test.bash` asserts exit status 0 and exactly one
    `UNCOVERED_INSTANCE_TERMS` line for `test_instance_types`.
- [ ] 5.5 *Nothing uncovered*: `test.bash` asserts that `UNCOVERED_INSTANCE_TERMS` does not appear for the existing
  cases, except those listed in the script because their instances carry members no type or declaration rule covers.
- [ ] 5.6 *Unused companion specification types*: for `test_pumps_instanceexample` (imports Machinery, uses none of
  its state machines), `test_pumps_instanceexample.shaclquery1` asserts that no node shape targets a Machinery state
  machine type.
- [ ] 5.7 *Example packages*: run `make kms-packages kms-packages-check` in `semantic-model/opcua` with the change and
  with main; compare `model-instance.jsonld` (identical), `shacl.ttl` (isomorphic) and list what `entities.ttl` gains.
- [ ] 5.8 End-to-end: `tests/owl2instances/e2e_shacl2flink.bash` builds both cases into KMS packages with
  `owl2kms.py`, runs them through shacl2flink's SQLite check and asserts the alerts: `hasLevel` on `State`; `hasExtra`
  on `Unit` and `hasLevel` on `Zeta`. Part of the opcua `test` target.
- [ ] 5.9 shacl2flink compiles the expected shapes: `make test-opcua-shapes` in `semantic-model/shacl2flink`.
- [ ] 5.10 Coverage of the changed code above 80 %, stated in the Pull Request.

## 6. Finish

- [ ] 6.1 `make lint` and `make test` in `semantic-model/opcua` pass.
- [ ] 6.2 The Pull Request lists every scenario with its test (5.1 to 5.8).
