# Delta for Validation Checkpoints

## Purpose

Defines how the SHACL validation keeps retained checkpoints, how a statementset is started from a checkpoint or savepoint, which checkpoints fit a deployed statementset, how it is computed whether a checkpoint can still be restored, the refresh period, and how the resync of the SHACL alerts chooses a checkpoint to restore, starts fresh or refuses.

## ADDED Requirements

### Requirement: Retained checkpoints
The validation statementset SHALL by default take exactly-once checkpoints at a configurable interval and keep a configurable number of them, in a configurable storage, also when its job is cancelled. A build option SHALL turn checkpointing off.

#### Scenario: Deployed by default
- **WHEN** the validation is deployed with the default build and has run for longer than the interval
- **THEN** Flink reports for its job checkpointing in exactly-once mode at the configured interval, checkpoints retained on cancellation, and at least one completed checkpoint

#### Scenario: Cancelled
- **WHEN** the validation job is cancelled after it completed a checkpoint
- **THEN** that checkpoint is still in the storage and can be restored

#### Scenario: Opted out
- **WHEN** the validation is built with checkpointing turned off
- **THEN** Flink reports checkpointing disabled for its job

### Requirement: A statementset names its start checkpoint
A BeamSqlStatementSet SHALL accept a checkpoint or savepoint path to start from. The operator SHALL start the first job of each version of the resource's spec from it and report the restored path. A path that can't be restored SHALL fail the start with Flink's reason, without starting the job empty. A later job of the same spec version SHALL start without it.

#### Scenario: Started from a checkpoint
- **WHEN** a statementset is created that names a retained checkpoint of an earlier job of the same statementset
- **THEN** the new job runs, Flink reports that checkpoint as restored, and the statementset's status names it

#### Scenario: A path that can't be restored
- **WHEN** a statementset names a path that holds no checkpoint
- **THEN** no job runs, the status reports a deployment failure with the reason, and no job without state is started for that spec

#### Scenario: A malformed path
- **WHEN** a statementset names a path with whitespace or without a storage scheme
- **THEN** the submission is refused, naming the path field, and no job is started

#### Scenario: Lost later
- **GIVEN** a job started from a checkpoint
- **WHEN** that job is lost and the operator starts the job again for the unchanged spec
- **THEN** the new job restores no checkpoint from that path

#### Scenario: Savepoint update
- **WHEN** a statementset with the savepoint update strategy has its spec changed while its job runs
- **THEN** the new job reports the savepoint taken at the stop as restored

### Requirement: A restore claims all state
A job started from a checkpoint or savepoint SHALL NOT run when part of that state has no place in the job.

#### Scenario: State of another statementset
- **WHEN** a statementset is started from a checkpoint of a statementset with other statements
- **THEN** the job doesn't run and the status reports that the state can't be restored

### Requirement: Checkpoints are recorded with what they fit
The statementset's status SHALL state a fingerprint of what its job runs and list the latest completed checkpoints of its jobs, newest first, each with its path, completion time, job and fingerprint. The fingerprint SHALL change with the statements, tables, views, settings other than checkpointing, among them the state backend, and the Flink version, and with nothing else. Checkpoints of different fingerprints SHALL be kept apart in the storage.

#### Scenario: A completed checkpoint
- **WHEN** the validation job completes a checkpoint
- **THEN** within a minute the status lists it first, with the job's fingerprint and the completion time Flink reports

#### Scenario: The same KMS deployed again
- **WHEN** the validation is deployed again from the same KMS and values
- **THEN** its fingerprint is unchanged

#### Scenario: A KMS change
- **WHEN** the validation is deployed from a KMS with a changed shape
- **THEN** its fingerprint differs and its checkpoints are stored apart from the previous ones

#### Scenario: Another interval
- **WHEN** only the checkpoint interval, or incremental checkpoints, are changed
- **THEN** the fingerprint is unchanged, and the job restores a checkpoint taken before the change

#### Scenario: Another state backend
- **WHEN** the validation is deployed with another state backend
- **THEN** its fingerprint differs

### Requirement: Restorability is computed
A recorded checkpoint SHALL count as restorable only while both hold, computed from live values with a margin: the time since the start of the last complete refresh before it, plus the estimated catch-up of the restored job, is less than the deployed state TTL; and its age is less than the retention Kafka reports for every topic the validation reads. The catch-up SHALL be estimated from the records since the checkpoint, the records of one refresh and a throughput.

#### Scenario: Just inside the state rule
- **GIVEN** a checkpoint whose last refresh, plus its estimated catch-up and the margin, ends one minute before the TTL is reached
- **WHEN** its restorability is computed
- **THEN** it passes the state rule

#### Scenario: Just outside the state rule
- **GIVEN** the same checkpoint two minutes later, with nothing else changed
- **WHEN** its restorability is computed
- **THEN** it fails the state rule, and the reason names the refresh, the TTL, the catch-up and the margin

#### Scenario: Catch-up grows with the backlog
- **GIVEN** two computations for the same checkpoint, with the read topics' end offsets grown by the throughput times ten minutes in between
- **WHEN** the catch-up is estimated
- **THEN** the second estimate is ten minutes larger than the first

#### Scenario: Just inside and outside the replay rule
- **GIVEN** a read topic whose retention is one hour
- **WHEN** the restorability of checkpoints aged one hour less the margin less one minute, and one hour less the margin plus one minute, is computed
- **THEN** the first passes the replay rule and the second fails it, naming the topic and its retention

