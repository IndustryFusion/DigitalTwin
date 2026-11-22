# Delta for Validation Checkpoints

## Purpose

Defines how the SHACL validation keeps retained checkpoints, how a statementset is started from a checkpoint or savepoint, which checkpoints fit a deployed statementset, and how the resync of the SHACL alerts chooses one to restore or refuses it.

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
The statementset's status SHALL state a fingerprint of what its job runs and list the latest completed checkpoints of its jobs, newest first, each with its path, completion time, job and fingerprint. The fingerprint SHALL change with the statements, tables, views, settings other than checkpointing, and the Flink version, and with nothing else. Checkpoints of different fingerprints SHALL be kept apart in the storage.

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
- **WHEN** only the checkpoint interval is changed
- **THEN** the fingerprint is unchanged

### Requirement: The resync chooses a checkpoint
A resync with a restore from a checkpoint SHALL restore the newest recorded checkpoint, or the recorded one given by its path, that has the deployed fingerprint, was completed after the validation's topics were last emptied or recreated, and is younger than the shortest retention of the topics the job reads, less a margin. Otherwise it SHALL stop before its first step, name why each candidate was refused, and change nothing.

#### Scenario: The latest fitting checkpoint
- **GIVEN** two recorded checkpoints of the deployed fingerprint, both young enough
- **WHEN** the resync runs with a restore and no path
- **THEN** the job restores the newer one, the topics weren't emptied, and the other resync steps run as with a fresh job

#### Scenario: After a KMS change
- **GIVEN** recorded checkpoints only of the fingerprint before a KMS change
- **WHEN** the resync runs with a restore
- **THEN** it exits non-zero before the first step, says that no checkpoint fits the deployed statementset and that a fresh replacement works, and no alert, job or topic has changed

#### Scenario: Too old
- **GIVEN** a recorded checkpoint older than the shortest retention of the topics the job reads, less the margin
- **WHEN** the resync runs with a restore from it
- **THEN** it exits non-zero before the first step, names the checkpoint's age and the limit, and nothing has changed

#### Scenario: Before the topics were emptied
- **GIVEN** a checkpoint completed before a resync with a fresh job emptied the validation's topics
- **WHEN** the resync runs with a restore from it
- **THEN** it exits non-zero before the first step and says that the checkpoint predates the topics

#### Scenario: A path not recorded
- **WHEN** the resync runs with a restore from a path the statementset hasn't recorded
- **THEN** it exits non-zero before the first step and says so

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
After a successful resync, the storage SHALL keep only the checkpoints that could still be restored or that the running job needs, and the status SHALL list no checkpoint that was removed.

#### Scenario: After a resync
- **WHEN** a resync completed and the running job completed a checkpoint
- **THEN** the storage holds no checkpoint directory of another fingerprint older than the read topics' retention, and none of the deployed fingerprint that the status doesn't list, except the running job's
