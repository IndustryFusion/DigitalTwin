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
- Whether a recorded checkpoint can still be restored is computed when it is needed, from live values, by two rules with a margin, with no fixed window and no change to the defaults:
  - **State rule:** the time since the last complete refresh before the checkpoint, plus the estimated time the restored job needs to read its backlog and the re-snapshot, must stay below the state TTL. Flink's TTL counts processing time, the time the job was down included, and an expired key read again becomes a duplicate in the pinned join.
  - **Replay rule:** the checkpoint's age must stay below the retention Kafka reports now for every topic the validation reads, so that deletes in the gap are replayed.
- `make shacl-resync REPLACE=checkpoint` restores the newest recorded checkpoint that fits the deployed statementset and passes both rules, or the one given by `RESTORE_FROM`. It refuses before its first step otherwise, with the reason per candidate. `REPLACE=auto` restores such a checkpoint if there is one and otherwise replaces the job fresh, saying which and why. The other steps of the resync (close, reset Core Services, re-snapshot, processed) stay as #1035 defines them.
- The refresh period of `kafka-connect-restart` becomes a value of its own, `flink.refreshPeriod`, capped at half the TTL, instead of always half the TTL. Its default of 30 min keeps today's effective period.
- The platform watchdog judges a restored state by the refresh before the checkpoint, and names in `ValidationConsistency` the newest restorable checkpoint and until when it stays restorable. For an inconsistent state it names `REPLACE=fresh`, with the TTL as the reason no checkpoint helps; for a rebuilding state it names `REPLACE=auto`. *Late refresh* follows the refresh period.
- A sizing guide in the README says how to set TTL, refresh period, checkpoint interval and topic retention for a wanted outage tolerance, and what each costs.
- Retained checkpoints that can't be restored any more are pruned after a resync and after a deploy.
- An e2e test on the platform takes a checkpoint, breaks the state, restores, and compares the open alerts with the violations of the model; it also checks the refusal after a KMS change and after a topic's retention was shortened, and `REPLACE=auto` falling back to fresh on a deployment with a short TTL.
- The cost of checkpointing (state size, duration, interval, storage) is measured on the e2e KMS with today's settings and with one example sizing (TTL 1 d, retention 1 d), and stated in the README; the restore tests calibrate the catch-up estimate.

## Capabilities

### New Capabilities
- `shacl2flink/validation-checkpoints`: checkpoints of the validation, starting a statementset from one, how restorability is computed, the refresh period, and how the resync restores, starts fresh or refuses.

### Modified Capabilities
- `helm/platform-watchdog`: new requirements **Restored validation state** and **Restorable checkpoint**; modified **Repair of an inconsistent state**, **Rebuilding validation state** and **Late refresh**. #1036 modifies three of them as well; this delta is rebased onto them once #1036 is archived (design, *Dependency on #1035*).

`shacl2flink/alert-resync`, requirement *Restore from a checkpoint*, comes with #1035 and is not archived. Its "refused until supported" part is replaced by this change; the delta is added here once #1035 is archived (design, *Dependency on #1035*).

## Out of Scope

- Periodic savepoints, and keeping checkpoints across a KMS change: a changed statementset always starts fresh.
- Restoring Core Services from a checkpoint; the resync keeps resetting it without state.
- Restoring after `flink-undeploy`: it deletes the validation's topics, so a checkpoint no longer fits them.
- Changing the generated SQL or the Debezium snapshots; tombstones for deleted entities.
- Changing the TTL or retention defaults, a fixed restore window, and refusing a deployment for its sizing.
- Running a restore without a person; the watchdog names it, a person runs the resync.

## Impact

- Components: `semantic-model/shacl2flink` (statementset settings and annotations, the resync script of #1035, the sizing guide), `FlinkSqlServicesOperator` (CRD field, restore, status), `FlinkSqlGateway` (restore path of a submission), `helm/values.yaml.gotmpl` (refresh period and the catch-up estimate's values; TTL and retention unchanged), `helm/charts/kafka` (the restarter's refresh period), `helm/charts/alerta` (the watchdog, and `get`/`list` on KafkaTopics in its Role), `helm/charts/flink` (unchanged settings, cited), README of shacl2flink and of the operator.
- Object store: retained checkpoints of the validation under `state.checkpoints.dir`; the resync and `flink-deploy` prune the ones that can no longer be restored.
- Contracts: no contract between components changes, and none states a retention, TTL or refresh period. The restore relies on the retention of the topics the validation reads and on deletes reaching it through the entity store, as `contracts/context-broker` states (design, *Contracts*).
- Depends on #1035 (PR #1036) for `make shacl-resync`.
