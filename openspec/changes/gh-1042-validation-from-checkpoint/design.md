# Design

## Context

**How the validation is built.** `create_sql_checks_from_shacl.py` writes the BeamSqlStatementSet `shacl-validation` with `lib/utils.py` `create_statementmap` (`create_sql_checks_from_shacl.py:124`, `lib/utils.py:580-631`). Its `sqlsettings` are a list of one-key maps: upsert materialization, mini-batch off, `execution.savepoint.ignore-unclaimed-state: true` (`:615`), object reuse, parallelism and idle timeout from helm values, RocksDB with its options, and `table.exec.state.ttl` from `shacl_state_ttl` (`lib/configs.py:86`, `{{.Values.flink.shaclTtl}}`, `3600 s` in `helm/values.yaml.gotmpl:123`; the dedup views use `viewTtl`, also `3600 s`, `:122`). Commit 07f3abbe pins the joins and count accumulators with `STATE_TTL ... '0d'` hints, so that state is bounded by the live model; the dedup views keep the TTL. Checkpointing is opt-in: `CHECKPOINT ?= false` (`Makefile:32`) maps to the switch `-p` (`Makefile:44-48`, `:76`), which adds only `execution.checkpointing.interval: {{ .Values.flink.checkpointInterval }}` (`lib/utils.py:627-628`; `1 min` in `values.yaml.gotmpl:85`, used by no other component). `make helm` copies the output into `helm/charts/shacl/templates` (`Makefile:79-85`); `flink-deploy` deletes the KafkaTopics of `output/ngsild-kafka.yaml` and `output/rdf-kafka.yaml` before `helmfile apply` (`Makefile:174-186`). The statementset carries `updateStrategy: none` (`lib/utils.py:630`).

**What the validation reads.** Built from the e2e KMS (`make build` with `tests/e2e-kms`, output not committed), the statementset lists the tables `alerts-bulk`, `attributes`, `attributes-insert`, `constraint-combination-table`, `constraint-table`, `constraint-trigger-table`, `entities`, `rdf` and the views `attributes-view`, `entities-view`. Its statements:
- read `attributes_view` and `entities_view`, deduplicating views over `iff.ngsild.attributes` and `iff.ngsild.entities` (`kafka`, `latest-offset`, `create_core_tables.py:216-220`, `create_ngsild_tables.py:72-75`);
- read `rdf`, `iff.rdf` (`upsert-kafka`, earliest);
- read and write `constraint_trigger_table`, `iff.ngsild.flink.constraint_trigger_table` (`upsert-kafka`);
- read `constraint_table` and `constraint_combination_table`, which are `postgres-cdc` tables on the database, not topics (`create_ngsild_tables.py:136`, `:205`);
- write `alerts_bulk`;
- don't use `attributes_insert` (`iff.ngsild.attributes_insert`, retention 10 s): a listed table that no statement reads gets no source.

So the topics the job reads are `iff.ngsild.attributes`, `iff.ngsild.entities`, `iff.rdf` and `iff.ngsild.flink.constraint_trigger_table`. #1035's Context counts all three constraint tables as topics the job reads back; for this build only the trigger table is.

**Their retention.** `iff.ngsild.attributes` takes `kafkaBridge.debezium.attributesTopicRetention` (`helm/values.yaml.gotmpl:307-309`, in `kafka-bridges/templates/bridge-topics.yaml:39`). `iff.ngsild.entities` has two KafkaTopic definitions: the kafka-bridges chart with `attributesTopicRetention` (`bridge-topics.yaml:56`) and shacl2flink's `ngsild-kafka.yaml` with `entityTopicRetention` (`values.yaml.gotmpl:302-304`, `lib/configs.py:38`, `create_ngsild_tables.py:60`). Who owns it is #1038. `iff.ngsild.flink.constraint_trigger_table` takes `entityTopicRetention` as well (`ngsild-kafka.yaml`). `iff.rdf` takes `rdf_retention_ms = 86400000`, fixed in `lib/configs.py:55` (`create_rdf_table.py:164`). The helm values fall back to `3600000` ms when the environment doesn't set them; `helm/environment/default.yaml` sets none, and `helm/environment/production.yaml:89-97` sets them to `28800000` (8 h). Since #978, `segment.ms` is `max(retention.ms, 1 h)` (`lib/utils.py:671`, `bridge-topics.yaml:24,40,57`). Kafka keeps a record at least `retention.ms` and drops it at most `retention.ms + segment.ms` plus the check interval later; only the retention is guaranteed.

**State TTL and refreshes.** Flink's state TTL works on processing time only: each entry keeps the time it was last written, and an entry older than the TTL is treated as absent when read, also after a restore, so the time a job was down counts (Flink 1.20 "State TTL"). The watchdog's own model states what an expired dedup row does (`platform-watchdog.yaml:28-35`): a key fed again after its state expired enters the pinned join as a second row, and no refresh removes it. The `kafka-connect-restart` CronJob refreshes every key by a Debezium re-snapshot: it restarts the Connect pods once they are older than `ttl/2 - max(60 s, ttl/100)` of the TTL deployed on `shacl-validation`, with `flink.ttl` as fallback (`helm/charts/kafka/templates/connect-restarter.yaml:57-74`), so a key's last refresh is at most about `ttl/2 + 240 s` old when the job runs normally (watchdog *Late refresh*).

