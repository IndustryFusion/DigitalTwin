# Proposal

Issue: #1042

## Why

The SHACL validation can only start empty. After a lost job, a JobManager restart or a resync with a fresh job (#1035) it rebuilds its whole state from a complete Debezium snapshot, and until that has gone through the validation is degraded. A restore from a checkpoint would bring back a consistent state without the wait, but the platform can't do it:

- the validation runs without checkpointing: checkpointing is opt-in at build time (`CHECKPOINT ?= false` in `semantic-model/shacl2flink/Makefile`), and a job on the platform reports a checkpoint interval of `Long.MAX_VALUE`;
- the object store holds no `checkpoints` or `savepoints` directory, so there is nothing to restore after a stop;
- a BeamSqlStatementSet can't name a checkpoint to start from. The operator's only savepoint path is its `updateStrategy: savepoint` update, which shacl2flink doesn't use, and it hands the path to the submit job as a SQL `SET` string while the submit job reads every setting as a map;
- nothing tells whether a checkpoint still fits the deployed statementset, or whether the topics still hold the records it needs.

The resync of #1035 (PR #1036, `make shacl-resync`) accepts `REPLACE=checkpoint` and refuses it with these gaps. This change closes them, so that the resync can restore instead of starting fresh.

## What Changes

- The validation statementset is built with checkpointing on by default: exactly-once, at a configurable interval, incremental, retained on cancellation, in a directory of the object store that is specific to the statementset and to what it runs. `CHECKPOINT=false` still builds it without.
- A BeamSqlStatementSet gets a field naming a checkpoint or savepoint to start from. The operator starts the job from it once, the SQL gateway passes it to Flink as the restore path of the submission, and the restore refuses state the new job can't claim. The operator's savepoint update uses the same way, which fixes the form it passes today.
- The operator records in the statementset's status the latest completed checkpoints of its jobs: path, completion time, job, and the fingerprint of what the job ran.
- `make shacl-resync REPLACE=checkpoint` picks the latest recorded checkpoint that fits the deployed statementset, or takes the one given by `RESTORE_FROM`, and refuses, before its first step, a checkpoint that doesn't fit, is older than the topics it reads can replay, or was taken before the validation's topics were last emptied or recreated. The other steps of the resync (close, reset Core Services, re-snapshot, processed) stay as #1035 defines them.
- An e2e test on the platform takes a checkpoint, breaks the state, restores, and compares the open alerts with the violations of the model; it also checks the refusals after a KMS change and for a too old checkpoint.
- The cost of checkpointing (state size, duration, interval, storage) is measured on the e2e KMS and stated in the README.

## Capabilities

### New Capabilities
- `shacl2flink/validation-checkpoints`: checkpoints of the validation, starting a statementset from one, and how the resync chooses or refuses one.

### Modified Capabilities

None on `main` yet. `shacl2flink/alert-resync`, requirement *Restore from a checkpoint*, comes with #1035 and is not archived. Its "refused until supported" part is replaced by this change; the delta is added here once #1035 is archived (design, *Dependency on #1035*).

## Out of Scope

- Periodic savepoints, and keeping checkpoints across a KMS change: a changed statementset always starts fresh.
- Restoring Core Services from a checkpoint; the resync keeps resetting it without state.
- Restoring after `flink-undeploy`: it deletes the validation's topics, so a checkpoint no longer fits them.
- Changing the generated SQL, the topic retention or the Debezium snapshots.
- Choosing a checkpoint by the watchdog or running the restore automatically.

## Impact

- Components: `semantic-model/shacl2flink` (statementset settings, Makefile, the resync script of #1035), `FlinkSqlServicesOperator` (CRD field, restore, status), `FlinkSqlGateway` (restore path of a submission), `helm/charts/flink` (unchanged settings, cited), README of shacl2flink and of the operator.
- Object store: retained checkpoints of the validation under `state.checkpoints.dir`; the resync prunes the ones that can no longer be restored.
- Contracts: no contract between components changes. The restore relies on the retention of the topics the validation reads and on deletes reaching it through the entity store, as `contracts/context-broker` states (design, *Contracts*).
- Depends on #1035 (PR #1036) for `make shacl-resync`.
