# Spec Delta

## Purpose

Defines how the SemForge SDK and its editor report the results of a node shape that a shape applies to the object of a relationship: where the violation belongs, how its cause is shown, and when such a node shape counts as reached.

## ADDED Requirements

### Requirement: The violation belongs to the referring entity's relationship
A violation of a node shape applied to a relationship's object SHALL be reported on the referring entity's relationship attribute, with the constraint identity of the referring shape, the relationship and the node constraint. An expectation naming this identity SHALL be accepted as a constraint that can fire.

#### Scenario: An expectation on the relationship's node constraint
- **GIVEN** a package whose `OwnerType` shape applies a node shape to the object of `hasLink`, and an example whose referenced entity violates it
- **WHEN** the examples are run with an expectation naming `OwnerTypeShape`, `hasLink` and the node constraint for the `OwnerType` entity
- **THEN** the expectation is met, and it is not reported as stale

### Requirement: The cause of the violation is shown
The validation report of the SDK and the editor's display of the violation SHALL show, with the violation, each violated constraint of the node shape: the referenced entity, the attribute and the constraint, with its message.

#### Scenario: The report names the missing attribute
- **GIVEN** a node shape requiring `hasLevel` on the entity referenced by `hasLink`
- **WHEN** the referenced entity `urn:link:1` has no `hasLevel` and the package is validated
- **THEN** the reported violation on the `OwnerType` entity's `hasLink` shows `urn:link:1`, `hasLevel` and the violated minimum count

#### Scenario: The editor shows the cause with the violation
- **GIVEN** the same package open in the editor
- **WHEN** the violation of `hasLink` is shown on the entity's page or in the Problems panel
- **THEN** the shown violation includes the referenced entity, `hasLevel` and the violated constraint

### Requirement: A node shape reached through a relationship counts as reached
A node shape without a target of its own that a shape applies to the object of a relationship SHALL count as reached by the entities whose relationships reach it, and SHALL NOT be shown as never reached or never fired while such entities exist.

#### Scenario: The shape page lists what reaches the node shape
- **GIVEN** a package with an `OwnerType` entity whose `hasLink` refers to an entity that the node shape constrains
- **WHEN** the shape page of the node shape is opened
- **THEN** it shows the referenced entity as reached through `OwnerTypeShape` and `hasLink`, and does not say that no case reaches it
