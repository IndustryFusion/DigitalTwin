# Design

## Context

A case is a `.jsonld` file declared in an `expectations.yaml` with `expect:
valid` or `invalid`, optional `asserts` (a constraint, and the entity it fires
on) and an optional pinned residue. The example runner fails an invalid case
when everything conforms or an assert does not fire; an invalid case without
asserts passes on any violation. The store's own documentation already calls
such a case unfinished.

New test… (`semforge/attributeTestOptions`, `semforge/newAttributeTest`)
derives one option per constraint it knows how to break and writes the broken
data and the assert. The validator reports, per case, every constraint it
evaluated with a status (violated, or conformant and whether vacuously), which
is what the case page shows as firing.

`contracts/kms-package` requires the examples to meet their expectations
without saying what that means for an invalid one.

## Decisions

### D1 — The runner fails an invalid case without asserts

- **Chosen:** the rule is in the one function that judges an example against
  its report, so the editor, `test`, `verify --tests`, `publish` and the
  release record agree.
- *Alternative:* a warning in the editor only. Rejected: the command line and
  a package's release would still count an unfinished test as met.
- *Alternative:* accept a pinned residue in place of an assert. Rejected: a
  residue pins whatever happened to fire; it does not say what is meant.

### D2 — No list of what can go wrong

- **Chosen:** a failing test starts valid and without a reason; the reason is
  taken from what the validator reports. It works alike for every constraint,
  including `sh:or` and SPARQL, and needs no code per constraint.
- *Alternative:* add `sh:in` and the missing constraints to the list.
  Rejected: the list never ends, and it decides the reason before the data is
  seen.
- *Alternative:* keep the list beside the two kinds. Rejected: two ways to one
  thing, the second incomplete; its code is removed.

### D3 — What can be asserted comes from the case's own results

- **Chosen:** every constraint that was evaluated on an entity of the case,
  whether it fires or holds. A constraint evaluated vacuously (the entity has
  no such attribute) is included, since giving the entity the attribute can
  make it fire.
- *Alternative:* all constraints of all shapes. Rejected: most cannot fire in
  the case, and on a large package the list is unusable.

### D4 — The tests about an attribute come from the validation results

- **Chosen:** computed on request from the last validation run, by shape and
  attribute; a case counts when one of the attribute's constraints fires, is
  asserted, or holds non-vacuously. Nothing is validated for the list, and it
  is replaced in place when a run ends.
- *Alternative:* by the suite's folder name. Rejected: a case in another
  suite may be the one that proves the attribute.

### D5 — `sh:in` items are written as the terms they are

- **Chosen:** a list item is read as its RDF term and written as the JSON-LD
  value that reads back as that term, because `sh:in` compares terms: a
  double carries its datatype (contracts/typed-literals), a text that would
  read as a number or boolean stays a text.

## Risks

- **A package with an invalid case that asserts nothing now fails its tests.**
  That is the point of the change. The examples of `semantic-model/kms` all
  assert. A published version is identified by its digest and is not affected;
  running its tests again may report such an example.
- **The pages show results of the last run** until a new one ends; the
  attribute editor's list follows it.

## Conflicts

`contracts/typed-literals` ("The SemForge SDK declares its doubles") requires
generated test cases that break a range or a count to hold declared doubles,
and has a scenario for such a case. This change generates none. The requirement
is modified: it keeps declared doubles for every generated and edited value,
and its scenario becomes a modeller breaking the range of a generated case.
*Alternative:* keep generating those cases behind the language server request
without offering them in the editor. Rejected: code nobody can reach, kept
only for a scenario.

`semforge-sdk/test-cases` says of a bad
case started from a violating main model that the model violates already; it
does not say that the case passes, and it now fails until it asserts that.