**The Flink session cluster.** `helm/charts/flink/templates/flink-deployment.yaml` runs Flink `v1_20` and sets `state.checkpoints.dir: s3://<bucket>/checkpoints`, `state.savepoints.dir: s3://<bucket>/savepoints` (`:82-83`), Kubernetes HA with `high-availability.storageDir` on the same bucket (`:84-85`), `restart-strategy: exponential-delay`, and `state.backend.incremental: false` (`:43`). The bucket is served by seaweedfs.

**The operator.** `FlinkSqlServicesOperator/beamsqlstatementsetoperator.py`:
- `create` (`:93`) sets `status.state: INITIALIZED` and `job_id: None`; the timer `monitor` (`:268`) builds the submission `{sqlsettings, tables, views, sqlstatementset}` and posts it to the gateway (`deploy_statementset`, `:534`). If Flink already runs a job of that name, it adopts it instead (`:555`).
- `update` (`:178`) runs on every spec change. With `updateStrategy: none` it cancels the job (`PATCH /jobs/<id>`, `flink_util.py:73-80`); with `savepoint` it calls `POST /jobs/<id>/stop` (`flink_util.py:83`) and keeps the location in `status.location` (`:258`).
- `create_sets` (`:476`) appends that location as the string `SET execution.savepoint.path = '...';` (`:499`). Nothing clears `status.location` afterwards: `create` resets state and job ID only, so every later deployment of the resource would carry the same path.
- The CRD (`FlinkSqlServicesOperator/kubernetes/crd.yml`, v1alpha4) has `sqlsettings`, `updateStrategy` (`none`, `savepoint`), `refreshInterval`, and no field for a start checkpoint. The status has no subresource and keeps unknown fields. `helm/install_operators.sh:66` applies the CRD.

**The gateway.** `FlinkSqlGateway/gateway.js` writes the posted body to `data/SQL-structures.json` and runs `/opt/flink/bin/flink run --python job.py` (`:45`, `:99-104`), splitting the command at spaces (`:62`). `submitjob/job.py:33-41` reads each entry of `sqlsettings` as a map (`set.keys()`) and sets it on the table config. A string entry, as `create_sets` writes for a savepoint, fails there. Read from the code, not run.

**Sources on a restore.** A restored job ignores the startup mode and continues each source from the position in the checkpoint: a Kafka partition from its offset, a `postgres-cdc` table from its log position on the database's replication slot (Flink's Kafka connector and Flink CDC documentation). If a restored Kafka offset has been deleted, the source falls back to its reset strategy, which for a latest-offset source is the end of the partition: the records in between are skipped without an error.

**The re-snapshot.** Both Debezium connectors run with `snapshotMode: always`. A snapshot publishes every row that exists; it publishes no delete for a row that is already gone. A delete reaches the validation only as the change record of that moment (`contracts/context-broker`, *Entity changes are published through the entity store*).

**How the watchdog sees a restore today.** `helm/charts/alerta/templates/platform-watchdog.yaml:235-285` reads `start-time`, `/checkpoints` (`counts.completed`, `latest.restored.restore_timestamp`) and the exception history of the job, and the JobManager pod's start. A job start, a failover or a JobManager restart empties the state unless `restore_timestamp` is at or after it; a start that restored a checkpoint keeps the previous reset and its cause (`:261-264`). A latched inconsistency ends only when the state is emptied after it (`:345-349`). The repair note (`:423-434`) picks the latest checkpoint in Flink's history completed before the state went stale and says it "brings a consistent state back, if it is retained and the topics still hold the records since". The watchdog keeps in its ConfigMap only the last complete refresh per connector (`<connector>.start`, `.done`), the reset, and the latch. Its Role may `get`/`list` beamsqlstatementsets and pods and `get`/`patch` its ConfigMap (`:11-27`).

**Flink 1.20 semantics** (documentation of Flink 1.20, "Checkpoints", "Savepoints", "State Backends", "State TTL", "Configuration"; the cluster runs 1.20.4):
- `execution.checkpointing.interval` turns checkpointing on; `EXACTLY_ONCE` is the default mode. `execution.checkpointing.externalized-checkpoint-retention: RETAIN_ON_CANCELLATION` keeps the latest `execution.checkpointing.num-retained` checkpoints when the job is cancelled; Flink never deletes a retained checkpoint afterwards. Since 1.20 the checkpoint keys are `execution.checkpointing.dir`, `.num-retained` and `.incremental` (the `state.checkpoints.*` and `state.backend.incremental` names are deprecated aliases), and the restore keys are `execution.state-recovery.path`, `.ignore-unclaimed-state` and `.claim-mode` (aliases `execution.savepoint.*`). State backend and checkpoint storage can be set per job, as the validation already does for RocksDB.
- A checkpoint is written to `<dir>/<job-id>/chk-<n>` with its `_metadata`; incremental RocksDB checkpoints share files under `<dir>/<job-id>/shared`. In the default claim mode `NO_CLAIM` the restored job doesn't own the snapshot, and its first checkpoint is a full one.
- A checkpoint is in the state backend's native format: it restores only into the same state backend kind (a savepoint in the canonical format can switch backends). A RocksDB checkpoint restores whether the new job writes incremental checkpoints or not.
- `flink run -s <path>` (`--fromSavepoint`) restores a job from a savepoint or a retained checkpoint; `-n` (`--allowNonRestoredState`) lets it start while state of the snapshot has no operator to go to; without it, the start fails.
- A SQL job's operator IDs are derived from its plan. Flink guarantees no state compatibility for a changed query or another Flink version. A checkpoint fits only the same statementset on the same Flink; after a KMS change only a fresh start works.
- `POST /jobs/<id>/stop` stops with a savepoint; `PATCH /jobs/<id>` cancels without one, keeping retained checkpoints.

