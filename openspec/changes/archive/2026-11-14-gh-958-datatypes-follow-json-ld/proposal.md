# Proposal

Issue: #958

## Why

A pump whose double attribute holds `80.0` raises a datatype alert on Flink.
The first version of this proposal made `xsd:double` accept every whole
number. Review showed that this works against SHACL: JSON-LD 1.1 already
defines the type of a plain JSON number (*Object to RDF Conversion*, steps 10
and 11). A plain number with a non-zero fractional part is an `xsd:double`;
every other plain number, `80.0` included, is an `xsd:integer`. A conformant
SHACL engine rejects a plain `80.0` on an `xsd:double` shape, and so should
shacl2flink.

Measured against that rule, the checks deviate in three places:

- **A declared double written as a whole number fails.** `{"@value": 80,
  "@type": "xsd:double"}` is a valid double, but its text is `80`, and the
  check wants a decimal point or an exponent. This holds on SQLite and on
  Flink.
- **SQLite reads a plain `80.0` as a double.** The SQLite checks read the
  model through rdflib, which types a JSON number by its notation, unlike
  JSON-LD 1.1. So a plain `80.0` passes `xsd:double` offline and fails on
  Flink, where the bridge has turned it into `80`. The pyshacl comparison
  inherits the same reading, and so does the SemForge SDK, which validates
  models offline with pyshacl on the same rdflib reading.
- **`0` passes `xsd:double` without a type, as a number or a string.** It is
  an exception in the pattern, there because the OPC UA tools write Double
  defaults as a plain `0.0`.

Flink already follows JSON-LD for plain numbers: the bridge writes `80.0` as
`80`, which is the integer the standard makes of it anyway.

## What Changes

- Plain numbers are typed as JSON-LD 1.1 types them, on SQLite, on Flink and
  in the SemForge SDK: `80.5` and `1e21` satisfy `xsd:double`; `80`, `80.0`
  and `0.0` satisfy `xsd:integer` and violate `xsd:double`.
- A declared type decides: a value declared `xsd:double` satisfies
  `xsd:double` whenever its text is a number, `80` included; a value declared
  `xsd:integer` still violates `xsd:double`, and one declared `xsd:double`
  violates `xsd:integer`.
- Strings are judged by their text, as today: `"80.0"` satisfies
  `xsd:double`, `"80"` satisfies `xsd:integer`. The live-data path sends
  values as strings and keeps working.
- The exception for `0` goes: a plain `0.0` is an integer, and the string
  `"0"` has no decimal point. A double zero is declared. Because of that,
  #961's writers land, and the instances in use are written again, **before**
  this change is deployed.
- The pyshacl comparison reads plain numbers as JSON-LD does, so it agrees
  with the checks on numbers; the deliberate divergence for strings stays.
- shacl2flink and the SemForge SDK each implement the reading where they load
  models, and both are tested against one table of test vectors.
- The shacl2flink documentation states the rule.

Saying "this whole number is a double" is the writer's job, with an `@type`.
That is a contract between components and is #961, not this change.

## Capabilities

### New Capabilities
- `shacl2flink/literal-datatypes`: Which values of an NGSI-LD property
  satisfy an `sh:datatype` of `xsd:double` or `xsd:integer` when shacl2flink
  validates a model, on SQLite and on Flink.
- `semforge-sdk/model-numbers`: How the SemForge SDK reads the numbers of a
  model, an example or a test case when it validates them offline.

### Modified Capabilities

None.

## Impact

- Contract between components: **no**. The bridge, Scorpio and the message
  formats are unchanged; the contract for writers is #961.
- shacl2flink (`semantic-model/shacl2flink`): the SQL generated for
  `sh:datatype`, how the SQLite checks and the pyshacl comparison read plain
  numbers from a model, their tests, and `docs/supported-features.md`.
- SemForge SDK (`semantic-model/SemForge-SDK`): the function through which
  its model loaders hand a document to rdflib, and its tests. Its validation
  and cross-check results change as SQLite's do.
- Flink:
  - a declared `xsd:double` written as a whole number stops raising an alert;
  - a `0` without a type, plain or string, starts raising one on an
    `xsd:double` shape.

  Nothing else changes on Flink.
- SQLite and SemForge: plain whole-valued doubles (`80.0`, `121.0`, `0.0`)
  now fail `xsd:double` offline, as they already do on Flink. On SQLite this
  also changes what `sh:in` and `sh:hasValue` compare, and how a list is
  written, towards what Flink sees (design, *Effects on other checks*).
  Expected results that change are listed in the Pull Request.
- Deployment: after #961's writers and the rewritten instances (design, D6).
- No change to any other component, image or chart.

## Out of Scope

- Writers declaring their doubles (the OPC UA tools, the SemForge SDK, the
  kms examples): #961.
- Typing values on the live-data path, which sends strings.
- Keeping the `.0` in JavaScript tools: under JSON-LD it carries no meaning.
- `xsd:float` and `xsd:decimal`, and the special `xsd:double` values `INF`,
  `-INF` and `NaN`.
- Range checks (`sh:minInclusive` and the like), which already compare
  numbers.
