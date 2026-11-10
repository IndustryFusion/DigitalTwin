# KMS packages

KMS stands for Knowledge, Model, Shapes. A **KMS package** is the unit in which
an ontology (knowledge), its SHACL constraints and rules (shapes) and NGSI-LD
entities (model) are authored, handed between components and deployed. The
format is the contract `contracts/kms-package` (openspec change
`gh-939-kms-package`); the SemForge SDK (`semantic-model/SemForge-SDK`) creates,
checks, packs and publishes packages.

This directory holds packages, one per subdirectory named after the package:

```text
kms/
├── default -> example        the package used when none is named
├── example/                  the platform's default KMS package
└── SchweissenUndSchneiden/   a directory of examples, not a package
```

`default` is a relative **symbolic link**. Components that need a KMS and are
given none use `kms/default`; shacl2flink's `Makefile` reads
`$(KMS)/shacl.ttl`, `$(KMS)/knowledge.ttl` and `$(KMS)/model-instance.jsonld`
with `KMS ?= ../kms/default`, so `make KMS=../kms/<name>` builds another one. A
checkout without symbolic link support (Windows without `core.symlinks`) gets
a text file instead of the link; builds and CI run on Linux.

A subdirectory that is not a package is ignored. A new package is created with
`semforge init kms/<name>`; lowercase kebab-case (`machine-cell`) is the
convention for new names.

Packages named `opcua-*` are generated from OPC UA models
(`semantic-model/opcua`, `make -f translate_<example>.make package`, see
`owl2kms.py` in [../opcua/README.md](../opcua/README.md)) and never committed:
this directory ignores them, and the `Build` workflow generates and verifies
`opcua-pumps`, `opcua-laser` and `opcua-simple`. The `opcua-` prefix is
reserved for them.

Running a package's tests (`semforge verify --tests`, `semforge publish`) is not
a sandbox: SPARQL constraints may contact services (`SERVICE`) and JSON-LD
contexts may be fetched. Checking a package or an archive without `--tests`
reads nothing from outside it.

```bash
semforge packages semantic-model/kms          # each package once, the default marked
semforge verify semantic-model/kms/default    # the contract, and the package digest
```

The `Build` workflow verifies and tests every package here: a package that
fails verification, including a published version whose content has changed,
fails the build, and so does an example that does not meet its expectations.
Coverage below a package's threshold fails the build only for a published
version.
