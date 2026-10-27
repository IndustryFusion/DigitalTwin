# SemForge Implementation Plan

Third document of three. [`manifest.md`](./manifest.md) says what SemForge must
be; [`architecture.md`](./architecture.md) says how it is built;
this says how it gets built, in what order, and what "done" means at each step.

Section references of the form §n are to `architecture.md` unless stated.

---

## 1. What already exists

Before planning new code, the inventory. `semantic-model/` already contains
working implementations of several things SemForge needs, and one of them —
`shacl2flink/tests/pyshacl-compare/compare.py` — has already solved the two
problems that would otherwise sink M1.

| Need | Existing code | Verdict |
|---|---|---|
| SHACL validation of NGSI-LD in RDF | `pyshacl-compare/compare.py` | **Reuse the hard parts** (§3.1) |
| NGSI-LD → RDF | `create_ngsild_models.py`, `datamodel/tools/jsonldConverter.js` | Reference; reimplement in the SIM |
| Knowledge closure | `create_knowledge_closure.py` | Port behind the reasoner port |
| OWL consistency | `opcua/check_consistency.py` (HermiT) | Wrap as-is, keep LGPL isolation |
| Example/expectation fixtures | `tests/sql-tests/**` | Convert to the corpus (§7) |
| Target compilation | `shacl2flink` | Call it; never reimplement (§7.4) |
| Ontology fetch/merge | `make ontology2kms` | Replace with versioned resolution (§6.2) |

### 1.1 The four facts `compare.py` already establishes

These are not incidental. Each is a correctness requirement for *any* offline
SHACL validation of NGSI-LD data, and each was learned the expensive way.

**F1 — RDF multiplicity is not NGSI-LD cardinality.** `urn:filter:1` carries
four `hasStrength` instances differing only in `observedAt`. To NGSI-LD that is
one attribute updated four times; to RDF it is four concurrent values, so
`sh:maxCount 1` reports a violation *on correct data*, and would on any entity
ever updated twice. `collapse_updates()` fixes this by handing the validator the
instance a broker would have kept: group by `(subject, predicate, datasetId)`,
keep the latest `observedAt`, drop the rest with their subtrees. `datasetId` is
in the key deliberately — two datasetIds are two attributes, and collapsing
across them would erase a value the broker keeps.

**Consequence: SemForge cannot hand a raw NGSI-LD graph to `pyshacl`.** A
normalisation pass is mandatory, not an optimisation. This becomes H2.

**F2 — Knowledge goes in the data graph, not `ont_graph`.** Passing
`knowledge.ttl` as `ont_graph` leaves it invisible to `sh:class`, so every
`sh:class` over a knowledge-typed value (`iff:state_OFF a iff:MachineState`)
reports a violation that is not one. §7.3's reasoner port must not be read as
"closure goes somewhere else": the validator has to see the same world the
constraints are written against.

**F3 — Blank nodes must be named by the attribute that owns them.**
`owner_and_edge()` climbs from a reported focus node to the owning entity,
stepping over edges that only say *how* a value is stored
(`ngsild:hasValue`, `hasValueList`, `hasJSON`, `hasObject`, `rdf:first`,
`rdf:rest`) and returning the edge *closest to the node* — so a sub-attribute
constraint is named `bolt`, not its grandparent `assembly`. Inverse paths need
`inverse_predicate()`, which recovers the predicate from the two-hop
`( [^hasObject] [^predicate] )` sequence pyshacl reports as an unnamed blank
node.

**Consequence: result normalisation is a solved problem — port it.** It is also
the only way to build a residue digest that does not contain blank-node labels
(H4).

**F4 — There is a documented list of places SHACL and the platform disagree.**
`expected-divergences.txt` is 8 entries, every one with a rationale. Three
matter for SemForge as a *product* decision, not just a test detail:

- *Lexical typing.* Checked, and it is not the problem the divergence file
  implies for SemForge — see §10.1. The compiler casts **both sides** to DOUBLE
  (`SQL_DIALECT_CAST(val AS DOUBLE) op SQL_DIALECT_CAST(bound AS DOUBLE)`), so
  it handles real numbers and numeric strings alike; it is not string-only. The
  production model carries real JSON numbers. SemForge stays spec-pure.
- *Empty ListProperty.* An empty list is `rdf:nil`, an IRI, so
  `sh:nodeKind sh:BlankNode` fails purely because the list is empty. A
  normalisation case for H2.
- *Rule output is an update, not an addition.* A `sh:rule` constructing a second
  `hasWasteclass` adds a triple in RDF, where NGSI-LD would replace. The fixpoint
  loop (§8) must apply NGSI-LD update semantics between iterations, or every
  rule that rewrites an existing attribute manufactures a cardinality violation.

---

## 2. Technology decisions

