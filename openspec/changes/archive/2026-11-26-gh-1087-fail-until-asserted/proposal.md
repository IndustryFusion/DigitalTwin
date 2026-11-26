# Proposal

Issue: #1087

## Why

A test case that expects a violation is written in SemForge by picking, from a
fixed list, which constraint it should break. The list has an entry per known
constraint and none for the rest: on an attribute whose value has an `sh:in`
list it offers nothing for the list, and the valid case it writes carries a
value the list does not allow. Meanwhile an invalid case that asserts nothing
passes as soon as anything violates in it, so an unfinished test looks
finished. Asserts can be added on the test case page but not removed, and
deleting a case is hard to find.

## What Changes

- **An invalid case fails until it names its reason.** A case that expects a
  violation and asserts nothing does not meet its expectations, whatever fires
  in it: in the editor, in `semforge test`, in `semforge verify --tests` and in
  everything else that runs a package's examples.
- **New test… asks for two things only:** the test should conform, or it
  should fail. A failing test starts from valid data, asserts nothing and
  therefore fails, until its data is edited and what fires is asserted. The
  list of constraints, and the code that broke the data for each, go.
- **A valid value respects `sh:in`.** A test that should conform takes its
  value from the list. The value picker of the case page offers the list's
  items, and any other value can still be typed.
- **The test case page adds and removes asserts.** Any constraint that judges
  an entity of the case can be asserted, whether it fires or holds now; every
  assert can be removed.
- **Tests are listed and deleted where they matter.** The attribute editor
  lists the test cases about its attribute, each opened or deleted there. The
  test case page shows Clone, Rename and Delete as buttons, and the case lists
  of the type and shape pages offer Delete.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `semforge-sdk/test-cases`: adds what New test… asks and writes, that a
  failing case needs a reason, and how asserts and cases are added and removed
  in the editor.
- `contracts/kms-package`: adds that an example which expects a violation
  meets its expectations only when it asserts one.
- `contracts/typed-literals`: no test case that breaks a range or a count is
  generated any more. The scenario becomes one of a modeller breaking the
  range of a generated case; every value is declared as before.

## Impact

- Contract between components: **yes**, `contracts/kms-package`: what
  "an example meets its expectations" means becomes narrower for an example
  that expects a violation and asserts none. SemForge is the only component
  that runs a package's examples. All examples of `semantic-model/kms` assert
  already, so no package in this repository changes its result.
  `contracts/typed-literals` loses a kind of generated case, not a rule on how
  a value is written.
- SemForge SDK (`semantic-model/SemForge-SDK`): the example runner, the test
  case writer of New test…, the case page, the attribute editor, the type and
  shape pages, the value picker, the extension and its README.
- The language server requests `semforge/attributeTestOptions` and
  `semforge/newAttributeTest` know the purposes `valid` and `invalid` only; the
  purposes naming a constraint are removed. `semforge/assertable` and
  `semforge/attributeCases` are added. Only the extension uses them.
- No change to any other component, image, chart or deployment.

## Out of Scope

- Suggesting, or writing, data that breaks a chosen constraint.
- Changing New case… of a SPARQL rule, which starts with its assert.
- Changing what a pinned residue means; it does not replace an assert.
