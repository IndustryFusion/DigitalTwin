# Tasks

## 1. Tests first

- [x] 1.1 Add `tests/test_owl2instances_properties.py` in `semantic-model/opcua`: without options Properties are followed, `--no-properties` leaves `HasProperty` out, `-p`/`--properties` changes nothing and does not undo `--no-properties` in either order, and `--help` describes both options; verify it fails on `main` and passes with the change
  - Verified: 7 cases pass with the change; on `main` all 7 fail (`--no-properties` is unknown, `get_ignored_hierarchical_references` does not exist)
- [x] 1.2 Add the golden case `test_reference_types_no_properties` to `tests/owl2instances/test.bash` (the nodeset of `test_reference_types_properties`, run with `--no-properties`) with goldens that hold no `test:hasMyProperty`; keep `-p` on `test_reference_types_properties` with its golden unchanged; drop `-p` from `test_interfaces`; verify `bash test.bash` fails on `main` for the new case
  - Verified: `bash test.bash` passes with the change; the new goldens differ from those of `test_reference_types_properties` only by `test:hasMyProperty` (4 attributes, 5 property shapes); on `main` `owl2instances.py` rejects `--no-properties`, so the case compares stale output and fails
- [x] 1.3 Add `tests/kms-packages/pumps-engineering-units.query` and run it from `make kms-packages-check`, together with a check that the package's `knowledge/entities.ttl` does not mention `hasEngineeringUnits`; verify the check fails, naming `opcua-pumps`, on a pump package built with `--no-properties` and passes on one built with the change
  - Verified: on the package built at `main` (no Properties) it fails with "opcua-pumps: no opcua:hasEngineeringUnits on pumps:hasMotorTemperature, see tests/kms-packages/pumps-engineering-units.query"; on the packages built with the change `make kms-packages-check` passes
- [x] 1.4 In the OPC UA chain test, expect 22 entities and 64 bindings (stages 1 and 2), 53 distinct attributes sent and 11 unset nodes, a sent `devices:hasManufacturer`, and no message for the unset `opcua:hasSize`; verify stages 1 to 4b pass with the change and stage 1 fails on `main`
  - Verified: locally stages 1, 2, 3, 4a and 4b pass (22 entities load into the pinned Scorpio, 64 bindings found, 53 attributes sent and mapped, `devices:hasManufacturer` = `ExampleManufacturer`); `main`'s message check fails on the new messages ("distinct attributes sent: 53"), and `main`'s output has 21 entities and 46 bindings, so the new stage 1 fails there

## 2. owl2instances.py

- [x] 2.1 Follow Properties by default, add `--no-properties`, keep `-p/--properties` as a no-op with that help text; verify tasks 1.1 and 1.2 pass
  - Verified: tasks 1.1 and 1.2 pass; `flake8` is clean
- [x] 2.2 Drop `-p` from `translate_laserExample.make` and `translate_type_contracts.make`; verify `make kms-packages` builds the three packages and `make kms-packages-check` passes, and that `opcua-laser` has the same digest as before
  - Verified: `make kms-packages` builds all three, `make kms-packages-check` passes; `opcua-laser` has digest `sha256:194bc4c6…0855` both at `main` and with the change; `opcua-pumps` with the change has the digest of `main`'s pump package built with `-p` (`sha256:3973c67b…c1270`)

## 3. Regenerated output

- [x] 3.1 Regenerate `tests/owl2instances/test_pumps_instanceexample.instances`; verify the only differences to the old golden are the added Properties (attributes and sub-attributes) and `bash test.bash` passes
  - Verified: the graph difference consists of added Properties (nameplate, file Properties, `hasEngineeringUnits`, `hasEURange`, `hasDefinition`, …) and the blank nodes of attributes that now carry sub-attributes; every other golden is unchanged; `bash test.bash` passes
- [x] 3.2 Leave the SemForge test corpus `tests/corpus/opcua-pumps` unchanged (design, D5); verify the SemForge unit tests on it and the VS Code e2e test `25-opcua` pass as on `main`
  - Verified: the SDK is not changed by this change; with the current corpus `25-opcua` passes 6 of 6. A re-sliced corpus was tried and dropped, see D5
- [x] 3.3 Verify `make test-opcua-shapes` in `semantic-model/shacl2flink` compiles the new golden shapes, and `make build KMS=../kms/opcua-pumps` completes on the new pump package
  - Verified: `test-opcua-shapes`: 26 compiled, 1 skipped (size), 0 failed, including `test_reference_types_no_properties`; `make build` on the new pump package completes in 170 s

## 4. Documentation

- [x] 4.1 Update the `owl2instances.py` usage in the README of the OPC UA tools and add a section on OPC UA Properties: what a Property of an object and of a variable becomes, `--no-properties`, the no-op `-p`, and that sub-attributes are declared in the shapes only, with an example; verify it answers the documentation scenario of the delta
  - Verified: the usage is the tool's `--help` (which also drops the removed `-mi`); the section "OPC UA Properties" covers both kinds of Property, bindings, `--no-properties`, `-p`, and the shapes as the contract for sub-attributes with a Turtle example
- [x] 4.2 Update the expected counts in the pump tutorial; verify the chain test's stage 1, which runs the tutorial's commands, passes
  - Verified: stage 1 passes with "22 entities" and "64 bindings"

## 5. Verification

- [x] 5.1 Measure the pump package's size and the time of `owl2instances.py`, `semforge verify`/`validate`, `shacl2flink make build` and the SemForge type pages with and without Properties, and state them in the Pull Request
  - Verified: the table in the design, "Size and time", and the Pull Request
- [x] 5.2 Measure the coverage of the changed code (above 80 %) and state it in the Pull Request
  - Verified: of the 7 changed statements in `owl2instances.py`, the unit test covers 6 (86 %); the seventh, the call in `main`, runs in every golden case of `tests/owl2instances` (100 % together). `pytest tests --cov=lib` of the OPC UA tools: 374 passed, 86.6 %
- [x] 5.3 Check every scenario of the delta specifications against the tests and report the result per scenario in the Pull Request
  - Verified: the per-scenario list in the Pull Request