| Decision | Choice | Why |
|---|---|---|
| Language | Python 3.11 | `rdflib`/`pyshacl` ecosystem; `opcua/` already targets 3.11, `shacl2flink` 3.10. Do not add a third runtime. |
| RDF | `rdflib==7.1.1` | Exact pin from `shacl2flink/requirements.txt`. A second rdflib major in one repo is a support burden with no upside. |
| SHACL | `pyshacl==0.29.0` | Same pin. Supports SHACL-AF (`advanced=True`), which §8 rules require. |
| CLI | `click` | Already a `shacl2flink` dependency. |
| Expectation files | `ruamel.yaml` round-trip mode | Already a dependency, and it **preserves comments and key order** — expectation files are human-edited and `accept` rewrites them in place. `pyyaml` would silently destroy every comment in the file on first accept. |
| Build | `Makefile` + `requirements.txt` | Every other component in `semantic-model/` works this way. No poetry/uv. |
| Tests | `pytest`, `--cov-fail-under=80` | Matches `shacl2flink/Makefile`. |
| Lint | `flake8` | Matches. |
| LSP (M6) | `pygls` | Deferred decision; nothing before M6 depends on it. |

**Non-decision:** `oxrdflib` is available as an rdflib store backend and is used
by `shacl2flink`. Do not adopt it until a measured performance problem exists;
it changes blank-node handling in ways H4 is sensitive to.

---

## 3. Code layout

```text
semantic-model/SemForge-SDK/
├── manifest.md  architecture.md  implementation-plan.md
├── Makefile  requirements.txt  requirements-dev.txt  setup.cfg
├── semforge/
│   ├── package/      loader, writer, semforge.yaml schema, module resolution
│   ├── sim/          node model, SemanticPath, indexes, RDF projection
│   ├── ngsild/       H2: the NGSI-LD normaliser (collapse, list, typing)
│   ├── rdfio/        H3: parse, serialize, text-anchored edit layer
│   ├── provenance/   tiers, origin records, why()
│   ├── validate/
│   │   ├── ports.py  orchestrator, ValidationReport
│   │   ├── applicable.py   H1: the applicable-set enumerator
│   │   ├── normalise.py    F3: result normalisation (ported)
│   │   └── adapters/  pyshacl.py, sqlite_crosscheck.py, hermit.py
│   ├── expect/       expectation store, residue, digest, accept, coverage
│   ├── rules/        §8 fixpoint with NGSI-LD update semantics
│   ├── derive/       observed → proposed
│   ├── diff/         semantic diff, regression
│   ├── target/       profile descriptors, export to KMS
│   └── cli/
└── tests/
    ├── unit/
    └── corpus/       §7
```

---

## 4. The hard problems

Sized S / M / L. These are scheduled first within their milestone, because each
one can invalidate the design above it.

### H1 — Per-constraint evaluation status (L)

**Problem.** V1 and V2 require every applicable constraint to report
`conformant` / `violated` / `not-applicable` / `not-evaluated`. **A SHACL engine
reports only violations.** Conformance is the absence of a result, which is
exactly the silence D7 forbids us to read as success.

**Approach.** An *applicable-set enumerator* independent of the validator:

1. Walk the shapes graph; for each shape compute its focus nodes — `sh:targetClass`
   (through the `rdfs:subClassOf*` closure), `sh:targetNode`,
   `sh:targetSubjectsOf`, `sh:targetObjectsOf`, and implicit class targets.
2. For each focus node, walk property shapes recursively (including through
   `sh:node`, and through the two-layer NGSI-LD encoding of §2.2) to produce the
   set of `(focus node, declared constraint ID)` pairs that *should* be evaluated.
3. Run pyshacl. Every reported result maps (via F3 normalisation) onto a pair.
4. Status: in the report ⇒ `violated`; in the enumerated set and not reported ⇒
   `conformant`; shape present but no focus node matched ⇒ `not-applicable`;
   enumerator could not decide, or the engine raised ⇒ `not-evaluated`.

**Invariant to test:** every reported result maps onto an enumerated pair. A
result that does not is an enumerator bug, and must fail loudly — an enumerator
that silently under-counts turns V1 into decoration.

**Risk.** The enumerator is a second partial implementation of SHACL targeting,
and it can drift from pyshacl's. Mitigated by the invariant above, which is
checkable on every corpus run and catches drift in the direction that matters.

### H2 — Data views: current vs history (L, was M)

**Problem.** F1 says validation needs the current value per `(entity, predicate,
datasetId)`, or cardinality is nonsense. But that is only true for constraints
that read *entity state*. **A SPARQL constraint or rule that aggregates over an
attribute's history needs the full instance stream**, and collapsing the graph
destroys its input — silently, producing an aggregate over one row where four
were meant.

So a single global pre-pass is wrong. There are two views of the same data:

| View | Content | Right for |
|---|---|---|
| `current` | latest instance per `(entity, predicate, datasetId)` | counts, datatypes, ranges, classes — everything about entity state |
| `history` | every instance | SPARQL aggregation over an attribute's observations |

