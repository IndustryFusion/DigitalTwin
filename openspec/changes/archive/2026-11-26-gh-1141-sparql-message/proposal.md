# Proposal

Issue: #1141

## Why

The SPARQL workbench shows a SPARQL constraint's `sh:message` but cannot change
it: adding, changing or removing it means editing `shacl.ttl` by hand. Nothing
says when the message does not fit its query, and on the platform that matters.
shacl2flink fills each `{?x}` of the message from the column `x` of the compiled
query, puts the message into SQL between apostrophes, and compiles only a SPARQL
constraint that has a message. A placeholder for a variable the query does not
select, an apostrophe, or a missing message therefore breaks there, while
SemForge, as pyshacl, shows the placeholder as text and validates as before.

## What Changes

- **The message is edited where the query is**: the workbench shows it with
  **Edit message** (**+ Message** when there is none); the constraint's menu on
  the shape page and on the type page, and the workbench's own menu, open the
  field directly. A rule has no message.
- **The field helps write it**: the variables the query, as it is edited,
  selects are offered for insertion; a preview fills the message from a
  violating row of the last run.
- **What does not fit is warned about**: a variable the query does not select,
  an apostrophe, and a missing message, while typing, in the Problems panel and
  in `semforge check`; a query edited so that its message no longer fits says so
  in its editor.
- **Saving writes that one value** into `shacl.ttl`, its language tag kept,
  checked by parsing, and refused if the message or the query changed in the
  file meanwhile. Emptied, the message is removed after asking. A constraint
  with several messages, or one that is no text, is edited in the `.ttl`.
- Two language server requests: check a draft message, save a message.

## Capabilities

### New Capabilities
- `semforge-sdk/sparql-message`: the `sh:message` of a SPARQL constraint, seen,
  checked and edited in the editor.

### Modified Capabilities
None.

## Impact

- Contract between components: **no**. The SDK writes an `sh:message` as
  shacl2flink already reads it; nothing is added to what shacl2flink reads.
- SemForge SDK (`semantic-model/SemForge-SDK`): the workbench page and its
  server side (`semforge/cooked`), the sanity check behind the Problems panel
  and `semforge check` (three new warning codes), the SPARQL query documents'
  diagnostics, two language server requests, the shape, type and workbench
  pages of the extension, the README. No new dependency.
- No change to shacl2flink or any other component, image, chart or deployment.

## Out of Scope

- Changing how shacl2flink fills or escapes a message (an apostrophe stays a
  warning in the SDK, not a fix in the compiler).
- Several `sh:message` values of one constraint (one per language): they are
  shown and left to the `.ttl`.
- Messages of property and node shapes, and of SPARQL rules.
- A placeholder for a variable of the query's pattern that it does not select:
  it is warned about, not added to the SELECT.
