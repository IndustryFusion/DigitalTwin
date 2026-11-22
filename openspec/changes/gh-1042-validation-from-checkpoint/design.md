# Design

## Context

**How the validation is built.** `create_sql_checks_from_shacl.py` writes the BeamSqlStatementSet `shacl-validation` with `lib/utils.py` `create_statementmap` (`create_sql_checks_from_shacl.py:124`, `lib/utils.py:580-631`). Its `sqlsettings` are a list of one-key maps: upsert materialization, mini-batch off, `execution.savepoint.ignore-unclaimed-state: true` (`:615`), object reuse, parallelism and idle timeout from helm values, RocksDB with its options, and `table.exec.state.ttl` from `shacl_state_ttl` (`lib/configs.py:86`, `{{.Values.flink.shaclTtl}}`, `3600 s` in `helm/values.yaml.gotmpl:123`). Commit 07f3abbe pins the joins and count accumulators with `STATE_TTL ... '0d'` hints, so that state is bounded by the live model, not by the TTL; the dedup views keep the TTL. Checkpointing is opt-in: `CHECKPOINT ?= false` (`Makefile:32`) maps to the switch `-p` (`Makefile:44-48`, `:76`), which adds only `execution.checkpointing.interval: {{ .Values.flink.checkpointInterval }}` (`lib/utils.py:627-628`; `1 min` in `values.yaml.gotmpl:85`, used by no other component). `make helm` copies the output into `helm/charts/shacl/templates` (`Makefile:79-85`); `flink-deploy` deletes the KafkaTopics of `output/ngsild-kafka.yaml` and `output/rdf-kafka.yaml` before `helmfile apply` (`Makefile:174-186`). The statementset carries `updateStrategy: none` (`lib/utils.py:630`).

**The Flink session cluster.** `helm/charts/flink/templates/flink-deployment.yaml` runs Flink `v1_20` and sets `state.checkpoints.dir: s3://<bucket>/checkpoints`, `state.savepoints.dir: s3://<bucket>/savepoints` (`:82-83`), Kubernetes HA with `high-availability.storageDir` on the same bucket (`:84-85`), `restart-strategy: exponential-delay`, and `state.backend.incremental: false` (`:43`). The bucket is served by seaweedfs.

**The operator.** `FlinkSqlServicesOperator/beamsqlstatementsetoperator.py`:
- `create` (`:93`) sets `status.state: INITIALIZED` and `job_id: None`; the timer `monitor` (`:268`) builds the submission `{sqlsettings, tables, views, sqlstatementset}` and posts it to the gateway (`deploy_statementset`, `:534`). If Flink already runs a job of that name, it adopts it instead (`:555`).
- `update` (`:178`) runs on every spec change. With `updateStrategy: none` it cancels the job (`PATCH /jobs/<id>`, `flink_util.py:73-80`); with `savepoint` it calls `POST /jobs/<id>/stop` (`flink_util.py:83`) and keeps the location in `status.location` (`:258`).
- `create_sets` (`:476`) appends that location as the string `SET execution.savepoint.path = '...';` (`:499`). Nothing clears `status.location` afterwards: `create` resets state and job ID only, so every later deployment of the resource would carry the same path.
- The CRD (`FlinkSqlServicesOperator/kubernetes/crd.yml`, v1alpha4) has `sqlsettings`, `updateStrategy` (`none`, `savepoint`), `refreshInterval`, and no field for a start checkpoint. The status has no subresource and keeps unknown fields. `helm/install_operators.sh:66` applies the CRD.

**The gateway.** `FlinkSqlGateway/gateway.js` writes the posted body to `data/SQL-structures.json` and runs `/opt/flink/bin/flink run --python job.py` (`:45`, `:99-104`), splitting the command at spaces (`:62`). `submitjob/job.py:33-41` reads each entry of `sqlsettings` as a map (`set.keys()`) and sets it on the table config. A string entry, as `create_sets` writes for a savepoint, fails there. Read from the code, not run.

