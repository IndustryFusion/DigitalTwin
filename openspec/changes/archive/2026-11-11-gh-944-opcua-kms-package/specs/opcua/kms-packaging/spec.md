# Delta for OPC UA KMS Packaging

## Purpose

Defines how the OPC UA tools turn an OPC UA model, translated by
`nodeset2owl.py` and `owl2instances.py`, into a KMS package as defined by the
contract `contracts/kms-package`: what the package contains, how it stays
standalone and reproducible, and how the example packages are generated and
checked in CI without being committed.

## ADDED Requirements

### Requirement: The OPC UA chain produces a KMS package
`owl2kms.py` SHALL write a directory that passes `semforge verify`, from the instance ontology written by `nodeset2owl.py` and the entities, shapes, instances and context written by `owl2instances.py`. It SHALL refuse an output directory that exists and is not empty.

#### Scenario: Pump example
- **WHEN** `owl2kms.py` is run on the output of the pump example's chain
- **THEN** the directory it writes passes `semforge verify`

#### Scenario: Existing output
- **WHEN** the output directory already holds files
- **THEN** nothing is written and the tool exits with an error naming the directory

### Requirement: The package holds the model and its whole type system
The package's knowledge SHALL be a `knowledge/` directory holding the instance ontology, the entities and every ontology they import through `owl:imports`, transitively, one file each. W3C vocabularies and the NGSI-LD vocabulary SHALL NOT be copied there. An import that cannot be read SHALL make the tool fail, naming it.

#### Scenario: Companion specifications contained
- **WHEN** the pump example's instance ontology imports the Pumps, Machinery, DI and core ontologies
- **THEN** all of them are files in `knowledge/`, and every `sh:targetClass` in `shacl.ttl` names a class declared in `knowledge/`

#### Scenario: Unreadable import
- **WHEN** an imported ontology is neither a readable file nor a reachable URL
- **THEN** no package is written and the error names that import

### Requirement: Nothing refers to the machine that built the package
No member SHALL refer to a location on the machine that assembled it. An `owl:imports` of a file that was copied into the package SHALL name the copied ontology's IRI instead of its file path. The descriptor SHALL record where each knowledge file came from only as a URL or as a name relative to the inputs.

#### Scenario: Local inputs
- **WHEN** the chain runs on locally built ontologies, so that `nodeset2owl.py` writes `owl:imports <file:///…>`
- **THEN** no member of the package contains `file:` or the absolute path of the build directory

### Requirement: The package is standalone
The NGSI-LD vocabulary SHALL be copied into the package as `vocabulary/ngsild.ttl` and declared in the descriptor. The context SHALL be the local `context.jsonld` written by `owl2instances.py`, with the published context URL declared beside it.

#### Scenario: Offline verification
- **WHEN** a generated package is verified on a machine without network access
- **THEN** `semforge verify` passes and fetches nothing

### Requirement: The descriptor names and versions the package
The descriptor SHALL be `kms.yaml` declaring `name`, given by the caller, `version`, given by the caller and `0.1.0` by default, and `format: 1`. The tool SHALL refuse a name or a version the KMS package format does not allow.

#### Scenario: Default version
- **WHEN** `owl2kms.py` is run with `--name opcua-pumps` and no version
- **THEN** `kms.yaml` declares `name: opcua-pumps`, `version: 0.1.0` and `format: 1`

#### Scenario: Invalid version
- **WHEN** `--version 1.0` is given
- **THEN** nothing is written and the error says that the version must be `MAJOR.MINOR.PATCH`

### Requirement: The package holds the main model only
The package SHALL hold no examples suite. It is a draft: its coverage is 0 % unless it has no constraints, and it is not publishable.

#### Scenario: Coverage of a generated package
- **WHEN** `semforge verify --tests` is run on a generated package with constraints
- **THEN** it passes and reports 0 examples and 0 % coverage

#### Scenario: Publishing a generated package
- **WHEN** `semforge publish` is run on a generated package with constraints
- **THEN** it refuses, because the coverage is below the threshold

### Requirement: Assembly is reproducible
Running the chain and the tool twice on the same inputs SHALL give the same package digest, on the same machine and on different machines and directories.

#### Scenario: Two builds
- **WHEN** the pump example is packaged twice, in two different directories
- **THEN** both packages have the same package digest

### Requirement: Each instance example has a package target
`translate_pumpExample.make`, `translate_laserExample.make` and `translate_simpleExample.make` SHALL each provide a `package` target that runs the chain and writes the package `opcua-pumps`, `opcua-laser` or `opcua-simple` into `semantic-model/kms`. The output directory SHALL be overridable.

#### Scenario: Pump package target
- **WHEN** `make -f translate_pumpExample.make package` is run in `semantic-model/opcua`
- **THEN** `semantic-model/kms/opcua-pumps` is written and passes `semforge verify`

#### Scenario: shacl2flink reads it
- **WHEN** `make build KMS=../kms/opcua-pumps` is run in `semantic-model/shacl2flink`
- **THEN** the build completes

### Requirement: Generated packages are built in CI and never committed
The `Build` workflow SHALL generate the three example packages and verify each with `semforge verify`; a package that does not verify SHALL fail the build. `semantic-model/kms` SHALL ignore generated `opcua-*` packages in git.

#### Scenario: Broken generation
- **WHEN** a change makes a generated package fail `semforge verify`
- **THEN** `Build` fails and names the package

#### Scenario: Nothing to commit
- **WHEN** the example packages have been generated in a working copy
- **THEN** `git status` shows no new files under `semantic-model/kms`
