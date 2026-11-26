# Design

## Context

Entities of a package are NGSI-LD documents in the main model's file(s), in test
cases and in files that cases include. A case and its includes are parsed into
one RDF graph: an id defined in two of them has both values. Shapes generated
from an OPC UA nodeset carry, beside a relationship's path, the reference type it
was made from (`base:hasReferenceType`). No existing specification covers
copying; `semforge-sdk/test-cases` starts a case from the whole model as a
snapshot with a relative context moved, and this follows the same two rules.
`semforge-sdk/editor-layout` is not contradicted: no title-bar button and no view
message is added.

## Decisions

### D1: A copy is a snapshot, kept by the editor
- **Chosen:** copying takes the documents as they are in their files, with the
  package and the folder each was read from; pasting writes those. The original
  may change or go, and one copy is pasted into several cases.
- *Alternative:* remember the id and read it on pasting. Rejected: the paste
  would not be what was copied, and fails when the original is gone.
- *Alternative:* the system clipboard. Rejected: pasted text in a page or a view
  has no known folder for a relative context, and overwrites what was there.

### D2: What a child is, in three steps
1. The shapes of the entity's types and of the types above decide, with the
   shapes they apply and their connectives: a relationship is to a child when
   its shape names a reference type that is `HasChild` or below it. The
   relationships of the knowledge count, and those of the OPC UA core are known
   even where the knowledge leaves them out. Declared without one: no child.
2. Not declared there: the other shapes declaring the same relationship decide.
   Any naming a child reference makes it one.
3. Declared nowhere, in a package whose shapes name reference types: the target
   is a child when it is defined and no other entity points at it, where the
   copied entity or the target is written. The editor says how many children
   came this way.
- *Alternative:* everything pointed at. Rejected: references to a parent, a
  neighbour or a shared entity take most of a model along.
- *Alternative:* the shapes only. Rejected: a folder's content and other
  instance-only components are not declared by any type, so the subtree of most
  machines would stop at their folders.
- *Alternative:* always the data. Rejected: in a package without reference types
  a relationship nobody else uses need not be a hierarchy.

### D3: Where a subtree's entities are found
- **Chosen:** for an entity of a case, the case, what it includes, then the main
  model; for one of an included file, that file, then the main model; else the
  main model. Only data files of the package are read. An id that one of these
  defines more than once is copied once, the row's own file first, and named.
  A case that is another case's file by a link is read with its own includes.
- *Alternative:* the row's file only. Rejected: a case that varies one entity
  would copy a hierarchy with holes the model can fill.

### D4: Replace, included and shared files
- **Chosen:** the editor first asks what a paste would do. Entities with other
  values are replaced only on request, in their place; the order of keys is no
  difference, the type of a value is. Included files are never written. When the
  case's own file is included by other cases, the editor asks. Nothing that the
  question answers decides a refusal, so the question and the write refuse alike,
  and the write with Replace writes what the question named.
- *Alternative:* always replace. Rejected: it loses what the case is about.
- *Alternative:* write an included entity into the case as well. Rejected: its
  values would add up.

### D5: The paste is checked, and whole
- **Chosen:** the paste is refused when the copy was taken in another package,
  when it is not what a copy holds, and while the case file has unsaved edits
  (saving them later would undo the paste). Folders are the package's own names,
  so a package made of links stays one package. The file is replaced whole, and
  a link stays a link.
- *Alternative:* allow another package. Rejected: prefixes, contexts and the
  types themselves are the other package's.

### D6: Ids are compared as the graph has them
- **Chosen:** relative ids, and ids written with a prefix of their context, are
  resolved for finding children, and reported and written as they are in the
  file. A prefix the context leaves open is expanded by the package's names, as
  the trees do.
- *Alternative:* compare the text. Rejected: a child named by its IRI in one
  entity and by a prefix in its own would be "written nowhere".
- *Alternative:* leave an open prefix as it is, as rdflib reads it. Rejected:
  `kms.yaml` names the namespace, and the package's own trees show the entity
  by it; such an id is no other entity to its author.

### D7: A paste button on the page, keys in the view only
- **Chosen:** keys act when the list of Entities & Test Cases has the focus and
  no text is typed. On a case page Ctrl/Cmd+V pastes, except in a field.
- *Alternative:* bind the keys in any SemForge page. Rejected: copying text from
  a page is what Ctrl+C is for there.

### D8: Entities written inside are refused
- **Chosen:** a file with entities inside `"@graph"`, or with an entity written
  in a relationship's object (in NGSI-LD the object is an id), is not read by a
  copy or a paste, and the message names the file, the entity and what is
  written in it. A reference `{"@id": …}` and a Property's value are no entity.
- *Alternative:* follow and keep entities written inside others. Rejected: one
  defined by itself as well, or in another file, ends up twice or is said to be
  missing; only part of it could be supported.

## Risks

- Step 3 of D2 can be wrong either way; it is confined to undeclared
  relationships, and reported.
- A subtree of thousands of entities makes a large case. Working it out is
  linear in the subtree (6,000 entities: about a second).
