# Proposal

Issue: #1109

## Why

A test case often needs entities that the main model, or another case, already
has: one entity, or an entity with its whole hierarchy (in an OPC UA package, a
machine with its components). Today they are written again, or copied by hand
in the `.jsonld` with their `@context` adjusted, or the case is started from the
whole main model and cut down. None of these is practical for a hierarchy of
dozens of entities.

## What Changes

- **Copy entity** and **Copy with subtree** on an entity's row in Entities &
  Test Cases and on its card, and **Paste** on a test case's row, the rows in
  it and its page; Ctrl/Cmd+C, +Shift+C and +V in the view, Ctrl/Cmd+V on the
  page. What was copied is a snapshot and can be pasted into several cases. An
  entity's row can be dragged onto a test case.
- **A subtree is the OPC UA hierarchy**: children are what a relationship leads
  to whose shape names the reference type `HasChild` or one below it; undeclared
  relationships are decided by other shapes, and else by the data.
- **Pasting never loses or doubles data silently**: it asks before it replaces
  an entity of the case that has other values, and before it changes a file that
  other cases include; it leaves what an included file has, and writes nothing
  when nothing changes. A relative `@context` still names the same file.
- **What was left out is said** on copying and on pasting.
- Two language server requests, to copy and to paste.

## Capabilities

### New Capabilities
- `semforge-sdk/entity-copy`: copying an entity or its subtree, and pasting it
  into a test case. Not part of `semforge-sdk/test-cases`, which defines how New
  test case… starts a case and what that start declares and runs: a paste
  creates and declares no case, and the copy side (what a subtree is) concerns
  the main model as much as a case.

### Modified Capabilities

None.

## Impact

- Contract between components: **no**. `base:hasReferenceType` is read as the
  OPC UA tool chain writes it into the shapes today; nothing writes it anew.
- SemForge SDK (`semantic-model/SemForge-SDK`): the instance model
  (`semforge/cooked`), two added language server requests, the extension
  (`vscode/src`, `package.json`: three commands, their menus and keys) and its
  README. No new dependency.
- No change to the `semforge` command line, to any other component, image,
  chart or deployment.

## Out of Scope

- Pasting into the main model, or from one package into another.
- Copy from an entity's id anywhere on a page (a page's right-click menu).
- Removing an entity; undoing a paste other than by version control or by
  removing what was pasted.
- Following other relationships than children, and entities written in a
  relationship's object: a file with one is refused, as one with `"@graph"`.
- Keeping what was pasted in sync with its original.
