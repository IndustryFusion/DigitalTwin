# Proposal

Issue: #965

## Why

On Flink, `sh:hasValue` with a number compares the value's text when the
value declares no type. The debezium bridge writes numbers as JavaScript does,
so a plain `80.0` reaches Flink as the text `80` and violates
`sh:hasValue 80.0`, although it is the same number. SQLite casts by the type
the model gives the value and finds them equal, so the two validators
disagree. The design of #958 found this (section *Effects on other checks*)
and left it to this issue.

The SQLite side has a bug of its own: for a value declared `xsd:integer` it
casts both sides to an integer, and `CAST('80.5' AS INTEGER)` is `80` there.
A declared integer `80` therefore satisfies `sh:hasValue 80.5` on SQLite.

## What Changes

- A number required by `sh:hasValue` is compared by its value (rule B in the
  design): a value satisfies it when it is the same number, whatever numeric
  datatype the constant or the value has, and whether or not the value
  declares a type. `80`, `80.0`, `{"@value": 80, "@type": "xsd:double"}` and
  `{"@value": 80, "@type": "xsd:integer"}` all satisfy `sh:hasValue 80.0` and
  `sh:hasValue 80`; `80.5` satisfies neither.
- A string whose text is the same number satisfies it too: `"80.0"` and
  `"80"` satisfy `sh:hasValue 80`. Flink cannot tell the string `"80"` from
  the number `80`, both arrive without a type, and strings are read by their
  text as for `sh:datatype` (D5 of #958). Text that is no number, such as
  `"eighty"`, violates it.
- A string constant, such as `sh:hasValue "1.0"`, is compared as text, as
  today: `"1.0"` satisfies it, `"1"` does not.
- SQLite and Flink give the same verdict, and the integer truncation on SQLite
  goes away.
- The result differs from a conformant SHACL engine, which compares RDF terms
  (value and datatype). The pyshacl comparison lists the differences as
  deliberate.
- The shacl2flink documentation of `sh:hasValue` states the rule.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `shacl2flink/literal-datatypes`: adds how `sh:hasValue` compares a number
  constant and a string constant, extends the agreement of SQLite and Flink
  and the documentation requirement to `sh:hasValue`.

## Impact

- **shacl2flink** only: the generated `sh:hasValue` check, the compiler that
  fills the constraint table, which gets one column for the datatype of the
  constant (design D4), the documentation, and the tests (a kms-constraints
  fixture, unit tests of the generated check, the pyshacl comparison, the
  Flink e2e test).
- Deploying the change means deploying a regenerated shacl2flink package: its
  table definitions and its SQL statements go together.
- **No contract between components changes.** The bridge, Scorpio, the
  writers of `contracts/typed-literals` and the live-data path stay as they
  are. The constraint table is written and read only by what shacl2flink
  generates (design D4).
- Verdicts change only where they were wrong under the rule: on Flink, plain
  whole numbers written with a decimal point, declared doubles that the bridge
  turned into whole numbers, and number strings in another notation no longer
  violate a numeric `sh:hasValue`; on SQLite, a declared integer no longer
  satisfies a fractional constant.

## Out of Scope

- A string constant against a plain number (`sh:hasValue "1.0"` and the plain
  value `1`): Flink compares the untyped text, SQLite casts by the
  `xsd:integer` the model gives it, so the two can still disagree. This change
  is about number constants; an issue should be opened for it.
- Constants of type `xsd:boolean`. They keep today's comparison; whether
  Flink and SQLite agree on them is not examined here, and an issue should be
  opened for it.
- `sh:in`, whose members are compared by text and type; #958 found Flink and
  SQLite already agree on it for numbers.
- Range checks, which already compare numbers.
- The SemForge SDK, whose offline validation uses a conformant SHACL engine
  and will keep comparing terms.
