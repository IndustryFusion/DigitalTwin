# shacl2flink/node-shapes-across-relationships Specification

## Purpose
Defines how the streaming validation evaluates a node shape that a shape applies to the object of a relationship, which entity the resulting alert belongs to, and that constraints underneath a relationship's object are never accepted without being evaluated.

## Requirements

### Requirement: A node shape on a relationship's object is evaluated on the referenced entity
When a property shape for a relationship applies a node shape to the relationship's object (`sh:node` on `ngsi-ld:hasObject`), the generated checks SHALL evaluate the constraints of that node shape on the attributes of the entity the relationship refers to.

#### Scenario: A missing attribute of the referenced entity is detected
- **GIVEN** a shape for `OwnerType` whose relationship `hasLink` applies a node shape requiring `hasLevel`
- **WHEN** an `OwnerType` entity's `hasLink` refers to an entity without `hasLevel`
- **THEN** an alert is raised

#### Scenario: The referenced entity conforms
- **GIVEN** the same shape
- **WHEN** the referenced entity has `hasLevel` as the node shape requires
- **THEN** no alert is raised for `hasLink`

### Requirement: The alert belongs to the referring entity
A violation of such a node shape SHALL be raised as one alert on the referring entity per relationship attribute instance, with the event `NodeConstraintComponent(<relationship path>[<index>])`, however many of the node shape's constraints are violated.

#### Scenario: Two violated inner constraints give one alert
- **GIVEN** a node shape requiring `hasLevel` and `hasMode`
- **WHEN** the referenced entity has neither
- **THEN** exactly one alert is open, on the `OwnerType` entity, with the event `NodeConstraintComponent(hasLink[0])`

#### Scenario: Each relationship instance has its own alert
- **GIVEN** an `OwnerType` entity with two `hasLink` instances (datasets) referring to two entities
- **WHEN** only the second referenced entity violates the node shape
- **THEN** one alert is open for the second instance and none for the first

#### Scenario: One violating instance of a placeholder relationship
- **GIVEN** an `OwnerType` entity with a placeholder relationship `hasLink` whose instances have the datasetIds `d1`, `d2` and `d3`
- **WHEN** only the entity referenced by the `d2` instance violates the node shape
- **THEN** exactly one alert is open, for the `d2` instance

### Requirement: The alert text names the path to the cause
The alert text SHALL name the referring entity, the relationship, the referenced entity and every violated constraint of the node shape with the attribute it concerns, so that the path from the alert to the cause can be reconstructed.

#### Scenario: The text leads to the missing attribute
- **GIVEN** a node shape requiring `hasLevel`
- **WHEN** the referenced entity `urn:link:1` has no `hasLevel`
- **THEN** the alert text names the referring entity, `hasLink`, `urn:link:1`, `hasLevel` and the violated minimum count

### Requirement: The alert follows changes of either entity
The alert SHALL be raised and cleared when the referenced entity's attributes change, when the relationship changes to refer to another entity, and when the referenced entity is deleted, in the same way as for changes of the referring entity's own attributes. A deleted or missing referenced entity SHALL be evaluated as an entity without attributes.

#### Scenario: Repairing the referenced entity clears the alert
- **GIVEN** an open alert because the referenced entity lacks `hasLevel`
- **WHEN** `hasLevel` is added to the referenced entity
- **THEN** the alert is cleared

#### Scenario: Deleting the referenced entity raises the alert
- **GIVEN** a node shape requiring `hasLevel` and a conforming referenced entity
- **WHEN** the referenced entity is deleted
- **THEN** an alert is raised on the referring entity

#### Scenario: The alert keeps working after a long quiet period
- **GIVEN** the validation has run longer than three times its configured state retention without any change to the two entities
- **WHEN** the referenced entity loses `hasLevel` and later gets it back
- **THEN** the alert is raised and then cleared

### Requirement: Inner constraints are those supported for an entity's own attributes
The constraints of such a node shape SHALL be evaluated as they are for an entity's own attributes, for every constraint that is supported there. A node shape that itself applies a node shape to the object of a further relationship SHALL be rejected at build time.

#### Scenario: A datatype constraint in the node shape is evaluated
- **GIVEN** a node shape requiring `hasLevel` with values of `xsd:double`
- **WHEN** the referenced entity's `hasLevel` holds a string
- **THEN** an alert is raised on the referring entity

#### Scenario: A count in the node shape counts distinct instances
- **GIVEN** a node shape requiring at least three instances of `hasItem`
- **WHEN** the referenced entity has `hasItem` instances with the datasetId `d1`, without a datasetId, and with the datasetId `d2`, the first two with equal values
- **THEN** no alert is raised, because the default instance counts as an instance of its own

#### Scenario: A second relationship hop is rejected
- **GIVEN** a node shape that applies another node shape to the object of one of the referenced entity's relationships
- **WHEN** the checks are built
- **THEN** the build fails and names the shape

### Requirement: Constraints underneath a relationship's object are never accepted silently
A constraint underneath a relationship's object that the generated checks cannot evaluate SHALL fail the build and name its shape. Only `sh:class` and node shapes as defined by this capability SHALL be accepted there.

#### Scenario: A property shape directly underneath the object fails the build
- **GIVEN** a shape with `sh:property` directly underneath `ngsi-ld:hasObject`
- **WHEN** the checks are built
- **THEN** the build fails and names the shape, instead of producing a check that never raises

### Requirement: SQLite and Flink agree
The checks generated for SQLite and for Flink SHALL raise the same alerts for every scenario of this specification.

#### Scenario: Same alerts in both targets
- **WHEN** the scenarios of this specification are run against the SQLite and the Flink checks
- **THEN** both raise the same alerts with the same events

### Requirement: The supported form is documented
The shacl2flink documentation of supported SHACL features SHALL state that a node shape on a relationship's object is evaluated on the referenced entity, that its alert belongs to the referring entity, that only one relationship is followed, and which constraints are rejected underneath a relationship's object.

#### Scenario: The documentation describes the check
- **WHEN** a reader looks up `sh:node` in the documentation of supported features
- **THEN** it describes the evaluation on the referenced entity, the alert, the one-relationship limit and the rejected forms
