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

Running a package's tests (`semforge verify --tests`, `semforge publish`, and
so the `kms-check` step of `Build`) is offline: nothing is fetched over the
network.

- The model keeps its published context URL. The package's own context
  resolves from the local file `kms.yaml` declares for that URL
  (`context: {local: context.jsonld, published: <url>}`); the file on disk is
  not rewritten. A package whose model names a context URL that `kms.yaml`
  does not declare fails, and the message names the URL and the line to add
  under `context:`.
- The NGSI-LD core context v1.8 resolves from a copy the SDK ships
  (`SemForge-SDK/semforge/package/contexts/`, byte for byte, checked by its
  hash; ETSI, BSD-3-Clause, see `Notice.md`). Any other remote context fails
  the tests, named; `--allow-network` lets the tests fetch it. Only `http(s)`
  URLs and files inside the package are read, whatever the spelling of the
  scheme.
- The NGSI-LD vocabulary resolves from the package (`ngsild: {source: …}`) or,
  for the official url `semforge init` pins, from a copy the SDK ships. Any
  other remote vocabulary is fetched only with `--allow-network`; a vocabulary
  that does not load fails the tests, naming its source. A package that names
  none is tested with the official one; `SEMFORGE_NGSILD` is ignored.
- Examples and their includes are read only from inside the package.
- No cache is read or written, neither the package's `.semforge/cache/` nor the
  user's: the package is judged by its files.
- `--allow-network` allows those two fetches and nothing else.
- `SERVICE` is rejected in every SPARQL of a package (constraints, rules and
  targets), with `--allow-network` too, naming the shape: SHACL does not
  allow it in constraints, the platform's validation cannot run it, and a
  package's results must not depend on a remote endpoint. SPARQL that does not
  parse is rejected as well.

Checking a package or an archive without `--tests` reads nothing from outside
it either. Nothing beyond the network is sandboxed.

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
