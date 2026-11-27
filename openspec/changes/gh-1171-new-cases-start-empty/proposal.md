# Proposal

Issue: #1171

## Why

Entities can be copied from the main model and pasted into a test case (#1109),
so the scene a new test needs is best pasted by its author: exactly the entities
the case is about. New test… of a SPARQL query and New case… of a shape page
still choose a scene themselves, which the author usually has to cut down first.
New case… of a shape page also asks nothing about the case, unlike every other
place a test is made, and always writes one that should fail.

## What Changes

- **New test… of a SPARQL query** and **New case… of a shape page** write an
  empty case by default. One that should fail is declared without an assert: it
  fails as unfinished until its data makes the query fire and Assert it names
  the firing. One that should conform is declared without an assert.
- **New case… of a shape page** first asks Should conform or Should fail, then
  the name, suggested free in the `good/` or `bad/` folder the answer picks.
- **The former start from a scene** stays for a request that asks for it
  (`scene: copy` in `semforge/newCase`), as specified today.
- **New test case…** offers An empty file first.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `semforge-sdk/test-cases`: a query's test and a shape page's case start empty;
  the shape page asks what the case should show; a scene is started only when
  asked for; An empty file is the first start of New test case….

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK`): the writer behind New case… and
  New test… of a query, the request `semforge/newCase` (an optional `scene`, and
  `scene` in its answer), the shape page, the type page's message and New test
  case…'s list of starts. No new dependency.
- No change to any other component, image, chart or deployment.

## Out of Scope

- New test… of an attribute: its scene is a generated value that breaks or
  meets the attribute's constraint, which is the point of that test.
- Removing the start from a scene: it stays as a request option.