**Verified on a local k3d platform** (read-only `kubectl get`/`exec`, Flink REST through the JobManager pod, the seaweedfs filer's listing; only names and numbers printed):
- `/config` reports `flink-version` `1.20.4`. `/jobmanager/config` reports `state.checkpoints.dir` `s3://flink/checkpoints`, `state.savepoints.dir` `s3://flink/savepoints`, `high-availability` `kubernetes` with storage `s3://flink/recovery`, `state.backend.incremental` `false`.
- `/jobs/overview` lists one job, `Core Services`, `RUNNING`, 10 tasks; no `shacl-validation` was deployed (`kubectl get bsqls` empty). The validation of a deployed KMS has been reported with 223 tasks; the e2e KMS is smaller.
- `/jobs/<id>/checkpoints/config` of Core Services: interval `9223372036854775807` (off), externalization enabled with `delete_on_cancellation: false`, state backend HashMap. That retention comes from the job's submitter (the Flink Kubernetes operator); the validation is submitted by `flink run` in the gateway and must set it itself.
- The filer lists `/buckets/flink/recovery/flink-deployment`; `/buckets/flink/checkpoints` and `/buckets/flink/savepoints` don't exist: no job has ever written a checkpoint or savepoint.
- Kafka 3.9: `iff.ngsild.attributes` has `retention.ms` and `segment.ms` `3600000` (KafkaTopic); `iff.ngsild.entities` and `iff.rdf` had `retention.ms` `86400000` and `segment.ms` `604800000`, not as KafkaTopic resources, since no shacl release was deployed. The retention a topic has can differ from the helm value, so the resync and the watchdog read it live (D10).

## Goals / Non-Goals

**Goals:**
- The validation takes retained, exactly-once checkpoints by default, at an interval and in a storage that are configurable.
- A statementset can name a checkpoint or savepoint to start from, and the job starts from it or not at all.
- Whether a recorded checkpoint can still be restored is computed from live values (TTL, refreshes, retention, backlog), not from a configured window.
- `make shacl-resync REPLACE=auto` restores when a checkpoint passes and starts fresh otherwise; `REPLACE=checkpoint` restores or refuses, with the reason per candidate.
- The watchdog reports until when the newest restorable checkpoint can be restored, and names the repair that fits the state.
- The refresh period is a value of its own; its default keeps today's effective period.
- A guide states how to size TTL, refresh period, checkpoint interval and retention for a wanted outage tolerance, and what each costs.
- A restored job ends with the same open alerts as a fresh one: those of the constraints violated now.

**Non-Goals:**
- Changing the defaults of the TTL or the topic retention; a fixed restore window; refusing a deployment for its sizing.
- Keeping state across a KMS change, a Flink upgrade or `flink-undeploy`.
- Restoring Core Services; changing the resync's alert steps.
- Running a restore without a person starting the resync.

## Decisions

### D1: Retained checkpoints, not periodic savepoints or a savepoint at each resync

The validation's `sqlsettings` get, when built with checkpointing (now the default, `CHECKPOINT ?= true`):
`execution.checkpointing.interval: {{ .Values.flink.checkpointInterval }}`, `execution.checkpointing.mode: EXACTLY_ONCE`, `execution.checkpointing.externalized-checkpoint-retention: RETAIN_ON_CANCELLATION`, `execution.checkpointing.num-retained: {{ .Values.flink.checkpointsRetained }}` (new, default 3), `execution.checkpointing.incremental: true` and `execution.checkpointing.min-pause` of half the interval. The interval keeps its existing value `flink.checkpointInterval` (only shacl2flink uses it) until the measurement (D9) sets the default. The cluster's `state.backend.incremental: false` stays for other jobs.

A retained checkpoint survives every way the job ends: the delete handler's cancel, a lost JobManager, the resync's stop. With checkpointing on, Flink also restores a failed-over task and, through Kubernetes HA, a restarted JobManager from the latest checkpoint by itself; the watchdog judges those restores like any other (D13).

*Exactly-once:* the count accumulators and joins work on retracting changelogs; replaying a record whose effect is already in the state (at-least-once after a restore) would count it twice. The sinks stay as they are; their upserts by key are idempotent.

*Alternatives:*
- **Periodic savepoints** (`POST /jobs/<id>/savepoints` by a CronJob). Full, canonical snapshots, more costly per run, and one more component and schedule; checkpoints are already taken by Flink.
- **Stop-with-savepoint at each resync.** Gives a snapshot only of the moment of the stop. It can't serve a job that was lost, and every resync would pay a full snapshot. A savepoint path remains usable through the same field (D2).
- **Turning on checkpointing cluster-wide.** It would change Core Services and every other job.
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

Before each submission the operator computes a fingerprint: SHA-256 (first 16 hex digits) of the canonical JSON of the submission (settings, table DDLs, views, statements) without `restoreFrom` and without the `execution.checkpointing.*` settings, plus the Flink version from `/config`. Deprecated keys are mapped to their 1.20 names first, so `state.backend.incremental` counts as `execution.checkpointing.incremental`. The operator sets `execution.checkpointing.dir` to `<state.checkpoints.dir>/<namespace>-<name>/<fingerprint>` unless the spec sets it, reading `state.checkpoints.dir` from `/jobmanager/config`, and writes `status.fingerprint`. Flink adds `<job-id>/chk-<n>` below. Every checkpoint under one fingerprint directory fits a job with the same fingerprint; a KMS change or a Flink upgrade gives a new directory; a change of the interval or the retention doesn't invalidate older checkpoints.

*The state backend belongs to the fingerprint.* `state.backend` and its RocksDB options are settings outside `execution.checkpointing.*`, so a change from RocksDB to the heap backend, or of a RocksDB option, gives a new fingerprint: a checkpoint is in the backend's native format and restores only into the same kind. Incremental or full is a checkpointing setting and stays out: a RocksDB checkpoint restores whichever way the new job writes its own. Changing a RocksDB option such as the write buffer size would not break a restore, but it is kept in, to stay on the side of a fresh start; the e2e test switches incremental to show that it is out (task 7.6).

*Why the rendered submission, not the KMS package digest:* the job graph also depends on helm values (parallelism, TTL, topic names) and on the table definitions; two packages with different digests can generate the same SQL. The submission is what Flink compiles.

*Alternatives:*
- **Let Flink decide** (D3 alone). A changed query that keeps the old operators and adds new ones would start with part of the verdicts.
- **A fingerprint computed by shacl2flink at build time.** It can't see helm values rendered later.

### D5: The operator records the checkpoints; the resync reads them

While a job runs, the operator reads `/jobs/<id>/checkpoints` at its timer and keeps in `status.checkpoints` the latest completed checkpoints of the resource's jobs, newest first, at most `checkpointsRetained` per job and five in all: `path` (`external_path`), `completedAt` (`latest_ack_timestamp`), `jobId`, `fingerprint`, and `offsets`: per read topic, the sum over its partitions of the job's source position (`KafkaSourceReader.topic.<t>.partition.<n>.currentOffset`), read at the same timer run. These are read up to one timer interval (10 s) after the checkpoint, so they can be a little ahead of the checkpointed offsets; D10 adds that interval's traffic to the backlog. Entries stay when the job ends, because they are what a restore needs. A resource created anew starts with no entries; `create` clears them, the same as `status.location`, which also stops reusing a savepoint path.

The resync works from this record, not by listing the object store: production may run another S3 store, and the resync then needs no object-store credentials. The record lives in the statementset, so it goes with the deployment it describes.

*Alternatives:* list `<dir>/<ns>-<name>/<fingerprint>/*/chk-*/_metadata` in the object store (needs credentials and a client in the resync; the age is only the object time); a ConfigMap per statementset (one more object to own, and the operator is generic).

### D6: How `shacl-resync` picks a checkpoint: `REPLACE=checkpoint` and `REPLACE=auto`

Before its first step the resync reads the deployed statementset, the watchdog's ConfigMap and Kafka, and goes through the candidates:

1. **Candidates:** `status.checkpoints` entries whose `fingerprint` equals `status.fingerprint`. With `RESTORE_FROM=<path>`, only the entry with that path; a path that isn't recorded is refused ("not a recorded checkpoint of this statementset").
2. **Taken after the last reset of the topics:** `completedAt` must be later than the statementset annotation `industry-fusion.com/topics-reset-at`. `flink-deploy` sets it after it recreated the KafkaTopics (`Makefile:177-178`), and the fresh resync after it emptied the trigger topic (#1035, D4). A checkpoint from before holds offsets and verdicts the topics no longer have.
3. **Taken while the state was consistent:** the watchdog marks a checkpoint completed while it held a latched inconsistency (D13). A marked one is refused, since its pinned state already holds the duplicates, whatever the rules below say.
4. **The two rules of D10**, computed now: the state rule and the replay rule.

The newest candidate that passes is restored.
- With `REPLACE=checkpoint`, if none passes, the resync exits non-zero and changes no alert, job or topic. For each candidate it names why: fingerprint, before the topics reset, taken while inconsistent, or the rule it fails with its numbers (refresh, TTL, estimated catch-up and margin; age, topic and retention). If none is recorded, it says so. The message names `REPLACE=fresh` and `REPLACE=auto`.
- With `REPLACE=auto`, if none passes, the resync runs as `REPLACE=fresh`. Its first line says which replacement it does and why: the checkpoint and until when it passes, or for each candidate the reason it didn't.

Then the steps of #1035 run as with a fresh job, except that on a restore the topics are not emptied: stop (delete the resource; the cancel keeps the retained checkpoints), close, reset Core Services, start (create the saved resource with `spec.restoreFrom` set and `status.checkpoints` carried over; wait until it runs, `status.restoredFrom` names the path, and its readers hold their partitions), re-snapshot, processed, end degraded. The rules are computed once, before the first step. The margin covers the time from there to the restored job reading.

*Why replay is needed although a re-snapshot follows:* the re-snapshot publishes every entity and attribute that exists, so changes and creations in the gap are covered either way. A delete in the gap is not: it reaches the validation only as a change record (Context). If that record is gone, the restored state keeps the deleted entity's pinned rows (07f3abbe, `'0d'`) and its alerts.

*After the restore:* the restored state equals the state of a job that kept running from that checkpoint and then read the gap. The #1036 review measured that, with the validation running, closing the SHACL alerts, resetting Core Services and a re-snapshot bring back every alert still violated. The restore needs no other alert step.

*Alternatives:*
- **Only `REPLACE=checkpoint` and `REPLACE=fresh`.** A person would have to try a restore, read the refusal and start again; `auto` gives one command for "restore if you can".
- **`REPLACE=auto` as the default of the resync.** The default stays `none` (#1035): a resync that replaces the job only when asked.
- **Restore the newest checkpoint without checks** and let the re-snapshot repair it. It repairs updates, not deletes, and not expired keys.
- **Let the resync take a fresh checkpoint first** (`POST /jobs/<id>/checkpoints`). With a running job, a restore from it changes nothing but the job ID; with a stopped or lost job there's no job to ask.

### D7: Storage is pruned by the resync and by `flink-deploy`

Flink never deletes a retained checkpoint. A short-lived Kubernetes Job with the Flink image and the cluster's S3 settings (`make shacl-checkpoints-prune`) deletes, under `<dir>/<ns>-<name>/`:
- directories of other fingerprints, and of jobs of the deployed fingerprint that no recorded entry references;
- checkpoints completed before `topics-reset-at`;
- never the running job's directory, nor the directory of the job it was restored from until it completed its first checkpoint (`NO_CLAIM`).

It removes the matching entries from `status.checkpoints`. The resync runs it after every successful run; `flink-deploy` runs it after the new job completed its first checkpoint. `flink-deploy` recreates the KafkaTopics (`Makefile:177-178`) and sets `topics-reset-at`, so no checkpoint from before a deploy can be restored. After a KMS change, the old fingerprint's directories go with that deploy, without waiting for a resync. A job that runs for long without a deploy or a resync keeps only `num-retained` checkpoints, as Flink does; only cancelled jobs leave more.

*Alternatives:* an object-store lifecycle rule (seaweedfs and other S3 stores differ, and it knows nothing of the running job); leaving it to the operator (it runs for every statementset, and deleting data is a step an operator should not take on a timer); pruning only in the resync (old fingerprints would stay until a resync that may never come).

### D8: Defaults and opting out

`CHECKPOINT ?= true` makes checkpointing the default for the validation; `CHECKPOINT=false` builds it as today. `REPLACE=checkpoint` then refuses and `REPLACE=auto` starts fresh, because `status.checkpoints` stays empty. `shacl-constraints` keeps building without. The TTLs (`shaclTtl`, `viewTtl` `3600 s`) and the topic retention stay as they are. With them a checkpoint is restorable for well under an hour after it was taken (D10); a platform that wants more sizes them by the guide (D14).

### D9: Measuring the cost and calibrating the estimate

On the e2e KMS (`tests/e2e-kms`) deployed by `test-flink-e2e`, with today's settings and checkpointing at 10 s, 1 min and 5 min, for 15 minutes each with the e2e traffic and one re-snapshot:
- from `/jobs/<id>/checkpoints`: `state_size`, `checkpointed_size`, `end_to_end_duration`, `alignment_buffered` and the number of failed checkpoints;
- from the job's vertices: `busyTimeMsPerSecond` and `backPressuredTimeMsPerSecond`;
- the size of the fingerprint directory in the object store;
- the time from a re-snapshot to the last alert in Alerta, compared with checkpointing off.

Once more with incremental off. The same is then measured for one example sizing of the guide (D14), TTL `1 d` and retention `1 d` on the read topics: state size and the RocksDB live data size (`state.backend.rocksdb.metrics` turned on for the run), the size on disk of each read topic (`kafka-log-dirs.sh --describe`), and Core Services' resend after a reset.

For the catch-up estimate (D10), the restore tests record the restore time and the time the restored job needed to process its backlog and the re-snapshot, against the estimate. They set `flink.restoreThroughput`, the start allowance and the margin so that the estimate is above the measured time in every run. The results, with the number of tasks, go into the shacl2flink README and set the default interval. A deployed KMS with 223 tasks is measured the same way where one is available; its numbers are stated without naming its model.

### D10: Restorability is computed from live values, by two rules

There is no configured restore window. For each candidate, with `c` its completion time, `r` the start of the last complete refresh of the connectors before `c`, and `now` the time of the decision:

- **State rule:** `now − r + catch-up + margin < TTL`, with the smaller of the deployed `shaclTtl` and `viewTtl` (read from the deployed statementset, as the watchdog reads the TTL today). Flink's state TTL works on processing time, so the time between checkpoint and restore counts. A key last refreshed at `r` expires at `r + TTL`, whether the job runs or not. If the restored job reads it again after that, through the backlog or the re-snapshot, its dedup row has expired and the key enters the pinned join as a second row (Context). The rule must still hold when the restored job has caught up and the re-snapshot after the restore has refreshed every key, hence the catch-up.
- **Replay rule:** `now − c + margin < retention` for every topic the job reads, each with the `retention.ms` Kafka reports now (`kafka-configs.sh --describe --all`), not the helm value. Kafka keeps a record at least that long, so every record since the checkpoint, deletes included, is still there.

`r` comes from the watchdog, which follows the refreshes: it records it per checkpoint in its ConfigMap (D13). A checkpoint without that record fails the state rule ("refresh before the checkpoint unknown"). The read topics come from the statementset annotation `industry-fusion.com/read-topics`, which shacl2flink writes from the tables the generated statements read (Context).

**Catch-up estimate:** `catch-up = start + (backlog + snapshot) / throughput`.
- `backlog` is, summed over the read topics, the end offsets now (`kafka-get-offsets.sh`) minus the `offsets` recorded with the checkpoint (D5), plus 10 s of the topics' recent write rate for the timer lag of that record. A topic with no recorded offsets fails the state rule.
- `snapshot` is the number of records the job's sources read during the last complete refresh. The watchdog records it as the difference of the job's source `numRecordsIn` between the refresh's start and end. If it is missing, the rule fails.
- `throughput` is `flink.restoreThroughput` (records per second, a helm value written as an annotation). If the watchdog has seen a lower records-in rate of the job's sources during a refresh, it takes that lower rate.
- `start` is `flink.restoreStartAllowance`, for submitting the job and restoring its state.
- `margin` is `flink.restoreMargin`.

Their defaults are first guesses (`500` records/s, `2 min`, `5 min`); D9's restore tests calibrate them so the estimate stays above the measured catch-up. The estimate errs on the side of a fresh start: a too high catch-up only means `auto` starts fresh where a restore would have worked.

*Until when:* a candidate passes the state rule until `t_a = r + TTL − margin − catch-up(t_a)`. The backlog grows with the write rate `w` of the read topics, so `catch-up(t) = catch-up(now) + w·(t − now)/throughput`, which gives `t_a = now + (r + TTL − margin − now − catch-up(now)) / (1 + w/throughput)`. It passes the replay rule until `t_b = c + min(retention) − margin`. It is restorable until `min(t_a, t_b)`. The watchdog reports this time (D13), and `auto` names it.

With today's defaults (TTL 1 h, refresh period 30 min) a checkpoint taken just after a refresh is restorable for about 1 h minus catch-up and margin; one taken just before the next refresh, for about half of that. Failovers and JobManager restarts restore within seconds and aren't limited by this. Flink restoring by itself after a longer outage is judged by the watchdog with the same state rule (D13).

*Alternatives:*
- **A configured restore window with deploy-time checks** (the previous version of this change). It fixes one number for every platform, and needs TTL and retention defaults to match. The rules work with whatever a platform runs, and the guide (D14) says how to size them.
- **Only the age against the shortest retention.** It ignores the TTL, so a restore after an hour would bring back expired keys as duplicates.
- **A catch-up of zero.** The keys of the backlog and of the re-snapshot are read after the decision, so their expiry must be counted at the time they are read.
- **Measuring the checkpointed offsets from the checkpoint's `_metadata`.** Exact, but needs object-store access and Flink's metadata format in the resync; the offsets read with the checkpoint are close enough given the margin.

### D11: The refresh period is its own value

The restarter derives its period from the TTL: it restarts the Connect pods once they are older than `ttl/2 − max(60 s, ttl/100)` (`connect-restarter.yaml:67-73`). With today's TTL of 1 h that is about 30 min. A platform that raises the TTL for a longer outage tolerance (D14) would also stretch the refresh, and drift would be swept more slowly. So the restarter takes a new value, `flink.refreshPeriod`, default `1800 s`, and restarts the pods once they are older than `min(refreshPeriod, ttl/2) − max(60 s, ttl/100)`. With the defaults that is the same `1740 s` as today. The cap at `ttl/2` keeps today's guarantee that a refresh comes before the TTL; the restarter logs when it applies. The watchdog's *Late refresh* measures against the same effective period plus 240 s (delta). shacl2flink writes `refreshPeriod` as an annotation of the statementset, so the restarter and the watchdog read the deployed value, as they do for the TTL.

*Alternatives:* keep `ttl/2` (a longer TTL slows the refresh); no cap (a refresh period set above the TTL would make every key expire between refreshes).

### D12: No deployment check

The deployment isn't refused for its sizing. Whether a checkpoint can be restored depends on the time since its refresh, the backlog and the retention at the moment of the restore. A check at deploy time can only compare configured numbers and would refuse working deployments that simply don't need restores. The resync and the watchdog compute it from live values (D10, D13); the guide (D14) says what to set for a wanted tolerance.

*Alternative:* a deploy check against a configured window (previous version). Dropped with the window.

### D13: The watchdog reports restorability and names the repair that fits

Against `helm/platform-watchdog` on `main`:
- **Restored validation state (added).** When the job starts, fails over or is relaunched by a JobManager restart and restores a checkpoint, the state is not emptied, as today. The watchdog judges the restored state by the state rule at the restore: consistent when, at the time of the restore, less than the TTL had passed since `r` of that checkpoint, and inconsistent otherwise. To know `r`, it keeps in its ConfigMap, for each checkpoint listed in the statementset's status and for the latest one in Flink's history:
  - the start of the last complete refresh before its completion;
  - whether an inconsistency was latched then;
  - for the last complete refresh, the job's source `numRecordsIn` at its start and end, and the lowest records-in rate seen during it.

  It drops the keys of checkpoints no longer listed. For a restore it has no record of, it takes the checkpoint's completion less the effective refresh period plus 240 s.
- **Restorable checkpoint (added).** The watchdog reports, in the text of `ValidationConsistency` whenever the state isn't inconsistent, the newest recorded checkpoint that passes both rules and until when (`restorable until <time>`), or that none does and why. It computes this as the resync does (D10), with two differences, since it has no access to Kafka's broker:
  - The backlog is the running job's source positions minus the recorded offsets. A running job, also one started empty after a loss, reads at the end of the topics.
  - The retention is that of the topics' KafkaTopic resources, which needs `get`/`list` on `kafkatopics` in its Role. A read topic without a KafkaTopic resource is named as unknown, and the time is given for the state rule only. When no job runs, it says the restorability can't be assessed and that the resync computes it.
- **Repair of an inconsistent state (modified).** The repair names `make shacl-resync REPLACE=fresh`, with the reason: once the TTL has passed since the last refresh a checkpoint holds, a restore brings back expired keys, so no checkpoint taken before the state went stale can restore a consistent state. Checkpoints taken after it are marked and refused (D6.3). Today's note that such a checkpoint "brings a consistent state back" is wrong for this reason.
- **Rebuilding validation state (modified).** While the state is rebuilding after it was emptied, for example after the job was lost and started empty, the warning names `make shacl-resync REPLACE=auto`. It adds the checkpoint that would be restored and until when, or that it would start fresh and that the refresh rebuilds the state by its due time.
- **Late refresh (modified).** Measured against the effective refresh period plus 240 s instead of half the TTL plus 240 s (D11).

*Where `restorable until` is reported:* in `ValidationConsistency`, whose text already says how the validation state is and which checkpoint could help. A second, informational alert (say `ValidationRestore`) would be one more event to keep and close, and would contradict `ValidationConsistency` while the state is inconsistent. One alert keeps the state and what can be done about it in one place. The time in the text changes each run, which updates the alert in Alerta without raising a new one.

*Alternatives:*
- **Name `REPLACE=checkpoint` in the inconsistency repair when a checkpoint fits.** It names a repair that recreates the duplicates it should remove.
- **`REPLACE=checkpoint` with the path in the rebuilding warning.** The path can stop passing between the warning and the command; `auto` decides when it runs, and the warning still names the checkpoint and its time.
- **Leave the watchdog as it is.** It would report a restore after a long outage as consistent, since the refreshes during the outage complete in the Connect log while the restored state's keys expired.

### D14: Sizing guide

The shacl2flink README gets a section on sizing for an outage tolerance `D`, the longest time between a checkpoint and its restore that should still restore. It states, from D10:
- `TTL > D + refresh period + 240 s + catch-up + margin`, for both `shaclTtl` and `viewTtl`;
- the retention of every read topic `> D + margin`;
- checkpoint interval and refresh period small against `D`, since a checkpoint is up to one interval old when the job stops and its keys up to one refresh period plus 240 s older.

And what each costs:
- **TTL:** the dedup state of keys no longer refreshed (deleted entities, changed `datasetId`s) stays until the TTL. This ghost state grows the state size and keeps drifted rows longer, which the refresh doesn't sweep.
- **Retention:** Kafka disk, mostly for `iff.ngsild.attributes`, which carries all attribute traffic. Through #978 segments roll at the retention, so a record can stay up to twice the retention. Core Services, which reads it from the earliest offset, resends up to the retention to Scorpio after a reset.
- **Checkpoint interval:** checkpoint I/O to the object store and alignment time.
- **Refresh period:** Debezium snapshot load on the database and Kafka.

It gives today's defaults (a tolerance of about 20 minutes in the worst case, under an hour at best) and the example of D9 (TTL 1 d, retention 1 d) with the measured numbers.

### Dependency on #1035

`make shacl-resync`, its steps and `shacl2flink/alert-resync` come from #1035 (PR #1036), which isn't archived; `openspec/specs/shacl2flink/alert-resync` doesn't exist on `main`. This change therefore puts its resync rules into the new capability (*The resync chooses a checkpoint*) and modifies no requirement of `alert-resync` yet. Once #1035 is archived, this change gets a MODIFIED delta of *Restore from a checkpoint*, replacing the refusal by:

> The resync SHALL accept, as replacements, a restore of the validation job from the newest recorded checkpoint that is restorable as `shacl2flink/validation-checkpoints` states, or from one given by its path, keeping the job's topics, and an automatic choice that restores when a checkpoint is restorable and starts a fresh job otherwise. It SHALL refuse a restore from a checkpoint that isn't restorable before its first step.

with the scenario *Not supported yet* replaced by *Refused* (none restorable: non-zero exit before the first step, nothing changed) and *Restored* kept.

The watchdog has the same order. #1036 also modifies *Repair of an inconsistent state*, *Flink not readable*, *Rebuilding validation state* and *Late refresh*. This change's watchdog delta is written against `main` as it is now, so that it validates, and touches only *Repair*, *Rebuilding* and *Late refresh*, plus two added requirements. #1036 is merged and archived first. This change is then rebased: each MODIFIED requirement is copied again from the archived text, with #1036's resync steps and its "while a resync is marked" clause, and this change's sentence is added to it. *Flink not readable* isn't touched here. Implementation starts after #1036 is merged; the order is in the tasks.

## Contracts

Every requirement of the four contract specs was read again for assumptions on retention, replays and writes during a restore:

- `contracts/context-broker`, *Entity changes are published through the entity store*: a delete is published once as a change, which is why the replay rule needs the retention (D10). The restore relies on it and changes nothing of it. *The entity store holds expanded JSON-LD* (scenario *Update of the broker on an existing store*: a re-snapshot publishes the same attributes) is what the re-snapshot after the restore relies on; unchanged. *Core Services writes no null values* and *Subscriptions and notifications*: Core Services is reset without state as in #1035. During the restore the validation writes only to its trigger topic and `iff.alerts.bulk`, and the broker gets no write it wouldn't get from a running validation. *What the platform doesn't rely on*: the restore uses no broker topic or API.
- `contracts/opcua-live-data`, *Only values are delivered*: a value not delivered leaves the broker's last value, which the re-snapshot publishes; the restore doesn't depend on device traffic. *The chain is verified automatically*: the chain test doesn't cover the validation.
- `contracts/typed-literals`, *Documents passed on keep their declared types*: the checkpointed state holds what the bridge published, so restored values keep their types.
- `contracts/kms-package`, *The package digest identifies the content*: D4 doesn't use the digest, since the job graph depends on more than the package. A new package version gives a new fingerprint exactly when it changes what is submitted, and one that doesn't leaves the checkpoints usable.

No contract states a retention, a TTL or a refresh period, or what the bridges and Core Services may assume about replays (searched for retention, TTL and replay in `openspec/specs`). This change keeps every default: retention and TTL stay as they are, and the refresh period keeps its effective value. The rules only read them. A platform that sizes them up by the guide (D14) gives a consumer that restarts more records to read again. The bridges read with committed consumer groups and are unaffected. Core Services reads `iff.ngsild.attributes` from the earliest offset, so after its reset it resends up to the retention to Scorpio, with unchanged values and `observedAt`; the guide states this. No requirement is broken, and no contract delta is needed. Whether the validation's topics and their retention should become a contract of their own is an open question.

## Conflicts with existing specifications

- `helm/platform-watchdog`, *Repair of an inconsistent state*, says a checkpoint taken before the state went stale could restore a consistent state; by the state rule none can. Modified (D13).
- `helm/platform-watchdog`, *Rebuilding validation state*, names no repair; it now names `REPLACE=auto`. Modified.
- `helm/platform-watchdog`, *Late refresh*, measures against half the TTL; with D11 the refresh period is its own value, capped at half the TTL. Modified.
- `helm/platform-watchdog`, *Emptied validation state*, already says a restored checkpoint doesn't empty the state; the added *Restored validation state* states how such a state is then judged. Unchanged.
- #1035 D2 makes `RESTORE_FROM` mandatory for `REPLACE=checkpoint` and knows no `REPLACE=auto`; this change makes the path optional and adds `auto`. #1035 D5 says externalization is disabled; it was verified on a Core Services job, which the Kubernetes operator submits with retention on (Context). #1035's Context counts three constraint topics as read back; for the build here two are `postgres-cdc` tables. None is a spec conflict on `main`; the resync's README follows this change.
- The values comment on `flink.ttl` (`values.yaml.gotmpl:95`) and the restarter's comments tie the refresh to `ttl/2`; they are rewritten for the refresh period.
- `FlinkSqlServicesOperator/README.md` describes `updateStrategy: savepoint`; it is updated for the field and the fixed path.

## Risks / Trade-offs

- [Checkpoints slow the validation or delay alerts] → Measured before the default interval is set (D9); `min-pause` bounds the share; `CHECKPOINT=false` opts out.
- [With today's defaults a checkpoint is restorable for well under an hour] → Stated by the watchdog's `restorable until` and in the guide; a platform that needs more sizes TTL and retention (D14); `auto` falls back to fresh.
- [The catch-up estimate is too low and a restore brings back expired keys] → Calibrated by the restore tests with a margin (D9). The watchdog judges every restore by the state rule afterwards and raises an inconsistency if it was too late.
- [The watchdog's record of `r`, the snapshot size or the offsets is missing] → The checkpoint fails the state rule; `auto` starts fresh.
- [A retention changed after the checkpoint] → The replay rule reads it from Kafka at the decision.
- [Storage grows with each job] → Pruned by the resync and `flink-deploy` (D7).
- [The fingerprint misses something that breaks compatibility] → D3 makes Flink refuse unclaimed state; the e2e test checks the refusal after a KMS change.
- [The record in the status is lost with the resource] → Then nothing is restorable and the resync says so; `REPLACE=fresh` and `auto` work.

## Migration Plan

Apply the new CRD (`install_operators.sh`) and roll out operator, gateway, kafka chart (restarter) and alerta chart (watchdog, Role) before deploying a statementset built with this change. An older operator ignores `restoreFrom` and the fingerprint directory; the resync then refuses `REPLACE=checkpoint` and `auto` starts fresh, because `status.fingerprint` is missing. The restarter's effective period doesn't change with the defaults. The next `flink-deploy` changes the settings, so the validation starts fresh once, as on every deploy; its checkpoints count from then. Rollback: build with `CHECKPOINT=false`.

## Open Questions

- The default interval and `num-retained`, and the defaults of throughput, start allowance and margin, wait for D9.
- Should the validation's topics and their retention become a contract (`contracts/…`)?
- Flink CDC continues a `postgres-cdc` table from its replication slot. Does the slot keep its position across `flink-deploy` and the fresh resync, or must those count as a reset of the constraint tables too? The e2e restore test checks it.
- Does a path set as `execution.state-recovery.path` on the table config of a `flink run --python` job also restore? If it does, `-s` and the setting must not disagree; a unit test of the gateway pins `-s` as the only way.