#### Scenario: A refresh not recorded
- **GIVEN** a checkpoint for which the start of the last refresh before it isn't known
- **WHEN** its restorability is computed
- **THEN** it isn't restorable, and the reason says so

#### Scenario: Restored after an outage within the limits
- **GIVEN** the validation deployed with a TTL of one day and its read topics' retention one day
- **WHEN** Flink is down for 70 minutes and then restores the job from its latest checkpoint, and the next complete refresh has passed
- **THEN** the open SHACL alerts are those of the violations, and no count is higher than the model's

### Requirement: The refresh period is its own value
The periodic refresh SHALL run at a configurable refresh period, independent of the TTL, at most half the TTL; the default SHALL keep today's effective period.

#### Scenario: Defaults
- **WHEN** the validation runs with the default values
- **THEN** every connector completes a refresh at least every 30 minutes plus 240 seconds, as before

#### Scenario: A longer TTL
- **WHEN** the validation is deployed with a TTL of one day and the default refresh period
- **THEN** the refreshes still come every 30 minutes plus at most 240 seconds

#### Scenario: A period above half the TTL
- **WHEN** the refresh period is set above half the TTL
- **THEN** refreshes come at half the TTL, and the restarter's log says that it capped the period

### Requirement: The resync chooses a checkpoint
A resync with a restore SHALL restore the newest recorded checkpoint, or the recorded one given by its path, that has the deployed fingerprint, was completed after the validation's topics were last emptied or recreated and while the state was consistent, and is restorable. Otherwise it SHALL stop before its first step, name why each candidate was refused, and change nothing.

#### Scenario: The latest restorable checkpoint
- **GIVEN** two restorable recorded checkpoints of the deployed fingerprint
- **WHEN** the resync runs with a restore and no path
- **THEN** the job restores the newer one, the topics weren't emptied, and the other resync steps run as with a fresh job

#### Scenario: After a KMS change
- **GIVEN** recorded checkpoints only of the fingerprint before a KMS change
- **WHEN** the resync runs with a restore
- **THEN** it exits non-zero before the first step, says that no checkpoint fits the deployed statementset and that a fresh or automatic replacement works, and no alert, job or topic has changed

#### Scenario: Not restorable
- **GIVEN** a recorded checkpoint that fails the state rule
- **WHEN** the resync runs with a restore from it
- **THEN** it exits non-zero before the first step, names the rule and its numbers, and nothing has changed

#### Scenario: A topic shortened after the checkpoint
- **GIVEN** a read topic whose retention was set below the checkpoint's age after the checkpoint was taken
- **WHEN** the resync runs with a restore
- **THEN** it exits non-zero before the first step, naming the topic, its retention and the checkpoint's age

#### Scenario: Taken while inconsistent
- **GIVEN** a checkpoint completed while the watchdog held an inconsistency of the validation state
- **WHEN** the resync runs with a restore from it
- **THEN** it exits non-zero before the first step and says that the checkpoint holds an inconsistent state

#### Scenario: Before the topics were emptied
- **GIVEN** a checkpoint completed before a resync with a fresh job emptied the validation's topics
- **WHEN** the resync runs with a restore from it
- **THEN** it exits non-zero before the first step and says that the checkpoint predates the topics

#### Scenario: A path not recorded
- **WHEN** the resync runs with a restore from a path the statementset hasn't recorded
- **THEN** it exits non-zero before the first step and says so

### Requirement: Automatic replacement
A resync with the automatic replacement SHALL restore the checkpoint a restore would choose if there is one, and otherwise run as with a fresh job. Its output SHALL say which it does and why: the checkpoint and until when it is restorable, or why each candidate isn't.

#### Scenario: Automatic, restorable
- **GIVEN** a restorable recorded checkpoint
- **WHEN** the resync runs with the automatic replacement
- **THEN** its output says that it restores that checkpoint and until when it was restorable, and the job reports it as restored

#### Scenario: Automatic, none restorable
- **GIVEN** recorded checkpoints, none of them restorable
- **WHEN** the resync runs with the automatic replacement
- **THEN** its output names for each checkpoint why it isn't restorable, it runs as with a fresh job, and the command exits with status 0

### Requirement: Restored verdicts
A validation restored by the resync SHALL leave open exactly the alerts of the constraints violated at the end of the resync, including changes and deletes made between the checkpoint and the restore.

#### Scenario: Restored after the state was lost
- **GIVEN** a checkpoint taken while the model had known violations, and a job that afterwards lost its state
- **WHEN** the resync restores that checkpoint
- **THEN** the open SHACL alerts are those of the model's violations, with the same severity and text as before the loss

#### Scenario: Changes in the gap
- **GIVEN** after the checkpoint one violation is repaired and one violating entity is deleted
- **WHEN** the resync restores that checkpoint
- **THEN** neither of their alerts is open, and every other violation's alert is

### Requirement: Retained checkpoints are pruned
After a successful resync, and after a deployment once its job completed a checkpoint, the storage SHALL keep only the checkpoints that could still be restored or that the running job needs, and the status SHALL list no checkpoint that was removed.

#### Scenario: After a resync
- **WHEN** a resync completed and the running job completed a checkpoint
- **THEN** the storage holds no checkpoint of another fingerprint, and none of the deployed fingerprint that the status doesn't list, except the running job's

#### Scenario: After a KMS change
- **WHEN** a changed KMS was deployed and its job completed a checkpoint, without a resync
- **THEN** the storage holds no checkpoint of the previous fingerprint
