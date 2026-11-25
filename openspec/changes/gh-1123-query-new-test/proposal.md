# Proposal

Issue: #1123

## Why

An attribute's row on a type page offers New test…; the row of a SPARQL query of
the same page does not. A test for a query is started from its shape page, only
one that should fail, and on an entity of whichever type the query reaches
first, not of the type whose page is open.

## What Changes

- **New test…** in the menu of a SPARQL constraint's row on a type page: one that
  should conform (the query runs on it and does not fire), or one that should
  fail (it asserts that the query fires, and fails until its data makes it).
- **Its scene has an entity of the page's type**, from a case, from the model
  with what it points at, or a new one.
- A `sh:rule` derives data and never fires, so its row does not offer it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `semforge-sdk/test-cases`: adds New test… of a SPARQL query.

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK`): the writer behind New case…, the
  language server request `semforge/newCase` (two optional parameters more, and
  the outcome of the run in its answer), the type page's menu, the README. No new
  dependency.
- No change to any other component, image, chart or deployment.

## Out of Scope

- New case… of a shape page: what it offers, writes and says stays as it is.
- Suggesting, or writing, data that makes a query fire.
- New test… of an attribute (#1087).
