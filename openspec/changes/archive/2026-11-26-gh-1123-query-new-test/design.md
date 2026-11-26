# Design

## Context

New case… of a shape page copies a scene the query is evaluated on (a case, else
the model's document), declares it `expect: invalid` and asserts that the query
fires. New test… of an attribute does the like for one attribute, and can write a
new entity with its required attributes. This change offers the first on a type
page, for that type, and uses the second where the type has no entity.

## Conflicts

None with approved specifications. #1087 (in progress) defines New test… of an
attribute, whose failing test asserts nothing: which constraint it should break is
not known. A query's failing test is about that one query, so it is asserted from
the start; it fails until the query fires, which is what #1087 asks of a failing
test. The two kinds of test have the same names in both, and neither change needs
the other.

## Decisions

### D1: Two kinds of test, the same as an attribute's
- **Chosen:** should conform and should fail.
- *Alternative:* failing only, as New case…. Rejected: a query no case holds on is
  as untested as one that never fires.

### D2: The type of the page decides the scene
- **Chosen:** an entity of the page's type or below it.
- *Alternative:* the first entity reached, as New case…. Rejected: on the page of
  one type it writes a test about another.

### D3: From data that conforms
- **Chosen:** a conforming test starts from a case expected to be valid, the model
  or a new entity. A failing one prefers a valid case, as New case…. From the
  model, a conforming test is about an entity the query does not fire on there,
  where the model has one.

### D4: A new entity only where the query is evaluated on it
- **Chosen:** refused otherwise. An assert, or silence, on an entity the query
  never sees proves nothing: the one could never pass, the other always would.
  The same holds for an entity copied from the model that the query reaches
  there only through what is not copied with it.
- *Alternative:* write it and let the modeller add what the target needs.
  Rejected for that reason.

### D5: A relative context is moved
- **Chosen:** as a start from the whole main model does: a copied document's
  relative `@context` is rewritten for the case's folder.
- *Alternative:* copy contexts as written, as New case… did. Rejected: the case
  does not load where the context is relative.

### D6: One writer
- **Chosen:** the writer of New case… gets the kind of test and the type as
  optional inputs; without them it does what it did.
