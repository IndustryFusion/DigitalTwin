# SemForge SDK

Offline authoring and validation of semantic packages: NGSI-LD examples, OWL
ontology, SHACL constraints and SHACL-SPARQL rules, developed and tested
together as one versioned unit.

- [`manifest.md`](./manifest.md) — what SemForge must be, and why
- [`architecture.md`](./architecture.md) — how it is built
- [`implementation-plan.md`](./implementation-plan.md) — how it gets built, in what order

## Quick start

```bash
make setup                          # venv, pinned dependencies, editable install
make test                           # pytest, 80% coverage gate
make test-e2e                       # the VS Code extension in a real VS Code
make lint                           # flake8
venv/bin/python -m semforge validate tests/corpus/kms
```

## Status

**Alpha.** The language, the validator and the editor are in daily use on the
KMS; formats and commands may still change, and the shacl2flink alignment
(constraint identity in alerts, `datasetId`, severity) is still open.

**M0 through M7 are implemented — the plan is complete** (see `implementation-plan.md` section 5).
A package loads, is projected to RDF, has its rules expanded to a bounded
fixpoint under NGSI-LD update semantics, is normalised into the data view its
shapes declare, and is validated with pyshacl. Every applicable constraint gets
a status, residue is pinned by digest, coverage reports which constraints are
actually exercised, and constraints can be edited in place without disturbing
the rest of the file.

On the real KMS: 248 constraints evaluated, 3 violations — all
three known and documented — and the compiled SQL agrees with pyshacl.

```bash
venv/bin/python -m semforge validate tests/corpus/kms
venv/bin/python -m semforge test tests/corpus/kms --coverage
venv/bin/python -m semforge explain tests/corpus/kms StateOnFilterShape
venv/bin/python -m semforge accept tests/corpus/kms
venv/bin/python -m semforge export tests/corpus/kms -o /tmp/kms --mode broker
venv/bin/python -m semforge validate tests/corpus/kms --cross-check sqlite
venv/bin/python -m semforge check tests/corpus/kms [--strict]   # links that point at nothing
venv/bin/python -m semforge where                 # which package applies here
venv/bin/python -m semforge diff <before> <after>
venv/bin/python -m semforge observe tests/corpus/kms
venv/bin/python -m semforge import schema.json --as jsonschema --namespace https://x/v1
venv/bin/python -m semforge resolve <package> --require-pinned
venv/bin/python -m semforge prefixes <package> [--fix]
venv/bin/python -m semforge retarget <package> --to local|published
venv/bin/python -m semforge serve-context <package>
```

Every command that reads a package **walks up** to find it, the way `cargo`,
`npm` and `git` do: stand anywhere inside a package and the command means that
package. Each one says which one it resolved, on stderr, so a report stays a
report:

```
$ cd kms/examples/test_FilterShape && semforge validate
package: /home/you/kms  (knowledge, shapes and model beside each other)
...
```

`semforge where` is the same question asked on its own — the root, how it was
found, and which file or directory holds each role.

A package declares a **local** and a **published** context. Work resolves the
local one, so a term is usable as soon as it is agreed and no build needs the
network; `export` points the model back at the published url and refuses to
write if the model uses a term that url does not declare.

## VS Code

`vscode/` holds the extension. See [vscode/README.md](./vscode/README.md) for
setup — in short, `make setup` here, then `npm install` there and
`code --extensionDevelopmentPath="$PWD" ../..`.

It shows validation and capability errors on the shape that causes them, and
flags constraints no example ever makes fire — the signal a passing test run
cannot give you, because a constraint that cannot fire looks exactly like one
that is satisfied.

It also carries the **cooked view** — the trees and the pages for entity
types, shapes, test cases, the main-model and the vocabulary — where every
edit rewrites just the text it changes, so comments survive and validation
follows immediately. [vscode/README.md](./vscode/README.md) describes it.

### What is implemented, and what is not

| Area | State | Notes |
| --- | --- | --- |
| Packages, validation (pyshacl), rules, data views | implemented | the per-variable *mixed* view is refused (`SF-CAP-005`); it needs the algebra of H2 step 4 |
| Test cases, expectations, residue, coverage, regression diff | implemented | |
| Cooked editing (types, shapes, attributes, constraints, cases, vocabulary) | implemented | in the VS Code extension; the write layer is `semforge.rdfio` |
| NGSI-LD vocabulary | implemented | declared by the package (`ngsild: {source, sha256}`), never shipped with the SDK: a local file while it is worked on — this repo's is `semantic-model/ontology/ngsild.ttl` — or the official url, pinned. Undeclared: the official url, or `SEMFORGE_NGSILD`. The official version still lacks the terms the local copy adds; publishing them is open |
| NGSI-LD instances: `datasetId`, `observedAt` series, `unitCode` | implemented | only the latest observation per `datasetId` is validated, an unstamped one counting as now — the platform's rule |
| Export | implemented | `compile` keeps every observation; `broker` keeps the one validated per `datasetId` and **refuses** a tie (two unstamped, or the same time) rather than guessing. The `sh:nodeKind sh:BlankNode` it adds to attribute shapes is listed shape by shape, and pinned to change no verdict (`test_export_contract.py`) |
| Target profile (shacl2flink) | implemented, copied | a hand-kept copy of the compiler's facts; `test_profile_drift.py` reads shacl2flink's source and fails when they drift. A descriptor shacl2flink publishes is planned |
| `--cross-check sqlite` | **approximate** | runs the package through shacl2flink's SQLite build and compares (resource, attribute, component) with counts. Two constraints of one component on one attribute share a key, so a disagreement between them can hide; what the compiler is known not to compile (units, `sh:node`'s inlining, types outside the profile) is reported as *expected*. A courtesy check: its findings are bug reports for the compiler, never reasons to hold up a package whose pyshacl verdict is clean. It needs `requirements-crosscheck.txt` and the `sqlite3` CLI |
| Constraint identity | implemented | SHACL's own addressing: the **shape's IRI**, the **path**, the **constraint type** — `MachineShape-3f9a1c2e/hasTemperature/MinCount…`. The shape's IRI is the identity, so every shape the editor names carries a random part (`-3f9a1c2e`) that marks it as an identifier, not a description; Rename… changes the name and keeps it. The path is all of it: an attribute's own sh:minCount and its value's are `hasTemperature/…` and `hasTemperature.hasValue/…`, its unit's `hasTemperature.unitCode/…`. Not yet carried into shacl2flink's alerts, which name a constraint by type and path only (the shacl2flink alignment) |
| Proposed constraints from examples | **planned** | the `proposed` tier exists and is enforced; no importer populates it |

## Scope

SemForge validates offline. It does not model Flink, Kafka, streaming state or
the alert projection, and making pyshacl agree with the compiled SQL is not its
job — see `architecture.md` section 7.4.
