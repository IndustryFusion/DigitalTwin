# Design

## Context

An entity is one document of a JSON-LD file: a file of the main model, a test
case's own file, or a file cases include. The tree and the pages show one row or
card per document. `semforge-sdk/editor-layout` is not contradicted: the action
is in a row's menu and on a card, not in a title bar, and not in the palette.

## Decisions

### D1: A row stands for a place in a file's content
- **Chosen:** rows and cards carry the document's place in its file and a digest
  of the file's content. A removal names both and is refused when the content is
  another one; the view and the page are then shown anew, and it can be repeated.
- *Alternative:* the id. Rejected: a file may define it twice.
- *Alternative:* the place and a digest of the document. Rejected: an edit
  elsewhere in the file can change what the entity means to the case, the issue
  asks to refuse a changed file, and shown anew it costs one click.
- *Alternative:* the number of the card on the page. Rejected: what is no entity
  has no card, so the numbers differ from the places.

### D2: The removal is checked against the question
- **Chosen:** the question carries a fingerprint of what it follows from (the
  file's content, the entity's place, the cases that use the file and all their
  asserts); the removal is refused when that differs. What was read of the file
  as a graph is not in it: one run may build the graph and the next not (D3),
  which is no change of the file.
  Unsaved edits of the file, behind links too, are refused before and after the
  question, as a paste of entities does.
- *Alternative:* only the file's content. Rejected: a new assert on the entity
  would go unsaid.

### D3: References are found in the graph
- **Chosen:** the file without the entity is read as a graph, as validation reads
  it. Only a relationship's object (`hasObject`, `hasObjectList` and the list
  nodes) points at it; a datasetId, a type or a value naming it does not. What
  points at the entity's IRI is found however either spells the id, in
  sub-attributes, several objects and lists, and is named as its document has it.
  When the graph cannot be built (a context that is not to be had), the question
  says what points at it is not known, and the removal is still possible.
- *Alternative:* compare ids as written. Rejected: misses a prefix or a whole IRI.
- *Alternative:* refuse when there is no graph. Rejected: removing a broken
  entity is one way to repair a case.

### D4: References are said, not changed
- **Chosen:** asserts, relationships, includes and pinned residues stay. A case
  whose entity is gone fails, and says so; a dangling relationship can be the
  point of a bad case.
- *Alternative:* remove the asserts with it. Rejected: an assert is the evidence
  that a constraint can fire; it must not go without its author.

### D5: The main model too
- **Chosen:** offered on every entity's row and card. The editor adds entities
  and removes attributes in the main model already; the question says that the
  file is the main model's.
- *Alternative:* only in test cases, as for pasting. Rejected: the issue asks for
  it on an entity's row in Entities & Test Cases, which has both, and a removal
  that is asked for by name on one row is not a paste gone to the wrong place.

### D6: The last entity leaves an empty list
- **Chosen:** the file stays, holding `[]`, whether it was a list or one object.
  It loads, the case keeps its declaration, and an entity can be added to it.
- *Alternative:* delete the file and its declaration. Rejected: that is Delete…,
  which says what evidence it costs.
- *Alternative:* refuse. Rejected: the last one is often to be replaced.

### D7: Only files the views show
- **Chosen:** a main model file, a declared case or a file a case includes, in
  the package; entities inside `"@graph"` are refused, as the row there stands
  for all of them.

## Risks

- A large main model takes about as long to ask about as to load. Accepted: it is
  one question at a time.
- The file is written with the two-space indentation every edit of SemForge
  writes; a file formatted by hand changes its formatting once.
- It shares helpers with the copy and paste of entities (gh-1109): reading a file,
  writing it whole, a case's files, unsaved edits. Whichever is merged second
  takes the first one's.
