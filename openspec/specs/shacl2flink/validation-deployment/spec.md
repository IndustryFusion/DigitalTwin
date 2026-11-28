# shacl2flink/validation-deployment Specification

## Purpose
Defines what deploying a SHACL validation guarantees, fresh or over a running one: the job reads each constraint row once, the deployed statements and the constraint tables belong to the same package, and the SHACL alerts match what the deployed validation finds.

## Requirements

### Requirement: The fingerprint of a deployment
The deploy SHALL compute a fingerprint of the validation as it would be deployed: the rendered statementset, its statements and table definitions, the platform values rendered into them, and the contents of the constraint tables and the knowledge table. Two renderings of the same package with the same values SHALL have the same fingerprint, and a change to any statement, rendered value, constraint row or knowledge row SHALL change it.

#### Scenario: The same package rendered twice
- **WHEN** a package is built and rendered twice without a change to its shapes, knowledge, the compiler or the platform values
- **THEN** both renderings have the same fingerprint

#### Scenario: A changed package or value
- **WHEN** a package is rendered again after one constraint, one knowledge triple, one generated statement or one rendered platform value changed
- **THEN** the new rendering has another fingerprint

### Requirement: The fingerprint is kept only for a consistent validation
The deploy SHALL keep the fingerprint in the cluster, readable with the cluster's API alone, together with the ID of the validation job it was written for, and SHALL write it only after the deployment, its alert resync included, has completed. A fingerprint kept for another job SHALL count as none, and a failed or interrupted deploy SHALL leave none of the new package. Keeping it SHALL NOT change the validation job.

#### Scenario: After a completed deploy
- **WHEN** a deploy has completed
- **THEN** the cluster holds the fingerprint of what was deployed and the ID of the running validation job, and the job has the same ID as before the fingerprint was written

#### Scenario: A fingerprint of another job
- **WHEN** the validation job was replaced by other means after a deploy, e.g. by a resync with a fresh job, and the same package is deployed again
- **THEN** the deploy replaces the validation, as the kept fingerprint belongs to another job

#### Scenario: After an interrupted deploy
- **WHEN** a deploy that replaces the validation is interrupted after the new statementset was created and before its resync completed, and the same package is deployed again
- **THEN** the second deploy replaces the validation again, and afterwards the SHACL alerts are those of a fresh deployment

### Requirement: The same package over a running validation rewrites nothing
When the validation job runs with all its tasks and the fingerprint kept for that job equals the fingerprint of the validation being deployed, the deploy SHALL NOT write the constraint tables or the knowledge table, and SHALL NOT replace the validation job. The job SHALL read every constraint row exactly once, and its verdicts SHALL stay as they were.

#### Scenario: Deploying the same package again
- **WHEN** a package is deployed, its job runs, and the same package is deployed again over it
- **THEN** the validation job has the same job ID, its source of each constraint table has emitted as many rows as the table holds, and every count verdict reports the same number as before the second deploy

#### Scenario: Deploying the same package three times
- **WHEN** the same package is deployed a third time over the running job
- **THEN** each constraint row is still read once, and no relationship count reports more relationships than the entity has

### Requirement: Anything else replaces the validation
When the kept fingerprint differs from the deployed one, when none is kept for the running job, or when no validation job runs with all its tasks, the deploy SHALL replace the validation by the new package through the resync's replacement by a new package. The constraint tables and the knowledge table SHALL be written only after the old job has stopped, and no Kafka topic SHALL be deleted.

#### Scenario: A changed package over a running validation
- **WHEN** a package is deployed, its job runs, and a changed package is deployed over it
- **THEN** the validation job runs with another job ID and the new package's statements, its source of each constraint table has emitted as many rows as the table holds, and every KafkaTopic resource keeps its topic ID

#### Scenario: A validation without a fingerprint
- **WHEN** a package is deployed over a running validation for which the cluster keeps no fingerprint
- **THEN** the deploy replaces the validation as for a changed package

#### Scenario: The resync cannot run
- **WHEN** the deploy has to replace the validation and a precondition of the resync is not met, such as another resync running
- **THEN** the deploy exits with a non-zero status naming the precondition, and the running job, the tables and the alerts are as they were

### Requirement: After a replacement the alerts are those of a fresh deployment
After the deploy replaced the validation, the SHACL alerts that are not closed SHALL be those a fresh deployment of the package raises for the current entities.

#### Scenario: Alerts after a changed package
- **WHEN** a changed package has replaced a running validation
- **THEN** the open SHACL alerts are those the new package raises for the current entities, and none that only the old package raised is open

#### Scenario: Relationship counts after a changed package
- **WHEN** a running validation has raised relationship-count alerts for two entities, and a changed package is deployed over it under which one of the entities satisfies its count and the other still violates it
- **THEN** after the deploy the alert of the first entity is closed and the alert of the second is open, with the number of relationships the entity has

#### Scenario: No validation running
- **WHEN** a package is deployed while no validation job runs, and an alert of a previous validation is still open for a constraint the current entities satisfy
- **THEN** after the deploy that alert is closed, and the open SHACL alerts are those the package raises for the current entities

#### Scenario: A knowledge triple removed by a new package
- **WHEN** a package whose knowledge lacks a triple of the running package's knowledge replaces the validation
- **THEN** after the deploy the knowledge the validation reads no longer has that triple, and the knowledge the validation reads is exactly the new package's knowledge

#### Scenario: The same knowledge again
- **WHEN** a package with the same knowledge as the running package replaces the validation
- **THEN** no knowledge triple is removed from what the validation reads

### Requirement: Kafka Connect is restarted only once the deployed job reads
In both cases, the deploy SHALL restart Kafka Connect only after the deployed validation job reads the entity and attribute topics, and SHALL report which job it waited for.

#### Scenario: Restart after a replacement
- **WHEN** a changed package replaces a running validation, and the operator acts on the new statementset only after a delay
- **THEN** the newest Kafka Connect pod was created after the new job started, there was no other Connect restart after that, and the new job reads the entities that restart published

#### Scenario: Restart over an unchanged validation
- **WHEN** the same package is deployed over the running validation
- **THEN** Kafka Connect is restarted after the deploy found the running job reading, and the deploy's output names that job's ID
