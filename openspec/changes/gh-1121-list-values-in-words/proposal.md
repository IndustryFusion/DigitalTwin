# Proposal

Issue: #1121

## Why

The attribute editor shows *one of* (`sh:in`) and *exactly* (`sh:hasValue`) as
Turtle and edits them in one text field. Adding a value to `( "Executing" )`
writes the whole list as one quoted text. A text with a comma, quotes or a colon
cannot be told from a list, a quoted text or a prefixed name, and an item with a
datatype or a language cannot be edited without knowing Turtle.

## What Changes

- **Values are shown as they read**, without quotes, brackets and datatypes.
- **One value per row**, added, changed and taken out; *exactly* has one row.
- **The kind of a value** (text, number, true/false, vocabulary term) follows from
  the value's datatype or from what was typed, and can be chosen.
- **What was not touched stays the same RDF term**, with its datatype or language.
- **A value that is not of its kind is refused.**
- A list written as Turtle in a text field stays a list.

## Capabilities

### New Capabilities
- `semforge-sdk/list-values`: how the values of `sh:in` and `sh:hasValue` are
  shown and edited.

### Modified Capabilities

None.

## Impact

- Contract between components: **no**. The shapes hold the same `sh:in` and
  `sh:hasValue` as before.
- SemForge SDK (`semantic-model/SemForge-SDK`): reading and writing list items,
  the value's forms (`semforge/cooked`), the language server request
  `semforge/editValueForms` (a value may be rows), the attribute editor, the type
  page's parameters, the README. No new dependency.
- The items are read with the list reading of #1087, so the implementation is
  based on it.
- No change to any other component, image, chart or deployment.

## Out of Scope

- The ticked list of a vocabulary class's values on the type page.
- Choosing a datatype or a language for a new value other than the one the value's
  shape names.
- Other constraints that hold values (`sh:equals` and the like).
- Opening the list of a type page's row in the attribute editor; the row keeps its
  text field.
