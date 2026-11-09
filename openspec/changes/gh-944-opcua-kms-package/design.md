# Design

## Context

The OPC UA chain is `nodeset2owl.py` (NodeSet to an ontology per namespace,
with `owl:imports` between them) followed by `owl2instances.py` (entities,
SHACL shapes, NGSI-LD instances and a JSON-LD context for one instance type).
The `translate_*.make` files run it for the pump, laser and simple examples and
leave the loose files in `semantic-model/opcua`. The KMS package format
(`contracts/kms-package`, #939, #940) defines what a package is; `semforge
verify` checks it.

A first assembler exists on an earlier, unmerged branch: `owl2semforge.py` and
`lib/semforge_package.py`. It already follows `owl:imports` and copies the
closure into `knowledge/`, one file per ontology, and maps `instances.jsonld`
to `model-instance.jsonld`. It writes the old `semforge.yaml` without `version`
and `format`, may declare a vocabulary outside the package, copies ontologies
byte for byte (so `owl:imports <file:///…>` written by `nodeset2owl.py` for
local inputs survive), and lists each source's absolute path in a descriptor
comment.

## Decisions

### D1 — A separate assembler, not a mode of `owl2instances.py`

- **Chosen:** `owl2kms.py`, built from the existing assembler. The package
  needs the outputs of both tools plus the import closure, which no single
  pipeline step owns.
- *Alternative:* a `--package` option on `owl2instances.py`. Rejected: it would
  make one step responsible for the whole chain's result, and `owl2instances.py`
  is also used for shapes only and for type contracts.
- Only the two commits holding `owl2semforge.py` and its library are carried
  over, not the branch they are on.

### D2 — The type system travels with the package

The instance's shapes target classes declared in the companion specifications.
Without them in `knowledge/`, every `sh:targetClass` names an undeclared class.
So the closure of `owl:imports` is copied, one file per ontology. W3C
vocabularies and the NGSI-LD vocabulary are excluded; the latter is copied
once, to `vocabulary/ngsild.ttl`, as the format requires.

- *Alternative:* reference the ontologies by URL (a dependency). Rejected for
  now: packages are standalone (#939); dependencies are planned separately.

### D3 — Imports name ontologies, not files

`nodeset2owl.py` writes `owl:imports` as `file:///<absolute path>` for local
inputs. Copied byte for byte, the package would name a directory on the
building machine, and its digest would differ per machine.

- **Chosen:** in each copied file, an `owl:imports` of another copied file is
  replaced by that file's ontology IRI (its `owl:Ontology` subject). This is the
  conventional form of an import, and every consumer that follows imports can
  resolve it from the package itself.
- *Alternative:* rewrite to a relative file IRI. Rejected: a relative IRI in
  Turtle resolves against the document's base, which differs per reader.
- *Alternative:* leave the files untouched. Rejected for the reasons above.
- The rewrite is the only change to a copied ontology. The descriptor records
  sources as URLs or names relative to the inputs, never absolute paths.

### D4 — Main model only

As #944 asks, no examples suite is generated. A generated package
is a draft with 0 % coverage; `semforge publish` refuses it, and `verify
--tests` passes. Generating cases from the shapes would test the shapes with
data derived from the same source, which proves little.

### D5 — Generated in CI, never committed

The pump example's knowledge holds about 200,000 triples. Committing generated
packages would put large generated diffs into every change of the OPC UA tools.

- **Chosen:** `package` targets write `semantic-model/kms/opcua-<example>`,
  where SemForge and shacl2flink find packages, and
  `semantic-model/kms/.gitignore` ignores `opcua-*/`. The `Build` workflow's
  `Build opcua tools` step generates the three packages and runs `semforge
  verify` on each, using the SemForge SDK set up in the step before it.
- *Alternative:* write them under `semantic-model/opcua/build/`. Rejected:
  `semforge packages semantic-model/kms` and `make build KMS=…` would not find
  them where packages live.
- *Alternative:* a naming rule other than the `opcua-` prefix. The prefix is
  what makes the ignore rule work; it is the convention for generated OPC UA
  packages, and hand-written packages must not use it.
- Generation downloads NodeSets and ontologies, which GitHub Pages
  intermittently answers with 503 in CI (see the retry loop in `build.yaml`).
  The package step runs inside the same retry, so a throttled download is
  retried and a real failure still fails.

### D6 — Reproducible output

The same inputs must give the same digest. The assembler is deterministic by
construction: sorted file names, byte copies apart from D3's rewrite, and a
descriptor with no timestamps or paths. Whether `nodeset2owl.py` and
`owl2instances.py` are deterministic (blank node labels, statement order) has
not been measured. Task 1.3 measures it; if they are not, the smallest fix
needed for packaging goes into this change, and nothing more (issue #944, out
of scope).

## Risks

- **Determinism of the chain** (D6): if `nodeset2owl.py` or `owl2instances.py`
  vary between runs, making them stable may be more than a small change. Task
  1.3 reports before anything else is built on it.
- **CI time:** three examples add downloads and generation to `Build`, which
  already takes about 72 minutes. The simple example is local; laser and pump
  share downloaded base ontologies.

## Conflicts with existing documentation

- `semantic-model/opcua/README.md` describes the loose output files as the end
  of the chain. It gains the `package` step.
- The SemForge SDK's test corpus holds a hand-made slice `opcua-pumps`. It stays
  as it is; generated packages are not test fixtures of the SDK.

## Follow-up

- Sharing the OPC UA base and companion specifications as one package, and
  machine packages that depend on it, belong to the planned dependency work.
