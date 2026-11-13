# Delta for shacl2flink Flink SQL Validation

## Purpose

Defines how the Flink SQL that shacl2flink generates is validated by Flink
before it is deployed: what is validated and against which Flink, what a
rejection reports, how a package is checked at build time, and how a
deployment refuses statements that Flink would reject, without stopping the
job that is running.

## ADDED Requirements

### Requirement: Flink validates what a deployment would run
Validation SHALL have Flink parse and plan everything a statement set's deployment runs: its SQL settings, the DDL of its tables and views, and every statement of the statement set, as one unit in deployment order. It SHALL use the Flink version, connectors and user-defined functions that the platform's SQL Gateway deploys with. It SHALL NOT start a job, and SHALL NOT connect to Kafka, a database or the Flink cluster.

#### Scenario: A statement Flink rejects
- **WHEN** a statement set holds a statement that Flink's parser rejects, such as a `POSITION` whose first operand is a `||` concatenation
- **THEN** validation fails, naming that statement (its position and its text) and giving Flink's error message

#### Scenario: A statement Flink cannot plan
- **WHEN** a statement parses but refers to a column, table or function that is not defined
- **THEN** validation fails, naming the statement and giving Flink's error message

#### Scenario: A valid statement set
- **WHEN** the statements of `kms/default` are validated
- **THEN** validation passes, no job is started, and no Kafka topic or database is read or written

#### Scenario: User-defined functions
- **WHEN** a statement calls one of shacl2flink's user-defined functions
- **THEN** validation knows the function, as the deployment does, and passes

### Requirement: A package's statements are validated at build time
shacl2flink SHALL provide a `make` target that validates the statement sets a package compiles to, rendered as they would be deployed: the resources of the `shacl` chart with its default values, and the core tables of the `sql-core` chart they use, composed into requests the way the operator composes them. The target SHALL exit with an error when a statement set does not validate. The `Build` workflow SHALL run it for every package it compiles, and for the package the K8s tests deploy.

#### Scenario: A broken template fails the build
- **WHEN** a change makes a template render a statement that Flink rejects
- **THEN** the `make` target fails, naming the statement set, the statement and Flink's message, and the `Build` workflow fails before any deployment

#### Scenario: The same statements as the deployment
- **WHEN** the target validates a package
- **THEN** the requests it validates are the ones the operator would send for the same rendered resources

#### Scenario: Runtime
- **WHEN** the target validates `kms/default` in the `Build` workflow
- **THEN** it takes less than five minutes

### Requirement: A deployment refuses statements Flink rejects
Before it cancels a statement set's running job or submits the statement set, the operator SHALL have it validated. When validation fails, the operator SHALL NOT cancel the running job and SHALL NOT submit the statement set; the statement set's status SHALL state that validation failed and carry Flink's message. The operator SHALL NOT validate or submit the same statements again until the statement set changes.

#### Scenario: An update Flink rejects
- **WHEN** a running statement set is updated with statements that do not validate
- **THEN** its job keeps running, nothing is submitted, and its status shows the validation failure with Flink's message

#### Scenario: A new statement set Flink rejects
- **WHEN** a statement set that does not validate is created
- **THEN** no job is started and its status shows the validation failure with Flink's message

#### Scenario: A valid update
- **WHEN** a running statement set is updated with statements that validate
- **THEN** it is deployed as before this change: the old job is cancelled and the new statements are submitted

#### Scenario: Fixed after a rejection
- **WHEN** a statement set whose validation failed is changed to statements that validate
- **THEN** it is validated again and deployed
