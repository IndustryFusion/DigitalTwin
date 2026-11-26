# Proposal

Issue: #1097

## Why

`sh:datatype` in the value shape of a property is only checked when the shape
also states `sh:nodeKind sh:Literal`. Without it the check is built but never
fires: a shape that requires `xsd:double` raises no alert for `"abc"`, neither
on SQLite nor on Flink, and the build says nothing. A conformant SHACL engine
reports a violation.

## What Changes

- `sh:datatype` of a value shape is checked whether or not the shape states
  `sh:nodeKind`, for each instance on its own, with the verdict the datatype
  check gives today for a literal with `sh:nodeKind sh:Literal`. This covers an
  `sh:and` of datatypes and an `sh:or` whose branches all state one.
- A missing `sh:nodeKind` still constrains no node kind: an attribute that has
  no value of `ngsi-ld:hasValue` (a Relationship, ListProperty or JsonProperty)
  conforms, as in SHACL. An IRI and a geometry violate every datatype.
- Connectives keep the verdicts they have, and a deactivated shape requires no
  datatype.
- In this check, a value declared with a datatype that is in a
  list of datatypes satisfies the list, also when the list names one of the
  datatypes judged by text, a declared boolean may be written `1` or `0`, a
  declared double `INF`, `-INF` or `NaN`, and a
  declared type is compared as a whole. Shapes with `sh:nodeKind sh:Literal` keep
  their verdicts in all three.
- On SQLite a JSON object or a geometry is not taken for a literal by this check.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `shacl2flink/literal-datatypes`: adds that `sh:datatype` does not depend on
  `sh:nodeKind`, and what a missing `sh:nodeKind` leaves unconstrained.

## Impact

- **shacl2flink** only: the generated datatype check, the documentation and
  the tests. The tables do not change, so deploying it means deploying the
  regenerated SQL statements.
- The SemForge SDK's cross-check compares the alerts with pyshacl's results. It
  knows that shacl2flink names `sh:datatype` where pyshacl names the `sh:or`
  of datatypes on a value shape. It does not know the same for an `sh:and`, for
  an `sh:or` on the property shape, and for an `sh:or` whose branches have other
  parameters than their datatype: a violated one without `sh:nodeKind` shows
  there as two differences. It showed as one, a missed alert, before.
- **No contract between components changes.**
- New alerts appear for shapes that state a datatype without `sh:nodeKind`. The
  packages in `semantic-model/kms` and the value shapes of the OPC UA generator
  state `sh:nodeKind sh:Literal` and keep their verdicts.

## Out of Scope

- Judging a connective for each instance on its own. An `sh:or`, `sh:xone` or
  `sh:not` is judged over all instances of an attribute together, and `sh:not`
  and `sh:xone` alert for an absent attribute, with `sh:nodeKind` as without. An
  `sh:not` or `sh:xone` of datatypes without `sh:nodeKind` therefore keeps the
  verdict it has, which does not read the datatype.
- A datatype without `sh:nodeKind` in an `sh:or` with a branch that states none
  or states a node kind or an `sh:path`, or under a connective of a node shape or of an enclosing
  attribute, stays unchecked, and so do the other parameters of an `sh:or` branch.
- A property whose value is a JSON object: the bridge passes on only literals and
  IRIs of a Property, so the attribute never reaches Flink and no check of its
  value runs there. Only the SQLite checks report it.
- The node kind check of SQLite, which takes a geometry or a JSON object for a
  literal where a shape states `sh:nodeKind sh:Literal`.
- The same three for shapes with `sh:nodeKind sh:Literal`, where a listed
  `xsd:decimal`, a language-tagged string or a declared boolean `1` still raises
  a false alert and `xsd:gYear` satisfies `xsd:gYearMonth`. Such a constraint can
  be a member of a connective, whose verdict would change with it.
- Teaching the SemForge SDK's cross-check these namings.
- A connective whose branches lead back to it: SHACL leaves recursive shapes
  open, so such a branch requires no datatype.
- `rdf:JSON` on a value shape of `ngsi-ld:hasValue`: the bridge names it `@json`,
  the model reader `rdf:JSON`. Such a datatype without `sh:nodeKind` stays
  unchecked.
- A value that reaches Flink without a type on a list with `rdf:langString`: the
  bridge passes no type on for a language-tagged string, nor for a plain number
  or boolean, so Flink accepts all of them, while the SQLite checks know the type
  of a plain number or boolean and report it.
- The time the platform's Flink gives the deployment of a job, see the design.
- `sh:deactivated` in the other checks, which do not read it.
- `sh:class` in a value shape without `sh:nodeKind sh:IRI`, which is not checked
  for the same reason. It needs its own decision on values that are literals.
- `sh:minCount` in a value shape, which is not checked. A shape that states
  `sh:minCount 1` there and no `sh:nodeKind` does not report a Relationship.
- The range, length, pattern, `sh:in` and `sh:hasValue` checks, which do not
  depend on `sh:nodeKind`.
- The other differences between SQLite and Flink for a value without a declared
  type, such as a plain number on `sh:datatype xsd:string`.
