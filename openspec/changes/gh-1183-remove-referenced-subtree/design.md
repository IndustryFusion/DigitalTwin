# Design

## Context

Remove with subtree… (#1174) is a request on an entity: `semforge/removeEntity`
with `subtree`, the entity's IRI, its file and the digest of that file as
shown. It removes the subtree Copy with subtree copies and every reference in
the file into what it removes, matched by IRI however it is written: one
object of several, the instance when no object is left, the attribute when no
instance is left. So the removal itself already keeps the other instances of
the parent's attribute. What is missing is a way to start it from the
reference.

## Decisions

### A reference row names its entity

A tree row of a Relationship's instance, of one of its `datasetId`s, or of a
Relationship attribute with a single instance carries the IRI of the entity it
points at (`object`) and the digest of its file, as entity rows already carry
theirs. The case page's rows of a Relationship already name it (`target`),
and their card the file's digest. The extension starts Remove with subtree…
from such a row with that entity, the row's file and the digest. The request
is not changed: it is the one an entity row sends. A file changed since the
row was shown is refused as before.

Alternatives:
- **A request on the reference** (entity, attribute, `datasetId`): a second
  path to the same removal, with refusals of its own. Rejected.
- **Remove… on an instance row removing the entity too**: it would change what
  Remove… on any instance does, also on a Property. Rejected.

### Where it is offered

The rows get a context value of their own (`…Ref`, beside their kind's), so
every menu of their kind still applies, and Remove with subtree… is added for
them only. Rows of a Property, a type or an entity's attributes that are not
references keep not offering it. The case page's row menu offers it on a
Relationship's row as the first removal, worded "Remove what … points at, with
its subtree"; the existing removals say "only this reference; the entity
stays" and "ALL n instances".

### The attribute's question

Removing an attribute row whose attribute has several instances asks "Remove
all n instances of hasPump from …?": the count is the number of its
`datasetId` rows.

## Risks

- A Relationship whose object is a list (`objectList`) points at several
  entities: its row names none, and Remove with subtree… is not offered there.
