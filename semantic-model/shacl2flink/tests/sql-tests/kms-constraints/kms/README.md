# The real kms shapes, under the SQLite oracle

Every other directory here defines its own small `shacl.ttl` to exercise one
feature. This one runs **the shapes that are actually deployed** — `shacl.ttl`,
`knowledge.ttl` and `model1.jsonld` are symlinks into `semantic-model/kms/`, not
copies, so the fixture cannot quietly drift onto last month's shapes. A copy is
how the sql-core chart ended up running SQL the generator had already fixed.

## Why it exists

The kms shapes had no oracle coverage at all: `tests/e2e-kms` feeds
`make test-flink-e2e`, and the SQLite suite only ever saw the small per-feature
shape files. So the one mechanism that can tell "this constraint was satisfied"
apart from "this constraint never ran" was never pointed at the production
shapes.

The gap first surfaced as an apparent divergence: with the cutter PROCESSING
and its filter not ON, `StateOnCutterShape` — *"Cutter running without running
filter"* — raised `critical` in SQLite while Flink appeared silent. The
divergence turned out to be in the observer, not the engine: the SPARQL
statements write straight to the alerts sink (never to
`constraint_trigger_table`, where the property and count checks report), and
the test writes had typed `hasState` as a Relationship (`{"object": ...}`)
where the model types it as a Property with an IRI value — a row the rule's
`type = 'Property'` join predicate correctly refuses. With a correctly typed
flip, Flink raises the same `critical` within seconds and retracts it on
recovery. The two dialects compile from the same templates and their join
skeletons are word-for-word identical; this fixture is what pins that down —
any future *real* divergence between the oracle and the deployed SQL shows up
here as a one-line diff.

## The four models

`model1` is the model as shipped: the healthy baseline, where
`StateOnCutterShape` is `ok`.

`model2` is that model with `urn:filter:1` switched to `state_OFF` while the
cutter keeps running. The two expected outputs differ in exactly one line:

    -'urn:plasmacutter:1','SPARQLConstraintComponent(StateOnCutterShape)','ok'
    +'urn:plasmacutter:1','SPARQLConstraintComponent(StateOnCutterShape)','critical'

`model3` is the shipped model with `urn:plasmacutter:1` idling at `state_ON`
while the filter keeps running — the trigger for `StateOnFilterShape`
(*"Filter running without running assigned machine"*). Again one line:

    -'urn:filter:1','SPARQLConstraintComponent(StateOnFilterShape)','ok'
    +'urn:filter:1','SPARQLConstraintComponent(StateOnFilterShape)','warning'

That rule could never fire before 2026-08-22: it asked for `?pc a
Plasmacutter` while the instance types the cutter as `Cutter`, and its FILTER
compared against the typo `iffBaseEntities:state_PROCESSING`. `model3` is the
regression guard for that fix.

`model4` is the shipped model with `urn:plasmacutter:2` — typed
`iffBaseEntities:Plasmacutter`, a SUBCLASS of Cutter — idling while its
`urn:filter:2` keeps running. Again one line:

    -'urn:filter:2','SPARQLConstraintComponent(StateOnFilterShape)','ok'
    +'urn:filter:2','SPARQLConstraintComponent(StateOnFilterShape)','warning'

It guards the subtype semantics: a plain `?pc a iffBaseEntities:Cutter`
compiles to an EXACT type match (only `sh:targetClass` goes through the
subclass closure), so the rule binds the machine's type through
`rdfs:subClassOf* iffBaseEntities:Cutter` explicitly. Everything else in
each diff is identical, so a regression in one rule cannot hide behind
unrelated noise.

`model2`, `model3` and `model4` are static files rather than symlinks, since
they have to differ from the shipped model. If `model-instance.jsonld` gains
or loses attributes, all three need regenerating along with all `_result`
files — and the one-line diffs above are the check that they still isolate
what they are meant to.

The `CountConstraintComponent(hasState[0] ==> hasXXXWorkpiece)` warnings on
`urn:cutter:1` and `urn:filter:1` in both models are correct: the shape requires
that sub-attribute `[1, 1]` and only `urn:plasmacutter:1` carries it.
