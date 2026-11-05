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

Every node is typed by its OPC UA NodeClass, using the classes of the OPC UA RDF
meta ontology `uardf:` (`http://opcfoundation.org/rdf/uacore#`, see `uardf.ttl`):

uardf:Object, uardf:Variable, uardf:Method, uardf:View, uardf:ObjectType,
uardf:VariableType, uardf:DataType, uardf:ReferenceType

Transform:

HasTypeDefinition

into:

uardf:hasTypeDefinition

Example:

Pump1
    HasTypeDefinition PumpType

becomes

Pump1 rdf:type uardf:Object ;
    uardf:hasTypeDefinition PumpType

HasTypeDefinition is deliberately not translated into rdf:type: the TypeDefinition of an
instance (and of an instance declaration) is OPC UA information, not an OWL class
membership. `nodeset2owl.py --enforce-opcua-type-semantic` writes rdf:type instead.

A type is represented twice: by the OWL class (e.g. PumpType) and by the type node,
which carries the node information and points to the class:

PumpTypeNode
    rdf:type uardf:ObjectType ;
    uardf:definesType PumpType ;
    uardf:isAbstract false

---

## Node Identification

The IRI of a node is the namespace URI followed by the base64url encoding (without
padding) of its canonical ExpandedNodeId. The node keeps its identification as data:

- uardf:nodeId: the canonical ExpandedNodeId, e.g. `nsu=http://opcfoundation.org/UA/Pumps/;i=1002`
  (`i=2042` for core nodes)
- uardf:namespaceUri, uardf:browseName (`nsu=<namespace>;<name>`), uardf:name,
  uardf:symbolicName, uardf:displayName, uardf:description
- uardf:parent: the ParentNodeId

Nodes which are the same in every server are static. Server specific (dynamic) nodes
are only translated when a server URI is given; their ExpandedNodeId contains it
(`svu=<server URI>;nsu=…;i=…`) and they carry uardf:serverUri.

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

sb:hasMotor rdf:type owl:ObjectProperty ;
    rdfs:subPropertyOf uardf:semanticBridgeReferenceType

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
    opcua:HasModellingRule Mandatory

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
    rdf:type uardf:Object ;
    uardf:hasTypeDefinition MotorType ;
    opcua:HasModellingRule Mandatory

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