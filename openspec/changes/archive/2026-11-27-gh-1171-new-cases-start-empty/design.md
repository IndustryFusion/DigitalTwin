# Design

## Context

`new_case` (expect/newcase.py) writes the case of New case… on a shape page and
of New test… of a query on a type page. It copies a scene from a case or the
model, or writes a new entity, and asserts that the query fires on the entity of
a failing test. Copy entity / Copy with subtree and Paste (#1109) put any
entities of the main model into a case.

## Conflicts

None with approved specifications beyond the four requirements this change
modifies. A failing case without an assert fails as unfinished, as specified for
a failing test case whose reason is not asserted (#1087).

## Decisions

### An empty file by default, the scene on request

`new_case` takes `scene`, `empty` by default or `copy`. The extension never asks
for `copy`; the start from a scene, its tests and its specified behaviour stay,
for a request that names it.

Alternatives:
- **Remove the start from a scene.** Less code, but it takes away a start other
  tools may use, and its tests with it; nothing requires removing it.
- **Ask for the start in New test…** (empty, or from a scene). One more question
  in every test made, for a start authors cut down anyway.
- **A setting.** A preference for something one action (Paste) replaces.

### No assert while there is nothing to name

An empty case has no entity for the query to fire on, so a failing one is
declared without an assert, as New test case… declares a failing case. An
assert of the constraint alone would not do: an assert without `resource`
matches only a firing without one.

### The answer says how the case started

`semforge/newCase` answers `scene` (`empty` or `copy`), and the extension words
its message by that, not by whether an entity is named.

### The shape page asks good or bad first

With the words of New test… of a type page (Should conform, Should fail), and a
name suggested free in the folder the answer picks (`silent`, `fires`).

## Risks

- A case that should conform passes while it is empty. Its description and the
  message say so; once something is pasted, it is judged like any case.
