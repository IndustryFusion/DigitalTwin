# Proposal

Issue: #961

## Why

JSON has one kind of number. JSON-LD 1.1 (*Object to RDF Conversion*, steps 10
and 11) therefore types a plain JSON number by its value: an `xsd:double` only
with a non-zero fractional part or an absolute value of at least 10^21, an
`xsd:integer` otherwise -- `80.0` included. The only way to say "this whole
number is a double" is to declare it: `{"@value": 80, "@type": "xsd:double"}`.
A SHACL shape that asks for `sh:datatype xsd:double` rejects every
whole-valued double written as a plain number, and with #958 shacl2flink
follows that rule on SQLite and in the SemForge SDK as it already did on Flink.

No writer in the platform declares a double. The only type any of them
writes is `xsd:dateTime`:

- **the OPC UA instance tool** writes Double, Float, Decimal and Duration
  variables as plain numbers. A whole value written as an integer literal in
  the nodeset comes out as `80`, and the default of a Double is a plain
  `0.0`;
- **the SemForge SDK** writes plain floats: in generated test cases (a valid
  case holds `60.0`, a range-break case `161.0`), in the package scaffold's
  example (`21.5`, and any whole value it is changed to), and in an example
  value a modeller edits on a page.

So a pump whose double happens to be whole raises a datatype alert as soon as
it reaches Flink, and with #958 the SemForge suites fail the same way: eight
unit tests on PR #959 fail only because SemForge's generators write `60.0`.

The tools that pass data on cannot repair this. Scorpio and the debezium
bridge keep a declared `@type` -- measured in #959, task 3.1 -- but they do
not know the shape, and JavaScript writes `80.0` as `80` anyway.

## What Changes

- **A contract for typed literals** (`contracts/typed-literals`):
  - a writer that knows an attribute's value is an `xsd:double`, `xsd:float`
    or `xsd:decimal` writes **every** value of it with that `@type`, whatever
    the value, so a value that is fractional today and whole tomorrow keeps
    its type;
  - the type resolves to the full XSD IRI in the document's context, since
    the NGSI-LD core context defines no `xsd` prefix;
  - integers, booleans and strings stay plain, and so does a number whose
    attribute admits integers as well (`sh:or ( xsd:double xsd:integer )`,
    the OPC UA `Number` type);
  - tools that pass a document on keep the `@type`.
- **The OPC UA instance tool** declares Double, Float, Decimal and Duration
  values and defaults.
- **The SemForge SDK** declares doubles in generated test cases (valid and
  break values), in the scaffold's example, and in example values a modeller
  edits.
- The OPC UA tools' and the SemForge SDK's documentation name the rule.

## Capabilities

### New Capabilities
- `contracts/typed-literals`: How a writer of NGSI-LD JSON-LD states a
  property value's numeric datatype, and what the components that pass the
  document on must keep.

### Modified Capabilities

None.

## Impact

- Contract between components: **yes**. It concerns every writer of NGSI-LD
  models, Scorpio, the debezium bridge and the checks of shacl2flink and the
  SemForge SDK.
- OPC UA tools (`semantic-model/opcua`): the instance tool's values and
  defaults, its tests and README. Generated instances and packages change
  form; packages are built in CI and never committed.
- SemForge SDK (`semantic-model/SemForge-SDK`): the test-case generator, the
  scaffold, the example value editor, their tests and README. Test cases
  generated before this change keep their plain values until regenerated or
  edited.
- kms packages (`semantic-model/kms`): no change. The only `xsd:double`
  attribute, `hasTrust`, holds no whole value in any committed example.
- No change to shacl2flink, the bridges, Scorpio, images or charts.
- **Order:** this change lands before #958 (`gh-958-datatypes-follow-json-ld`,
  design D6), and instances in use are written again before #958 is
  deployed. Landing first makes no verdict worse (design, *Order with #958*).

## Out of Scope

- The live-data path (dataservice, NgsildAgent, MQTT bridge), which sends
  every value as a string; the checks judge strings by their text
  (`contracts/opcua-live-data`, *Value forms in messages*).
- Items of a list (`ListProperty`): the list checks match the serialised
  array and accept any number for `xsd:double`.
- The shacl2flink checks themselves: #958.
- Changing how JavaScript tools parse numbers.
- Rewriting test cases that already exist in a package; they are regenerated
  or edited by their owners.
