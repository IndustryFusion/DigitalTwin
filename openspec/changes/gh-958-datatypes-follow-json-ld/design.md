# Design

## Context

shacl2flink compiles `sh:datatype` into one SQL check that runs on SQLite (the
offline tests, the SemForge cross-check) and on Flink. For the datatypes it
knows -- `xsd:double`, `xsd:integer`, `xsd:boolean`, `xsd:string` -- the check
reads two columns of an attribute: its value as text and its declared type,
`valueType`. Today a value satisfies `xsd:double` when its type is missing or
`xsd:double`, and its text has a decimal point or an exponent or is `0`; it
satisfies `xsd:integer` when its type is missing or `xsd:integer`, and its
text is digits with an optional sign.

JSON-LD 1.1 (*Object to RDF Conversion*, steps 10 and 11) types a plain JSON
number by its value: `xsd:double` if it has a non-zero fractional part or an
absolute value of at least 10^21, otherwise `xsd:integer`. A declared
`xsd:double` stays a double whatever its value.

There are three validators, and only Flink follows the standard for plain
numbers:

| Source value | JSON-LD 1.1 | Flink: text, type | SQLite: text, type | SemForge (pyshacl) |
|---|---|---|---|---|
| `80` | integer | `80`, none | `80`, `xsd:integer` | integer |
| `80.0` | integer | `80`, none | `80.0`, `xsd:double` | double |
| `0.0` | integer | `0`, none | `0.0`, `xsd:double` | double |
| `80.5` | double | `80.5`, none | `80.5`, `xsd:double` | double |
| `1e21` | double | `1e+21`, none | `1e+21`, `xsd:double` | double |
| `{"@value": 80, "@type": "xsd:double"}` | double | `80`, `xsd:double` | `80`, `xsd:double` | double |
| `{"@value": 80, "@type": "xsd:integer"}` | integer | `80`, `xsd:integer` | `80`, `xsd:integer` | integer |
| `"80.0"` | string | `80.0`, none | `80.0`, none | string |

- **Flink** receives what the debezium bridge writes. JavaScript writes `80.0` as `80`, and the bridge passes a type on only when the stored value has an `@type`.
- **SQLite** receives what rdflib (6.1.1) makes of the JSON-LD model. rdflib types a JSON number by its notation, so a plain `80.0` becomes an `xsd:double`.
- **SemForge** validates with pyshacl on a graph that rdflib parsed the same way. All three of its model loaders hand the document to rdflib through one function that makes its contexts absolute.
- **The pyshacl comparison** in shacl2flink loads its fixtures the same way.

No existing specification covers datatype checks. The shacl2flink
documentation lists `sh:datatype` as supported without saying what a value
has to look like.

## Decisions

### D1 — Plain numbers follow JSON-LD 1.1

- **Chosen:** a plain number is a double only with a non-zero fractional
  part or an absolute value of at least 10^21. On Flink this is already so;
  on SQLite and in SemForge it needs D2.
- *Alternative:* accept every number on `xsd:double` (the first version of
  this proposal). Rejected in review: a conformant SHACL engine rejects a
  plain `80.0` on an `xsd:double` shape, and shacl2flink would accept what
  the standard rejects.
- *Alternative:* keep the `.0` through every JavaScript tool, so that `80.0`
  reaches Flink as written. Rejected: under JSON-LD the `.0` carries no
  meaning, so this would build rdflib's non-standard reading into the
  platform, and it would need every JavaScript tool on the way -- import UI,
  NgsildAgent, MQTT bridge, update path, debezium bridge -- to parse numbers
  losslessly, which any outside producer can undo again.

A whole-valued double has to be declared. That is the writers' part, #961.

### D2 — The offline readers read plain numbers as JSON-LD does

- **Chosen:** before a model is handed to rdflib, a plain number that is
  whole-valued and below 10^21 in absolute value is read as that integer:
  `80.0` as `80`, `0.0` as `0`, `1e20` as `100000000000000000000`. A value
  with a declared `@type` is left as it is, and so is `1e21`. This happens in
  three places: the SQLite checks' model reader, the pyshacl comparison, and
  SemForge's one function in front of rdflib.
- The bound matters: in Python `(1e21).is_integer()` is true, so "whole
  floats become integers" alone would turn `1e21` into an integer, against
  the standard.
- *Alternative:* a conformant JSON-LD processor (PyLD) instead of rdflib.
  Rejected: a new dependency on the path every test, every SemForge
  validation and the cross-check take, for one rule.
- *Alternative:* in SQL, treat a value of type `xsd:double` with whole text
  as an integer. Rejected: on SQLite a declared `{"@value": 80.0, "@type":
  "xsd:double"}` and a plain `80.0` both arrive as `80.0` typed
  `xsd:double`. Only the model can tell them apart, and SemForge does not use
  the SQL at all.

