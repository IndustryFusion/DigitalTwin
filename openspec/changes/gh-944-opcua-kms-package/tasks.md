# Tasks

## 1. Assembler

- [ ] 1.1 Carry over `owl2semforge.py` and `lib/semforge_package.py` from the earlier branch as `owl2kms.py` and `lib/kms_package.py` (copyright IndustryFusion Foundation); verify the existing tests of the library pass under the new names
- [ ] 1.2 Write `kms.yaml` (`name`, `version` default `0.1.0`, `format: 1`, local and published context, `vocabulary/ngsild.ttl`), copy the vocabulary, refuse invalid names and versions and a non-empty output directory; verify the scenarios of "The descriptor names and versions the package", "The package is standalone" and "The OPC UA chain produces a KMS package"
- [ ] 1.3 Measure whether `nodeset2owl.py` and `owl2instances.py` give identical output for identical input in two directories; verify by diffing two runs of the pump example, and report the result before 1.4
- [ ] 1.4 Rewrite `owl:imports` of copied files to the copied ontology's IRI and keep absolute paths out of the descriptor; make assembly reproducible (and the chain, as far as 1.3 requires); verify "Local inputs" and "Two builds" with the pump example in two directories
- [ ] 1.5 Fail on an unreadable import, naming it; exclude W3C vocabularies and NGSI-LD from `knowledge/`; verify "Companion specifications contained" and "Unreadable import"

## 2. Make targets and CI

- [ ] 2.1 Add a `package` target to `translate_pumpExample.make`, `translate_laserExample.make` and `translate_simpleExample.make`, writing `semantic-model/kms/opcua-<example>` (overridable); verify "Pump package target" and that the three packages pass `semforge verify`
- [ ] 2.2 Add `semantic-model/kms/.gitignore` ignoring `opcua-*/`; verify "Nothing to commit" after generating the three packages
- [ ] 2.3 Generate and verify the three packages in the `Build opcua tools` step, inside its retry loop and after the SemForge SDK step; verify "Broken generation" with a deliberately broken assembler on a scratch branch, and that the step passes on this pull request
- [ ] 2.4 Verify "shacl2flink reads it" (`make build KMS=../kms/opcua-pumps`), "Offline verification", "Coverage of a generated package" and "Publishing a generated package" on the generated pump package

## 3. Documentation

- [ ] 3.1 Describe the `package` step in `semantic-model/opcua/README.md` and the generated `opcua-*` packages in `semantic-model/kms/README.md`; verify the commands in both run as written

## 4. Integration check

- [ ] 4.1 Run `openspec validate gh-944-opcua-kms-package --strict`, the OPC UA tests (`make test`) and `semforge verify` on the three packages; verify all pass, and that `Build` and `K8s tests` pass on the pull request
