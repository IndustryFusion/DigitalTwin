# Design

## Context

New test case… (`semforge/testCaseOptions`, `semforge/addTestCase`) writes a
`.jsonld` file into `examples/<suite>/good/` or `bad/`, declares it in the
`expectations.yaml` beside it and validates it once. Its starts are a copy of
a case (includes written in), one entity of the model, a fresh entity of a
type, an empty file, or declaring a file nobody runs. The main model is one
file or a directory of files (`main/`, `model-instance/`, `model/`); the
package loader lists them in load order.

A case is composed from its includes and its own file into one RDF graph
(the store's `compose`); the main model is not part of a case's graph. No
existing specification covers New test case…, and no other component reads
what it writes beyond the `semforge test` runner. The SemForge README
describes the starts and is updated.

## Decisions

### D1 — The model's documents are written into the case

- **Chosen:** read every JSON-LD file of the main model in load order and
  write all of its documents, unchanged and in order, into the new case file.
  The case is then a snapshot that the existing case-page tools edit.
- *Alternative:* declare the case with the model files as `include:`.
  Rejected: includes and the case parse into one graph, so a case could not
  remove an included entity or override a value; the issue rules it out.
- *Alternative:* write the model as the package's normalised graph (one
  document per entity, re-serialised). Rejected: it rewrites what the
  modeller wrote (contexts, compact names, order) and differs from how a copy
  of a case writes its includes in.

### D2 — The description is set after the one run

- **Chosen:** declare the case with the neutral placeholder "Started from the
  whole main model.", run it once, and then set the description from the
  outcome: conforming or violating model, good or bad case, each saying that
  it was started from the whole main model and whether the model conformed.
  Only when the caller gave no description; a case that does not load keeps
  the placeholder.
- *Alternative:* validate the main model before writing the case. Rejected:
  a second full validation for the same data; the run that every start does
  already answers the question.
- *Alternative:* one fixed description per expectation. Rejected: a bad case
  from a model that already violates passes as it is, and a fixed "fails
  until edited" would then be wrong.

### D3 — The start is offered only when there is a main model

- **Chosen:** the options carry the main model's files; the picker offers
  "The whole main model" only when that list is not empty, between "A copy of
  a case" and "An entity from the model", and it needs no second pick. The
  suggested name is the first of `whole-model`, `whole-model-2`, … that no
  case or file in the target folder has. The SDK refuses the start for a
  package without a main model.
- *Alternative:* always offer it and let an empty model write an empty case.
  Rejected: that is "An empty file" under another name.

The start list is a plain choice among starts, not a list with actions, so
the "actions on top" rule of long pickers does not apply to it.

### D4 — A relative context is rewritten for the case's folder

- **Chosen:** a relative `@context` string, or a relative entry of an
  `@context` list, is rewritten relative to the new case's folder, so it
  names the same file (`context.jsonld` becomes `../../../context.jsonld`).
  URLs, absolute paths and inline objects are kept.
- *Alternative:* resolve relative contexts against the package root when a
  case is composed. Rejected: it changes how every case reads its context,
  and a case file would mean something different read on its own.
- *Alternative:* make them absolute paths. Rejected: the package would stop
  working when moved or checked out elsewhere.

### D5 — Ids shared by model files are reported, not merged

The model loader parses all model files into one graph and does not report
an id that two model files define; the identity check only looks at test
cases. Such an id is two definitions of one entity in the model, and the
same in the case's graph.

- **Chosen:** write each definition as it is and name the shared ids in the
  result and in the editor's message. The case means what the model means;
  the identity check flags the repeat in the case file, where it can be
  resolved by editing.
- *Alternative:* merge the documents into one per id. Rejected: the JSON-LD
  documents may use different contexts and attribute forms, and a merge that
  is right for all of them is a feature of its own.

### D6 — Nothing half-made stays behind

- **Chosen:** the case file is written to a temporary file beside it and
  renamed into place, and when anything fails after that and before the
  outcome is returned, the file is removed and the `expectations.yaml` put
  back as it was (removed when this created it). This holds for every start.
- *Alternative:* leave the file and tell the user. Rejected: a declared case
  that nobody meant to keep is a failing test in the suite.

## Risks

- A large model (an OPC UA package) makes a large case file. The case is
  validated once, as any other start; that cost is the one `semforge test`
  pays for the case later anyway.
