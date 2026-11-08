# Proposal

Issue: #939

## Why

A KMS (Knowledge, Model, Shapes) is the input of almost every semantic
component, but nothing defines what one is. shacl2flink, the dataservice, the
debezium bridge chart, the Fuseki upload and the end-to-end tests each hard-code
`knowledge.ttl`, `shacl.ttl` and `model-instance.jsonld`. The SemForge SDK reads
more than that (each part may be a directory of files, a descriptor, examples
beside the model), so a KMS that SemForge accepts can break every other
consumer. There is no way to hand a KMS over as one file and know that it
arrived complete and unmodified, no rule for when a KMS needs a new version,
and `semantic-model/kms` can hold only one KMS.

This change makes the KMS package an official format, generalised from what the
SemForge SDK already reads, with a verified archive form and immutable
published versions, and turns `semantic-model/kms` into a directory of
packages. Consumers and producers adopt the format in their own changes.

## What Changes

- Define the **KMS package**: a directory with the descriptor `kms.yaml`
  (`name`, `version`, `format: 1`), three roles (knowledge, shacl,
  model-instance), each **one file or one directory of files**, an optional
  context, examples suite and documentation, and a defined list of members.
  A role present in two forms makes the package invalid.
- Packages are **standalone**: nothing in a package refers to a local file
  outside it.
- Define the **distribution form** `<name>-<version>.kms.zip`: the members plus
  a `SHA256SUMS` file. The **package digest** is the SHA-256 of `SHA256SUMS`.
  Packing is deterministic. An archive is verified in full before any of it is
  used.
- **Published versions are immutable**: a package records each published
  version and its digest; a package whose published version no longer has that
  digest fails verification until its version is raised.
- **Only tested versions are published**: every example of the suite must
  meet its expectations, and the share of constraints that some example makes
  fire must reach the package's threshold (`tests.coverage`, default 80 %).
  The release record keeps the results. Drafts are not gated. CI runs the
  tests of every package in `semantic-model/kms`.
- **`semantic-model/kms` becomes a directory of packages**: today's KMS moves to
  `kms/example/`, and `kms/default` is a link to the package used when none is
  named. Other directories in `kms/` that are not packages, such as
  `SchweissenUndSchneiden/`, are ignored. Paths into `kms/` are updated.
- SemForge SDK: `semforge pack`, `verify`, `publish` and `version`; every
  command that reads a package also reads an archive; the editor warns when a
  published package is changed; `init` creates a conforming package; existing
  names (`semforge.yaml`, `main.jsonld`, `shapes/`) keep loading and are
  reported as not conforming.

## Capabilities

### New Capabilities
- `contracts/kms-package`: What a KMS package is in its directory and archive
  forms, how its integrity and its published versions are checked, how
  `semantic-model/kms` holds packages, and what a consumer may rely on.
- `semforge-sdk/package-tools`: How the SemForge SDK creates, packs, verifies,
  publishes, versions and loads KMS packages.

### Modified Capabilities

None.

## Impact

- Contract between components: **yes**, this creates it. Consumers of a KMS:
  shacl2flink, dataservice, kafka-bridges (debezium bridge knowledge
  ConfigMap), the Fuseki upload, `test/bats`. In this change only their paths
  into `semantic-model/kms` change (to `kms/default`); reading packages is
  their own follow-up change.
- SemForge SDK (`semantic-model/SemForge-SDK`): new commands, descriptor
  `kms.yaml`, archive input, the published-version warning in the editor.
- `semantic-model/kms`: becomes `kms/example/` plus the link `kms/default`;
  gains `kms.yaml` (from `semforge.yaml`) and its NGSI-LD vocabulary inside the
  package (`vocabulary/ngsild.ttl`).
- `Build` workflow: runs the tests of every package in `semantic-model/kms`.
- shacl2flink `Makefile`: default `SHACL`, `KNOWLEDGE`, `MODEL` and the
  `ontology2kms` target point into `kms/default/`.
- No change to any image, chart or deployment.
- `kms/example` has 6 examples, all passing, that make 4 of its 117
  constraints fire as asserted (3.4 %). It stays a draft until its coverage
  reaches 80 %; raising it is a follow-up.

## Out of Scope

- **Consumers**: shacl2flink, the dataservice, kafka-bridges, Fuseki and
  `test/bats` reading packages and checking their integrity.
- **OPC UA**: a separate assembler `owl2kms.py` that builds a package from the
  output of `nodeset2owl.py` and `owl2instances.py`.
- **Version suggestions**: proposing patch, minor or major from the semantic
  diff. This change offers all three and lets the author choose.
- **Delta packages and dependencies**: packages that add to an existing setup,
  dependencies between packages, `owl:imports` of remote ontologies by URI,
  and scoped package names (e.g. `iff/opcua-pumps`).
- Coverage of inference rules (`sh:rule`), and raising `kms/example` to 80 %.
- Where published archives are stored (GitHub releases, a registry), and
  signatures.
- Turning `SchweissenUndSchneiden/` into a package.
