# Proposal

Issue: #1136

## Why

`owl2instances.py` follows OPC UA Properties (`HasProperty`) only with
`-p/--properties`. The pump and simple examples, the pump tutorial and every
script that calls the tool without options therefore lose the units and ranges
of analog variables (`EngineeringUnits`, `EURange`) and the Properties of
objects, such as a machine's nameplate. The package `opcua-pumps` built at
`main` holds no `opcua:hasEngineeringUnits` at all; built with `-p` its shapes
hold 319 of them, its instances 23.

## What Changes

- **BREAKING (output):** `owl2instances.py` follows OPC UA Properties by
  default. A Property of an object becomes an attribute of its entity, bound
  like a variable; a Property of a variable becomes a sub-attribute of the
  variable's attribute, constrained in the shapes and filled in the instances.
  Shapes, instances and bindings written without options grow.
- `--no-properties` opts out and writes what the tool writes today without `-p`.
- `-p/--properties` stays accepted and has no effect; `--help` and the README
  say so.
- `translate_laserExample.make` and `translate_type_contracts.make` drop the
  now redundant `-p`. The pump and simple examples now hold the Properties.
- `make kms-packages-check` also checks that the analog variable
  `pumps:hasMotorTemperature` of `pumps:DriveMeasurementsType` carries
  `opcua:hasEngineeringUnits` in its shape.
- The pump example's chain has 22 entities instead of 21 (the `FileType` of
  the pump's technical data, reached only through Properties) and 64 bindings
  instead of 46 (the nameplate and the file's Properties). The pump tutorial,
  the OPC UA chain test and the contract scenario that names the number of
  bindings follow.
- The README of the OPC UA tools states that the shapes are the contract for
  sub-attributes: `entities.ttl` never declares a sub-attribute such as
  `opcua:hasEngineeringUnits`.
- The golden files of `tests/owl2instances` are regenerated from the new
  output.

## Capabilities

### New Capabilities

- `opcua/properties`: how the OPC UA tools translate OPC UA Properties: followed
  by default, the opt-out, the compatible no-op flag, and that the shapes, not
  the entities, declare sub-attributes.

### Modified Capabilities

- `opcua/kms-packaging`: adds the requirement that the package check proves
  the pump package holds the units of its analog variables.
- `contracts/opcua-live-data`: the scenario of "Bindings vocabulary" names 64
  bindings instead of 46. The rule itself, one vocabulary that the generated
  bindings, the dataservice, the test servers and the binding validation agree
  on, does not change.

## Impact

- **semantic-model/opcua**: `owl2instances.py` (options), the example
  makefiles, `Makefile` (`kms-packages-check`), the README, unit tests and the
  `tests/owl2instances` golden files.
- **semantic-model/dataservice**: the pump tutorial's expected counts only. The
  dataservice reads the 18 new bindings with the code it has; no code changes.
- **test/opcua-chain**: expected entity, binding and message counts.
- **semantic-model/SemForge-SDK**: unchanged. Its test corpus `opcua-pumps` is
  a fixed slice of an older chain output (design, D5).
- **Contract between components:** `contracts/opcua-live-data` changes one
  scenario's number, not a rule. Its consumers (dataservice, test servers,
  binding validation) are checked by the OPC UA chain test.
- Packages built by the default chain grow: the pump package's `shacl.ttl`
  from 0.57 MB to 2.65 MB, `model-instance.jsonld` from 27 KB to 58 KB, the
  package from 13 MB to 16 MB; `owl2instances.py` on the pump example from
  49 s to 72 s. `semforge validate` from 17 s to 26 s, `shacl2flink make build` from
  111 s to 170 s (design, Size and time).
- Anyone who built a package without `-p` gets more attributes on rebuild;
  `--no-properties` restores the old output.

## Out of Scope

- Declaring sub-attributes in `entities.ttl`. They stay in the shapes only; the
  documentation says so.
- Bindings of sub-attributes: a Property of a variable keeps the nodeset's value
  and gets no binding, as with `-p` today.
- Removing `-p/--properties`.
- Changing how Properties are translated when followed: the output equals what
  `-p` writes today.
- Rebuilding packages that are not generated in this repository.
- Re-slicing the SemForge test corpus and the SemForge effects found while
  trying it (design, D5).
