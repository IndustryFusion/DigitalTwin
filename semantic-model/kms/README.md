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

A package's release record `.kms/releases.yaml` is append-only. On a pull
request, `Build` compares it with the record on the base branch: removing an
entry, or changing its digest, date or test results, fails and names the
version and the field; appending the entry `semforge publish` writes passes,
and so does a package that has no record on the base branch yet. A package is
identified by the name in its `kms.yaml`: it is compared with the record at
its path on the base branch and with the record of every package of its name
there, so moving a package here, or giving it a published name, keeps it held
to that name's record. Two packages here must not declare the same name. Only
a name the base branch does not have (a new package, or one renamed as well as
moved) starts a new record. The record and `.kms` must not be symbolic links,
and a record on the base branch that does not parse fails, because neither
could be compared. Deleting a whole package with its record is left to the
pull request's review. Locally,
`make kms-check` in `SemForge-SDK` compares with `origin/main`
(`KMS_AGAINST=<ref>` names another ref, `KMS_AGAINST=` skips it), and
`semforge verify --against <ref> <package>` checks one package.

The record is not part of the package or its archive, so only its git history
protects it. A package without history has nothing to compare with: an
archive or a directory outside a git work tree is refused by `--against`, and
a package never committed, such as a generated `opcua-*` package, has no
record on the base branch and passes. For those, the record is taken as it is.