**Sources.** The validation reads `iff.ngsild.entities` and `iff.ngsild.attributes` with `scan.startup.mode: latest-offset` (`create_ngsild_tables.py:75`, `create_core_tables.py:129`, `:220`, `:302`), `iff.rdf`, and reads back its own `constraint_table`, `constraint_combination_table` and `constraint_trigger_table` (upsert-kafka, earliest offset). A job restored from a checkpoint ignores the startup mode and continues each partition from the offset in the checkpoint, as Flink's Kafka source documents. Kafka keeps a record at least `retention.ms`; since #978 (`lib/utils.py:671`, `segment_ms`) segments roll at `max(retention.ms, 1 h)`, so a record goes after at most retention + segment + check interval, but only the retention is guaranteed. If a restored offset has been deleted, the source falls back to its reset strategy, which for a latest-offset source is the end of the partition: the records in between are skipped without an error.

**The re-snapshot.** Both Debezium connectors run with `snapshotMode: always`, and `kafka-connect-restart` restarts them every two minutes once the pods are older than about half the state TTL (#1035, Context). A snapshot publishes every row that exists; it publishes no delete for a row that is already gone. A delete reaches the validation only as the change record of that moment (`contracts/context-broker`, *Entity changes are published through the entity store*).

**Flink 1.20 semantics** (documentation of Flink 1.20, "Checkpoints", "Savepoints", "Configuration", "Upgrading applications"; the cluster runs 1.20.4):
- `execution.checkpointing.interval` turns checkpointing on; mode `EXACTLY_ONCE` is the default. `execution.checkpointing.externalized-checkpoint-retention: RETAIN_ON_CANCELLATION` keeps the latest `execution.checkpointing.num-retained` checkpoints when the job is cancelled; Flink never deletes a retained checkpoint afterwards. Since 1.20 the checkpoint keys are `execution.checkpointing.dir`, `.num-retained` and `.incremental` (the `state.checkpoints.*` and `state.backend.incremental` names are deprecated aliases), and the restore keys are `execution.state-recovery.path`, `.ignore-unclaimed-state` and `.claim-mode` (aliases `execution.savepoint.*`). State backend and checkpoint storage can be set per job, as the validation already does for RocksDB.
- A checkpoint is written to `<dir>/<job-id>/chk-<n>` with its `_metadata`; incremental RocksDB checkpoints share files under `<dir>/<job-id>/shared`. In the default claim mode `NO_CLAIM` the restored job doesn't take ownership of the snapshot, and its first checkpoint is a full one, so the restored snapshot can be deleted once that first checkpoint completed.
- `flink run -s <path>` (`--fromSavepoint`) restores a job from a savepoint or a retained checkpoint; `-n` (`--allowNonRestoredState`) lets it start while state of the snapshot has no operator to go to. Without it, the start fails.
- A SQL job's operator IDs are derived from its plan. Flink guarantees no state compatibility for a changed query, a changed parallelism beyond the max parallelism, or another Flink version. A checkpoint fits only the same statementset on the same Flink; after a KMS change only a fresh start works.
- `POST /jobs/<id>/stop` stops with a savepoint (a full, canonical snapshot, taken on request); `PATCH /jobs/<id>` cancels without one, keeping retained checkpoints.

**Verified on a local k3d platform** (read-only `kubectl get`/`exec`, Flink REST through the JobManager pod, the seaweedfs filer's listing; only names and numbers printed):
- `/config` reports `flink-version` `1.20.4`. `/jobmanager/config` reports `state.checkpoints.dir` `s3://flink/checkpoints`, `state.savepoints.dir` `s3://flink/savepoints`, `high-availability` `kubernetes` with storage `s3://flink/recovery`, `state.backend.incremental` `false`.
- `/jobs/overview` lists one job, `Core Services`, `RUNNING`, 10 tasks; no `shacl-validation` was deployed (`kubectl get bsqls` empty). The validation of a deployed KMS has been reported with 223 tasks; the e2e KMS is smaller.
- `/jobs/<id>/checkpoints/config` of Core Services: interval `9223372036854775807` (off), externalization enabled with `delete_on_cancellation: false`, state backend HashMap. That retention comes from the job's submitter (the Flink Kubernetes operator); the validation is submitted by `flink run` in the gateway and must set it itself.
- The filer lists `/buckets/flink/recovery/flink-deployment`; `/buckets/flink/checkpoints` and `/buckets/flink/savepoints` don't exist: no job has ever written a checkpoint or savepoint.
- Kafka 3.9: `iff.ngsild.attributes` has `retention.ms` and `segment.ms` `3600000` (KafkaTopic); `iff.ngsild.entities` and `iff.rdf` have `retention.ms` `86400000` and `segment.ms` `604800000` (not KafkaTopic resources). The three constraint topics have `3600000` (#1035, Context).

## Goals / Non-Goals

**Goals:**
- The validation takes retained, exactly-once checkpoints by default, at an interval and in a storage that are configurable.
- A statementset can name a checkpoint or savepoint to start from, and the job starts from it or not at all.
- The resync restores only a checkpoint that fits the deployed statementset and can still be replayed, and refuses every other before it changes anything.
- A restored job ends with the same open alerts as a fresh one: those of the constraints violated now.
- The cost is measured and stated.

**Non-Goals:**
- Keeping state across a KMS change, a Flink upgrade or `flink-undeploy`.
- Restoring Core Services; changing the resync's alert steps.
- Automatic restores; the watchdog keeps reporting only.

## Decisions

### D1: Retained checkpoints, not periodic savepoints or a savepoint at each resync

The validation's `sqlsettings` get, when built with checkpointing (now the default, `CHECKPOINT ?= true`):
`execution.checkpointing.interval: {{ .Values.flink.checkpointInterval }}`, `execution.checkpointing.mode: EXACTLY_ONCE`, `execution.checkpointing.externalized-checkpoint-retention: RETAIN_ON_CANCELLATION`, `execution.checkpointing.num-retained: {{ .Values.flink.checkpointsRetained }}` (new, default 3), `execution.checkpointing.incremental: true` and `execution.checkpointing.min-pause` of half the interval. The interval keeps its existing value `flink.checkpointInterval` (only shacl2flink uses it) until the measurement (D9) sets the default. The cluster's `state.backend.incremental: false` stays for other jobs.

A retained checkpoint survives every way the job ends: the delete handler's cancel, a lost JobManager, the resync's stop. With checkpointing on, Flink also restores a failed-over task and, through Kubernetes HA, a restarted JobManager from the latest checkpoint by itself, which the watchdog already distinguishes (*A failover restored from a checkpoint*).

*Exactly-once:* the count accumulators and joins work on retracting changelogs; replaying a record whose effect is already in the state (at-least-once after a restore) would count it twice. The sinks stay as they are; their upserts by key are idempotent.

*Alternatives:*
- **Periodic savepoints** (`POST /jobs/<id>/savepoints` by a CronJob). Full, canonical snapshots, more costly per run, and one more component and schedule; checkpoints are already taken by Flink.
- **Stop-with-savepoint at each resync.** Gives a snapshot only of the moment of the stop. It can't serve a job that was lost or whose state went stale before, and every resync would pay a full snapshot. A savepoint path remains usable through the same field (D2).
- **Turning on checkpointing cluster-wide.** It would change Core Services and every other job; per job keeps the scope to the validation.
- **At-least-once mode** to avoid barrier alignment on the 223 tasks. Rejected for the double counting above; D9 measures the alignment time.

### D2: The start checkpoint is a CRD field, passed as the submission's restore path

The BeamSqlStatementSet v1alpha4 gets `spec.restoreFrom` (string, a checkpoint or savepoint directory or its `_metadata`, `s3://` or `file://`). The operator adds it to the submission as a top-level `restoreFrom`, not as a setting. The gateway checks it (scheme, no whitespace, at most 1024 characters; otherwise `400` naming the field) and runs `flink run -s <path> --python job.py`. The operator's `savepoint` update strategy uses the same top-level field for `status.location`, so `create_sets` no longer writes the `SET` string, and `job.py` keeps reading only maps.

*Once per generation:* the operator uses `restoreFrom` only for the first submission of the resource's `metadata.generation` and records `status.restoredFrom: {path, generation, jobId}`. A later redeployment of the same generation (job lost, `NOT_FOUND`) starts without it, since that checkpoint is older by then than what the job had. Removing the field afterwards would be a spec change, which cancels the job under `updateStrategy: none`.

*Reported:* when the job runs, the operator reads `/jobs/<id>/checkpoints` and keeps `latest.restored.external_path` in `status.restoredFrom`; a start that fails because the path can't be read or claimed sets `DEPLOYMENT_FAILURE` with Flink's reason in `status.messages`, and the operator does not fall back to an empty start for that generation.

*Alternatives:*
- **A `sqlsettings` entry `execution.state-recovery.path`.** It would sit in the spec next to the settings that define the job, could not be made one-shot, and would become part of the fingerprint (D4). Whether a path set on the table config of a `flink run --python` job reaches the job graph's restore settings is not documented; `-s` is.
- **An annotation on the statementset.** Not validated by the CRD and invisible to `kubectl explain`; a field states the interface.

### D3: The restore claims all state

shacl2flink drops `execution.savepoint.ignore-unclaimed-state: true` from the validation's settings, and the gateway never passes `-n`. A restore whose state has no operator in the new job fails to start. With D4 that should never happen; if it does, the start fails visibly instead of running with part of its state.

*Alternative:* keep it for the `savepoint` update strategy of other statementsets. The validation doesn't use that strategy; other statementsets keep their own settings, since only shacl2flink's are changed.

### D4: A fingerprint names what fits, and is the checkpoint directory

Before each submission the operator computes a fingerprint: SHA-256 (first 16 hex digits) of the canonical JSON of the submission (settings, table DDLs, views, statements) without `restoreFrom` and without the `execution.checkpointing.*` settings, plus the Flink version from `/config`. It sets `execution.checkpointing.dir` to `<state.checkpoints.dir>/<namespace>-<name>/<fingerprint>` unless the spec sets it, reading `state.checkpoints.dir` from `/jobmanager/config`, and writes `status.fingerprint`. Flink adds `<job-id>/chk-<n>` below. So every checkpoint under one fingerprint directory fits a job with the same fingerprint, a KMS change or a Flink upgrade gives a new directory, and a change of the interval or of the retention doesn't invalidate older checkpoints.

*Why the rendered submission, not the KMS package digest:* the job graph also depends on helm values (parallelism, TTL, topic names) and on the table definitions; two packages with different digests can generate the same SQL. The submission is what Flink compiles.

*Alternatives:*
- **Let Flink decide** (D3 alone). A changed query that keeps the old operators and adds new ones would start with part of the verdicts.
- **A fingerprint computed by shacl2flink at build time.** It can't see helm values rendered later.

### D5: The operator records the checkpoints; the resync reads them

While a job runs, the operator reads `/jobs/<id>/checkpoints` at its timer and keeps in `status.checkpoints` the latest completed checkpoints of the resource's jobs, newest first, at most `checkpointsRetained` per job and five in all: `path` (`external_path`), `completedAt` (`latest_ack_timestamp`), `jobId`, `fingerprint`. Entries stay when the job ends, because they are what a restore needs. A resource created anew starts with no entries; `create` clears them, the same as `status.location`, which also stops reusing a savepoint path.

The resync works from this record, not by listing the object store: production may run another S3 store, and the resync then needs no object-store credentials. The record lives in the statementset, so it goes with the deployment it describes.

*Alternatives:* list `<dir>/<ns>-<name>/<fingerprint>/*/chk-*/_metadata` in the object store (needs credentials and a client in the resync; the age is only the object time); a ConfigMap per statementset (one more object to own, and the operator is generic).

### D6: How `shacl-resync REPLACE=checkpoint` picks or refuses

Before its first step the resync reads the deployed statementset and decides:

1. **Candidates:** `status.checkpoints` entries whose `fingerprint` equals `status.fingerprint`. With `RESTORE_FROM=<path>`, only the entry with that path; a path that isn't recorded is refused ("not a recorded checkpoint of this statementset").
2. **Taken after the last reset of the topics:** the entry's `completedAt` must be later than the annotation `industry-fusion.com/topics-reset-at` of the statementset. `flink-deploy` sets it after it recreated the KafkaTopics (`Makefile:177-178`), and the fresh resync after it emptied the three topics (#1035, D4). A checkpoint from before holds offsets and verdicts the topics no longer have.
3. **Replayable:** `now - completedAt + RESTORE_MARGIN` must be below the smallest `retention.ms` of the topics the job reads, read from Kafka at that moment (`kafka-configs.sh --describe --all`). With the defaults that is 1 h (`iff.ngsild.attributes` and the constraint topics) minus a margin of 10 min. `RESTORE_MARGIN` covers the time to stop and start; it can be overridden.
4. The newest remaining candidate is restored. If none is left, the resync exits non-zero naming for each candidate why it was refused (fingerprint, before the topics reset, too old by how much), or that none is recorded, and changes no alert, job or topic. The message names `make shacl-resync REPLACE=fresh` as the way that always works.

Then the steps of #1035 run as with a fresh job, except that the topics are not emptied: stop (delete the resource; the cancel keeps the retained checkpoints), close, reset Core Services, start (create the saved resource with `spec.restoreFrom` set and `status.checkpoints` carried over; wait until it runs, `status.restoredFrom` names the path, and its readers hold their partitions), re-snapshot, processed, end degraded.

*Why replay is needed although a re-snapshot follows:* the re-snapshot publishes every entity and attribute that exists, so changes and creations in the gap are covered either way. A delete in the gap is not: it reaches the validation only as a change record (Context). If that record is gone, the restored state keeps the deleted entity's pinned rows (07f3abbe, `'0d'`) and its alerts. So the rule is: a checkpoint is restorable only while every topic the job reads still holds every record since the checkpoint; the re-snapshot covers the rest.

*After the restore:* the restored state equals the state of a job that kept running from that checkpoint and then read the gap. The #1036 review measured that, with the validation running, closing the SHACL alerts, resetting Core Services and a re-snapshot bring back every alert still violated (the state TTL passes unchanged results on again). The restore needs no other alert step.

*Alternatives:*
- **Restore the newest checkpoint without checks** and let the re-snapshot repair it. It repairs updates, not deletes.
- **Let the resync take a fresh checkpoint first** (`POST /jobs/<id>/checkpoints`). With a running job, a restore from it changes nothing but the job ID; with a stopped or lost job there's no job to ask.

### D7: Storage is pruned by the resync

Flink never deletes a retained checkpoint. After a successful resync (any `REPLACE`), the resync deletes, through a short-lived Kubernetes Job with the Flink image and the cluster's S3 settings, the directories `<dir>/<ns>-<name>/<fingerprint>/<job-id>` that no recorded entry of the current fingerprint references, except those of the running job and of a job restored from until the running job completed its first checkpoint (`NO_CLAIM`). It removes the matching entries from `status.checkpoints`. Directories of other fingerprints are deleted when they are older than the largest retention of the read topics.

*Alternatives:* an object-store lifecycle rule (seaweedfs and other S3 stores differ, and it knows nothing of the running job); leaving it to the operator (it runs for every statementset, and deleting data is a step an operator should not take on a timer).

### D8: Defaults and opting out

`CHECKPOINT ?= true` makes checkpointing the default for the validation; `CHECKPOINT=false` builds it as today, and `REPLACE=checkpoint` then refuses because `status.checkpoints` stays empty. `shacl-constraints` keeps building without.

### D9: Measuring the cost

On the e2e KMS (`tests/e2e-kms`) deployed by `test-flink-e2e`, with checkpointing at 10 s, 1 min and 5 min, for 15 minutes each with the e2e traffic and one re-snapshot: from `/jobs/<id>/checkpoints` the `state_size`, `checkpointed_size`, `end_to_end_duration`, `alignment_buffered` and the number of failed checkpoints; from the job's vertices `busyTimeMsPerSecond` and `backPressuredTimeMsPerSecond`; the size of the fingerprint directory in the object store; and the time from a re-snapshot to the last alert in Alerta, compared with checkpointing off. Once more with incremental off. The results, with the number of tasks, go into the shacl2flink README, and set the default interval. A deployed KMS with 223 tasks is measured the same way where one is available; its numbers are stated without naming its model.

### Dependency on #1035

`make shacl-resync`, its steps and `shacl2flink/alert-resync` come from #1035 (PR #1036), which isn't archived; `openspec/specs/shacl2flink/alert-resync` doesn't exist on `main`. This change therefore adds its resync rules to the new capability (*The resync chooses a checkpoint*) and modifies no requirement of `alert-resync` yet. Once #1035 is archived, this change gets a MODIFIED delta of *Restore from a checkpoint*, replacing the refusal by:

> The resync SHALL accept, as the other kind of replacement, a restore of the validation job from the latest retained checkpoint that fits the deployed statementset, or from one given by its path, and SHALL keep the job's topics as they are. It SHALL refuse a checkpoint that doesn't fit, can't be replayed or predates the last reset of the topics before its first step, as `shacl2flink/validation-checkpoints` states.

with the scenario *Not supported yet* replaced by *Refused* (no fitting checkpoint: non-zero exit before the first step, nothing changed) and *Restored* kept. Implementation starts after #1036 is merged.

## Contracts

Every requirement of the four contract specs was read; the restore touches these:

- `contracts/context-broker`, *Entity changes are published through the entity store*: a delete is published once as a change, which is why D6 bounds the checkpoint age by the retention. The restore relies on it and changes nothing of it. *The entity store holds expanded JSON-LD* (scenario *Update of the broker on an existing store*: a re-snapshot publishes the same attributes) is what the re-snapshot after the restore relies on; unchanged. *Core Services writes no null values* and *Subscriptions and notifications*: Core Services is reset without state as in #1035; the restore adds no write to the broker. During the restore the validation writes only to its own topics and `iff.alerts.bulk`; the broker receives no write it wouldn't get from a running validation. *What the platform doesn't rely on*: the restore uses no broker topic or API.
- `contracts/opcua-live-data`, *Only values are delivered*: a value not delivered leaves the broker's last value, which the re-snapshot publishes; the restore doesn't depend on device traffic. *The chain is verified automatically*: the chain test doesn't cover the validation; unchanged.
- `contracts/typed-literals`, *Documents passed on keep their declared types*: the checkpointed state holds what the bridge published, so restored values keep their types; no requirement is touched.
- `contracts/kms-package`, *The package digest identifies the content*: D4 doesn't use the digest, since the job graph depends on more than the package; a new package version gives a new fingerprint exactly when it changes what is submitted, and one that doesn't leaves the checkpoints usable. No requirement is touched.

No contract names the validation's topics or their retention, or what the bridges and Core Services may assume about replays. The restore relies on the retention of `iff.ngsild.attributes`, `iff.ngsild.entities`, `iff.rdf` and the constraint topics, read at run time (D6) rather than assumed. The alerta-bridge and Core Services see a restored validation as one that kept running; the replays they get are those of #1035. None is broken; no contract delta is needed. Whether the topics and their retention should become a contract of their own is an open question.

## Conflicts with existing specifications

- `helm/platform-watchdog`, *Repair of an inconsistent state*, names "the latest checkpoint taken before the state went stale" as a way to restore. With D6 such a checkpoint is restorable only while it is younger than the read topics' retention. The text says the checkpoint *could* restore and stays true; whether the watchdog should name only one young enough is an open question, not changed here.
- `helm/platform-watchdog`, *When the state was emptied*: a restore by the resync is a start that restored a checkpoint, so the watchdog doesn't count it as emptied. That is the intended reading; unchanged.
- #1035 D2 makes `RESTORE_FROM` mandatory for `REPLACE=checkpoint`; this change makes it optional (latest fitting). #1035 D5 says externalization is disabled; it was verified on a Core Services job, which the Kubernetes operator submits with retention on (Context). Neither is a spec conflict on `main`; the resync's README follows this change.
- `FlinkSqlServicesOperator/README.md` describes `updateStrategy: savepoint`; it is updated for the field and the fixed path.

## Risks / Trade-offs

- [Checkpoints slow the validation or delay alerts] → Measured before the default interval is set (D9); `min-pause` bounds the share; `CHECKPOINT=false` opts out.
- [Storage grows with each job] → Pruned by the resync (D7); a platform that never resyncs keeps at most `num-retained` per job, plus the last ones of each cancelled job; the README says so.
- [The fingerprint misses something that breaks compatibility] → D3 makes Flink refuse unclaimed state; the e2e test checks the refusal after a KMS change.
- [A retention shorter than assumed] → Read from Kafka at the decision, not configured.
- [The record in the status is lost with the resource] → Then nothing is restorable and the resync says so; `REPLACE=fresh` works.
- [A restore takes longer than a fresh start for a large state] → D9 measures the restore time; the resync waits with its own time limit.

## Migration Plan

Apply the new CRD (`install_operators.sh`) and roll out operator and gateway before deploying a statementset built with this change; an older operator ignores `restoreFrom` and the fingerprint directory, and the resync refuses because `status.fingerprint` is missing. The next `flink-deploy` changes the settings, so the validation starts fresh once, as on every deploy; its checkpoints count from then. Rollback: build with `CHECKPOINT=false`.

## Open Questions

- The default interval and `num-retained` wait for D9.
- Should the watchdog name a checkpoint only when it is young enough to be restored (*Repair of an inconsistent state*)?
- Should the validation's topics and their retention become a contract (`contracts/…`), since the restore depends on them?
- Does a path set as `execution.state-recovery.path` on the table config of a `flink run --python` job also restore? If it does, `-s` and the setting must not disagree; a unit test of the gateway pins `-s` as the only way.