**The platform already does this, per variable.** `attributes_view` is a
`ROW_NUMBER() OVER (PARTITION BY id, datasetId ORDER BY observedAt, offset)`
top-1 dedup — the `current` view — and all generated constraint SQL joins it.
But `create_attribute_table_expression()` emits a placeholder instead whenever
the query has `group_by_vars`, and
`replace_attributes_table_expression()` then resolves the **aggregated**
variables to the raw `attributes` table (history) while every other variable
falls back to `attributes_view` (current). One query, two views, chosen per
variable.

**SemForge cannot do that directly, and this is a genuine asymmetry.** SQL names
a table per join, so per-variable view selection is free. `pyshacl` evaluates
against *one* RDF graph; there is no way to say "this variable sees four
instances and that one sees the latest". Hand it the history graph and the
non-aggregated variable multiplies rows; hand it the collapsed graph and the
aggregate is wrong.

**Plan, staged, with the limit stated.**

1. **Per-shape view selection (M1).** A shape declares its view; shapes are
   partitioned by it and validated in one pyshacl run per view, and the reports
   merged. Default `current` — it is right for every Core constraint and for the
   entire production KMS.

   ```turtle
   [] a sh:NodeShape ; semforge:dataView "history" ; sh:sparql [ … ] .
   ```

2. **A static check that the declaration is honest (M1).** A shape declaring
   `current` whose SPARQL body contains an aggregate or references
   `ngsild:observedAt` across instances is a build error naming it. Getting this
   wrong is silent — the aggregate simply computes over the wrong rows and
   returns a plausible number — which is the D7 class, so it fails loudly per
   C1. Detection follows `sparql_to_sql.py`'s own rule: presence of `GROUP BY` /
   aggregate functions in the algebra.

3. **The mixed case is unsupported, and says so (M1).** A single query that
   aggregates one variable over history *and* reads another's current state —
   which the platform supports — has no single-graph evaluation. It is rejected
   by the capability check with that reason, rather than evaluated against
   either graph and quietly wrong.

4. **Later, if a real shape needs it (post-M4).** Reconstruct the per-variable
   semantics on the RDF side: read the aggregated variables from the algebra, as
   `sparql_to_sql.py` does, and collapse only the attribute instances bound to
   the *non*-aggregated ones. This is not compiler-fidelity work forbidden by
   §7.4 — it is NGSI-LD semantics, which SemForge does own. It is deferred
   because nothing needs it yet.

**Nothing on the M1–M4 path needs anything but `current`.** The production
`kms/shacl.ttl` contains no `GROUP BY` at all — every shape there is entity
state. Two fixtures use aggregation (`kms-rules/test4`, `kms-udf/test6`), and
they become the first tests of step 1 and the corpus cases for step 3.

**Transforms in the `current` view.** Each independently switchable and tested:

| Transform | Rule |
|---|---|
| `collapse_updates` | Port from `compare.py` verbatim, including the `datasetId` key and the observedAt-only guard |
| `empty_list` | Treat `rdf:nil` under `ngsild:hasValueList` as a well-formed empty ListProperty |
| `rule_output` | Between fixpoint iterations, a constructed value *replaces* the existing instance of the same `(entity, predicate, datasetId)` |

**Constraint.** The view builder touches the data graph only, never shapes, and
every run reports which view each shape used and how many instances each
transform removed. A transform that quietly drops a value is indistinguishable
from a validator that missed one.

### H3 — Lossless artifact editing (M, with a defined fallback)

**Problem.** P1 (round-trip isomorphism) is satisfiable with rdflib. **P2 (edit
locality) is not** — rdflib reserialises the whole file, losing comments and
ordering. KMS shapes carry load-bearing comments (`CartridgeShape`'s explanation
of the two-hop inverse path is the only place that reasoning is written down).

**Approach, staged.**

- **M1** — read-only. rdflib only. P1 holds; P2 is not yet needed.
- **M3** — writes arrive. Build a triple → byte-span index over a lossless
  tokenizer, and edit the text through it.

**Spike before committing (first task of M3, timeboxed).** Candidates in order:
a tree-sitter Turtle grammar; a purpose-built Turtle tokenizer (the grammar is
small and we need spans, not semantics); patching rdflib's parser for position
callbacks (last resort — a fork we would own).

**Fallback if the spike fails.** Shape-block granularity: rewrite the whole
`sh:NodeShape` block from the SIM, byte-preserve everything outside it. Coarser
diffs within an edited shape, everything else in the file untouched.
Implementable in days, and it keeps M3 off the critical path of a research task.

### H4 — Residue canonicalisation (M)

**Problem.** The residue digest (§7.5) must change when and only when a verdict
changes. pyshacl results contain blank nodes whose labels are not stable across
runs, so a naive digest churns on every execution and the whole mechanism is
worthless.

**Approach.** Canonical tuple per result, then sort, then digest:

