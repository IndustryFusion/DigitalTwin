# Design

## Context

`contracts/typed-literals` says how a number is written: declared for a double,
float or decimal, plain otherwise. The SDK follows it whenever an example's value
is edited, by the attribute's shape. A value is therefore what the shape asks,
which is right for data and wrong for a test of the shape's datatype.

## Conflicts

`contracts/typed-literals`, *The SemForge SDK declares its doubles*, has every
edited value of an `xsd:double` attribute declared. A type chosen on purpose
contradicts this. The delta adds the exception as a requirement of its own, so
that the rule stays as it is for every other value. #1087 changes the wording of
that requirement (the generated cases it lists); this change does not touch it.

## Decisions

### D1: The type is an action of its own
- **Chosen:** editing a value follows the shape as before; its type is changed by
  another action, on the value where its type is said.
- *Alternative:* keep the type a value has when it is edited. Rejected: an integer
  by mistake would stay one, which is what #961 removed.
- *Alternative:* let the notation typed decide (`50` or `50.0`). Rejected by #961.

### D2: The forms of the contract
- **Chosen:** a double or decimal is declared with the full XSD IRI (a decimal as
  text), integers, booleans and texts are plain, a term is `{"@id": …}`.
- *Alternative:* declare every chosen type, integers too. Rejected: *Other values
  stay plain*, and JSON-LD reads the same from the plain form.
- Two exceptions, found in review: an integer of 10^21 and more is declared with
  its digits as text, because JSON-LD reads a JSON number that large as a double;
  the other XSD integer types (`xsd:int`, …) are declared with their datatype,
  because a plain number is an `xsd:integer`, which their shapes reject.
- Numbers are written out with at most 1000 digits; more is refused by name, so
  that a mistyped exponent cannot make a file of a billion digits.

### D3: Said only where it cannot be seen
- **Chosen:** beside numbers and true/false, in any type. The row menu offers the
  change for every value that is no structure. A superseded observation says its
  type but does not offer to change it: with several datasetIds its row is joined
  to the current observation, so a change there would land on that one.
- *Alternative:* beside every value. Rejected: `text` beside every text of a page
  says nothing.

### D4: As the shape says
- **Chosen:** the one datatype the shape names, in the row an edit follows (names
  compared by what they mean, #1094), the datatype read with the shapes'
  prefixes. Without one, as an edit.
- *Alternative:* always as an edit. Rejected: an edit reads `50` as a number, so a
  text of digits in an `xsd:string` attribute could not be had back.

### D5: One write
- **Chosen:** the value is read, converted and written in one step, through the
  same writer as an edit.

## Risks / Trade-offs

- A plain `50.0` is an integer to JSON-LD, and some JSON-LD readers make it a
  double. The page says integer, as `contracts/typed-literals` does.
