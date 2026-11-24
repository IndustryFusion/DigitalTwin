# shacl2flink/alert-resync Specification

## Purpose
Defines how one command brings the SHACL alerts in Alerta in line with what the validation finds now, whether the validation job was started fresh, restored or kept running before, when the resync counts as processed, and how the platform shows the validation as degraded while it runs.

## Requirements

### Requirement: One command for the resync
The resync SHALL run from one command in shacl2flink, on the deployed validation, in these steps, each after the previous completed: mark the validation degraded, stop the job if a replacement is asked for, close the SHACL alerts, reset Core Services, start the stopped job, trigger a complete re-snapshot, wait until it is processed, end the degraded state. It SHALL report each step's start and end, and refuse to start while another resync runs or `iff.alerts` has more than one partition.

#### Scenario: Without replacing the job
- **WHEN** the resync runs without a replacement while the validation runs
- **THEN** its output reports the steps without stopping and starting the job, in this order, each starting after the previous one ended, the validation job has the same job ID afterwards, and the command exits with status 0

#### Scenario: With a fresh job
- **WHEN** the resync runs with a fresh replacement
- **THEN** its output reports every step in this order, the validation job runs with another job ID afterwards, and the command exits with status 0

#### Scenario: No validation deployed
- **WHEN** the resync runs while no validation statementset is deployed
- **THEN** it exits with a non-zero status before the first step, its message says to deploy the validation first, and no alert has been changed

#### Scenario: Another resync running
- **WHEN** the resync runs while another resync is marked as running and its time limit has not passed
- **THEN** it exits with a non-zero status before the first step, its message names the running resync and its step, and no alert, job or mark has been changed

#### Scenario: More than one partition of iff.alerts
- **WHEN** the resync runs while `iff.alerts` has more than one partition
- **THEN** it exits with a non-zero status before the first step, its message names the number of partitions, and no alert, job or mark has been changed

### Requirement: A fresh job replays nothing
With a fresh replacement, the resync SHALL stop the validation job and, before a new job starts, remove every record from the topics the job writes and reads back: those of `constraint_table`, `constraint_combination_table` and `constraint_trigger_table`. It SHALL delete no topic and remove no record from any other topic. The new job SHALL run the deployed statementset unchanged.

#### Scenario: A raise of the previous job
- **GIVEN** a raise in `constraint_trigger_table`, written before the resync, for a constraint that is satisfied now
- **WHEN** a resync with a fresh job has completed
- **THEN** none of the three topics holds a record written before the job was stopped, and no alert is open for that resource and constraint

#### Scenario: Topics kept
- **WHEN** a resync with a fresh job runs
- **THEN** every KafkaTopic resource exists throughout with the same topic ID in Kafka, and a record written to `iff.ngsild.entities` before the resync can still be read afterwards

### Requirement: Restore from a checkpoint
The resync SHALL accept, as the other kind of replacement, a restore of the validation job from a checkpoint or savepoint given by its path, which keeps the job's topics as they are. As long as the platform can't start the statementset from a given checkpoint, the resync SHALL refuse this option before its first step and name what is missing.

#### Scenario: Not supported yet
- **WHEN** the resync is run with a restore from a checkpoint on a platform that can't start the statementset from one
- **THEN** it exits with a non-zero status before the first step, its message says that the statementset can't be started from a given checkpoint yet, and no alert, job or topic has been changed

#### Scenario: Restored
- **GIVEN** a platform that can start the statementset from a given checkpoint
- **WHEN** the resync runs with a restore from a retained checkpoint
- **THEN** the new job reports that checkpoint as restored, the job's topics were not emptied, and the other steps run as with a fresh job

### Requirement: Only SHACL alerts are closed
The close step SHALL close every alert of service `SHACL Validator` that is not closed, whatever its status, and SHALL change no other alert. When the job was stopped, the step SHALL begin only after Alerta has received no SHACL alert for a settle time. It SHALL complete only when no SHACL alert is left that is not closed.

#### Scenario: Every status
- **GIVEN** SHACL alerts that are open, acknowledged, shelved and expired
- **WHEN** the close step has completed
- **THEN** all of them are closed

#### Scenario: Other alerts
- **GIVEN** an open alert of another service, such as the platform watchdog's alerts of service `System`
- **WHEN** the resync has completed
- **THEN** that alert has the same status and severity as before, and its history has no entry from the close step

#### Scenario: Many alerts
- **GIVEN** more SHACL alerts that are not closed than Alerta changes in one request
- **WHEN** the close step has completed
- **THEN** none of them is left that is not closed

#### Scenario: A raise of the stopped job in flight
- **GIVEN** a raise of the stopped job that reaches Alerta shortly after the job was stopped
- **WHEN** the close step has completed
- **THEN** that alert is closed

### Requirement: Core Services forwards unchanged raises again
The reset step SHALL replace the running Core Services job with one that restores no state, and SHALL complete only when exactly one Core Services job runs with all its tasks and its reader of `iff.alerts.bulk` holds its partition, before the re-snapshot. After it, Core Services SHALL forward the first alert it receives for each resource and event, even when its severity and text equal those it forwarded before.

#### Scenario: A new job
- **WHEN** the reset step has completed
- **THEN** Flink runs exactly one job named `Core Services`, with another job ID than before, all its tasks running and no checkpoint restored

#### Scenario: A reader placed late
- **GIVEN** a new Core Services job that runs with all its tasks, whose reader of `iff.alerts.bulk` has no partition yet
- **WHEN** the reset step waits
- **THEN** it completes only once the reader holds its partition, and no re-snapshot is triggered before

