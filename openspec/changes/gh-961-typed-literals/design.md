# Design

## Context

JSON-LD 1.1 types a plain JSON number by its value: an `xsd:double` only with
a non-zero fractional part or an absolute value of at least 10^21, otherwise
an `xsd:integer`. #958 (`gh-958-datatypes-follow-json-ld`, PR #959) makes
shacl2flink and the SemForge SDK read plain numbers that way on every path,
as Flink already did. A whole-valued double therefore passes `sh:datatype
xsd:double` only when it is declared.

Measured in #959 (task 3.1, `ibn40/scorpio-all-in-one-runner:v0.10`): Scorpio
stores a declared `@type` and the notation unchanged. The debezium bridge
publishes the type as `valueType` and the value as JavaScript prints it, `80`
for a declared `80.0`; #958 makes a declared double accept that text.

The writers today:

| Writer | Where | A whole-valued double comes out as |
|---|---|---|
| OPC UA instance tool, values | `opcua/lib/jsonld.py`, `get_value` | the RDF literal's own value: `80.0` from a double literal, `80` from an integer literal on a Double variable. A `float` cast is computed but never applied. |
| OPC UA instance tool, defaults | `get_default_value` | plain `0.0` for Double, Float, Decimal, Duration and Number |
| SemForge, generated cases | `semforge/expect/attributecase.py` | `float(number)`: `80.0` for a valid case, `161.0` for a range break |
| SemForge, scaffold | `semforge/package/scaffold.py` | the example's temperature as given, plain |
| SemForge, example editor | `semforge/cooked/examples.py` | the modeller's text parsed as JSON, plain |

The only `@type` any writer emits is `xsd:dateTime`, in its compact form.
The OPC UA tool maps Float, Double, Decimal and Duration to `xsd:double`, and
Number to `xsd:double` or `xsd:integer`, whose shapes are an `sh:or` of both.

The live-data path sends values as strings and is specified separately
(`contracts/opcua-live-data`). This change does not touch it.

## Decisions

### D1 — Every value of a double attribute is declared, not only whole ones

- **Chosen:** a writer that knows an attribute is a double declares every
  value of it.
- *Alternative:* declare only whole values. Rejected:
  - the value of an attribute changes, and a writer that types `80.5` plain
    and `80` declared writes two forms for one attribute;
  - readers would have to know which form to expect;
  - a value edited from `80.5` to `80` would silently need a different form.
- *Alternative:* write every number with a type, integers included.
  Rejected: an integer is already what JSON-LD makes of a plain whole number,
  and the declared form is heavier to read and write by hand.

### D2 — Writers write the full XSD IRI

- **Chosen:** the OPC UA tool and the SemForge SDK write
  `"@type": "http://www.w3.org/2001/XMLSchema#double"`. The specification
  allows the compact form where the context defines `xsd`, so hand-written
  models may use it.
- *Alternative:* `xsd:double`, as the existing `xsd:dateTime` values do.
  Rejected for the writers:
  - the OPC UA tool references its context by URL, chosen at deployment
    (`--context-url`), so the tool cannot know that it defines `xsd`;
  - the NGSI-LD core context does not define it;
  - an undefined prefix does not fail: JSON-LD reads `xsd:double` as an IRI
    of the scheme `xsd`, and the value silently has a type nobody checks for.
- The existing `xsd:dateTime` values are left as they are (see Risks).

### D3 — Where the writers learn the datatype

- **OPC UA instance tool:** from the variable's data type, through the
  existing map. Float, Double, Decimal and Duration are declared; Number is
  written plain, with a whole value as an integer, so that `0.0` becomes `0`.
- **SemForge SDK:** from the attribute's shape, which the generator and the
  page already read (`sh:datatype xsd:double` alone). An attribute under an
  `sh:or` of a double and an integer is written plain.
- *Alternative:* in SemForge, declare by the JSON type of the value (any
  float). Rejected: an integer attribute given `80.0` by a modeller would
  become a declared double and violate its shape; the shape is what says what
  the value is.

### D4 — The example editor declares what the modeller types

- **Chosen:** when a modeller sets the value of an `xsd:double` attribute,
  the number they type is written as a declared double; a value object they
  type themselves is kept as typed.
- *Alternative:* keep the modeller's text as it is. Rejected: `80` typed on
  a page would be the integer the shape rejects, and the editor would create
  the violation it is meant to help avoid.

### D5 — Lists stay plain

- **Chosen:** items of a `ListProperty` stay plain numbers.
- The list checks match the serialised array and accept any number for
  `xsd:double` (`LIST_ELEMENT_PATTERNS` in shacl2flink). A declared value
  object inside a list would serialise as an object and fail that pattern.

## Order with #958

This change lands before #958, and instances in use are written again
before #958 is deployed. Landing first makes no verdict worse:

| Value written by this change | Before #958 (main) | After #958 |
|---|---|---|
| declared `80.0`, read on Flink | text `80`, type double: fails, as a plain `80.0` fails today | passes |
| declared `80.0`, read on SQLite | text `80.0`, type double: passes, as a plain `80.0` does today | passes |
| declared `0.0`, read on Flink | text `0`, type double: passes (the old exception for `0`) | passes |
| declared `80`, read in SemForge (pyshacl) | `"80"^^xsd:double`: passes | passes |
| plain `0` for a Number | integer under `sh:or`: passes | passes |

The eight SemForge unit tests that fail on PR #959 pass once #959 is rebased
onto this change, because the generator stops writing plain `60.0`.

## Risks

- **Instances and test cases written before this change** keep their plain
  values. With #958 deployed, a whole-valued double among them raises an
  alert, as it already does on Flink today. Generated packages are rebuilt in
  CI; committed SemForge test cases are regenerated or edited by their
  owners. The kms examples hold none.
- **Hand-written models** have to follow the rule. The shacl2flink and
  SemForge documentation (#958) says how to write a whole-valued double.
- **`xsd:dateTime` values** are still written as `xsd:dateTime` and depend on
  the context defining `xsd`. They are not part of this change; a check of
  how they resolve in the OPC UA and SemForge contexts belongs to an issue of
  its own.
