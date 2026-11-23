# Design

## Context

After #965 the `sh:hasValue` check compares a number constant by its value
and everything else as before: by the value's declared type for
`xsd:double`, `xsd:integer` and `xsd:boolean` (casting both sides to that
type), and as text otherwise. The constraint table holds the constant as
Python writes it (`toPython()`) and, since #965, the constant's datatype in
the internal column `hasValueType`.

The two sides fill a value's row differently (measured with
`kms-constraints/test28` for SQLite; Flink's text is what the bridge's
`JSON.stringify` writes, see below):

| Value written | Flink: text, type | SQLite: text, type |
|---|---|---|
| plain `1` | `1`, none | `1`, `xsd:integer` |
| plain `1.0` | `1`, none | `1`, `xsd:integer` |
| plain `0.5` | `0.5`, none | `0.5`, `xsd:double` |
| plain `1e21` | `1e+21`, none | `1e+21`, `xsd:double` |
| `{"@value": 1, "@type": "xsd:double"}` | `1`, `xsd:double` | `1.0`, `xsd:double` |
| `{"@value": 1, "@type": "xsd:integer"}` | `1`, `xsd:integer` | `1`, `xsd:integer` |
| plain `true` | `true`, none | `True`, `xsd:boolean` |
| plain `false` | `false`, none | `False`, `xsd:boolean` |
| `{"@value": "1", "@type": "xsd:boolean"}` | `1`, `xsd:boolean` | `True`, `xsd:boolean` |
| string `"true"`, `"True"`, `"1"`, `"1.0"` | the text, none | the text, none |

And the constants: Turtle `true` is stored as `True` with `xsd:boolean`, the
string `"1.0"` as `1.0` with no type.

**What the platform writes.** The debezium bridge (`KafkaBridge`) takes the
`@value` of an attribute from the entity Scorpio stores and sends it in a
JSON message (`JSON.stringify`), so a number reaches Flink as JavaScript's
text for that number (ECMA-262 Number::toString: shortest round-trip digits,
no decimal point for a whole number, an exponent from 10^21 up and below
10^-6) and a boolean as `true` or `false`; Flink's JSON format keeps that
text for a STRING column. Whatever notation Scorpio's store keeps for a
number (`1.0` in a jsonb column), it is parsed by the bridge into a
JavaScript number first, so the notation the client wrote is lost. The type
is passed on only when the value declares one. The `sh:datatype` work of #958
measured the same texts (`1e+21`, `1.5e-7`, `80` for `80.0`).

So the disagreements:

- `sh:hasValue "1.0"` and a plain `1`: Flink compares `1` with `1.0` and
  alerts; SQLite casts both to an integer and does not.
- A declared `xsd:integer` or `xsd:double` against a string constant: SQLite
  casts the constant too and truncates (`CAST('1.0' AS INTEGER)` is 1);
  Flink's `TRY_CAST` yields NULL for a constant that is no integer text, and
  `NULL <> x` never alerts.
- `sh:hasValue true` and a plain `true`: Flink compares `true` with `True`
  and alerts. SQLite casts to BOOLEAN, which has numeric affinity there, so
  `True`, `False` and `true` all become 0: a plain `false` and the string
  `"True"` satisfy `sh:hasValue true` on SQLite.

## Goals / Non-Goals

**Goals:** the verdicts of the decision recorded on #1044 and #1045, the
same on SQLite and Flink, with a rule that Flink can apply to the text it
receives.

**Non-Goals:** number constants (#965) beyond rejecting the ones the sides
cannot compare alike (D8), `sh:in`, SemForge's offline validation (see the
proposal, *Out of Scope*).

## Decisions

### D1 — A string constant is compared with the text the platform sends

- **Chosen:** a value meets a string constant when the text the platform
  sends for it is the constant. Flink already receives that text, so an
  untyped value (or one declared `xsd:string`) is compared by its text. For a
  value SQLite holds as a number (a plain number is typed there, a declared
  number on both sides), the compiler decides at build time whether the
  constant is exactly the platform's text of some number — the text
  JavaScript writes for `float(constant)` equals the constant — and marks it
  in `hasValueType`. The check then compares the value and the constant as
  numbers only when the constant is marked and the value's text is a number
  (the pattern of `sh:datatype`). Because JavaScript's text is a one-to-one
  function of the number, "same number and the constant is its canonical
  text" is exactly "the platform's text of the value is the constant". A
  boolean value is read as `true` or `false` (D3).
- *Alternative A, compare the text SQLite holds:* SQLite holds `1.0` for a
  declared double `1` and `1` for a plain `1.0`; Flink holds `1` for both.
  Rejected: the texts differ between the sides for the same value.
