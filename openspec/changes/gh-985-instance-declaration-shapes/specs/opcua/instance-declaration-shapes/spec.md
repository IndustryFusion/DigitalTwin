# Spec Delta

## Purpose

Defines how the SHACL shapes generated from an OPC UA information model validate the members that a child's instance declaration adds beyond what the child's own type defines, so that everything a type defines is validated.

## ADDED Requirements

### Requirement: Additions of a child declaration are validated through the relationship
When an object child declaration of a type declares members that its own type, including the type's supertypes, does not define, the generated shapes SHALL constrain the entity referenced by that child's relationship with a node shape for the declaration. The node shape SHALL have no target of its own and SHALL be applied through the relationship's object.

#### Scenario: A mandatory added variable is required on the referenced entity
- **GIVEN** an `OwnerType` with a mandatory child `Link` declared as `BaseObjectType`, whose declaration adds a mandatory variable `Level` of data type Double
- **WHEN** the shapes are generated and an `OwnerType` entity's `hasLink` relationship refers to an entity without `hasLevel`
- **THEN** validation reports a violation on the `OwnerType` entity for its `hasLink` attribute

#### Scenario: The referenced entity satisfies the declaration
- **GIVEN** the same model
- **WHEN** the entity referenced by `hasLink` has `hasLevel` with a Double value
- **THEN** validation reports no violation for `hasLink`

### Requirement: The node shape follows the declaration's members
The node shape SHALL constrain each added member as a member of the same kind defined by a type is constrained: a mandatory member SHALL be required, an optional member SHALL NOT be required, and an added variable SHALL be constrained by its data type and value rank.

#### Scenario: An optional added member may be absent
- **GIVEN** a declaration that adds an optional variable `Note`
- **WHEN** the referenced entity has no `hasNote`
- **THEN** validation reports no violation for it

#### Scenario: An added variable with the wrong data type is reported
- **GIVEN** a declaration that adds a variable `Level` of data type Double
- **WHEN** the referenced entity's `hasLevel` holds a string
- **THEN** validation reports a violation on the owning entity for its relationship

### Requirement: Placeholder members added by a declaration are constrained per instance
A placeholder member that a declaration adds SHALL be constrained in the node shape as a placeholder defined by a type is constrained: each instance, identified by its `datasetId`, SHALL be checked on its own, and the count SHALL be the number of distinct `datasetId`s. A mandatory placeholder SHALL require at least one instance.

#### Scenario: One of several instances refers to an entity of the wrong class
- **GIVEN** a declaration of `Link` that adds an optional placeholder `Item<no>` of type `ItemType`
- **WHEN** the referenced `Link` entity has children `Item1` and `Item2`, and only `Item2` is not an `ItemType`
- **THEN** validation reports a violation on the owning entity for its relationship to `Link`, and the `Item1` instance alone would conform

#### Scenario: A mandatory placeholder without instances is reported
- **GIVEN** a declaration of `Mand` that adds a mandatory placeholder `<Part>`
- **WHEN** the referenced `Mand` entity has no instance of it
- **THEN** validation reports a violation on the owning entity for its relationship to `Mand`

### Requirement: Membership of a placeholder is decided by name where the name can decide it
A child of the referenced entity SHALL count as an instance of a placeholder member when its whole browse name matches the placeholder's pattern. If the pattern has a fixed part, the name alone SHALL decide, so that a wrong type is reported. If the whole browse name is the placeholder, a child SHALL count only when its type is the placeholder's type or a subtype.

#### Scenario: A named pattern does not take in other children
- **GIVEN** a declaration of `Link` that adds the placeholder `Item<no>` and the optional object `Inner`
- **WHEN** the referenced `Link` entity has the children `Item1` and `Inner`
- **THEN** only `Item1` is an instance of `Item<no>`, and `Inner` is not checked against `ItemType`

#### Scenario: A fully generic placeholder counts only children of its type
- **GIVEN** a declaration of `Mand` that adds the placeholder `<Part>` of type `ItemType`
- **WHEN** the referenced `Mand` entity has a child `Part1` of type `ItemType` and a child `Other` of another type
- **THEN** only `Part1` is an instance of `<Part>`, and no violation is reported for `Other`

### Requirement: Placeholder membership is documented
The documentation of the OPC UA tools SHALL describe the shapes generated for members that an instance declaration adds, the one-relationship limit and its report, and how placeholder membership is decided, including that for a fully generic placeholder a child of a wrong type cannot be told apart from an unrelated child.

#### Scenario: A reader learns why a wrong-typed child of a generic placeholder is not reported
- **WHEN** a reader looks up placeholders in the documentation of the OPC UA tools
- **THEN** it explains the name-based and the type-based membership, gives an example of each, and states the limitation of fully generic placeholders

### Requirement: The constraints of the child's type still apply
The node shape SHALL be in addition to the constraints of the child's declared type: the referenced entity SHALL also be validated against its type, and the relationship SHALL still require the referenced entity to be of the declared type.

#### Scenario: A violation of the child's own type is reported as before
- **GIVEN** a child declared with a type that requires a variable `Status`, and a declaration that adds a variable `Level`
- **WHEN** the referenced entity has `hasLevel` but no `hasStatus`
- **THEN** validation reports the missing `hasStatus` on the referenced entity, as it does without the addition

### Requirement: Declarations without additions are generated as before
For a child declaration that adds no member beyond its type, the generated shapes SHALL be the same as without this capability.

#### Scenario: No addition, no node shape
- **GIVEN** a child declaration whose members are all defined by its type
- **WHEN** the shapes are generated
- **THEN** no node shape is generated for it, and the owning type's shape is unchanged

### Requirement: Entity types are unchanged
The generated instances SHALL keep the declared type of every child entity; no type SHALL be generated or assigned for a declaration.

#### Scenario: The referenced entity keeps its declared type
- **GIVEN** a child `Link` declared as `BaseObjectType` with an added variable
- **WHEN** the instances are generated
- **THEN** the `Link` entity's type is `BaseObjectType`

### Requirement: Validation stops after one relationship
Members added by a declaration that is reached through more than one relationship from the owning type SHALL NOT be validated. Variables and their properties SHALL NOT count as a relationship.

#### Scenario: An addition two relationships deep is not validated
- **GIVEN** an `OwnerType` whose child `Link` has a child object `Inner`, and the declaration of `Inner` adds a variable `Level`
- **WHEN** the shapes are generated
- **THEN** no shape constrains `hasLevel` of the `Inner` entity

#### Scenario: A property of an added variable does not count as a relationship
- **GIVEN** a declaration of `Link` that adds a variable `Level` with a property `EngineeringUnits` defined by Level's variable type
- **WHEN** the shapes are generated
- **THEN** the node shape for `Link` constrains `hasLevel` and its `hasEngineeringUnits` as for a variable defined by a type

### Requirement: Additions that are not validated are reported once per owning type
The generator SHALL report every owning type that has additions beyond one relationship, once per type, with the number of such declarations and their browse paths. It SHALL NOT report them once per declaration.

#### Scenario: Several deep additions in one type give one report
- **GIVEN** an `OwnerType` with three declarations that add members two relationships deep
- **WHEN** the shapes are generated
- **THEN** the generator's output contains one report for `OwnerType` naming the three browse paths, and no further report for them
