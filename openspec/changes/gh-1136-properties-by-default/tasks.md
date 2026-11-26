# Tasks

## 1. Tests first

- [ ] 1.1 Add `tests/test_owl2instances_properties.py` in `semantic-model/opcua`: without options Properties are followed, `--no-properties` leaves `HasProperty` out, `-p`/`--properties` changes nothing and does not undo `--no-properties` in either order, and `--help` describes both options; verify it fails on `main` and passes with the change
- [ ] 1.2 Add the golden case `test_reference_types_no_properties` to `tests/owl2instances/test.bash` (the nodeset of `test_reference_types_properties`, run with `--no-properties`) with goldens that hold no `test:hasMyProperty`; keep `-p` on `test_reference_types_properties` with its golden unchanged; drop `-p` from `test_interfaces`; verify `bash test.bash` fails on `main` for the new case
- [ ] 1.3 Add `tests/kms-packages/pumps-engineering-units.query` and run it from `make kms-packages-check`; verify the check fails, naming `opcua-pumps`, on a pump package built with `--no-properties` and passes on one built with the change
- [ ] 1.4 In the OPC UA chain test, expect 22 entities and 64 bindings (stages 1 and 2), 53 distinct attributes sent and 11 unset nodes, a sent `devices:hasManufacturer`, and no message for the unset `opcua:hasSize`; verify stages 1 to 4b pass with the change and stage 1 fails on `main`

## 2. owl2instances.py

- [ ] 2.1 Follow Properties by default, add `--no-properties`, keep `-p/--properties` as a no-op with that help text; verify tasks 1.1 and 1.2 pass
- [ ] 2.2 Drop `-p` from `translate_laserExample.make` and `translate_type_contracts.make`; verify `make kms-packages` builds the three packages and `make kms-packages-check` passes, and that `opcua-laser` has the same digest as before

## 3. Regenerated output

- [ ] 3.1 Regenerate `tests/owl2instances/test_pumps_instanceexample.instances`; verify the only differences to the old golden are the added Properties (attributes and sub-attributes) and `bash test.bash` passes
- [ ] 3.2 Re-slice `semantic-model/SemForge-SDK/tests/corpus/opcua-pumps` from the new pump package with `tests/corpus/slice_opcua.py`, keeping its test cases; adapt the tests that list the knowledge files or pick an attribute row; verify the SemForge unit tests pass and the VS Code e2e test on the corpus (`25-opcua`) passes
- [ ] 3.3 Verify `make test-opcua-shapes` in `semantic-model/shacl2flink` compiles the new golden shapes, and `make build KMS=../kms/opcua-pumps` completes on the new pump package

## 4. Documentation

- [ ] 4.1 Update the `owl2instances.py` usage in the README of the OPC UA tools and add a section on OPC UA Properties: what a Property of an object and of a variable becomes, `--no-properties`, the no-op `-p`, and that sub-attributes are declared in the shapes only, with an example; verify it answers the documentation scenario of the delta
- [ ] 4.2 Update the expected counts in the pump tutorial; verify the chain test's stage 1, which runs the tutorial's commands, passes

## 5. Verification

- [ ] 5.1 Measure the pump package's size and the time of `owl2instances.py`, `semforge verify`/`validate`, `shacl2flink make build` and the SemForge unit tests on the corpus with and without Properties, and state them in the Pull Request
- [ ] 5.2 Measure the coverage of the changed code (above 80 %) and state it in the Pull Request
- [ ] 5.3 Check every scenario of the delta specifications against the tests and report the result per scenario in the Pull Request