### D3 — One rule, implemented in each component, tested against one table

- **Chosen:** shacl2flink and the SemForge SDK each implement D2 where they
  read models. Both test their implementation against **one** table of test
  vectors -- source value, expected RDF type and text, as in the context
  table -- kept in shacl2flink's tests and read by SemForge's tests from
  there. The cross-check guards the agreement at run time.
- *Alternative:* SemForge imports shacl2flink's reader. Rejected: SemForge
  runs without shacl2flink, which it needs only for the optional cross-check
  and only as a separate process with shacl2flink's own dependencies.
- *Alternative:* a shared Python package for both. Rejected: there is none
  today, and creating one, with its build and release, is out of proportion
  to a rule of a dozen lines.

The pyshacl comparison uses shacl2flink's implementation. It doesn't test
that implementation, so the implementation is tested on its own against the
table first (task 1.3). Otherwise a bug in it would be invisible to the
comparison.

### D4 — A declared xsd:double accepts any number

- **Chosen:** when the type is `xsd:double`, the text has to be a number --
  an optional sign, digits with an optional decimal point or a decimal point
  and digits, an optional exponent -- so `80`, `0`, `80.0`, `.5`, `1e3` and
  `-0` pass.
- *Alternative:* cast the text to a number. Rejected: SQLite's cast never
  fails (`'eighty'` gives 0), Flink's accepts `NaN` and `Infinity`, so the
  dialects would disagree.

`INF`, `-INF` and `NaN` are valid `xsd:double` text but are left out; no
writer produces them.

### D5 — Strings stay judged by their text

- **Chosen:** a string without a type is read by its text: a decimal point
  or an exponent for a double, digits for an integer.
- *Alternative:* follow the standard, where a string is an `xsd:string` and
  violates every numeric shape. Rejected: the live-data path sends every
  value as a string (`"v": "80.0"`), so every live number would raise an
  alert. The divergence from pyshacl for strings is already listed as
  deliberate.

### D6 — No exception for 0; #961 lands first

- **Chosen:** the pattern for a value without a type loses its exception for
  `0`. A plain `0` or `0.0` is an integer, and the string `"0"` has no
  decimal point. Writers that mean a double zero declare it, which #961 makes
  them do.
- *Alternative:* keep the exception until #961 is implemented (the previous
  version of this proposal). Rejected:
  - pyshacl in SemForge sees `0` as an `xsd:integer` and cannot be given an
    exception, so SemForge and shacl2flink would disagree on exactly the
    values the exception exists for;
  - the exception also let the string `"0"` through, against the rule for
    strings.
- **Order:** #961's writers land and the affected instances are written
  again **before** this change is deployed. That order costs nothing:
  - a declared double is no worse off before this change than a plain one,
    since both whole-valued forms already fail on Flink and both pass on
    SQLite;
  - a declared zero passes on Flink before this change as well.

  The other order would turn every plain `0.0` -- the OPC UA tool's default
  for a Double -- into a standing alert on Flink until #961 is done.

## Effects on other checks

D2 changes the type and text that the SQLite checks see for a plain
whole-valued number: `"80.0"^^xsd:double` becomes `"80"^^xsd:integer`. Two
other checks read them:

- **`sh:in`** compares the text and, when there is one, the type with the
  members as Turtle writes them (`80` is an `xsd:integer`, `80.0` an
  `xsd:decimal`). A plain `80.0` now matches a member `80` on SQLite, which
  it did not as `"80.0"^^xsd:double`. Flink, which sees the text `80` without
  a type, matches it already. SQLite moves to what Flink does.
- **`sh:hasValue`** compares by the declared type's cast, and by text when
  there is none. On SQLite a plain `80.0` against `80.0` is now cast as an
  integer instead of a double and still compares equal. On Flink it is
  compared as text, `80` against `80.0`, and differs -- before and after
  this change. That divergence is not this change's to fix and is reported
  separately.
- **Lists:** SQLite now writes `[80,1.5]` for a list where it wrote
  `[80.0,1.5]`, which is what Flink sees.
- **Range checks** compare numbers and are unaffected.

Task 2.3 lists every expected result these effects change.

## Risks

- Offline results change for packages that write whole-valued doubles as
  plain numbers (`80.0`, `121.0`, as the SemForge test-case generator does):
  they now fail `xsd:double` on SQLite and in SemForge, as they already do on
  Flink. #961 changes the generator; until it does, such cases fail offline.
- Deploying this change before #961's writers and the rewritten instances
  turns plain Double defaults (`0.0`) into alerts on Flink. The order in D6
  avoids it; task 5.1 checks it before merge.
- The Flink scenarios for declared types assume Scorpio stores a typed
  `@value` with its `@type` and the bridge forwards it. This is checked
  before the Flink tests are written (task 3.1).
