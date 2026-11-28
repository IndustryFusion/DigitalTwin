# Spec Delta

## MODIFIED Requirements

### Requirement: One command for the resync
The resync SHALL run from one command in shacl2flink, on the deployed validation, in these steps, each after the previous completed: mark the validation degraded, stop the job if a replacement is asked for, close the SHACL alerts, reset Core Services, install the new package if the replacement is by a new package, start the stopped job or the new package's job, trigger a complete re-snapshot, wait until it is processed, end the degraded state. It SHALL report each step's start and end.

#### Scenario: Without replacing the job
- **WHEN** the resync runs without a replacement while the validation runs
- **THEN** its output reports the steps without stopping and starting the job, in this order, each starting after the previous one ended, the validation job has the same job ID afterwards, and the command exits with status 0

#### Scenario: With a fresh job
- **WHEN** the resync runs with a fresh replacement
- **THEN** its output reports every step except the install, in this order, the validation job runs with another job ID afterwards, and the command exits with status 0

#### Scenario: No validation deployed
- **WHEN** the resync runs without a replacement by a new package while no validation statementset is deployed
- **THEN** it exits with a non-zero status before the first step, its message says to deploy the validation first, and no alert has been changed

### Requirement: A fresh job replays nothing
With a fresh replacement or a replacement by a new package, the resync SHALL stop the validation job and, before a new job starts, remove every record from the topics the job writes and reads back: those of `constraint_table`, `constraint_combination_table` and `constraint_trigger_table`. It SHALL delete no topic and remove no record from any other topic. With a fresh replacement the new job SHALL run the deployed statementset unchanged, with a new package the package's statementset.

#### Scenario: A raise of the previous job
- **GIVEN** a raise in `constraint_trigger_table`, written before the resync, for a constraint that is satisfied now
- **WHEN** a resync with a fresh job or with a new package has completed
- **THEN** none of the three topics holds a record written before the job was stopped, and no alert is open for that resource and constraint

#### Scenario: Topics kept
- **WHEN** a resync with a fresh job or with a new package runs
- **THEN** every KafkaTopic resource exists throughout with the same topic ID in Kafka, and a record written to `iff.ngsild.entities` before the resync can still be read afterwards

### Requirement: A failed resync stops
When a step fails or does not complete within its time limit, the resync SHALL stop without starting a later step, exit with a non-zero status, name the step, and leave `ValidationConsistency` critical, naming that step, until a later resync completes.

#### Scenario: Alerta unreachable
- **WHEN** Alerta can't be reached during the close step
- **THEN** the resync exits with a non-zero status, its message names the close step, Core Services runs the same job as before, and `ValidationConsistency` is critical, naming the close step

#### Scenario: Not processed in time
- **WHEN** a consumer still has records left to read, or the marker has not reached Alerta, when the wait step's time limit has passed
- **THEN** the resync exits with a non-zero status, names the wait step and the consumer or the marker, and `ValidationConsistency` is critical, naming the wait step

## ADDED Requirements

### Requirement: A resync refuses to start
The resync SHALL refuse to start while another resync runs or `iff.alerts` has more than one partition.

#### Scenario: Another resync running
- **WHEN** the resync runs while another resync is marked as running and its time limit has not passed
- **THEN** it exits with a non-zero status before the first step, its message names the running resync and its step, and no alert, job or mark has been changed

#### Scenario: More than one partition of iff.alerts
- **WHEN** the resync runs while `iff.alerts` has more than one partition
- **THEN** it exits with a non-zero status before the first step, its message names the number of partitions, and no alert, job or mark has been changed

### Requirement: A stopped validation names the command that completes it
If the job was stopped and not started again, the message SHALL say that the validation doesn't run and name the command: for a replacement by a new package the deploy of that package, for the others the resync. Running that command again SHALL complete it.

#### Scenario: Failed while the job is stopped
- **WHEN** a resync with a fresh job fails after the job was stopped and before it was started
- **THEN** its message says that the SHACL validation doesn't run and names the command to run again

#### Scenario: Failed while the job of a new package is stopped
- **WHEN** a resync with a new package fails after the job was stopped and before the new package's job was started
- **THEN** its message says that the SHACL validation doesn't run and names the deploy of the package as the command to run again, not a resync with a fresh job

#### Scenario: Run again
- **WHEN** the resync is run again after a failed step, with the cause removed
- **THEN** it completes every step, exits with status 0, and `ValidationConsistency` is normal afterwards unless the watchdog keeps an inconsistency

### Requirement: Replace the validation by a new package
The resync SHALL accept, as a third kind of replacement, the replacement of the validation by a new package. It SHALL run as with a fresh job, with the install step between resetting Core Services and starting the job: install the new package, which writes its constraint and knowledge tables and creates its statementset, also when the package's chart equals the one installed before. Its time limit SHALL include the install step.

#### Scenario: A new package over a running validation
- **WHEN** a resync with a new package runs while a validation job runs
- **THEN** its output reports the steps in this order: mark, stop, close, reset, install, start, re-snapshot, processed, end. The tables were written only after the old job was stopped, the validation runs with another job ID and the new package's statements, and the command exits with status 0

#### Scenario: A package whose chart is unchanged
- **WHEN** a resync with a new package runs whose statementset and chart equal the deployed ones and whose knowledge table differs
- **THEN** the install step creates the statementset again after the stop deleted it, and the new job runs

#### Scenario: The install fails
- **WHEN** the install step of a resync with a new package fails
- **THEN** the resync exits with a non-zero status naming the install step, and the watchdog reports the resync as failed in that step until a later resync completes

### Requirement: The new package's job is started, not the stopped one
With a new package, the start step SHALL wait for the statementset the install created and for its job, and SHALL NOT create the stopped statementset again; a stopped statementset kept by an earlier failed resync SHALL be discarded and SHALL NOT refuse the run. With no statementset deployed, the resync SHALL skip the stop step and run the others.

#### Scenario: The started statementset
- **WHEN** a resync with a new package has completed over a running validation
- **THEN** the deployed statementset is the new package's, and no stopped statementset is kept for a later start

#### Scenario: After a failed resync with a fresh job
- **WHEN** a resync with a fresh job failed after its stop, and a resync with a new package runs next
- **THEN** it runs, installs and starts the new package, and the kept statementset of the failed resync is gone afterwards

#### Scenario: A new package with no validation deployed
- **WHEN** a resync with a new package runs while no validation statementset is deployed
- **THEN** it skips the stop step, installs the package and starts its job, and exits with status 0
