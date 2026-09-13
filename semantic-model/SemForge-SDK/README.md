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
make lint                           # flake8
venv/bin/python -m semforge validate tests/corpus/kms
```

## Status

**M0 through M7 are implemented — the plan is complete** (see `implementation-plan.md` section 5).
A package loads, is projected to RDF, has its rules expanded to a bounded
fixpoint under NGSI-LD update semantics, is normalised into the data view its
shapes declare, and is validated with pyshacl. Every applicable constraint gets
a status, residue is pinned by digest, coverage reports which constraints are
actually exercised, and constraints can be edited in place without disturbing
the rest of the file.

On the real KMS: 152 constraints evaluated, 149 conformant, 3 violated — all
three known and documented — and the compiled SQL agrees with pyshacl.

```bash
venv/bin/python -m semforge validate tests/corpus/kms
venv/bin/python -m semforge test tests/corpus/kms --coverage
venv/bin/python -m semforge explain tests/corpus/kms StateOnFilterShape
venv/bin/python -m semforge accept tests/corpus/kms
venv/bin/python -m semforge export tests/corpus/kms -o /tmp/kms --mode broker
venv/bin/python -m semforge validate tests/corpus/kms --cross-check sqlite
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

It also carries the **cooked view**: a tree of entity types, attributes and
constraints, where editing a Core parameter rewrites just that value in
`shacl.ttl`. Cooked and raw are one state — the edit is a raw edit — so
comments survive and validation follows immediately.

`--cross-check sqlite` runs the package through shacl2flink's SQLite build and
compares. It needs `requirements-crosscheck.txt` and the `sqlite3` CLI, and it
is a courtesy check: its findings are bug reports for the compiler, never
reasons to hold up a package whose pyshacl verdict is clean.

What is **not** yet true, stated rather than implied:

- Constraints are referenced structurally (`shape/attribute/Component`), not by
  a declared frozen `semforge:id`. A structural reference changes when the path
  changes, which is the rename a regression report exists to explain
  (`architecture.md` section 5.4).
- Nothing yet derives `proposed` constraints from examples: the tier exists and
  is enforced, but no importer populates it.
- Constraints are still referenced structurally. The declared, frozen
  `semforge:id` of `architecture.md` section 5.4 is not implemented, so a
  reference changes when a path changes — the rename a regression report exists
  to explain.
- Cooked mode does not exist. The write layer is there (`semforge.rdfio`) and
  the editor is raw-only; no structured UI uses it.
- The mixed per-variable data view is refused rather than evaluated
  (`SF-CAP-005`). Supporting it needs the algebra work in H2 step 4.

## Scope

SemForge validates offline. It does not model Flink, Kafka, streaming state or
the alert projection, and making pyshacl agree with the compiled SQL is not its
job — see `architecture.md` section 7.4.
