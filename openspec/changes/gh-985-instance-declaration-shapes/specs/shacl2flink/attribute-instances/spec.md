# Spec Delta

## Purpose

Defines how shacl2flink keeps the instances of a multi-instance attribute apart, keyed by their `datasetId`, in the models it builds from NGSI-LD data for its offline checks, and how its checks count these instances.

## ADDED Requirements

### Requirement: Every attribute instance is kept with its own datasetId
The models built from NGSI-LD data SHALL contain every instance of an attribute once, with its own `datasetId`, or as the default instance when it has none. Instances with equal values SHALL NOT be merged, and no instance SHALL be given another instance's `datasetId`. This SHALL hold for properties, relationships, list properties and JSON properties.

#### Scenario: Equal values with and without a datasetId stay apart
- **GIVEN** an entity whose property `hasLevel` has the instances 5 with datasetId `d1`, 5 without a datasetId, and 7 with datasetId `d2`
- **WHEN** the models are built
- **THEN** they contain three instances of `hasLevel`: 5 for `d1`, 5 for the default instance and 7 for `d2`

#### Scenario: Relationships with the same object stay apart
- **GIVEN** an entity whose relationship `hasLink` has two instances referring to the same entity, one with datasetId `d1` and one without a datasetId
- **WHEN** the models are built
- **THEN** they contain both instances, for `d1` and for the default instance

#### Scenario: List and JSON properties stay apart
- **GIVEN** an entity with two instances of a list property and two instances of a JSON property, each pair with equal values, one instance of each pair with datasetId `d1` and one without a datasetId
- **WHEN** the models are built
- **THEN** they contain both instances of each attribute

### Requirement: Counts count distinct instances
A count constraint SHALL count the distinct instances of an attribute, the default instance included.

#### Scenario: Three instances satisfy a minimum count of three
- **GIVEN** a shape requiring at least three instances of `hasLevel`
- **WHEN** the entity has the three instances of the first scenario
- **THEN** the offline checks raise no alert for `hasLevel`

### Requirement: Offline checks and pyshacl agree on instances
For every scenario of this specification, the offline checks SHALL report the same results as pyshacl on the same data.

#### Scenario: No divergence for equal values across instances
- **WHEN** the scenarios of this specification are compared with pyshacl
- **THEN** no divergence is reported
