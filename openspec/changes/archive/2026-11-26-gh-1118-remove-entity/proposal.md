# Proposal

Issue: #1118

## Why

The SemForge editor adds an entity to a test case or to the main model, and
removes an attribute, but does not remove an entity. The `.jsonld` has to be
edited by hand, where nothing says what still points at the entity, which cases
assert something on it, or which other cases use the file.

## What Changes

- **Remove entity…** on an entity's row in Entities & Test Cases and on its card,
  in a test case, in a file that cases include, and in the main model.
- **It asks first**, and says what the removal touches: what still points at the
  entity in its file, the cases that assert something on it, the cases that use
  the file, whether the file is of the main model, is left empty, or defines the
  entity once more. Only the entity is removed; asserts and relationships stay.
- **It removes the one that was meant**: an id may be written twice in a file. A
  file that changed since it was shown, or since the question, is refused, and so
  is one with unsaved edits. A file is written whole or not at all.
- One language server request; entity rows and cards say their place in the file
  and which content of it they were read from.

## Capabilities

### New Capabilities
- `semforge-sdk/entity-removal`: removing an entity from the file it is written
  in. Not part of `semforge-sdk/test-cases`, which defines how New test case…
  starts a case and what that start declares and runs: a removal creates and
  declares no case, and is offered in the main model and in included files too.

### Modified Capabilities

None.

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK`): the instance model
  (`semforge/cooked`), one added language server request, two added fields of
  entity rows and cards, the extension (`vscode/src`, `package.json`: one
  command and its menu entries) and its README. No new dependency.
- No change to the `semforge` command line, to any other component, image, chart
  or deployment.

## Out of Scope

- Removing an entity and its children together, or several entities at once.
- Changing what refers to the entity: relationships, asserts, residues, includes.
- Undoing a removal other than by version control.
- Removing an entity that is written inside another entity's document.
- What points at the entity from other files.
- Entities inside `"@graph"`.
