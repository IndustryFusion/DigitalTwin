# Design

## Context

The `sh:hasValue` check today compares by the value's declared type: as a
double for `xsd:double`, as an integer for `xsd:integer`, as a boolean for
`xsd:boolean`, and as text otherwise. The two sides fill that type
differently (measured in #958, task 3.1, and in its design's table):

| Value written | Flink: text, type | SQLite: text, type |
|---|---|---|
| plain `80` | `80`, none | `80`, `xsd:integer` |
| plain `80.0` | `80`, none | `80`, `xsd:integer` |
| `{"@value": 80, "@type": "xsd:double"}` | `80`, `xsd:double` | `80.0`, `xsd:double` |
| `{"@value": 80, "@type": "xsd:integer"}` | `80`, `xsd:integer` | `80`, `xsd:integer` |
| plain `80.5` | `80.5`, none | `80.5`, `xsd:double` |
| string `"80.0"` | `80.0`, none | `80.0`, none |
| string `"80"` | `80`, none | `80`, none |

The constant comes from Turtle, where `80.0` is an `xsd:decimal`, `80` an
`xsd:integer` and `"80.0"` a string. So on Flink a plain `80.0` is compared as
the text `80` against `80.0` and violates `sh:hasValue 80.0`, and a declared
double `80` is cast and passes. On SQLite the plain `80.0` is cast as an
integer and passes, and a declared integer `80` is compared with
`CAST('80.5' AS INTEGER)`, which SQLite truncates to `80`, so it satisfies
`sh:hasValue 80.5`.

The bridge does not keep the notation of a number, and it passes no type on
for a plain number. Flink therefore cannot know whether a plain value was
written as `80`, `80.0` or `"80"`.

## Goals / Non-Goals

**Goals:** one rule for a number constant that Flink can apply to what it
receives, the same verdicts on SQLite, strings judged by their text as for
`sh:datatype`.

**Non-Goals:** string constants against plain numbers, boolean constants,
SemForge's offline validation (see the proposal, *Out of Scope*).

## Decisions

### D1 — Rule B: a number constant is compared by its value

- **Chosen (B, pure value):** a number constant is satisfied by any value that
  is the same number, whatever its numeric datatype (integer, decimal,
  double), and whether or not it declares a type. Whether the value has the
  right datatype is the job of `sh:datatype`, which a shape states beside
  `sh:hasValue` when it matters.
- *Alternative A, SHACL term equality:* value and datatype must both match,
  as in a conformant SHACL engine (`"80"^^xsd:integer` is not
  `"80.0"^^xsd:decimal`). Rejected:
  - Flink does not know the type of a plain value: plain `80`, `80.0` and
    `"80"` all arrive as the text `80` without a type, so term equality cannot
    be computed there, and SQLite and Flink would disagree again.
  - Since #961 the writers declare every double. Turtle types `80.0` as
    `xsd:decimal`, so under A no declared double could satisfy
    `sh:hasValue 80.0` as modellers write it; the shape would have to say
    `"80.0"^^xsd:double`.
- *Alternative C, value within the same datatype family:* integer and decimal
  values are compared as numbers among themselves, doubles among themselves.
  Rejected for the same first reason: for a plain value Flink does not know
  the family, and the bridge turns a declared double `80.0` into `80`. It also
  adds a distinction that `sh:datatype` already makes.

### D2 — A string that reads as the number satisfies it

- **Chosen:** a value without a declared type whose text is a number counts
  as that number, so the strings `"80"` and `"80.0"` satisfy
  `sh:hasValue 80`. Flink cannot tell the string `"80"` from the number `80`;
  both arrive untyped with the same text. The live-data path sends every
  value as a string. It is the reading D5 of #958 gave strings for
  `sh:datatype`.
- *Alternative:* compare strings as text even against a number constant.
  Rejected: impossible on Flink for the reason above, and it would make the
  string `"80.0"` satisfy `sh:datatype xsd:double` but not
  `sh:hasValue 80.0`.

### D3 — What counts as a number

- **Chosen:** a value is a number when its declared type is a numeric XSD
  datatype or missing, and its text matches the number pattern of
  `sh:datatype` (an optional sign, digits with an optional decimal point or a
  decimal point and digits, an optional exponent). Only then are both sides
  cast, on Flink with a cast that yields NULL instead of failing the job.
  Anything else falls back to today's comparison, so `"eighty"` and `true`
  differ from `80` as text.
- *Alternative:* cast every value and treat a failed cast as "no number".
  Rejected: SQLite casts any text to a number (`CAST('eighty' AS REAL)` is
  `0`), so `"eighty"` would satisfy `sh:hasValue 0`, and nothing would
  guarantee that the two databases accept the same texts as numbers. The
  shared pattern decides that on both, and keeps `sh:datatype` and
  `sh:hasValue` reading strings alike.
- **Precision:** both sides are compared as double precision numbers.
  Integers beyond 2^53 compare approximately; JavaScript, and so the bridge,
  already writes them that way. An exact decimal comparison would be exact
  only on SQLite, so the sides would disagree.
- The fallback no longer casts a constant to an integer when the constant is a
  number, which removes SQLite's truncation of `80.5`.

### D4 — The constant's datatype travels in the constraint table

- **Chosen:** the compiler stores the datatype of the `sh:hasValue` constant
  in a new column of the constraint table, `hasValueType`, NULL for a
  constant without one and for every other constraint. The check is numeric
  only when that datatype is numeric.
- *Alternative:* infer it from the constant's text. Rejected: the constant is
  stored as text, so `"1.0"` (a string) and `1.0` (a decimal) would look the
  same, and a string constant must stay a text comparison.
- *Alternative:* infer it from the value's type. Rejected: on Flink a plain
  value has none.
- **Is the column a contract?** No. The constraint table is generated by
  shacl2flink and read only by the SQL statements shacl2flink generates in
  the same package; no other component reads or writes it. It is therefore
  not specified in the delta, which describes observable verdicts only. The
  one consequence for operation is that the table definitions and the
  statements of a package are deployed together, which is already how a
  package is deployed.

### D5 — The divergence from pyshacl is deliberate

The pyshacl comparison compares RDF terms. Under D1 and D2 shacl2flink
accepts nine values that pyshacl reports (fixture `kms-constraints/test27`):

- against `sh:hasValue 80.0` (a decimal): plain `80`, plain `80.0`, a declared
  integer `80`, a declared double `80`, the strings `"80.0"` and `"80"`;
- against `sh:hasValue 80`: a declared double `80`, the strings `"80.0"` and
  `"80"`.

They are recorded as deliberate in the comparison's list of expected
divergences, with the reason. `80.5` and `"eighty"` are reported by both.

## Conflicts with existing specifications

- The Purpose of `shacl2flink/literal-datatypes` aims at "the verdict a
  conformant SHACL engine gives". For `sh:hasValue` on numbers this change
  deliberately gives another one (D1, D5), as #958 already did for strings.
  The Purpose names only `sh:datatype`; it should mention `sh:hasValue` once
  this change is archived.
- `contracts/typed-literals` is unchanged. Rule B is what lets its declared
  doubles satisfy a numeric `sh:hasValue` written the usual way in Turtle.

## Known divergences left open

- **A string constant against a plain number:** `sh:hasValue "1.0"` and the
  plain value `1`. Flink compares the untyped text `1` with `1.0`, SQLite
  casts by the `xsd:integer` the model gives it. A unit test records this as
  an expected failure. An issue should be opened.
- **Boolean constants** keep today's comparison by the declared type and are
  not examined here. An issue should be opened.

## Risks

- A shape that relied on `sh:hasValue 80.0` rejecting a whole number or a
  declared integer no longer does; such a shape has to add `sh:datatype`.
  No shape in the repository uses a number constant with `sh:hasValue` today,
  apart from the fixtures this change adds.
- Verdicts on Flink change for values that were wrongly rejected: alerts for
  them close when the package is deployed.
