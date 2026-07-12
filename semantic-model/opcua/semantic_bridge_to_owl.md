# Part 14 Specification: Semantic Bridge to Pure OWL Ontology Transformation

## 1. Purpose

This specification defines the transformation of an OPC UA Semantic Bridge representation into a pure OWL ontology suitable for:

- OWL reasoning
- Ontology consistency checking
- Type satisfiability analysis
- Detection of contradictory OPC UA type constructions

The input model is the Semantic Bridge representation produced by Part 5.

The output ontology contains only OWL constructs:

- Classes
- Subclass relations
- Object properties
- Restrictions
- Cardinality constraints

The resulting ontology contains no OPC UA Instance Declarations.

---

# 2. Design Principle

OPC UA Instance Declarations behave as local type definitions embedded inside ObjectTypes and VariableTypes.

OWL has no equivalent construct.

Therefore every Instance Declaration is transformed into a generated OWL class called a **Virtual Type**.

The transformation replaces declaration inheritance with ordinary OWL class inheritance.

---

# 3. Input Assumptions

The input graph already contains:

## Type Hierarchies

ObjectTypes, VariableTypes and DataTypes are represented as OWL classes.

Example:

```ttl
PumpSubType
    rdfs:subClassOf PumpType .
```

## Semantic Bridge Properties

Hierarchical OPC UA relationships have already been expanded into explicit semantic properties.

Example:

```ttl
PumpType
    sb:hasMotor MotorDeclaration .
```

## Declaration Metadata

Declarations may contain:

- BrowseName
- TypeDefinition
- ModellingRule
- ValueRank
- Child declarations

---

# 4. Effective Declaration Tree

## Motivation

A transformation based only on locally declared Instance Declarations is not sufficient.

A subtype inherits declarations from all supertypes.

Virtual types must therefore be constructed from the complete inherited declaration structure.

---

## Definition

The Effective Declaration Tree of a type T is defined as:

```text
EffectiveDeclarationTree(T)

=
Inherited Declarations
+
Locally Declared Declarations
+
Declaration Overrides
```

where declaration overrides replace inherited type definitions for the affected BrowsePath.

---

## Example

```text
BaseType
  Motor : MotorType

PumpType <: BaseType

AdvancedPumpType <: PumpType
```

The Effective Declaration Tree of all three types contains:

```text
Motor
```

even though only the base type physically declares it.

---

## Requirement

All Virtual Types shall be generated from the Effective Declaration Tree rather than directly from physically stored declarations.

This guarantees preservation of OPC UA inheritance semantics.

---

# 5. Browse Path Identification

Every declaration is uniquely identified by its fully qualified BrowsePath.

Example:

```text
Drive/Motor/Temperature
```

Namespace qualified form:

```text
1:Drive/2:Motor/1:Temperature
```

The BrowsePath shall be calculated recursively through the containment hierarchy.

---

# 6. Virtual Type Construction

For every type T and every BrowsePath P visible within the Effective Declaration Tree of T, create exactly one Virtual Type:

```text
VT(T,P)
```

Example:

```text
VT(PumpType, Drive/Motor)
```

---

# 7. Virtual Type Identifiers

Virtual Type identifiers are constructed from:

```text
OwnerType
+
BrowsePath
```

The BrowsePath may be replaced by a stable hash.

Example:

```text
PumpType_f8a92d1c519f7a2e20f31b6d
```

A minimum of 96 bits (24 hexadecimal digits) is recommended.

The original BrowsePath shall remain accessible as metadata.

Example:

```ttl
sb:originalBrowsePath
    "Drive/Motor"
```

---

# 8. Base Typing Rule

Let:

```text
D = declaration
```

and

```text
BaseType(D)
```

be its OPC UA TypeDefinition.

Generate:

```ttl
VT(T,P)
    rdfs:subClassOf BaseType(D) .
```

Example:

```ttl
PumpType_Motor
    rdfs:subClassOf MotorType .
```

The Virtual Type therefore becomes the OWL representation of the declaration.

---

# 9. Virtual Type Inheritance

## Principle

Virtual Types inherit along two independent dimensions:

1. OPC UA type inheritance
2. OPC UA declaration type definition

As a result, the resulting OWL model naturally becomes a multiple-inheritance hierarchy.

---

## Rule

If:

```text
T <: S
```

and BrowsePath P exists in both Effective Declaration Trees:

generate:

```ttl
VT(T,P)
    rdfs:subClassOf
        VT(S,P) .
```

---

## Example

```text
BaseType
  Motor

PumpType <: BaseType

AdvancedPumpType <: PumpType
```

produces:

```ttl
PumpType_Motor
    rdfs:subClassOf BaseType_Motor .

AdvancedPumpType_Motor
    rdfs:subClassOf PumpType_Motor .
```

