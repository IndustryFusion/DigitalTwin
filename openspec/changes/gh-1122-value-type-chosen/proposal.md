# Proposal

Issue: #1122

## Why

A value on a test case's page is shown as it is written: `50.0` may be a double,
an integer, a decimal or a text. Which one decides whether a datatype constraint
fires, and the page does not say it. Nor can it be chosen: the editor writes a
number as the attribute's shape asks, so a test that a shape rejects another
type needs its JSON-LD edited by hand.

## What Changes

- **The type is said** beside a value that looks like a number, `true` or
  `false`: its spelling does not tell it.
- **Type of the value…**, a click on it or in the row's menu, makes the value
  another type and keeps what it says: as the shape says, double, integer,
  decimal, text, true/false or vocabulary term.
- **A value that cannot be of that type is refused** and kept.
- One language server request.

## Capabilities

### New Capabilities
- `semforge-sdk/value-types`: the type of an example's value, seen and chosen in
  the editor.

### Modified Capabilities
- `contracts/typed-literals`: adds that a modeller may choose another type for a
  value than its shape asks, which the SDK's rule on doubles excludes today.

## Impact

- Contract between components: **yes**, `contracts/typed-literals` gets one
  exception, for a type chosen on purpose in an example. No component other than
  the SemForge SDK writes or reads anything differently: a chosen type is
  written in the forms the contract has already.
- SemForge SDK (`semantic-model/SemForge-SDK`): the values of examples
  (`semforge/cooked`), one added language server request, the case page, one
  command, the README. No new dependency.
- No change to any other component, image, chart or deployment.

## Out of Scope

- Other types than the ones listed as a choice: dates, language-tagged texts,
  `xsd:float`. *As the shape says* still writes whatever datatype the shape
  names, a date included.
- Choosing the type in the Entities & Test Cases view.
- Values of a ListProperty, and of other kinds of attribute than Property.
- Remembering a chosen type: editing the value afterwards writes it as the
  shape asks, as before.
