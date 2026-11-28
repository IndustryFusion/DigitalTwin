# Proposal

Issue: #1183

## Why

An entity whose children hang off one Relationship with several instances (one
`datasetId` per child, e.g. `hasPump` with a dozen pumps) cannot have **one**
child removed with its subtree where the user sees it: under the parent.

- On the row of one instance, Remove… takes only that reference. The child and
  its own children stay in the file, pointed at by nothing.
- On the attribute's row, Remove… takes every instance, and its question names
  only the attribute. A user who means one child loses all the references.
- Remove with subtree… (#1174) is offered only on the child's own entity row,
  which in a large model is far from the reference.

## What Changes

- **Remove with subtree… on a reference row**: the row of a Relationship's
  instance, of one of its `datasetId`s, or of a Relationship attribute with a
  single instance, in Entities & Test Cases and in the case page's row menu.
  It removes the entity the row points at, with the subtree Copy with subtree
  copies. Of the parent's references, only those into the removed subtree go,
  so the attribute's other instances and their entities stay.
- **The removal of an attribute names its instances**: "all 15 instances of
  hasPump" when it has several.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `semforge-sdk/entity-removal`: Remove with subtree… is also offered on
  reference rows; removing an attribute says how many instances go.

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK`): the tree rows of a Relationship
  name the entity they point at and the file's digest; the extension's Remove
  with subtree… on those rows, its menu entries, the case page's row menu and
  the attribute removal's question. The request `semforge/removeEntity` is
  unchanged. No new dependency.
- No change to any other component, image, chart or deployment.

## Out of Scope

- Remove entity… (without the subtree) on a reference row.
- A reference to an entity written in another file: Remove with subtree… is
  refused there, as from the entity's own row in that file.