```
(declared constraint ID, owning entity IRI, attribute path as dotted names,
 severity, value lexical form or None)
```

Blank nodes never enter the digest — the owning entity and attribute path come
from F3's `owner_and_edge` climb. Path is the dotted attribute-name form
(`hasFilter.hasTrust`), not a serialized SHACL path expression, so it is stable
against prefix changes.

**Acceptance:** run the corpus twice in one process and twice in separate
processes; all four digests identical. Then permute the input file's statement
order and re-run; digests still identical.

### H5 — Deterministic export (S)

Stable prefix assignment (from `semforge.yaml`, never auto-generated —
today's `default1:`/`default2:` in `knowledge.ttl` are exactly this failure) and
a stable statement order. rdflib's serializer guarantees neither, so this is a
custom serializer or a sorting post-pass. **Acceptance:** export twice, `cmp`
the bytes.

### H6 — Proving a constraint is alive (M) — *architecture amendment*

**Problem, and it is a real gap.** §7.2's V1 gives per-example status, and I
claimed it catches the dead-shape case. It does not. A SPARQL constraint whose
body can never match — `StateOnFilterShape` asking for `?pc a Plasmacutter`
against instances typed `Cutter`, comparing to the typo
`iffBaseEntities:state_PROCESSING` — returns an empty result set, which is
byte-for-byte what a satisfied constraint returns. H1's arithmetic then
classifies it `conformant` on every example, forever.

**The check is a negative example, not a statistic.** A bad example that asserts
the constraint fires proves liveness directly: the target is reachable, the path
resolves, the SPARQL body binds. If the shape is dead, that assertion fails —
an ordinary test failure, not a heuristic. This is already in the design; what
was missing is the requirement that it *exist*.

**A positive example proves nothing about liveness.** `conformant` and
`unsatisfiable` produce identical output, so a constraint with only
expected-valid examples is untested no matter how many there are. The two sides
check different things and neither substitutes for the other:

| | proves |
|---|---|
| bad example asserting the constraint fires | the constraint **can** fire — target, path and body all resolve |
| good example asserting it does not | the constraint does not fire **spuriously** |

So the coverage report is per-constraint and two-sided, and names the side that
is missing:

```bash
semforge test --coverage          # per constraint: has a firing example? a non-firing one?
semforge test --coverage --fail-on no-firing-example      # CI
```

**Both sides can still flip together, and this is the honest limit.** The exact
`StateOnFilterShape` bug survives a two-sided suite: the shape asked for
`Plasmacutter`, so a negative example written to make it fire would be typed
`Plasmacutter` too. Bad example passes, shape looks alive, and production data
typed `Cutter` goes unvalidated. Example and shape encode the same misconception,
so a correlated error defeats both sides. No amount of expectation bookkeeping
fixes that, because the bookkeeping is written by the same author.

Three partial mitigations, offered as such:

- **Examples derived from real data** (D3) rather than hand-written against the
  shape. An imported example cannot share the shape author's assumption about
  what production is typed as.
- **Report the target set a constraint actually matched**, not just whether it
  matched: *"fired on 1 focus node of type `Plasmacutter`; target class `Cutter`
  has 3 subclasses, 2 never exercised."* This is the mechanised form of what
  `kms-constraints/kms/model4` does by hand — it exists solely to pin that the
  rule binds through `rdfs:subClassOf*`, using a subclass different from the one
  in `model3`.
- **Require the firing and non-firing examples to differ in target type** where
  the target class has subclasses. Cheap, and it is exactly the guard that was
  missing.

None of these is a proof. The plan states the residual risk rather than
designing around it: **a constraint can be alive, two-sided, fully covered, and
still be validating the wrong thing.** What the suite can guarantee is that it
is not validating *nothing*.

**This requires an amendment to §7.2/§7.6 of `architecture.md`**, which
currently over-claims for V1. See §10.2.

---

## 5. Milestones

Each milestone lists deliverables and **executable** acceptance criteria. A
milestone is done when its criteria run green in CI against the corpus (§7).

> **Status: M0 through M7 are implemented and green** -- 162 tests, flake8
> clean. The VS Code extension is in `vscode/`, with setup in its README.
>
> What each later milestone actually cost, beyond the plan:
>
> * **M5** hit the two bugs this project keeps hitting. Blank node labels leaked
>   into the diff, so a package differed from ITSELF; and attribute-level and
>   value-level constraints shared a key, so a real `minCount` edit was masked by
>   its sibling and the diff reported nothing.
> * **M6** had to aggregate the unexercised-constraint warning per shape. One
>   finding per constraint put 72 annotations on the corpus, and a warning
>   nobody can read is a warning nobody acts on.
> * **M7**'s importers stop at the `proposed` tier, enforced by a test that
>   asserts `shacl.ttl` is byte-identical and the validation result unchanged
>   after an import.
>
> **M6 was reported complete when it was not.** Its own acceptance criteria
> named find-references and S1/S2 -- a cooked edit that round-trips to raw --
> and only go-to-definition was built. Cooked mode has since landed: a
> TreeView over entity types, attributes and constraints, editing Core
> parameters through the text-anchored writer, so a cooked edit IS a raw edit
> and S1 holds by construction rather than by agreement. Changing `1` to `0`
> rewrites one byte. On the real KMS, 89 constraints are evaluated -- 87 conformant,
> 2 violated -- with the enumerator invariant holding (`complete: True`).
>
> **find-references has since landed. M6 is still open on S2**: nothing
> marks an OWL axiom Core cannot project as `unprojected` yet. From the
> `owl:ObjectProperty` in `knowledge.ttl` it reaches the `sh:path`, the SPARQL
> bodies that read the term, and every corpus example carrying it -- asserted
> against an independent scan of the files on disk, so a case the package
> forgets to list fails the test. Matching is on the expanded IRI, never the
> text, and building it found two bugs that were already there:
> rdflib's `Context.expand` runs the keyword `@id` through `@vocab`, so a
> `{"@id": ...}` value never expanded to anything; and the example lister read
> the model role's source path, which for a directory-shaped model is the
> directory itself, so the Knowledge view silently counted none of its
> documents.
>
> **The H3 spike resolved in favour of the tokenizer, and better than the
> fallback.** Turtle's statement grammar is small and what was needed is spans
> rather than semantics, so `rdfio/turtle_index.py` locates statements directly;
> an edit is a text insertion into the existing block, so even comments *inside*
> the edited shape survive, which the planned shape-block rewrite would have
> lost. The same index gives every shape a `file:line` locator, which is what
> provenance reports and what an editor service will need.
>
> The corpus caught a real bug in it immediately: a `#` inside an IRI
> (`<...shacl#>`) read as a comment start swallowed the statement terminator and
> merged three prefix directives with the shape that followed, so the first
> shape in the file was simply absent from the index. IRIs are now their own
> token, and a test pins it.
>
> **Resolved: `main` compiles its own kms.** M4 was built against an older
> `main`, where `create_sql_checks_from_shacl.py` raised `WrongSparqlStructure`
> on `isUsedFrom`; the fix was on `material-waste-class` at the time and has
> since merged. On current `main` the cross-check runs end to end and **pyshacl
> and the compiled SQL agree exactly** on the corpus.
>
> Rebasing onto that `main` changed the corpus, since it symlinks the kms: 152
> constraints now (was 89), three `hasXXXWorkpiece` violations (was two) because
> the model gained a second filter/cartridge pair. Three pinned tests failed and
> were reviewed before being updated -- the regression mechanism doing exactly
> its job.
>
> It also surfaced a latent enumerator bug the old corpus could not reach. The
> new `CartridgeShape` forbids one cartridge sitting in two filters, stated as a
> two-hop inverse path that pyshacl reports as an unnamed blank node. The
> adapter recovered the predicate name; the enumerator did not, so a violation
> of that rule would have been reported AND flagged as enumerator drift. The
> corpus cannot expose it -- the same change gave every filter its own cartridge
> -- so a test now attaches a second filter to `urn:cartridge:1` and makes it
> fire.
>
> **The corpus needed a vendored `context.jsonld`.** The shipped kms cannot be
> compiled without fetching a remote `@context`, because the compiler requires a
> local one and the model names a URL. `semforge export` therefore emits a
> context, and the cross-check refuses to run without one rather than fetching
> silently. See `tests/corpus/kms/README.md`.
>
> **M3 retired the one irreducible entry in `expected-divergences.txt`.** With
> update semantics between rule iterations, the constructed `hasWasteclass`
> replaces the value it was derived from instead of joining it, so the spurious
> `maxCount` violation is gone -- and is still reproducible with `rules=False`,
> asserted as a test.
>
> One thing M2 changed that was not planned: **shape identity is the full IRI,
> not the local name.** The corpus carries both `base_shacl:CartridgeShape` and
> `filter_shacl:CartridgeShape`; collapsing them to one short name merged two
> shapes' verdicts, which would have corrupted both coverage and the residue
> digest. Display uses the CURIE (`:CartridgeShape` vs `default1:CartridgeShape`)
> so expectation files stay readable and still unambiguous.
>
> Deviations from what is written below, all deliberate:
>
> 1. **The corpus is `main`'s KMS.** This branch is based on `main`, so
>    `kms-constraints/kms/` (the four-model fixture) and the `inversePath`
>    cartridge work are not present — they are on `material-waste-class`.
>    M1 criteria 2 and 3, which compare against those models, are therefore
>    substituted by pinning the corpus's own violation set against its
>    documented provenance (`test_corpus_validation.py`). All three violations
>    it produces are known and explained: one is the rule-writeback divergence
>    of F4, two are the `hasXXXWorkpiece` sub-attribute counts documented in
>    `kms-constraints/kms/README.md`. The stronger comparison lands when those
>    fixtures reach `main`.
> 2. **Cardinality assertions 5 and 6 are implemented; 7 is deferred to M4.**
>    M2's constraint references are structural (`shape/attribute/Component`)
>    rather than the declared, frozen `semforge:id` of architecture section 5.4;
>    those annotations arrive with the write layer in M3.
>    Rejecting the mixed per-variable case needs the capability check, which is
>    M4 work; detecting it needs SPARQL algebra analysis rather than the regex
>    that suffices for 6.
> 3. **`flake8` is ahead of shacl2flink's pin** (7.1.1 vs 5.0.4). The old pin
>    predates PEP 701 and mis-parses f-strings on Python 3.12, reporting dozens
>    of phantom errors. Reasoning is in `requirements-dev.txt`.
> 4. **Python 3.12**, not 3.11 — it is what the machine has, and nothing in the
>    dependency set objects.

### M0 — Skeleton and corpus (S)

- Package scaffold, `Makefile` (`setup`, `test`, `lint`), CI job.
- `tests/corpus/kms/` — the real `semantic-model/kms/` imported as a SemForge
  package, **by symlink to the source files**, following the precedent of
  `kms-constraints/kms/`. A copy is how the `sql-core` chart ended up running
  SQL the generator had already fixed.

**Accept:** `make test lint` green on an empty suite; corpus loads as files.

### M1 — Load, project, validate (L)

- `package/` loader; `sim/` node model, `SemanticPath`, RDF projection.
- `ngsild/` normaliser (H2).
- `validate/adapters/pyshacl.py` with F2 graph placement; `normalise.py` (F3).
- `semforge validate`.

**Accept:**
1. **P1** — load/save every corpus artifact; `rdflib.compare.isomorphic` holds.
2. Violation set for `model1..model4` equals `compare.py`'s pyshacl findings,
   entry for entry.
3. `model2` and `model3` each differ from `model1` in exactly one violation —
   `StateOnCutterShape` and `StateOnFilterShape` respectively. (These one-line
   deltas are documented in `kms-constraints/kms/README.md` and are the sharpest
   available check that the pipeline isolates what it should.)
4. The cardinality suite of §5.1 — four assertions, two of which are the guards
   that keep the normaliser honest.

#### 5.1 The cardinality suite (M1 criterion 4)

This is the concrete shape of H2, and it is worth spelling out because the
normaliser is the one component that *removes* data before validation. A
transform that deletes a value is indistinguishable from a validator that missed
one, so the tests have to pin both directions: it must remove the spurious
violation, and it must be incapable of removing a real one.

**The case.** `urn:filter:1` in `model-instance.jsonld` carries four
`hasStrength` instances — `0.9`, `0.8`, `0.7`, `0.6` — one second apart, sharing
a `datasetId`, differing only in `observedAt`, resolving to `0.6` at
`13:52:35`. `FilterShape` declares `hasStrength` `minCount 1 ; maxCount 1`.

To NGSI-LD that is one attribute updated four times. To RDF it is four blank
nodes hanging off one predicate. So pyshacl on the raw graph reports
`MaxCountConstraintComponent` on `urn:filter:1` — a violation of a shape that is
correct, on data that is correct, and one that would fire on **any entity ever
updated twice**.

| # | Assertion | What it protects |
|---|---|---|
| 1 | With the normaliser, the `hasStrength` count constraint on `urn:filter:1` is `conformant`, and the surviving value is `0.6` | the fix works, and keeps the right instance — not merely one of them |
| 2 | With the normaliser **disabled**, the same run reports `MaxCountConstraintComponent` on `urn:filter:1` | nobody can delete the normaliser and see green. Without this, criterion 2 of M1 is the only thing standing between us and silently reintroducing F1 |
| 3 | `test1/model14` — two `datasetId`s, each updated twice — collapses 4 instances to **2, not 1** | `datasetId` stays in the collapse key. Drop it and two attributes that merely share a name become one, which **hides** any real count violation across them |
| 4 | Instances carrying **no** `observedAt` are never collapsed: two concurrent values still report `MaxCountConstraintComponent` | repeated values without a timestamp are not an update sequence. This is the direction that matters — the normaliser must not be able to suppress a genuine cardinality violation |

Assertions 3 and 4 are the load-bearing ones. 1 and 2 test that the transform
fires; 3 and 4 test that it is *bounded*, which is the property that makes it
safe to run before every validation. `collapse_updates()` already gets all four
right — the work is porting it with its guards intact, not reinventing it, and
the tests exist so that a later "simplification" of the key cannot pass.

Three more pin the view selection of H2 — the point being that collapsing is
correct *for state constraints* and wrong for anything aggregating:

| # | Assertion | What it protects |
|---|---|---|
| 5 | A shape declaring `dataView "history"` sees all four `hasStrength` instances; an aggregate over them counts 4, not 1 | the collapse is scoped to the view, not global. Without this the first aggregating rule silently averages one value |
| 6 | A shape declaring `current` (or defaulting) whose body contains an aggregate fails the build, naming the shape | the declaration cannot drift from the body. This is the silent case — a wrong aggregate returns a plausible number, never an error |
| 7 | A query aggregating one variable while reading another's current state is rejected by the capability check, with that reason | the mixed case is refused, not evaluated against whichever graph happens to be loaded |

Assertion 5 uses `kms-rules/test4`, assertion 7 `kms-udf/test6` — the two
existing fixtures that aggregate. The production KMS has no `GROUP BY`, so 5–7
guard a path nothing currently walks, which is exactly when a silent default is
most likely to be wrong and least likely to be noticed.

### M2 — Status, expectations, residue, coverage (L)

- H1 enumerator; H4 digest; `expect/` store, `semforge test`, `semforge accept`.
- H6 coverage report.

**Accept:**
1. **V1/V2** — every corpus example yields a status for every applicable
   constraint; no constraint is absent.
2. Enumerator invariant — every pyshacl result maps to an enumerated pair.
3. Digest stability (H4's four-way + permutation check).
4. **The historical-bug fixture:** a corpus variant reintroducing the
   pre-2026-08-22 `StateOnFilterShape` (`?pc a Plasmacutter`, typo'd state IRI)
   is reported `never-exercised` by `--coverage`, while every per-example status
   stays `conformant`. This asserts both that coverage catches the bug and that
   per-example status alone does not.
5. Adding a new constraint to the corpus produces a residue delta on every
   example in its target class, and `semforge test` fails until accepted.

### M3 — Writes, provenance, tiers, rules (L)

- H3 spike then implementation (or fallback).
- `provenance/`, tiers, `semforge explain` / `why()`.
- `rules/` fixpoint with F4 update semantics and a declared iteration bound.

**Accept:**
1. **P2** — declare a constraint through the API; the diff touches only that
   shape; every comment elsewhere in the file survives byte-identical.
2. Corpus rules reach fixpoint; `ChangeWasteClassRulesShape` escalates
   `urn:cartridge:1` in one iteration and does not oscillate.
3. Without F4 update semantics, the second `hasWasteclass` raises a spurious
   cardinality violation — asserted as a test (this is
   `expected-divergences.txt`'s one irreducible MISSED entry).
4. A rule with a removed guard hits the iteration bound and is reported as a
   package error naming it, not as a hang.
5. `why()` on an imported constraint reports origin, file and line.

### M4 — Export, capability check, cross-check (M)

- `target/` profile descriptors; `semforge export --target kms`; emission modes
  (`compile` / `broker`, §6.3); static capability check (§9.1).
- `validate --cross-check sqlite`.

**Accept:**
1. **H5** — export twice, bytes identical.
2. Export of the corpus, fed to `shacl2flink make build`, compiles clean.
3. A shape exceeding the profile's depth is reported as a constraint-level
   diagnostic with file and line, *before* the compiler is invoked.
4. Cross-check on the corpus reports only divergences listed in
   `expected-divergences.txt`; anything else fails.

### M5 — Diff and regression (M)

**Accept:** `semforge diff` between corpus HEAD and a variant with
`minCount 1 → 0` produces the §11 report — the classified model change *and*
the affected example — and classifies a changed `sh:select` body as
`rule-body-changed, impact-unknown` rather than guessing.

### M6 — Editor service and VS Code (L)

**Accept:** go-to-definition from `sh:path` in `shacl.ttl` to the
`owl:ObjectProperty` in `knowledge.ttl`; find-references from there to every
corpus example exercising it; **S1/S2** — a cooked edit round-trips to raw, and
an OWL axiom Core cannot project survives load/edit/save and is marked
`unprojected`.

### M7 — Importers and registry (M)

**Accept:** OPC UA and JSON-Schema importers emit at `proposed` tier only —
asserted by a test that no importer output reaches `shacl.ttl` without an
explicit accept. `knowledge.ttl` reproducible from declared dependencies.

### Sequencing

```
M0 ─ M1 ─ M2 ─ M3 ─ M4 ─ M5
              └── M6 (needs M3's write layer)
              └── M7 (needs M3's tiers)
```

M1 and M2 are the load-bearing pair: **if a SemForge package cannot reproduce
today's KMS and re-run its fixtures, nothing above it is trustworthy.** M4–M7
parallelise once M3 lands.

---

## 6. Testing the SDK itself

- `tests/unit/` — pytest, `--cov-fail-under=80`, matching `shacl2flink`.
- `tests/corpus/` — every milestone's acceptance criteria, run in CI.
- **Property tests** on the two pieces where hand-written cases will not reach
  the failure modes: round-trip (P1) over generated graphs, and digest stability
  (H4) over permuted inputs.
- **Negative tests for every invariant.** P1, P2, V1, V2, S1, S2, C1, H4, H5
  each get a test that fails when the invariant is broken. An invariant with no
  failing test is a comment.

---

## 7. The corpus

`tests/corpus/kms/` symlinks the production KMS (M0). Two properties are
deliberate and must not be traded away:

- **Symlinks, not copies** — the fixture cannot drift onto last month's shapes.
- **The corpus is the acceptance suite** — every milestone is gated on the real
  model, not on toy shapes. Toy shapes go in `tests/unit/`.

Beyond it, convert `shacl2flink/tests/sql-tests/kms-constraints/**` (23 cases,
each with several models and expected outputs) into corpus packages with
`asserts` + `residue`. That conversion is itself the best available test of the
expectation format: if a case cannot be expressed, the format is wrong.

---

## 8. Risks

| Risk | Trigger | Mitigation |
|---|---|---|
| Mixed-view shape needed sooner than expected | A real shape aggregates one variable and reads another's current state | H2 step 4; until then the capability check refuses it loudly rather than guessing |
| H1 enumerator drifts from pyshacl | Report maps to no enumerated pair | The invariant fails the run; it is checked on every corpus execution |
| H3 spike fails | Timebox expires in M3 | Shape-block fallback, already specified |
| pyshacl blocked by a security scanner | Snyk flagged pyshacl before in this repo — `requirements-dev.txt` still carries the disabled `pyshacl==0.20.0` line (CWE-918), and `tests.sh` has the call commented out for the same reason | Pin and track; the validator port keeps the engine swappable. **This is the single dependency SemForge cannot function without — treat an advisory against it as a P1.** |
| Residue churn unusable at scale | M2 corpus run produces unreviewable accept diffs | Measure at M2 (open question 5); add per-constraint grouping to `accept` if needed |
| Legacy fixtures carry string-typed numbers | Converting `test2`/`test5` to corpus packages raises 8 range violations | Expected and correct (§10.1). Fix the fixtures' typing; do not relax the validator |
| Scope creep into `shacl2flink` | Any task mentioning Flink, Kafka or streaming state | §7.4 is the line; such a task is a `shacl2flink` issue |

---

## 9. Explicitly not in this plan

No Flink, Kafka, Alerta or Scorpio code. No writeback delivery. No streaming
semantics. No VS Code UI before M6. No LLM-assisted authoring. No replacement of
`shacl2flink`, and no attempt to make pyshacl agree with it.

---

## 10. Decisions needed

### 10.1 Lexical typing — checked, and it resolves to spec-pure

You asked whether the SQLite tests and the Flink compilation cope with real
types. **They do, and that removes the dilemma.** The generated comparison casts
*both sides*:

```sql
SQL_DIALECT_CAST(val AS DOUBLE) IS NULL
  OR NOT (SQL_DIALECT_CAST(val AS DOUBLE) {op} SQL_DIALECT_CAST(`bound` AS DOUBLE))
```

(`lib/shacl_properties_to_sql.py`, `sql_check_property_minmax`.) So a real
number and a numeric string are treated identically, and a value that does not
parse as a number raises a `not comparable with` violation rather than passing
silently. The compiler is not string-only; it is type-agnostic by construction.

Two further facts settle it:

- **The production model already carries real JSON numbers** —
  `model-instance.jsonld` has `0.6`, `2.1`, `5`, `100`, not `"0.6"`.
  String-typed numbers appear only in older fixtures (`test2/model7-9`,
  `test5/model1-2`), which is where all eight `expected-divergences.txt`
  entries under that heading come from.
- **The compiler's lexical comparison is a consequence of its storage model, not
  a semantic choice.** It reads `val` from the attributes table, a text column
  where the datatype has already been erased, so casting is the only thing it
  *can* do. pyshacl reads RDF, where `"100"^^xsd:string` and `100^^xsd:integer`
  are still distinguishable. SemForge does not inherit the workaround because it
  does not have the problem.

**Decision: spec-pure (option (a)), no normaliser transform, no new severity.**
pyshacl handles properly typed values correctly — that is just SHACL — and the
corpus is properly typed, so this costs nothing on the real model. Where a
payload does carry `"height": "100"`, reporting it is *correct*: the data says
that value is a string, a string has no place on a numeric range, and that is a
genuine defect in the payload worth surfacing rather than papering over.

The consequence to accept knowingly: converting `test2` and `test5` into corpus
packages (§7) will produce those eight violations. They are findings about those
fixtures, not about SemForge, and the right fix is to type the fixture values.

### 10.2 Amend §7.2/§7.6 for H6

`architecture.md` claims V1 catches the dead-shape case. It does not (H6): a
never-matching SPARQL body reads as `conformant` under any per-example scheme.
The fix is small — add coverage as a distinct mechanism, and soften V1's claim to
what it actually delivers. **Not applied; awaiting your call**, since it changes
a document already reviewed.
