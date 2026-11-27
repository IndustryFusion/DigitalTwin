# Proposal

Issue: #1174

## Why

A test case that varies the main model is built by pasting a scene into it
(#1109) and cutting away what the case is not about. Remove entity… (#1118)
takes out one document: an entity's children, theirs, and the parent's
reference to it stay in the file, the reference pointing at nothing. Cutting a
part of a tree away takes one removal per entity and leaves the references.

## What Changes

- **Remove with subtree…** on an entity's row in Entities & Test Cases,
  directly below Remove entity…, as Copy with subtree sits below Copy entity.
- **It removes the subtree Copy with subtree copies** from the row's file;
  members written in another file stay, and so does a child another entity
  still points at, with what is reached only through it.
- **The references to what is removed go with it**: each relationship object
  left in the file that is a removed entity, matched by its IRI however it is
  written, the instance when no object is left, the attribute when no
  instance is left.
- **The question** names what goes, what stays and why; the refusals and the
  whole-file write are those of Remove entity.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `semforge-sdk/entity-removal`: adds Remove with subtree….

## Impact

- Contract between components: **no**.
- SemForge SDK (`semantic-model/SemForge-SDK`): `cooked/removeentity.py`
  (`remove_subtree`), the request `semforge/removeEntity` (an optional
  `subtree`), the extension's command, its menu entry and its question. No
  new dependency.
- No change to any other component, image, chart or deployment.

## Out of Scope

- Removing references to an entity with Remove entity…: it keeps reporting
  them, as specified.
- Remove with subtree… on an entity's card on a page.