#### Scenario: An unchanged raise is forwarded
- **GIVEN** a raise that Core Services forwarded before the resync
- **WHEN** the same raise, with the same severity and text, arrives after the reset step
- **THEN** Core Services forwards it to Alerta

### Requirement: A complete re-snapshot
After the reset step, and after the job started if it was stopped, the resync SHALL start a complete snapshot of every Debezium connector feeding the validation. A snapshot SHALL count only when it started after the resync began and completed. The periodic restart of the Connect pods SHALL stay enabled during the resync. With a fresh job, it SHALL trigger the re-snapshot only once the new job reads the topics the snapshot writes.

#### Scenario: Snapshot after the start
- **WHEN** the re-snapshot step has completed
- **THEN** the log of each connector shows a snapshot that started after the resync began and completed

#### Scenario: A snapshot that dies halfway
- **GIVEN** a connector whose snapshot started after the resync began and did not complete
- **WHEN** the resync waits for the snapshot
- **THEN** that snapshot does not count, and the resync goes on waiting for a completed one until its time limit

#### Scenario: The periodic restart
- **WHEN** a resync runs
- **THEN** the periodic restart of the Connect pods is not suspended at any time, and a snapshot it started after the resync began counts like the resync's own

### Requirement: Processed
The resync SHALL take the re-snapshot as processed only when every connector completed a snapshot that started after the resync began; after that, for a quiet period, the debezium-bridge, the validation job and Core Services have each read every topic they consume to its end; and then a marker the resync writes to Core Services' output topic, behind its records, has reached Alerta. Only then SHALL it end the degraded state.

#### Scenario: Records left
- **GIVEN** every connector completed a snapshot after the resync began
- **WHEN** the validation job or Core Services has not yet read one of its source topics to the end
- **THEN** the resync keeps waiting and `ValidationConsistency` stays a warning

#### Scenario: A backlog in front of Alerta
- **GIVEN** the three consumers were quiet for the quiet period, and records of Core Services' output that the alerta-bridge has not yet posted to Alerta
- **WHEN** the resync waits for its marker
- **THEN** it keeps waiting and `ValidationConsistency` stays a warning until the marker is in Alerta, and by then every alert written before the marker is in Alerta too

#### Scenario: Quiet
- **WHEN** every connector completed a snapshot after the resync began, the three consumers have read their topics to the end throughout the quiet period, and the marker written after it has reached Alerta
- **THEN** the wait step completes, and the marker is a closed alert of service `System`, not a SHACL alert

### Requirement: Degraded while the resync runs
From its first step until the re-snapshot is processed, the resync SHALL keep the platform watchdog's `ValidationConsistency` alert a warning that the SHACL validation is degraded, a resync is in progress and the SHACL alerts are incomplete, naming the current step. The alert SHALL become normal only after the re-snapshot is processed, unless the watchdog keeps an inconsistency.

#### Scenario: During the resync
- **WHEN** a step of the resync runs
- **THEN** `ValidationConsistency` is a warning that names the resync and that step

#### Scenario: Snapshot completed, not yet processed
- **WHEN** every connector completed its snapshot but the validation job has not read its source topics to the end
- **THEN** `ValidationConsistency` is still a warning

#### Scenario: After the resync
- **WHEN** the resync has completed and the watchdog keeps no inconsistency
- **THEN** `ValidationConsistency` is normal

### Requirement: A failed resync stops
When a step fails or does not complete within its time limit, the resync SHALL stop without starting a later step, exit with a non-zero status, name the step, and leave `ValidationConsistency` critical, naming that step, until a later resync completes. If the job was stopped and not started again, the message SHALL say that the validation doesn't run and name the command. Running the resync again SHALL complete it.

#### Scenario: Alerta unreachable
- **WHEN** Alerta can't be reached during the close step
- **THEN** the resync exits with a non-zero status, its message names the close step, Core Services runs the same job as before, and `ValidationConsistency` is critical, naming the close step

#### Scenario: Not processed in time
- **WHEN** a consumer still has records left to read, or the marker has not reached Alerta, when the wait step's time limit has passed
- **THEN** the resync exits with a non-zero status, names the wait step and the consumer or the marker, and `ValidationConsistency` is critical, naming the wait step

#### Scenario: Failed while the job is stopped
- **WHEN** a resync with a fresh job fails after the job was stopped and before it was started
- **THEN** its message says that the SHACL validation doesn't run and names the command to run again

#### Scenario: Run again
- **WHEN** the resync is run again after a failed step, with the cause removed
- **THEN** it completes every step, exits with status 0, and `ValidationConsistency` is normal afterwards unless the watchdog keeps an inconsistency

### Requirement: Alerts after the resync
After a resync, with or without a replacement of the job, the SHACL alerts that are not closed SHALL be exactly those of the constraints that the current entities violate. This SHALL hold for count constraints and for every other constraint type.

#### Scenario: A count constraint satisfied now
- **GIVEN** an open alert of a count constraint that the entity satisfies now
- **WHEN** the resync has completed
- **THEN** the alert is closed

#### Scenario: Another constraint type satisfied now
- **GIVEN** an open alert of a value constraint that the entity satisfies now
- **WHEN** the resync has completed
- **THEN** the alert is closed

#### Scenario: Still violated
- **GIVEN** an open alert of a constraint that the entity still violates
- **WHEN** the resync has completed
- **THEN** within one minute the alert is open, with the same severity and text, and its history shows it was closed by the resync and opened again

#### Scenario: An entity that no longer exists
- **GIVEN** an open alert for an entity that no longer exists
- **WHEN** the resync has completed
- **THEN** the alert is closed, and it is still closed two minutes later