---

# 10. Declaration Override Rule

## Example

```text
BaseType
  Motor : MotorType

PumpType <: BaseType
  Motor : AdvancedMotorType
```

Virtual Types:

```ttl
BaseType_Motor
    rdfs:subClassOf MotorType .

PumpType_Motor
    rdfs:subClassOf BaseType_Motor ;
    rdfs:subClassOf AdvancedMotorType .
```

This preserves both:

- inherited declaration semantics
- overridden type semantics

Contradictions become visible to an OWL reasoner.

---

# 11. Recursive Expansion

Virtual Type generation shall recursively process all declarations in the Effective Declaration Tree.

Example:

```text
PumpType
 └─ Drive
      └─ Motor
           └─ Temperature
```

Creates:

```text
PumpType_Drive
PumpType_Drive_Motor
PumpType_Drive_Motor_Temperature
```

Each receiving inheritance and typing rules independently.

---

# 12. Property Semantics

Semantic Bridge properties remain global semantic predicates.

Example:

```ttl
sb:hasMotor
sb:hasTemperature
sb:hasDrive
```

No owner-specific domain or range definitions are generated.

This avoids incorrect global domain/range intersections.

---

# 13. Property Restrictions

Declaration semantics are attached to the owning class through OWL restrictions.

For a declaration:

```text
PumpType
  hasMotor
  PumpType_Motor
```

generate:

```ttl
PumpType
    rdfs:subClassOf [
        rdf:type owl:Restriction ;
        owl:onProperty sb:hasMotor ;
        owl:someValuesFrom PumpType_Motor
    ] .
```

This expresses:

```text
PumpType hasMotor some PumpType_Motor
```

---

# 14. Universal Restrictions

Where the declaration defines the complete expected target type, generate:

```ttl
PumpType
    rdfs:subClassOf [
        owl:onProperty sb:hasMotor ;
        owl:allValuesFrom PumpType_Motor
    ] .
```

This expresses:

```text
PumpType hasMotor only PumpType_Motor
```

---

# 15. Combining Restrictions

Both restrictions may be generated simultaneously.

Example:

```ttl
PumpType
    rdfs:subClassOf
       (hasMotor some PumpType_Motor) .

PumpType
    rdfs:subClassOf
       (hasMotor only PumpType_Motor) .
```

This produces:

```text
PumpType hasMotor exactly members of the Virtual Type hierarchy.
```

---

# 16. Modelling Rule Transformation

Modelling Rules are transformed into cardinality restrictions on semantic bridge properties.

The constraint is attached to the owner type.

It is not attached to the Virtual Type.

---

## Mandatory

```text
ModellingRule = Mandatory
```

becomes:

```ttl
PumpType
    rdfs:subClassOf [
        owl:onProperty sb:hasMotor ;
        owl:minQualifiedCardinality 1 ;
        owl:onClass PumpType_Motor
    ] .
```

---

## Optional

```text
ModellingRule = Optional
```

does not require a minimum-cardinality restriction.

An optional declaration may still generate:

```ttl
allValuesFrom
```

constraints.

---

# 17. ValueRank Transformation

Numeric ValueRank values shall be replaced by symbolic class representations.

Examples:

```text
ValueRank_Any
ValueRank_Scalar
ValueRank_OneDimension
ValueRank_ScalarOrOneDimension
ValueRank_OneOrMoreDimensions
ValueRank_MoreDimensions
```

---

## Rule

Attach ValueRank constraints to the Virtual Type.

Example:

```ttl
PumpType_Temperature
    rdfs:subClassOf
        opcua:ValueRank_Scalar .
```

---

# 18. Datatype Constraints

Datatype information is preserved on Variable Virtual Types.

Example:

```text
Temperature : Double
```

becomes a datatype restriction associated with:

```ttl
PumpType_Temperature
```

Datatype handling is orthogonal to Virtual Type generation.

---

# 19. Removal of Instance Declarations

After Virtual Type generation all OPC UA Instance Declaration nodes shall be removed.

The following information must remain representable:

- declaration inheritance
- declaration overrides
- type hierarchy
- modelling rules
- datatype constraints
- ValueRank constraints
- containment semantics

---

# 20. Resulting Ontology

The output ontology consists of:

- OWL Classes
- Virtual Types
- Subclass hierarchies
- Semantic Bridge properties
- existential restrictions (`someValuesFrom`)
- universal restrictions (`allValuesFrom`)
- cardinality restrictions
- datatype constraints
- symbolic ValueRank classes

The ontology contains no Instance Declarations and can be processed by standard OWL DL reasoners for consistency and satisfiability checking.