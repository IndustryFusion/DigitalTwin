# Tasks

## 1. Test models

- [x] 1.1 `semantic-model/opcua/tests/owl2instances/test_declaration_types.NodeSet2.xml`: a type `AlphaType` with a
  mandatory child `Blocks` of type `FolderType` whose declaration adds, with `HasAddIn`, a child `State` of type
  `BetaType`; `BetaType` defines a mandatory variable `Level`. `AlphaType` also declares a child `Delta` of type
  `DeltaType` (with a mandatory variable) whose instance uses `DeltaSubType`, a subtype without members of its own.
  One instance of `AlphaType` whose `State` lacks `Level` and whose `Blocks` carries an extra variable that only the
  instance adds. Verified: `nodeset2owl.py` translates it without error.
- [x] 1.2 `test_instance_types.NodeSet2.xml`: `AlphaType` declares a mandatory child `Unit` of `UnitType` (mandatory
  `Count`); the instance's `Unit` uses `UnitSubType`, which adds a mandatory `Extra`, and lacks it. The instance
  organizes an object of `ZetaType` (mandatory `Level`, referenced by no type) that lacks `Level`, and an object of
  plain `BaseObjectType`. The `Count` variable of `Unit` refers with `HasEffect` to an object of `EtaType` (mandatory
  `Rate`) that lacks `Rate`. A second child `Unit2` of `UnitType` uses `UnitMethodType`, which adds only a Method,
  and lacks `Count`; a third, `Unit3` of `PlainType` (mandatory `Amount`), uses
  `PlainNoRuleType`, whose members give no rule, and lacks `Amount`. `ZetaType`
  defines an `Organizes` reference, and `Zeta` refers to a variable that refers to an object of `GhostType`. Verified: `nodeset2owl.py` translates it without error.
- [x] 1.3 A type without a definition: `nodeset2owl.py` refuses a nodeset whose instance names an undefined type
  definition, so such a type only reaches `owl2instances.py` through an ontology not written by `nodeset2owl.py`.
  Covered by a unit test of the coverage helpers instead of a nodeset.

## 2. Types of the instance nodes get their shapes

- [x] 2.1 Determine the root entities before the shapes are written, and before writing them scan, with the existing
  type scan, every object type of the instance nodes reachable from the root entities that needs a shape and has
  none (design D1). Verified by 5.1 and 5.2: on main, `test_instance_types` has no shape for `UnitSubType` and
  `ZetaType` and pyshacl reports it conformant; with the change both shapes exist and both violations are reported.
- [x] 2.2 Keep `--shacl-only`, `--type-all`, `-eid` and `--maximalshacl` working with the earlier root entities.
  Verified: all existing cases in `tests/owl2instances/test.bash` pass unchanged, and its no-instances check (shapes
  written with and without `-so`, exit status 0 and 1).

## 3. Attributes of the entities are declared

- [x] 3.1 When an entity is written, declare every attribute without a domain among the entity's type and its
  supertypes, in the written or the loaded ontologies, with the entity's type as domain (design D2). Verified by 5.3.

## 4. Coverage warning

- [x] 4.1 After the outputs are written, write one `UNCOVERED_INSTANCE_TERMS` warning grouped per type, with the
  definitions of design D3; suppressible with `-sw`; exit status unchanged. Verified by 5.4 and 5.5.

## 5. Tests (one per scenario of `specs/opcua/instance-coverage/spec.md`)

- [x] 5.1 Shapes. `test.bash` cases with expected `.shacl`, `.instances` and `.pyshacl`, and `.shaclquery` files:
  - *Type added in a folder's declaration*: `test_declaration_types.NodeSet2.shaclquery1` (shape of `BetaType`
    requiring `hasLevel`).
  - *Instance of a subtype that adds a member*, *Type reached only through Organizes*, *Type reached only through a
    variable's reference*, *Subtype that adds only a Method*, *Subtype whose members give no rule*, *Type without
    rules*, *Type behind an ignored variable*:
    `test_instance_types.NodeSet2.shaclquery1` (shapes of `UnitSubType` requiring `hasExtra`, of `ZetaType` requiring
    `hasLevel` and of `EtaType` requiring `hasRate`; no shape targeting `UnitMethodType`, `PlainNoRuleType`,
    `GhostType` or `BaseObjectType`), and unit tests `test_objects_behind_variables_are_reached`,
    `test_variables_behind_references_are_not_followed`, `test_methods_give_no_rule`, `TestShapeAddsNothing`.
  - *Subtype without own members*: `test_declaration_types.NodeSet2.shaclquery1` (no shape targeting
    `DeltaSubType`).
  - *Missing mandatory members found*: the `.pyshacl` files of both cases (one violation each for `State`, `Unit`,
    `Zeta`, `Eta`, and exactly one each for `Unit2` and `Unit3`).
