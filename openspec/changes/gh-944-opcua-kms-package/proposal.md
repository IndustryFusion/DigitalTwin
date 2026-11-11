# Proposal

Issue: #944

## Why

The OPC UA tools turn a NodeSet into an ontology (`nodeset2owl.py`) and into
entities, shapes and a context (`owl2instances.py`). What comes out is a set of
loose files that every consumer assembles itself: no descriptor, no version, the
imported companion specifications referenced by `owl:imports` instead of being
contained (as `file:///` paths on the machine that built them, for local
inputs), and nothing checks the result against the KMS package format (#939).
An OPC UA machine therefore cannot be handed over, verified or versioned like
`kms/example`.

This change adds the producer: a tool that assembles the output of the OPC UA
chain into a KMS package, a `package` target per example, and a `Build` step
that generates and verifies the example packages without committing them.

## What Changes

- New tool `semantic-model/opcua/owl2kms.py` that writes a KMS package from
  the instance ontology (`nodeset2owl.py`) and the entities, shapes, instances
  and context (`owl2instances.py`):
  - `knowledge/` holds the instance ontology, the entities and every ontology
    they import, one file each; imports of copied files name the copied
    ontology, never a location on the building machine;
  - `shacl.ttl`, `model-instance.jsonld` and `context.jsonld`;
  - the NGSI-LD vocabulary copied into `vocabulary/`;
  - `kms.yaml` with `name`, `version` (default `0.1.0`) and `format: 1`.
- The package holds the **main model only**: no examples suite. It is a draft
  with 0 % coverage and is not publishable.
- Assembly is reproducible: the same inputs give the same package digest, on
  any machine.
- `translate_pumpExample.make`, `translate_laserExample.make` and
  `translate_simpleExample.make` get a `package` target writing
  `semantic-model/kms/opcua-<example>` (`opcua-pumps`, `opcua-laser`,
  `opcua-simple`).
- Generated packages are **built in CI and never committed**: the `Build`
  workflow generates and verifies the three example packages, and
  `semantic-model/kms` ignores them in git.

## Capabilities

### New Capabilities
- `opcua/kms-packaging`: How the OPC UA tools assemble a KMS package from an
  OPC UA model, what it contains, how it is kept reproducible and standalone,
  and how the example packages are generated and checked in CI.

### Modified Capabilities

None. The package format is `contracts/kms-package` from #940; this change is a
producer of it and does not change it.

## Impact

- OPC UA tools (`semantic-model/opcua`): new `owl2kms.py` and its library, new
  `package` targets, tests, README.
- `semantic-model/kms`: a `.gitignore` for generated `opcua-*` packages.
- `Build` workflow: a job of its own, `opcua-kms-packages`, sets up the
  SemForge SDK, generates the example packages and verifies them, in parallel
  with the `build` job.
- Contract between components: no change. Consumers (shacl2flink, SemForge)
  read the generated packages like any other.
- Depends on #940 (the format and `semforge verify`). Implementation starts
  after #940 is merged.

## Out of Scope

- Examples or tests for generated packages, and publishing them.
- Dependencies between packages, sharing the OPC UA base as one package, and
  delta packages that add a machine to an existing setup.
- Changing `nodeset2owl.py` or `owl2instances.py` beyond what reproducible
  packaging needs.
- Committing generated packages.