- *Alternative B, compare a number value with the constant as numbers:* a
  plain `1` would meet `"1.0"`. Rejected by the decision: only `"1.0"` meets
  `"1.0"`, as #965 already specifies for strings, and Flink cannot apply it
  to a plain `1` it receives as untyped text without also making the string
  `"1"` meet `"1.0"`.
- *Alternative C, produce JavaScript's text of the value in SQL:* would let
  the check compare texts on both sides. Rejected: neither SQLite nor Flink
  SQL can format a double that way without a user-defined function, and the
  compiler can do the equivalent once for the constant.
- **Where the mark lives:** in `hasValueType`, the column #965 added for the
  constant's datatype. A string constant has no numeric datatype, so the
  value is free; the mark is an internal URN, not an XSD datatype. A separate
  column was considered and rejected: it would grow the constraint table for
  one flag. The column stays internal (#965, D4): the constraint table is
  generated and read only by shacl2flink, and a package's table rows and
  statements are deployed together.

- **Only finite numbers are marked.** `NaN`, `Infinity` and `-Infinity`
  read as numbers to Python, but the platform never sends them for a number
  (`JSON.stringify` writes `null`), and SQLite casts the text `NaN` to 0.0,
  so a marked `"NaN"` would be met by `0` on SQLite while Flink alerts. The
  compiler marks a text only when it is the text of a finite number.

### D2 — A boolean constant is met by the same boolean

- **Chosen:** the compiler stores a boolean constant as `true` or `false`
  (not Python's `True`). A value declared `xsd:boolean` is read as a boolean
  — `true`/`1` true, `false`/`0` false, ignoring case because SQLite holds
  `True`/`False` — and compared with the constant. A value without a
  declared type is compared by its text, so only exactly `true` or `false`
  meets it; on Flink that covers the plain boolean, which arrives untyped.
  Any other value — a number, `"1"`, `"True"` — violates it.
- *Alternative A, read every value as a boolean (`"True"`, `"1"`, `1`
  count):* rejected by the decision, and Flink could not tell the string
  `"1"` from the number `1` from the declared boolean `1` without the type.
- *Alternative B, SHACL term equality:* only `true`/`"1"^^xsd:boolean` meet
  `true`. Rejected: Flink receives a plain boolean as the untyped text
  `true`, the same as the string `"true"`, so it cannot be computed there.
  This is why the string `"true"` meets `sh:hasValue true` (a deliberate
  divergence from pyshacl, D5).
- *Keep casting to BOOLEAN:* rejected: SQLite's BOOLEAN has numeric affinity
  and casts `True`, `False` and `true` all to 0.

### D3 — A boolean value against a string constant is `true` or `false`

- **Chosen:** a value declared `xsd:boolean` is sent as `true` or `false`
  against a string constant, also when the model wrote it as `1` or `0`. So
  `"true"` is met by a plain `true`, a declared `1` and the string `"true"`,
  and `"1"` is not met by a declared boolean `1`.
- *Alternative, the text the client wrote (`1`):* that is what Flink
  receives for a declared `{"@value": "1", "@type": "xsd:boolean"}`, but
  SQLite only knows the boolean: the RDF reading of the model normalises the
  text to `true`. The two sides would disagree again. The decision does not
  name this case; it is a corner case of a declared boolean against a string
  constant, and the chosen reading keeps the sides in agreement.

### D4 — No cast to the type a value declares

- **Chosen:** the check compares by the constant's datatype only: a number
  constant as a number (#965), a boolean constant as in D2, any other
  constant as in D1. It never casts a value or a constant to `INTEGER` or
  `BOOLEAN`, and casts to `DOUBLE` only text that the number pattern let
  through. A value declared `xsd:string` is read like an untyped one, as
  SQLite already does (it turns a value's `xsd:string` into no type), which
  also aligns Flink with SQLite for a declared `xsd:string` against a number
  constant.
- *Alternative:* keep the per-type casts for typed values and only fix
  untyped ones. Rejected: the casts are what make SQLite truncate, read every
  text as the boolean 0, and Flink return NULL.

### D5 — The divergences from pyshacl are deliberate

pyshacl compares RDF terms, and the fixture `kms-constraints/test28` holds
values it judges differently on purpose; they are listed in
`tests/pyshacl-compare/expected-divergences.txt` with the reason:

- Accepted by shacl2flink, reported by pyshacl (twelve): plain `1`, plain
  `1.0`, declared double and integer `1` against `"1"`; plain `0.5` and
  declared double `0.5` against `"0.5"`; plain `1e21` against `"1e+21"`;
  plain `true`, declared `true` and declared boolean `"1"` against `"true"`;
  the string `"true"` against `true` and the string `"false"` against
  `false`.
- Accepted under D7 (one): the declared double written as the string
  `"1.0"` against `"1"`.
- Accepted under D6 (fourteen): plain `1`, plain `1.0`, declared double and
  integer `1`, the declared double written as `"1.0"` and the string `"1"`
  against `"1"^^xsd:token` and against `"1"` of a datatype of the model's
  own; plain `2020` and the string `"2020"` against `"2020"^^xsd:gYear`.
- Nothing that pyshacl accepts is reported by shacl2flink.

### D6 — A constant of another datatype is compared like a string constant

- **Chosen:** a constant that is neither numeric nor `xsd:boolean` —
  `"2020"^^xsd:gYear`, `"1"^^xsd:token`, a datatype of the model's own, a
  language-tagged string — is compared as D1 compares a string constant: with
  its text as written, and marked when that text is the platform's text of a
  finite number. So plain `2020` meets `"2020"^^xsd:gYear` on both sides:
  Flink compares the untyped text `2020`, SQLite (which types the value
  `xsd:integer`) compares the numbers because the constant is marked. The
  compiler stores the lexical form of such a constant instead of
  `toPython()`, which turned `"2020"^^xsd:gYear` into the date `2020-01-01`.
  For the same reason the SQLite side now holds a value of such a datatype by
  its lexical form (`{"@value": "2020", "@type": "xsd:gYear"}` was
  `2020-01-01` there and `2020` on Flink); numbers and booleans keep the text
  the checks are written against.
- *Alternative, keep the verdict of origin/main:* there SQLite cast a typed
  integer and the constant to INTEGER, and Flink compared texts; it agreed
  for `"2020"^^xsd:gYear` only by accident of the cast and disagreed for the
  declared `xsd:gYear` value. Rejected: it brings back the casts of D4.
- *Remaining limitation:* rdflib still normalises some lexical forms when it
  reads the model (an `xsd:dateTime` written with `Z` becomes `+00:00`), so a
  declared `xsd:dateTime` value can still differ in text between the sides.
  That predates this change and is not addressed here.

### D7 — A declared number is compared by its value, also when written as a string

- **Chosen, as the one forced exception to "the text the platform sends":**
  `{"@value": "1.0", "@type": "xsd:double"}` is sent by the bridge as the
  text `1.0`, typed `xsd:double`. The SQLite side reads the model through
  RDF, where it is the number 1.0, the same as `{"@value": 1, "@type":
  "xsd:double"}` (sent as `1`). SQLite cannot tell the two apart, so the only
  verdict both sides can give is the one by value: it meets `"1"` and
  violates `"1.0"`. The check already does this for every declared number
  (D1); the requirement now states it.
- *Alternative, compare the sent text:* would need the SQLite side to keep
  the JSON form of the value, which the RDF reading of the model loses.
  Rejected.

### D8 — A constant the sides cannot compare alike fails the build

- **Chosen:** a number constant that is ill-typed (`"abc"^^xsd:integer`) or
  not finite (`"NaN"^^xsd:double`, `"INF"^^xsd:double`), and an ill-typed
  boolean constant (`"yes"^^xsd:boolean`), fail the build with
  `UnsupportedShape`, naming the constraint and its shape path, collected
  with the other problems of the build. That is how the compiler treats every
  shape it cannot translate ("fail loud": a constraint silently not checked is
  worse than a failed build). For such a number Flink's `TRY_CAST` yields
  NULL and never alerts while SQLite casts the text to 0 and alerts for every
  value but 0 — older than this change; an ill-typed boolean silently became
  `false`.
- *Alternative, a warning:* the compiler has none that a build step reads
  (`test_fail_loud.py`: depth problems used to be a warning on stdout that
  nobody saw). Rejected.

## Conflicts with existing specifications

- `shacl2flink/literal-datatypes`, *sh:hasValue compares a string by its
  text*: its scenarios stay (`"1.0"` meets `"1.0"`, `"1"` does not); the
  requirement is restated to say what a number and a boolean are compared
  as, that constants of other datatypes are compared alike (D6), and that a
  declared number is compared by its value (D7). A new requirement states
  that the build rejects the constants of D8. Its Purpose already names `sh:hasValue` and deliberate divergences from
  a conformant engine, so it stays.
- `contracts/typed-literals` is unchanged.

## Risks

- A shape that relied on `sh:hasValue "1.0"` accepting a plain `1` on
  SQLite no longer does; on Flink it never did. A shape that needs a number
  should use a number constant.
- Verdicts on Flink change for plain booleans against a boolean constant
  (they now pass): alerts for them close when the package is deployed.
- The JavaScript number formatting is reproduced in the compiler. It is
  pinned by unit tests against known outputs of JavaScript; a change of the
  bridge to another language would need it revisited.
