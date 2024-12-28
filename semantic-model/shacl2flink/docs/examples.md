# KMS Examples & Tutorial

## Introduction to KMS

*KMS* combines three essential ingredients for semantic data modeling:

1. **K (Knowledge):** Encodes domain taxonomies and ontologies in OWL/RDF, typically serialized in Turtle format. This represents the conceptual structure of the domain.
2. **M (Model-Instance):** Describes real-world instances and their relationships in NGSI-LD/JSON-LD format.
3. **S (SHACL):** Specifies constraints and rules to validate instances against the Knowledge model.

This tutorial demonstrates how to combine these elements to ensure data integrity and semantic consistency. By the end, you will understand how to define NGSI-LD instances, create an OWL knowledge model, and validate data using SHACL.

---

## NGSI-LD Instance Model

### Defining Instances

Let’s define two entities, a **Cutter** and a **Filter**, and their relationship:

1. The Cutter (`urn:iff:cutter:1`) has:
   - A **relationship**: `hasFilter` pointing to the Filter (`urn:iff:filter:1`).
   - Two **properties**:
     - `hasState` with the value `executingState`.
     - `hasTemperature` with the value `30.5`.

2. The Filter (`urn:iff:filter:1`) has:
   - One **property**: `hasState` with the value `executingState`.

Here’s the JSON-LD representation:

```json
[
  {
    "@context": [
      "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
      { "@vocab": "https://industry-fusion.org/base/v1/" }
    ],
    "id": "urn:iff:cutter:1",
    "type": "Cutter",
    "hasFilter": {
      "type": "Relationship",
      "object": "urn:iff:filter:1"
    },
    "hasState": {
      "type": "Property",
      "value": { "@id": "https://industry-fusion.org/ontology/v1/executingState" }
    },
    "hasTemperature": {
      "type": "Property",
      "value": 30.5
    }
  },
  {
    "@context": [
      "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
      { "@vocab": "https://industry-fusion.org/base/v1/" }
    ],
    "id": "urn:iff:filter:1",
    "type": "Filter",
    "hasState": {
      "type": "Property",
      "value": "https://industry-fusion.org/ontology/v1/executingState"
    }
  }
]
```

### Key Concepts:

- **Properties**: Attributes like `hasState` and `hasTemperature` provide data about an entity.
- **Relationships**: Connections between entities, such as `hasFilter`.
- **Unique Identifiers**: Each entity has a unique `id`.
- **International Resource Identifiers (IRIs)**: IRIs are encoded in JSON-LD by `"@id": "iri"`

---
## OWL Knowledge Model

The Knowledge model defines the conceptual structure and relationships between types. For this example:

1. **Machine Taxonomy**:
   - `Cutter` and `Filter` are subtypes of `Machine`.

2. **States**:
   - The `MachineState` class includes:
     - `executingState`
     - `errorState`
     - `notExecutingState`

Here’s the OWL representation in Turtle syntax:

```turtle
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix iffbase: <https://industry-fusion.org/base/v1/> .
@prefix ontology: <https://industry-fusion.org/ontology/v1/> .

iffbase:Machine a owl:Class .

iffbase:Cutter a owl:Class ;
    rdfs:subClassOf iffbase:Machine .

iffbase:Filter a owl:Class ;
    rdfs:subClassOf iffbase:Machine .

ontology:MachineState a owl:Class .

ontology:executingState a ontology:MachineState .
ontology:errorState a ontology:MachineState .
ontology:notExecutingState a ontology:MachineState .
```

---

## SHACL Shapes and Validation

### Understanding SHACL

SHACL shapes define constraints and rules for validating data against the Knowledge model. They operate on graph structures and can validate both properties and relationships.

### Example: Cutter Temperature Constraint

We want to validate that:

**Every Cutter must have exactly one `hasTemperature` property of type `double`.**

#### SHACL Shape Definition:

```turtle
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix iffbase: <https://industry-fusion.org/base/v1/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

cutterTemperatureShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:maxCount 1 ;
        sh:minCount 1 ;
        sh:nodeKind sh:BlankNode ;
        sh:property [
            sh:path ngsi-ld:hasValue ;
            sh:datatype xsd:double ;
        ]
    ] .
```

---

### Adding Min/Max Constraints

To specify acceptable temperature ranges, we extend the shape:

**Constraint**: Temperature must be between 20.0 (inclusive) and 50.0 (exclusive).

```turtle
cutterTemperatureWithMinMaxShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
    sh:property [
        sh:path iffbase:hasTemperature ;
        sh:maxCount 1 ;
        sh:minCount 1 ;
        sh:nodeKind sh:BlankNode ;
        sh:property [
            sh:path ngsi-ld:hasValue ;
            sh:datatype xsd:double ;
            sh:minInclusive 20.0 ;
            sh:maxExclusive 50.0 ;
        ]
    ] .
```

---

### Relationship Constraints

**Constraint**: Every Cutter must have at most one `hasFilter` relationship pointing to an entity of type `Filter`.

```turtle
cutterLinkedToFilterShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
    sh:property [
        sh:path iffbase:hasFilter ;
        sh:maxCount 1 ;
        sh:nodeKind sh:BlankNode ;
        sh:property [
            sh:path ngsi-ld:hasObject ;
            sh:class iffbase:Filter ;
        ]
    ] .
```

