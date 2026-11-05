# Tutorial: Ontology (Graph) Validation

This is validation type 1 of 3 (see [Validation Overview](./validation-overview.md)).
It checks the **nodeset itself**, before any instance data exists: are
`HasComponent`, `HasProperty`, `ValueRank`, `ArrayDimensions`, `Historizing` and
`ModellingRule` used the way OPC UA Part 3 requires?

None of these errors are caught by the OPC UA XML schema. `UANodeSet.xsd` is
happy with `ValueRank="-7"`, with a `HasProperty` reference pointing at an
`Object`, or with an `ArrayDimensions` list whose length disagrees with the
`ValueRank`. They are *modelling* errors, and they are found by running a fixed
set of SHACL shapes over the Semantic Bridge ontology that `nodeset2owl.py`
produces.

## Prerequisites

Follow [Overview & Setup](./overview.md) first, then from
`DigitalTwin/semantic-model/opcua`:

```
export BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.3/base.ttl
export BASE_ONTOLOGY_NS=https://industryfusion.github.io/contexts/ontology/v0/base/

make -f translate_default_nodesets.make core.owl.ttl
```

That builds `core.owl.ttl`, the OWL representation of the OPC UA core
specification, which every other nodeset depends on. It takes a few minutes and
needs network access. See the note on the two base-ontology values
in the [Validation Overview](./validation-overview.md#a-note-on-the-base-ontology)
— they are different strings and both are needed.

Nothing beyond `make setup` has to be installed: this validation uses `pyshacl`,
which is already in `requirements-dev.txt`.

## The example model

Two small nodesets are provided:

- [`SensorArray.NodeSet2.xml`](./files/SensorArray.NodeSet2.xml) — consistent
- [`SensorArrayBroken.NodeSet2.xml`](./files/SensorArrayBroken.NodeSet2.xml) — one deliberate error

Both declare the same tiny model:

```
SensorType  --HasComponent-->  Samples  (Variable, Mandatory)
                                  |
                                  | HasTypeDefinition
                                  v
                          SampleArrayType  (VariableType, DataType=Double,
                                            ValueRank=1, ArrayDimensions=0)
```

`SampleArrayType` is a VariableType for a **one-dimensional array** of Doubles:
`ValueRank="1"` means "one dimension" and `ArrayDimensions="0"` means "one
dimension whose length is not fixed". `SensorType` has a Mandatory component
`Samples` typed by it.

In the consistent nodeset, `Samples` is declared as an array too:

```xml
  <UAVariable NodeId="ns=1;i=2001" BrowseName="1:Samples"
              DataType="Double" ValueRank="1" ArrayDimensions="0">
```

The broken one makes a single modelling change — `Samples` is declared a
**scalar** while its TypeDefinition still says array. That takes two XML
attributes, because `ArrayDimensions` has no meaning on a scalar and goes
away with the rank:

```xml
  <UAVariable NodeId="ns=1;i=2001" BrowseName="1:Samples"
              DataType="Double" ValueRank="-1">
```

## Step 1: Convert the nodeset to OWL

```
python3 nodeset2owl.py docs/files/SensorArray.NodeSet2.xml \
    -i ${BASE_ONTOLOGY} core.owl.ttl \
    -b ${BASE_ONTOLOGY_NS} -burl ${BASE_ONTOLOGY} \
    -v http://example.com/v0.1/sensor/ -p sensor -o sensor.owl.ttl
```

This is the same first step as in the [Simple Example](./simple-example.md); the
difference is what happens next. Ontology validation stops here — it needs only
the `*.owl.ttl`, not `owl2instances.py`'s output.

## Step 2: Validate

```
python3 validate.py -m ontology -ni sensor.owl.ttl
```

```
Using SHACL shapes from .../validation/ontology: hasComponent.shacl.ttl, hasProperty.shacl.ttl, historizing.shacl.ttl, modellingRule.shacl.ttl, rankValue.shacl.ttl
Validation Conforms: True
No validation errors found.
```

Note what `-m ontology` did on its own: with no `-s` given it merged **every**
`*.shacl.ttl` file in `validation/ontology/`. Unlike instance validation there is no
single canonical shapes file to point at, only a small fixed set of structural rules
that apply to any ontology equally.

`-ni` (`--no-imports`) validates the file entirely on its own. The ValueRank rules used
in this tutorial fire anyway, because they only need the nodeset's own triples. Without
`-ni`, `validate.py` follows the input's `owl:imports` (network fetches of the base
ontology, and `core.owl.ttl`), so the shapes can see the full class hierarchy, but the
imported ontologies become part of the validated graph: the run validates all of
`core.owl.ttl` as well, takes as long as validating core itself (see
[below](#validating-a-real-companion-specification)) and also reports core's own
findings. Rules that walk the class hierarchy (`hasComponent.shacl.ttl`'s
`rdfs:subClassOf*` check) only report what the loaded hierarchy proves, so with `-ni`
they may miss a violation whose type lives in an imported ontology, but they do not
report false ones.

## Step 3: Break it

```
python3 nodeset2owl.py docs/files/SensorArrayBroken.NodeSet2.xml \
    -i ${BASE_ONTOLOGY} core.owl.ttl \
    -b ${BASE_ONTOLOGY_NS} -burl ${BASE_ONTOLOGY} \
    -v http://example.com/v0.1/sensor/ -p sensor -o sensorbroken.owl.ttl

python3 validate.py -m ontology -ni sensorbroken.owl.ttl
```

```
Validation Conforms: False

=== SHACL Validation Report ===
Validation Report
Conforms: False
Results (1):

    Constraint Violation in SPARQLConstraintComponent (http://www.w3.org/ns/shacl#SPARQLConstraintComponent):
        Severity: http://www.w3.org/ns/shacl#Violation
        Source Shape: https://industryfusion.github.io/contexts/ontology/v0/base/OPCUANodeShape
        Focus Node: http://example.org/sensor/bnN1PWh0dHA6Ly9leGFtcGxlLm9yZy9zZW5zb3IvO2k9MjAwMQ
        Value Node: http://example.org/sensor/bnN1PWh0dHA6Ly9leGFtcGxlLm9yZy9zZW5zb3IvO2k9MjAwMQ
        Source Constraint:
[] sh:message "The node {$this} has a valueRank {?valueRank} which does not match its type definition's valueRank {?parentValueRank}."^^xsd:string ;
    sh:select """
          SELECT $this ?valueRank ?parentValueRank WHERE {
            ...
          }
        """^^xsd:string .

        Message: The node http://example.org/sensor/bnN1PWh0dHA6Ly9leGFtcGxlLm9yZy9zZW5zb3IvO2k9MjAwMQ has a valueRank -1 which does not match its type definition's valueRank 1.
```

`validate.py` also exits with status `1`, so this works in a CI pipeline.

Reading the report:

- **Focus Node** `http://example.org/sensor/bnN1PWh0dHA6Ly9leGFtcGxlLm9yZy9zZW5zb3IvO2k9MjAwMQ` is the offending node.
  The IRI is built from the model URI plus the base64url encoding of the node's
  canonical ExpandedNodeId, so `ns=1;i=2001` in namespace `http://example.org/sensor/`
  is `nsu=http://example.org/sensor/;i=2001` and becomes the IRI above — that is the
  `Samples` Variable. The ExpandedNodeId itself is stored in `uardf:nodeId`, so the
  node can be looked up with
  `grep -B3 'uardf:nodeId "nsu=http://example.org/sensor/;i=2001"' sensorbroken.owl.ttl`.
- **Source Shape** names the shape that fired, `base:OPCUANodeShape`, which lives
  in `validation/ontology/rankValue.shacl.ttl`.
- **Source Constraint** is the full SPARQL query of the rule. It is verbose, but
  it is also the precise definition of what was checked; the `Message` line at
  the bottom is the readable summary.

## Scoping the check to a single rule

When a report is long, it helps to run one rule at a time. Pass a single file to
`-s` instead of letting it default to the whole directory:

```
python3 validate.py -m ontology -ni -s validation/ontology/rankValue.shacl.ttl sensorbroken.owl.ttl
```

This is exactly what `tests/validation/test.bash` does, so that each test case
can assert which specific rule fired.

## Validating a real companion specification

The same command works on any `*.owl.ttl` the build produces:

```
python3 validate.py -m ontology -ni core.owl.ttl
```

```
Validation Conforms: False
...
Results (2):
...
        Message: Variable node http://opcfoundation.org/UA/aT0zMjQzMw reached by HasComponent reference must be (or inherit from) opcua:BaseDataVariableType.
...
        Message: Variable node http://opcfoundation.org/UA/aT0xNTAxNA reached by HasComponent reference must be (or inherit from) opcua:BaseDataVariableType.
```

The two findings are real statements about the core nodeset: `aT0zMjQzMw` is
`i=32433` and `aT0xNTAxNA` is `i=15014`, the placeholders `<FieldName>` and
`<OptionalFieldName>` of `BitFieldType`. They are components (HasComponent), so they
are DataVariables, but their TypeDefinition is the abstract `BaseVariableType`
rather than `BaseDataVariableType` or one of its subtypes.

and on the companion specifications built from it:

```
make -f translate_default_nodesets.make di.owl.ttl
python3 validate.py -m ontology -ni di.owl.ttl
```

```
Validation Conforms: True
No validation errors found.
```

Be patient with the large ones. The rules are SPARQL-based, so runtime grows
quickly with the graph: `di.owl.ttl` takes about three seconds, while
`core.owl.ttl` has hundreds of thousands of triples and takes roughly six and a
half minutes. `-ni` avoids re-fetching the imports on every run, and scoping
with `-s` to the single rule you care about is much faster than the merged
default.

## The rules

`validation/ontology/` holds one file per topic. All of them are merged when no
`-s` is given.

| File | What it enforces |
|------|------------------|
| `rankValue.shacl.ttl` | `ValueRank` is an `xsd:integer` `>= -3` occurring at most once; `ArrayDimensions` is a well-formed list of non-negative integers; a Variable's `ValueRank` is compatible with its TypeDefinition's; a VariableType's `ValueRank` is compatible with its supertype's; `ArrayDimensions` agrees with the `ValueRank`, which per Part 3 means: a `ValueRank > 0` needs exactly that many entries, `-1` (Scalar) forbids them, `-3` (ScalarOrOneDimension) allows at most one, and `-2` (Any) and `0` (OneOrMoreDimensions) are left unconstrained. |
| `hasComponent.shacl.ttl` | A Variable reached by `HasComponent` is (or inherits from) `BaseDataVariableType` (reported only when its TypeDefinition is known to derive from `BaseVariableType`/`PropertyType` instead, so a type whose hierarchy is not loaded with `-ni` is not reported); a Variable that itself has `HasComponent` children is a DataVariable (i.e. it is itself a component of something); the target of a `HasComponent` is a Variable, Object or Method; the source/target node-class pairing is legal (a Variable target needs an Object, ObjectType, DataVariable or VariableType source; an Object or Method target needs an Object or ObjectType source). |
| `hasProperty.shacl.ttl` | `HasProperty` references a Variable (`uardf:Variable`) of `PropertyType`, by IRI; a node reached via `HasProperty` has no `HasProperty` links of its own (Properties are leaves). |
| `modellingRule.shacl.ttl` | `HasModellingRule` occurs at most once, only on Objects, Variables and Methods, and references one of the five real modelling rules: `Mandatory` (`i=78`), `Optional` (`i=80`), `ExposesItsArray` (`i=83`), `OptionalPlaceholder` (`i=11508`), `MandatoryPlaceholder` (`i=11510`). |
| `historizing.shacl.ttl` | `Historizing` is an `xsd:boolean` occurring at most once, and only on Variables. |

The rules work on the node representation `nodeset2owl.py` writes: shapes target the
node classes (`uardf:Variable`, `uardf:Object`, ...), the TypeDefinition is
`uardf:hasTypeDefinition` (or `rdf:type` with `--enforce-opcua-type-semantic`), a type
node points to its class with `uardf:definesType`, and references are the OPC UA
reference types (`opcua:HasComponent`, `opcua:HasProperty`, `opcua:HasModellingRule`).
See the README's [Node Identification](../README.md#node-identification-uardf).

Adding a rule is a matter of dropping another `*.shacl.ttl` file into that
directory — it is picked up automatically by the merged default. The `*.shacl.ttl`
suffix is a naming convention, not content sniffing, so the extension matters.

## What this validation cannot find

Ontology validation reasons about one node and its immediate references. It
cannot see a contradiction that only exists between a supertype's declaration and
a subtype's override, because neither node is wrong on its own. For that, see
[Virtual Type Validation](./virtual-type-validation.md).
