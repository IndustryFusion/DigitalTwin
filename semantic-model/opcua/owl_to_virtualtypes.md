# Part 14 Specification: Semantic Bridge to OWL Virtual Types Transformation

Implemented by `owl2virtualtypes.py` (`lib/owlbuilder.py`'s `OwlBuilder`).

## 1. Purpose

This specification defines the transformation of an OPC UA Semantic Bridge representation into an OWL ontology of Virtual Types, containing no individuals (Instance Declarations) at all -- only classes and restrictions -- suitable for:

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

Where an Instance Declaration's own content genuinely diverges from what it inherits, it is transformed into a generated OWL class called a **Virtual Type** (see section 6 for the exact, need-based minting criterion). Where it does not -- a pure pass-through of an inherited declaration, or a plain override with no local extension -- ordinary OWL subsumption or a direct reference to the real overriding type already expresses it, with no synthetic class required.

The transformation replaces declaration inheritance with ordinary OWL class inheritance, minting only the Virtual Types actually needed to do so.

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

## Need-Based Minting

Constructing the Effective Declaration Tree does not imply that every entry in it requires its own Virtual Type.

A Virtual Type is only minted for an entry whose own content genuinely diverges from what is already established by inheritance: an overridden TypeDefinition, an overridden ValueRank or Datatype (Variables only), or the declaration node carrying local structure of its own beyond its nominal type (OPC UA permits *retyping by addition*, not only *retyping by substitution* -- see section 10).

Where nothing has changed, the entry's target is simply reused unchanged: ordinary `rdfs:subClassOf` already propagates the ancestor's restriction for free, so a redundant Virtual Type would add nothing but a synthetic wrapper.

Where only the TypeDefinition changes and the declaration has no local structure of its own, the entry's target becomes the real overriding type directly -- it already fully specifies itself as an independently-processed class, so no synthetic wrapper is needed there either.

See section 6 for the full minting rule.

---

# 5. Browse Path Identification

Every declaration is uniquely identified within its owner by its namespace-qualified BrowseName segment.

Example:

```text
1:Temperature
```

A Virtual Type's owner is either a real OWL class (from `get_cdt`) or another, enclosing Virtual Type produced one level further up the containment hierarchy -- so a multi-level declaration such as `Drive/Motor/Temperature` is identified not by one flattened three-segment path computed up front, but by a chain of single-segment lookups, one per nesting level:

```text
VT(PumpType, "Drive")
  owns  VT(VT(PumpType,"Drive"), "Motor")
          owns  VT(VT(...,"Motor"), "Temperature")
```

Only the levels where minting is actually needed (section 6) appear in this chain at all; a level with nothing to say is simply skipped, and the original full BrowsePath remains recoverable by walking the `sb:originalBrowsePath` annotation (section 7) of each Virtual Type actually present outward to its owner.

---

# 6. Virtual Type Construction

Virtual Types are minted need-based, not exhaustively: not every entry of the Effective Declaration Tree gets one.

For a declaration D at owner O (a type T, or an enclosing Virtual Type one level up the containment hierarchy -- section 5), let I be the corresponding entry inherited from O's direct supertype at the same BrowseName segment, if any.

Create a Virtual Type `VT(O, key)` if, and only if, at least one of the following holds:

- D's TypeDefinition differs from I's (an override), **and** D is a Variable, **or** D itself carries local structure of its own (see below) -- a plain Object override with nothing else changed does not qualify (section 10);
- D is a Variable and its ValueRank differs from I's;
- D is a Variable and its Datatype differs from I's;
- D itself has its own declared children beyond what its nominal TypeDefinition alone provides ("local structural extension" -- OPC UA permits retyping by *addition*, not only retyping by *substitution*: a component may be typed as a plain, otherwise-empty type while locally adding its own specific sub-properties. See the `PubSubDiagnosticsDataSetWriterType`/`LiveValues` pattern in the OPC UA core nodeset for a real occurrence);
- D is brand new (I does not exist) and any of the above would otherwise apply to it in isolation (a new Variable always qualifies, to carry ValueRank/Datatype; a new plain Object declaration with no local extension does not).

Where none of these hold, no Virtual Type is created: the declaration's target is simply I's target, reused unchanged (section 9). Where only the TypeDefinition changed and D has no local extension, the target becomes the real overriding type directly, with no Virtual Type at all (section 10).

Example:

```text
VT(PumpType, "Drive")
```

is only created if PumpType's own "Drive" declaration overrides its TypeDefinition, changes something about it, or locally extends it -- not merely because "Drive" is visible in PumpType's Effective Declaration Tree.

---

# 7. Virtual Type Identifiers

Virtual Type identifiers are constructed from:

```text
Owner
+
BrowseName segment (key)
```

where Owner is the real class or enclosing Virtual Type this declaration was found on (section 5), and key is the single, namespace-qualified BrowseName segment -- not the full multi-level BrowsePath.

The Owner+key pair may be replaced by a stable hash. The implementation hashes exactly the `Owner|key` string (SHA-256, first 96 bits / 24 hex digits) and namespaces the result under Owner's own namespace -- but does not additionally prefix the hash with Owner's own local name, only with the fixed literal `VT_`.

Example:

```text
VT_f8a92d1c519f7a2e20f31b6d
```

A minimum of 96 bits (24 hexadecimal digits) is recommended.

The original BrowseName segment shall remain accessible as metadata -- one segment per Virtual Type, not the full multi-level path (section 5).

Example:

```ttl
sb:originalBrowsePath
    "Motor"
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

Where a Virtual Type is actually minted (section 6), it inherits along two independent dimensions:

1. OPC UA type inheritance
2. OPC UA declaration type definition

As a result, the resulting OWL model naturally becomes a multiple-inheritance hierarchy.

Where a subtype's declaration is a pure, unchanged pass-through of what it inherited, *no* Virtual Type is minted for it at all: the real `T rdfs:subClassOf S` edge already propagates S's restriction on that BrowsePath to T for free, so a subtype-specific Virtual Type would only duplicate what plain OWL subsumption already gives for nothing.

---

## Rule

If:

```text
T <: S
```

and BrowsePath P is present in T's Effective Declaration Tree only because it minted its own Virtual Type there (section 6) -- not merely because P is visible in T's Effective Declaration Tree at all -- and P is *also* present as a minted Virtual Type in S's tree:

generate:

```ttl
VT(T,P)
    rdfs:subClassOf
        VT(S,P) .
```

If T's own declaration at P needed no Virtual Type (nothing changed relative to S), T simply reuses `VT(S,P)` (or S's own real type, if S needed no Virtual Type there either) as its own target directly -- no new class is created for T at P.

---

## Example

```text
BaseType
  Motor

PumpType <: BaseType

AdvancedPumpType <: PumpType
```

Since neither `PumpType` nor `AdvancedPumpType` says anything new about `Motor`, this produces **no** Virtual Type for `Motor` at either level: both simply inherit `BaseType`'s restriction on `Motor` via the ordinary `rdfs:subClassOf` edge.

---

# 10. Declaration Override Rule

## Plain Object Override (No Virtual Type)

```text
BaseType
  Motor : MotorType

PumpType <: BaseType
  Motor : AdvancedMotorType
```

If `AdvancedMotorType` is a genuine, independently-declared OWL subtype of `MotorType` and PumpType's own "Motor" declaration adds no local structure of its own, **no Virtual Type is minted** for either level:

```ttl
PumpType
    rdfs:subClassOf [ owl:onProperty sb:hasMotor ; owl:allValuesFrom AdvancedMotorType ] ,
                    [ owl:onProperty sb:hasMotor ; owl:minQualifiedCardinality 1 ; owl:onClass AdvancedMotorType ] .
```

The restriction targets `AdvancedMotorType` directly. Consistency with `BaseType`'s own restriction on "Motor" is guaranteed by the real class hierarchy alone (`AdvancedMotorType rdfs:subClassOf MotorType`) -- OPC UA only allows overriding a component with a genuine subtype of the original TypeDefinition, so a plain Object override of this kind can never be structurally contradictory in the first place; there is nothing for a Virtual Type to usefully add here.

---

## Overrides That Require a Virtual Type

A Virtual Type is required wherever section 6's criteria are met -- a Variable's TypeDefinition/ValueRank/Datatype changes, or the declaration carries its own local structure beyond its nominal type. In that case both edges are asserted simultaneously on the newly minted type:

```ttl
PumpType_Motor
    rdfs:subClassOf AdvancedMotorType ;    -- §8, the override
    rdfs:subClassOf BaseType_Motor .       -- §9, the inherited declaration (itself subClassOf MotorType)
```

This preserves both inherited declaration semantics and overridden type semantics simultaneously, so contradictions (e.g. an overridden ValueRank that is disjoint from the inherited one) become visible to an OWL reasoner. See section 17 for the ValueRank case, which is the primary practical source of genuinely contradictory overrides, since OPC UA's own subtyping rules already rule out contradictory plain TypeDefinition overrides.

---

## Local Structural Extension (Retyping by Addition)

OPC UA also permits a declaration to keep its nominal TypeDefinition unchanged while locally adding its own extra children -- "retyping by addition" rather than "retyping by substitution" (the `LiveValues` pattern under `PubSubDiagnosticsDataSetWriterType` in the OPC UA core nodeset is a real occurrence). This, too, requires a Virtual Type, even though no TypeDefinition/ValueRank/Datatype changed:

```ttl
PumpType_Sensor
    rdfs:subClassOf SensorType ;             -- §8, unchanged nominal type
    rdfs:subClassOf [ owl:onProperty sb:hasExtraDiagnostic ; owl:allValuesFrom ... ] .
```

Since this local structure exists only under this specific declaration, minting must propagate along the *entire* containment path down to the extension, not only at the level where the extra structure physically appears -- a parent whose own declaration has no local structure of its own but whose child does must still get its own Virtual Type, purely to attach the restriction that reaches the child's Virtual Type. Otherwise the extension would either be unexpressible or would leak onto every other, unrelated usage of the same nominal type.

---

# 11. Recursive Expansion

Virtual Type generation processes the Effective Declaration Tree recursively, but recursion is need-based (section 6), not exhaustive: it descends into a declaration's own nested structure only where a Virtual Type was actually minted for it.

Example:

```text
PumpType
 └─ Drive : DriveType (unchanged)
      └─ Motor : MotorType (unchanged)
           └─ Temperature : Double (Variable, always its own Virtual Type)
```

Since "Drive" and "Motor" are plain, unextended Object declarations, this creates only:

```text
VT(MotorType, "Temperature")
```

with `PumpType`'s restriction on "Drive" pointing directly at `DriveType`, and `DriveType`'s own restriction on "Motor" pointing directly at `MotorType` -- neither "PumpType_Drive" nor "PumpType_Drive_Motor" is created at all. Had "Drive" instead overridden its TypeDefinition, or carried its own local extension, the same recursive minting would continue into it, producing a Virtual Type at that level and, from there, at every level further down that itself requires one (section 10).

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

Declaration semantics are attached to the owning class (a real type, or the enclosing Virtual Type one level up) through OWL restrictions, generated only where the target of the declaration is written (i.e. wherever section 6/9/10 actually change or introduce a target).

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
        owl:allValuesFrom PumpType_Motor
    ] .
```

This expresses:

```text
PumpType hasMotor only PumpType_Motor
```

`owl:someValuesFrom` is deliberately never generated **on this containment property**: under OWL 2 semantics `hasMotor some C` is logically equivalent to `owl:minQualifiedCardinality(1, hasMotor, C)` without the unique name assumption, so for a Mandatory declaration it would be pure redundancy with the cardinality restriction (section 16); for an Optional declaration it would be outright wrong, since it would wrongly force every instance to have the relationship, contradicting "optional" (which must permit zero occurrences).

This reasoning is specific to containment properties, where "the relationship exists at all" genuinely varies by ModellingRule. It does **not** extend to the ValueRank/Datatype relationships (sections 17/18): those describe OPC UA Attributes that are Mandatory and single-valued for every real Variable/VariableType regardless of ModellingRule, so `someValuesFrom` is simply true there, not an overreach -- see sections 17/18 for why it is required precisely to make an incompatible override detectable as a genuine contradiction.

---

# 14. Universal Restrictions

The restriction in section 13 is applied unconditionally, regardless of ModellingRule -- it holds vacuously when the property has zero values, which is exactly what makes it correct for Optional declarations too (section 16).

---

# 15. Combining Restrictions

Where the declaration is Mandatory (or Mandatory Placeholder), the universal restriction (section 13/14) and the cardinality restriction (section 16) are both generated simultaneously on the same owner:

```ttl
PumpType
    rdfs:subClassOf
       (hasMotor only PumpType_Motor) ,
       (hasMotor min 1 PumpType_Motor) .
```

This produces:

```text
PumpType hasMotor exactly members of the Virtual Type hierarchy, at least once.
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

## Mandatory Placeholder / Optional Placeholder

OPC UA also defines two Placeholder variants of the same two ModellingRules, used where a declaration is a naming *template* rather than a single fixed BrowseName (e.g. an array of like-typed children whose actual names are only fixed at instantiation time).

For the purposes of this transformation, `MandatoryPlaceholder` is treated identically to `Mandatory` (cardinality restriction generated) and `OptionalPlaceholder` identically to `Optional` (no cardinality restriction) -- the placeholder aspect itself (that the declaration serves as a template rather than a single fixed instance) is recorded but does not otherwise change the restrictions generated for it.

---

# 16a. Declarations Without a Recognized ModellingRule

**Status: unresolved -- documents current behavior, not a settled rule.**

OPC UA permits a child to be aggregated (via `HasComponent`/`HasProperty` or another `HasChild` subproperty) with no ModellingRule reference at all. The most common real occurrence is the set of named States/Transitions inside a StateMachineType-derived type (e.g. `ExclusiveLimitStateMachineType`'s `"High"`, `"HighToHighHigh"`, ...): these are fixed, always-present members of the state machine's structure, closer in spirit to enum members than to an Optional-or-Mandatory instantiation choice, but OPC UA gives them no formal ModellingRule to hang that distinction on.

## Current Behavior

Two modes exist, selected by `require_modelling_rule` (`owl2virtualtypes.py --require-modelling-rule`; `virtual_type_stats.py`'s `--include-unruled` is its inverse):

- **Default (`require_modelling_rule=False`)**: an unruled child is processed exactly like any other declaration -- Virtual Type minted if section 6's criteria are met, `allValuesFrom` restriction generated (section 13/14). Since it has no ModellingRule, it can never be classified `is_optional=False`, so it never receives a cardinality restriction (section 16) either -- cardinality-wise it is treated exactly like `Optional`, even though conceptually it is always present, unconditionally, in every instance of the type.
- **`require_modelling_rule=True`**: an unruled child is skipped entirely -- no Virtual Type, no restriction, and nothing nested inside it is visited either (the whole subtree beneath it is pruned). This is the strict, ModellingRule-literal reading of "Instance Declaration."

## Open Question

Neither mode is a considered, correct representation of what these children actually are: the default mode under-constrains them (silently equivalent to Optional, when they are in fact never absent), and the strict mode drops them from the model entirely (losing real structure, e.g. a StateMachineType's actual states). A more faithful treatment would likely need a third category -- "always present, no ModellingRule choice involved" -- with its own cardinality treatment (closer to Mandatory than to Optional), but this has not been designed or agreed yet. Flagged here for further discussion rather than resolved.

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

`ValueRank_Scalar`, `ValueRank_OneDimension` and `ValueRank_MoreDimensions` are the only three *leaves* of this vocabulary and shall be declared pairwise disjoint (`owl:AllDisjointClasses`). The others (`ValueRank_Any`, `ValueRank_ScalarOrOneDimension`, `ValueRank_OneOrMoreDimensions`) are common ancestors of one or more leaves, not disjoint from anything -- they exist only to express OPC UA's own wildcard ValueRank codes (-3/-2/0). Without the leaf disjointness axiom, no OWL reasoner has anything to derive a contradiction from in the first place; this is what makes a ValueRank-axis override the primary practical source of genuinely detectable contradictions (section 10).

---

## Rule

ValueRank is a Mandatory, single-valued OPC UA Attribute of every Variable and VariableType -- something a declaration *has*, not a category it *is a member of*. It is therefore attached via a relationship, `sb:hasValueRank`, declared `owl:FunctionalProperty` (at most one value), exactly mirroring how Datatype is attached (section 18) -- **not** via a direct `rdfs:subClassOf` onto the symbolic class itself.

Both `owl:allValuesFrom` and `owl:someValuesFrom` are generated on `sb:hasValueRank`, unlike the containment property (section 13): `someValuesFrom` is simply true here (a real Variable always has a ValueRank), and it is exactly what makes an incompatible override actually unsatisfiable -- `FunctionalProperty` plus two disjoint `someValuesFrom` fillers (this declaration's own, and an inherited/ancestor one, section 9/10) forces the single permitted value to belong to both disjoint leaves at once.

Example:

```ttl
PumpType_Temperature
    rdfs:subClassOf
        [ a owl:Restriction ; owl:onProperty sb:hasValueRank ; owl:allValuesFrom opcua:ValueRank_Scalar ] ,
        [ a owl:Restriction ; owl:onProperty sb:hasValueRank ; owl:someValuesFrom opcua:ValueRank_Scalar ] .
```

---

## Own-Type ValueRank

A VariableType (not only an instance declaration typed by it) may itself explicitly declare a ValueRank on its own definer node -- an attribute of the type itself, orthogonal to any instance declaration's own ValueRank where this type happens to be the TypeDefinition. Where explicitly present, this rule attaches the same relationship directly to the VariableType class:

```ttl
SomeVariableType
    rdfs:subClassOf
        [ a owl:Restriction ; owl:onProperty sb:hasValueRank ; owl:allValuesFrom opcua:ValueRank_OneDimension ] ,
        [ a owl:Restriction ; owl:onProperty sb:hasValueRank ; owl:someValuesFrom opcua:ValueRank_OneDimension ] .
```

Without this, an instance declaration whose explicit ValueRank is incompatible with its own TypeDefinition's explicitly-declared ValueRank could never surface as a contradiction: the instance's Virtual Type would be `rdfs:subClassOf` that VariableType (section 8), but the VariableType itself would carry no ValueRank relationship at all for a reasoner to conflict with. Only fires where the type's own definer node explicitly declares a ValueRank -- not the default-when-absent case (Scalar) -- since asserting it unconditionally on every VariableType regardless of whether it says anything about ValueRank would be a much larger, unverified change in scope.

---

# 18. Datatype Constraints

Datatype is likewise a Mandatory, single-valued OPC UA Attribute of every Variable and VariableType, attached via a relationship, `sb:hasDataType`, declared `owl:FunctionalProperty`, with both `owl:allValuesFrom` and `owl:someValuesFrom` generated -- for the same reason as section 17's ValueRank case: a real Variable always has a Datatype, and `someValuesFrom` is what makes an incompatible override (e.g. narrowing to an unrelated sibling Datatype instead of a genuine subtype) actually unsatisfiable rather than vacuously satisfiable by a Datatype-less instance.

Datatypes are OPC UA classes already present in the type hierarchy (section 3); sibling Datatypes under a common parent (2 or more direct subtypes of the same DataType, where at least one is newly declared) shall be declared pairwise disjoint (`owl:AllDisjointClasses`), the same role section 17's ValueRank leaves play, and for the same reason: without it, there is nothing for a Datatype override to conflict with.

Example:

```text
Temperature : Double
```

becomes, associated with `PumpType_Temperature`:

```ttl
PumpType_Temperature
    rdfs:subClassOf
        [ a owl:Restriction ; owl:onProperty sb:hasDataType ; owl:allValuesFrom opcua:Double ] ,
        [ a owl:Restriction ; owl:onProperty sb:hasDataType ; owl:someValuesFrom opcua:Double ] .
```

Datatype handling is orthogonal to Virtual Type generation.

## Own-Type Datatype

As with ValueRank (section 17), a VariableType may itself explicitly declare a Datatype on its own definer node, attached the same way, directly on the VariableType class, subject to the same explicit-only scoping.

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
- universal restrictions (`allValuesFrom`) on containment properties -- `someValuesFrom` is deliberately not used there (section 13)
- cardinality restrictions on containment properties
- ValueRank/Datatype relationships (`sb:hasValueRank`/`sb:hasDataType`, both `owl:FunctionalProperty`), each with both `allValuesFrom` and `someValuesFrom` (sections 17/18) -- unlike containment, `someValuesFrom` is required here to make an incompatible override actually unsatisfiable
- symbolic ValueRank classes, with the three leaves pairwise disjoint
- sibling Datatypes pairwise disjoint, the Datatype-axis counterpart of the ValueRank leaves

The ontology contains no Instance Declarations and can be processed by standard OWL DL reasoners for consistency and satisfiability checking.