- [x] 5.2 *Same shape on both paths*: in `test.bash`, generate the shapes with `-t BetaType` and compare the node
  shape targeting `BetaType` with the one from `test_declaration_types` for isomorphism.
- [x] 5.3 Ontology. `.query` files on `entities.ttl`:
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
  - *Organizes reference*: `test_instance_types.NodeSet2.query1` (`opcua:Organizes` with the domain `BaseObjectType`
    only, although `ZetaType` defines one); keys prefixed with the instance ontology's prefixes:
    `tests/test_owl2instances_attributes.py`, also at the declaration.
- [x] 5.4 Warning, in `test.bash` (`UNCOVERED_EXPECTED`) and `tests/test_libinstance_coverage.py`:
  - *Member added only by the instance*: `test_declaration_types` names `test:hasExtra`.
  - *Member added more than one relationship deep*: `test_declaration_additions` names `test:hasDeep`.
  - *Member added by a declaration*: unit test `test_declaration_shape_constrains_the_referred_entity`, and
    `test_declaration_additions` does not name the members its declaration shapes constrain.
  - *Subtype with members of its own without a shape*: unit test
    `test_subtype_with_own_members_without_shape_is_named`.
  - *Type without a definition*: unit test of `uncovered_terms` for an undefined type.
  - *Gaps reported once*: the node reference check at the end of `test.bash` asserts exit status 0 and exactly one
    `UNCOVERED_INSTANCE_TERMS` line for `test_instance_types`.
- [x] 5.5 *Nothing uncovered*: `test.bash` asserts that `UNCOVERED_INSTANCE_TERMS` does not appear for the existing
  cases, except those listed in the script because their instances carry members no type or declaration rule covers.
- [x] 5.6 *Unused companion specification types*: for `test_pumps_instanceexample` (imports Machinery, uses none of
  its state machines), `test_pumps_instanceexample.shaclquery1` asserts that no node shape targets a Machinery state
  machine type.
- [x] 5.7 *Example packages*: run `make kms-packages kms-packages-check` in `semantic-model/opcua` with the change and
  with main; compare `model-instance.jsonld` (identical), `shacl.ttl` (isomorphic) and list what `entities.ttl` gains.
  Verified: shapes, context and instances of all three identical to main; `entities.ttl` of pump and simple too;
  laser's gains 16 triples (none removed), among them the Machinery building blocks' `hasMachineryItemState` and
  `hasMachineryOperationMode` with domain `FolderType`; `kms-packages-check` passes.
- [x] 5.8 End-to-end: `tests/owl2instances/e2e_shacl2flink.bash` builds both cases into KMS packages with
  `owl2kms.py`, runs them through shacl2flink's SQLite check and asserts the alerts: `hasLevel` on `State`; `hasExtra`
  on `Unit`, `hasLevel` on `Zeta`, `hasRate` on `Eta` `hasCount` on `Unit2` and `hasAmount` on `Unit3`. Part of the opcua `test` target; in CI, shacl2flink's Python dependencies live
  in their own venv (`SHACL2FLINK_PYTHON`), because they pin other rdflib versions than the opcua tools.
- [x] 5.9 shacl2flink compiles the expected shapes: `make test-opcua-shapes` in `semantic-model/shacl2flink`.
- [x] 5.10 Coverage of the changed code above 80 %, stated in the Pull Request. Measured: 54 of 59 changed statements
  of `owl2instances.py` in the two cases (92 %); the other five run in `tests/test_owl2instances_attributes.py` and in
  the no-instances check of `test.bash`. `lib/instance_coverage.py` 99 %, `lib` 87 %.

## 6. Finish

- [x] 6.1 `make lint` and `make test` in `semantic-model/opcua` pass.
- [x] 6.2 The Pull Request lists every scenario with its test (5.1 to 5.8).