---

### Using Ontology Links

**Constraint**: Every Machine must have at least one `hasState` property of class `MachineState`.

```turtle
machineStateShape a sh:NodeShape ;
    sh:targetClass iffbase:Machine ;
    sh:property [
        sh:path iffbase:hasState ;
        sh:maxCount 1 ;
        sh:minCount 1 ;
        sh:nodeKind sh:BlankNode ;
        sh:property [
            sh:path ngsi-ld:hasValue ;
            sh:class ontology:MachineState ;
        ]
    ] .
```

---

## Advanced Constraints with SPARQL

SHACL supports custom constraints using SPARQL. For example:

**Constraint**: A Cutter in `executingState` must have a linked Filter also in `executingState`.

#### SPARQL Query:

```sparql
SELECT ?this ?filter WHERE {
    ?this iffbase:hasFilter [ ngsi-ld:hasObject ?filter ] .
    ?this iffbase:hasState [ ngsi-ld:hasValue ?cstate ] .
    ?filter iffbase:hasState [ ngsi-ld:hasValue ?fstate ] .
    FILTER (?cstate = ontology:executingState && ?fstate != ontology:executingState)
}
```

#### SHACL Shape with SPARQL:

```turtle
:cutterStateInLineWithFilterShape a sh:NodeShape ;
    sh:targetClass iffbase:Cutter ;
    sh:sparql [
        a sh:SPARQLConstraint ;
        sh:message "Cutter {?this} executing without executing filter {?filter}" ;
        sh:select """
            PREFIX ontology: <https://industry-fusion.org/ontology/v1/>
            PREFIX iffbase: <https://industry-fusion.org/base/v1/>
            PREFIX ngsi-ld: <https://uri.etsi.org/ngsi-ld/>

            SELECT ?this ?filter WHERE {
                ?this iffbase:hasFilter [ ngsi-ld:hasObject ?filter ] .
                ?this iffbase:hasState [ ngsi-ld:hasValue ?cstate ] .
                ?filter iffbase:hasState [ ngsi-ld:hasValue ?fstate ] .
                FILTER (?cstate = ontology:executingState && ?fstate != ontology:executingState)
            }
        """ ;
    ] .
```



## Construct Nodes with SHACL Rules

TBD

---

## Validation with PyShacl

### Precondition

- Python >= 3.9
- PyShacl is installed `pip install pyshacl`
- Working directory is `docs`

### Files needed for validation

#### NGSI-LD Instances
- [./files/cutter-filter-full.jsonld](./files/cutter-filter-full.jsonld) - Correct Cutter and Filter instances
- [./files/cutter-filter-full-no-temp.jsonld](cutter-filter-full-no-temp.jsonld) - Missing Temperature in Cutter
- [./files/cutter-filter-full-high-temp.jsonld](./files/cutter-filter-full-high-temp.jsonld) - Too temperature
- [./files/cutter-filter-full-low-temp.jsonld](./files/cutter-filter-full-low-temp.jsonld]) - Too low temperature
- [./files/cutter-filter-full-no-filter.jsonld](./files/cutter-filter-full-no-filter.jsonld) - Cutter does not have a `hasFilter` Relationship
- [./files/cutter-filter-full-wrong-filter.jsonld](./files/cutter-filter-full-wrong-filter.jsonld) - Cutter is linked with Filter of wrong type
- [./files/cutter-filter-full-wrong-state.jsonld](./files/cutter-filter-full-wrong-state.jsonld) - Cutter state is not of class `ontology:MachineState`
- [./files/cutter-filter-full-not-aligned-states.jsonld](./files/cutter-filter-full-not-aligned-states.jsonld) - Cutter state in on `ontology:executingState` but connected Filter has wrong state

#### SHACL file

[./files/shacl.ttl](./files/shacl.ttl)

#### Knowledge/Ontology File

[./files/knowledge.ttl](./files/knowledge.ttl)

### Validation Examples

Validate an NGSI-LD Instace with

        pyshacl -s ./files/shacl.ttl -df json-ld ./files/<file.jsonld> -e files/knowledge.ttl

To simplify the output we append `| egrep 'Conforms|Message'` to the validation. For instance, validation of the correct instances is done by

        pyshacl -s ./files/shacl.ttl -df json-ld ./files/cutter-filter-full.jsonld -e ./files/knowledge.ttl | egrep 'Conforms|Message'
Output:

        Conforms: True

Validate the low temparature example:

        pyshacl -s ./files/shacl.ttl -df json-ld ./files/cutter-filter-full-low-temp.jsonld -e ./files/knowledge.ttl | egrep 'Conforms|Message'

Output:

        Conforms: False
        Message: Value is not >= Literal("20.0", datatype=xsd:decimal)

Validate the SPARQL query example:

        pyshacl -s ./files/shacl.ttl -df json-ld ./files/cutter-filter-full-not-aligned-states.jsonld -e ./files/knowledge.ttl | egrep 'Conforms|Message'

Output:

        Conforms: False
        Message: Cutter urn:iff:cutter:1 running without running filter urn:iff:filter:1
