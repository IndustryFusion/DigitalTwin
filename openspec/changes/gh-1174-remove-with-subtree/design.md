# Design

## Context

`remove_entity` (`cooked/removeentity.py`) removes one document from the file a
row or card stands for, refuses what changed meanwhile (`digest`, `plan`),
writes the whole file or nothing, and reports what still points at the entity
without changing it. `copy_entities` (`cooked/examples.py`) with `subtree`
walks the children an entity has by the shapes' (or the data's) HasChild
references, as far as the file, what a case includes and the main model have
them.

## Conflicts

The entity-removal spec says what refers to a removed entity is reported,
never changed. That stays so for Remove entity…. Remove with subtree… is a
separate command whose point is to leave no reference into what it cut away;
it says so in its question, and nothing is written before the author confirms.

## Decisions

### The subtree is the one Copy with subtree takes

`remove_subtree` calls `copy_entities(…, subtree=True)` and removes those of
its entities the row's file writes. One walk for both commands, so what is
pasted in is what can be taken out again.

Alternatives:
- **Its own walk over the file's relationships.** It would follow references
  that are no children (an Organizes, a pointer to a workpiece) and remove
  entities Copy with subtree would never have brought along.
- **Every entity the root reaches.** The same, worse.

### Only the row's file is written

A member written in a file the case includes, or in the main model, stays
there and is named in the question. Writing the shared file would change
every case that includes it.

### A child another entity uses stays

A member other than the root that an entity outside the subtree points at
stays, with what is reached from the root only through it, and is named.
Otherwise removing one tree would break another one that shares a part.

### References go, matched by IRI

Each relationship object of an entity left in the file that is a removed
entity goes: one object of several, the instance when it has none left, the
attribute when it has no instance left. Objects are resolved with the
document's context (`_Names.resolve`), as Remove entity finds references, so a
prefixed, relative or whole id counts alike; `object` lists and `objectList`
entries too. When a context cannot be had, ids are compared as written and the
answer says why (`unread`).

### One request, one question

`semforge/removeEntity` takes `subtree`; check, plan and the refusals are those
of Remove entity, with the plan covering the members that go, the file and the
asserts of the cases that use it.

## Risks

- A reference outside the row's file (another case, the main model) to a
  removed entity stays; it is outside what is written, and the question names
  the cases that share the file.
