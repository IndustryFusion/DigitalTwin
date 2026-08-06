# OPC UA Semantic Bridge Transformation Specification

## 1. Goal

Transform an OPC UA information model into an RDF representation that preserves:

- OPC UA type hierarchies
- OPC UA instances
- containment structures
- browse-name semantics
- modelling rules
- type definitions

while making the implicit semantics of OPC UA explicit in RDF.

The output is not yet a pure OWL ontology.

Instead, it is an intermediate Semantic Bridge representation from which:

- OWL ontologies can be generated
- SHACL constraints can be generated
- JSON-LD instance models can be validated

The Semantic Bridge therefore acts as a semantic normalization layer.

---

# 2. Meta Model Separation

The first step separates OPC UA meta-model concepts from domain semantics.

## Type Definitions

Transform:

HasSubtype

into:

rdfs:subClassOf

for

- ObjectTypes
- VariableTypes
- DataTypes

Example:

PumpType
    HasSubtype
        PumpSubType

becomes

PumpSubType
    rdfs:subClassOf PumpType

---

## Type Assignment

Transform:

HasTypeDefinition

into:

rdf:type

Example:

Pump1
    HasTypeDefinition PumpType

becomes

Pump1 rdf:type PumpType

---

## Reference Types

ReferenceTypes become OWL ObjectProperties.

Example:

Organizes

becomes:

opcua:Organizes rdf:type owl:ObjectProperty

Reference hierarchies become:

rdfs:subPropertyOf

---

# 3. Semantic Expansion of Aggregate References

OPC UA aggregate references such as:

- HasComponent
- HasProperty
- HasOrderedComponent

carry semantic meaning through the BrowseName of the target.

This semantic information is implicit in OPC UA.

The Semantic Bridge makes it explicit.

---

# 4. Property Generation

For every aggregate reference:

Parent --Aggregate--> Child

create a semantic property derived from the BrowseName.

Example:

PumpType
    HasComponent Motor

becomes

PumpType sb:hasMotor Motor

where:

sb:hasMotor rdf:type owl:ObjectProperty

---

# 5. Property Naming

Property names are generated from:

BrowseName
+ Namespace

Example:

2:Temperature

becomes

ns2:hasTemperature

Namespace information must be preserved.

---

# 6. Preservation of OPC UA Structure

The original aggregate reference should remain available.

Example:

PumpType
    opcua:HasComponent Motor

PumpType
    sb:hasMotor Motor

The semantic property is additional information.

---

# 7. Modelling Rules

ModellingRules remain attached to the declaration node.

Example:

MotorDeclaration
    opcua:ModellingRule Mandatory

No OWL cardinalities are generated at this stage.

---

# 8. Variable Metadata

Variable properties remain attached to variable declarations.

Examples:

- DataType
- ValueRank
- AccessLevel
- EURange

No symbolic OWL interpretation is performed yet.

---

# 9. Instance Declarations

Instance declarations are preserved.

Example:

PumpType
    sb:hasMotor MotorDeclaration

MotorDeclaration
    rdf:type opcua:InstanceDeclaration

Instance declarations remain first-class nodes.

---

# 10. Result

The Semantic Bridge graph contains:

- OWL classes representing OPC UA type definitions
- explicit semantic properties derived from BrowseNames
- preserved instance declarations
- preserved modelling rules
- preserved ValueRank information
- preserved subtype hierarchies

The model remains structurally very close to OPC UA while exposing its implicit semantics.