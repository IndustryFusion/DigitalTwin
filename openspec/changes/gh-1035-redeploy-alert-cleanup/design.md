# Design

## Context

**What the review on #1036 measured.** On a deployment with the validation running and not restarted, the reviewer closed the open SHACL alerts, restarted Core Services by its restart nonce and deleted the Connect pod. Within 30 s of the snapshot every closed alert that was still violated was open again with the same severity and text, plus one violation Alerta hadn't shown before, and the set stayed stable for 15 minutes. The validation runs with a state TTL (07f3abbe pins the joins and count accumulators, the dedup views expire), so the results of a re-snapshot are passed on again even when unchanged. The same review links the flink shard failure of the first implementation (https://github.com/IndustryFusion/DigitalTwin/actions/runs/44902037744/job/136843080878): on a fresh platform kafka-bridges creates `iff.ngsild.entities`, and the shacl release can't import it once `flink-deploy` no longer deletes it. A resync that neither undeploys nor deploys leaves that topic alone; who owns it is #1038.

**The path of an alert.** The entity connector writes `iff.ngsild.public.entity`; the debezium-bridge (consumer group `debeziumBridgeGroup`) turns it into `iff.ngsild.entities` and `iff.ngsild.attributes`. The rdf connector writes `iff.rdf`. The validation job reads these, writes `constraint_table`, `constraint_combination_table` and `constraint_trigger_table` and reads them back (upsert-kafka, which reads from the earliest offset), and writes `iff.alerts.bulk`. Core Services reads `iff.alerts.bulk` and writes `iff.alerts`, which the alerta-bridge posts to Alerta.

**How the validation is deployed today.** `semantic-model/shacl2flink/Makefile` builds the chart into `helm/charts/shacl` (`make helm`) and deploys it with `helm/helmfile-shacl.yaml`. `flink-deploy` (Makefile:174-188) scales the Strimzi entity operator down, deletes the KafkaTopics of `output/ngsild-kafka.yaml` and `output/rdf-kafka.yaml`, applies the helmfile, scales the entity operator up, uploads the KMS to Fuseki, runs `test-shacl-flink-deployment` and deletes the kafka-connect pods (`kubectl -l app.kubernetes.io/instance=kafka-connect delete pod`). `flink-undeploy` runs `helmfile destroy` twice. `test-flink-e2e` deploys a throwaway KMS (`tests/e2e-kms`), runs `test-shacl-flink-e2e` and `test-shacl-flink-scorpio-e2e`, and undeploys; it runs in the `flink` shard of `k8s-e2e.yaml` and in `k8s-tests.yaml`.

**Statementsets, checkpoints and savepoints.** `FlinkSqlServicesOperator/beamsqlstatementsetoperator.py`:
- The delete handler (lines 107-154) cancels the job without a savepoint and lets the resource go only after Flink confirms the cancellation.
- The update handler (lines 175-261) runs on a change of the spec. With `updateStrategy` `none` it cancels the job, and the next timer run deploys a new one without state. With `savepoint` it stops the job with a savepoint (`flink_util.stop_job`, `POST /jobs/<id>/stop`, into `state.savepoints.dir`), waits for it and keeps its location in `status.location`. `create_sets` (lines 476-501) then adds it for the next submission.
- When a running job is found cancelled, the timer resets the resource to `INITIALIZED` (lines 438-446) and deploys a new job.
shacl2flink always writes `updateStrategy: none` (`lib/utils.py:630`, `:663`). Checkpointing is opt-in: `CHECKPOINT ?= false` in the Makefile, and only `-p` adds `execution.checkpointing.interval` (`lib/utils.py:627`). The Flink deployment sets `state.checkpoints.dir` and `state.savepoints.dir` (`helm/charts/flink/templates/flink-deployment.yaml:82-83`). Nothing in the statementset spec names a checkpoint to start from. `create_sets` adds the savepoint location as the SQL string `SET execution.savepoint.path = '...';`, while every other setting is a map, and the submit job reads each setting as a map (`set.keys()`, `FlinkSqlGateway/submitjob/job.py:34-41`). Read from the code, not run: that path would fail as written. `flink-deploy` over a running validation is a spec change with `updateStrategy: none`, so the job starts without state and replays the three topics (#977).

**The re-snapshot.** Both connectors (`entity-table-connector`, `rdf-table-connector`, `helm/charts/kafka/templates/kafkaConnector.yml`) run with `snapshotMode: always`, so every start of the Connect pod is a complete snapshot. The `kafka-connect-restart` CronJob (`helm/charts/kafka/templates/connect-restarter.yaml`) runs every two minutes. It deletes the pods only when none is younger than `TEST_TIME = ttl/2 - max(60 s, ttl/100)`, with a floor of 60 s (lines 67-105). The platform watchdog reads a complete snapshot per connector from the Connect log: `Snapshot step 1 - Preparing`, then `Snapshot ended with SnapshotResult [status=COMPLETED`.

**Core Services.** `CoreServices.java` reads `iff.alerts.bulk` with group `flink_json_key_reader2` and `OffsetsInitializer.latest()`, and writes `iff.alerts`. Between them are a session window (200 ms by default) and `AlertsFilter`, which keeps the last severity and text per key in keyed state and passes a record only when one of them changed. The same job runs the SQL of `sql_statements.sql`, which reads `iff.ngsild.attributes` from the earliest offset and writes `iff.ngsild-updates`. It runs as the FlinkSessionJob `core-services-job` (`helm/charts/sql-core/templates/core-services-job.yaml`) with `upgradeMode: stateless`, and `restartNonce` sits at the level of `spec`, beside `job`. The Flink kubernetes operator 1.14 generates a new job ID for every submission that is not a retry (`SessionJobReconciler`, `JobID.generate()`). Core Services enables no checkpointing, so a nonce restart has nothing to restore.

**Alerta.** The platform runs `alerta/alerta-web:9.0.4` (`helm/values.yaml.gotmpl`). Every SHACL alert is published with `service` `['SHACL Validator']` (`lib/shacl_properties_to_sql.py` and its SPARQL and construct variants); the watchdog posts `service` `["System"]`. The 9.0.4 API (`alerta/views/bulk.py`):
- `PUT /api/_bulk/alerts/status` takes a filter in the query, runs synchronously, changes at most 1000 alerts per call (`Alert.find_all`, `page_size=1000`) and answers 404 when nothing matches.
- `PUT /api/_bulk/alerts/action` hands its work to a Celery task.
- `DELETE /api/_bulk/alerts` deletes.
In the filters (`database/backends/postgres/utils.py`), `service=X` matches alerts whose service list contains X, `status!=closed` excludes closed ones, and `from-date` filters on the last receive time. In the alarm model (`models/alarms/alerta.py`) a closed alert that receives a raise is opened again (`CLS-3`), or shelved again if it was shelved before it was closed (`CLS-2`). Tests and the watchdog authenticate with `Authorization: Key` and the `alerta-admin-key` of the secret `alerta`.

**The platform watchdog.** `helm/charts/alerta/templates/platform-watchdog.yaml` (#975) runs every two minutes, keeps its memory in the ConfigMap `platform-watchdog-state` (`helm.sh/resource-policy: keep`; its Role may `get` and `patch` only that ConfigMap) and posts `ValidationConsistency` on resource `shacl-validation`. Its `persist` writes back every key it read, with the keys it dropped set to null (lines 196-207). A key another writer changed during a run would therefore be overwritten with the value the run read. Its repair text (line 288) names four manual steps: redeploy, restart Core Services, delete the open SHACL alerts, restart kafka-connect.

**Verified on a local k3d platform** (read-only kubectl get and exec, printing names and numbers only):
- `kafka-consumer-groups.sh --list` in the broker pod lists `debeziumBridgeGroup`, `alertakafkabridge` and the other bridges' groups, but no `flink_json_key_reader2` and no group of the validation's sources.
- The Flink REST API shows for both jobs: checkpoint counts all 0, checkpoint interval `Long.MAX_VALUE` (disabled), externalization disabled. Every Kafka source vertex of both jobs reports `KafkaSourceReader.commitsSucceeded` 0, `...partition.<n>.committedOffset` -1 and `KafkaConsumer.records-lag-max` `NaN` (0 on the one source with a recent fetch). So the Flink sources commit no offsets without checkpointing, and Kafka has no lag to report for them.
- The same vertices report `pendingRecords` 0 and `KafkaSourceReader.topic.<topic>.partition.<n>.currentOffset`, where Flink's metric query service writes every `.` of the topic name as `_` (`iff_alerts_bulk`), so the topic is matched to Kafka's list of topics by the same replacement. For `iff.ngsild.entities` `currentOffset` was 16487 with an end offset of 16488 (`kafka-get-offsets.sh`): it is the offset of the last record read.
- `kafka-consumer-groups.sh --describe --group debeziumBridgeGroup` reports lag 0 on `iff.ngsild.public.entity`. The same for `alertakafkabridge` reported a committed offset that stayed put while the end offset of `iff.alerts` grew: the bridge commits only every 200 records (D9). `iff.alerts` has one partition.
- The three validation topics have `retention.ms: 3600000` and no compaction (KafkaTopic config); the broker runs Kafka 3.9.0 and has `kafka-delete-records.sh`.
- Both connectors' snapshots start and complete within a second of each other in the Connect log, with the markers above, on a small model.
- The statementset carries `updateStrategy: none` and `table.exec.state.ttl` `3600 s`; neither CronJob is suspended.

## Goals / Non-Goals

**Goals:**
- One command that leaves open exactly the SHACL alerts of the constraints violated now, for every constraint type, with the leaves kept sparse, whatever happened before.
- Replacing the job is an option of that command, not its premise.
- While the alerts are incomplete, the platform says so, and only says the validation is complete when the re-snapshot has gone through.
- No topic is created or deleted, and nothing outside the validation's own topics loses records.

**Non-Goals:**
- Changing the generated SQL, Core Services code or the bridges.
- Starting a statementset from a checkpoint (it needs operator changes, D5).
- Running the resync automatically.
- Keeping acknowledgements and shelving across a resync.

## Decisions

### D1: A resync, with replacing the job as an option

The resync rests on what the review measured: closing the SHACL alerts, emptying Core Services' filter state and a complete re-snapshot make the running validation raise what is violated now, because its TTL makes it pass on unchanged results again. Replacing the job is only needed when its state is wrong (the watchdog's inconsistency) or when an operator wants a clean start. Then a fresh job must not replay the previous job's records, or a raise it finds satisfied stays in its state.

*Alternatives:*
- **The redeploy of the first proposal** (undeploy, wait for the topics to be deleted, close, restart Core Services, deploy). It fits only a fresh start, deletes topics and, through the undeploy, `iff.ngsild.entities`, which failed the flink shard. Rejected in the review.
- **Ok verdicts per group, as in the closed #1027.** The count checks would write a verdict for every entity and count constraint, and the trigger table would grow from the number of violations to entities × count constraints. It also covers only the counts. Rejected in the comment on #1027.
- **A generation sweep in Core Services, a tombstone pre-step, a sweep by the watchdog.** As in the first proposal: the validation never says when it converged, a tombstone step leaves the alerts in Alerta and the filter state, and the watchdog reports without repairing.

### D2: The entry point

`make shacl-resync` in `semantic-model/shacl2flink`, with `REPLACE=none` (default), `REPLACE=fresh` or `REPLACE=checkpoint RESTORE_FROM=<path>`, runs a script beside `fuseki_kms.sh`. `CHECKPOINT` is already taken in the Makefile (it enables checkpointing at build time), hence `RESTORE_FROM`. The script works on the deployed statementset `shacl-validation` and needs no KMS. It refuses to start when the statementset doesn't exist, and refuses `REPLACE=checkpoint` before the first step (D5). It prints `step <n>/<total> <name>: started` and `... done`, runs each step under `set -euo pipefail`, and on a failure prints `resync failed in step <n>/<total> <name>: <reason>`, marks the failure (D10) and exits non-zero. If the job was stopped and not started again, the message adds that the SHACL validation doesn't run and that `make shacl-resync REPLACE=fresh` starts it. Every wait has a time limit, overridable by an environment variable. The steps are safe to repeat. Each step runs in the background and the script waits for it, so a TERM or INT is taken at once: it is passed on to the step as TERM, and the failure path marks and posts the interruption like any other failure; the exit status is 130 for INT and 143 for TERM. The script runs with `umask 077`. Alerta's key goes to curl from a header file of mode 0600 in the work directory (`curl -H @file`, curl 7.55 or later, checked before the first step), never on a command line.

Alerta and the Flink REST API are reached through a port-forward, as `fuseki_kms.sh` reaches Fuseki. The Kafka tools run in the broker pod with a small heap and one at a time, as `tools/ttl_test.py` runs `kafka-get-offsets.sh`, since the broker pod has little memory to spare.

*Alternatives:*
- **Make `flink-deploy` always resync.** It also deploys on a fresh platform and in `test-flink-e2e`, where closing alerts and restarting Core Services is wrong or slow, and an operator should choose to lose acknowledgements. Whether `flink-deploy` should end by pointing to the resync is an open question.
- **A Helm hook Job in the shacl chart, or a script under `test/` or `helm/`.** As in the first proposal: a hook needs Alerta's key and rights on another release's FlinkSessionJob and can't order the waits; the deploy targets are in shacl2flink.

### D3: The order: close before resetting Core Services

The steps run in this order: mark degraded; with `REPLACE=fresh`, stop the job and empty its topics; close; reset Core Services; with `REPLACE=fresh`, start the job; re-snapshot; wait until processed; end the degraded state. The review lists the reset before the close. Closing first is safer while the validation runs. A raise that passes a freshly reset filter between the reset and the close puts its key into the filter state, is then closed, and the re-snapshot's unchanged raise for it is dropped: the alert stays closed while violated. Close first, and a raise between close and reset either passes the old filter and reopens a still violated alert, or is dropped and comes back with the re-snapshot after the reset. A clear that Core Services misses while it restarts (it starts at the latest offset) leaves a closed alert closed. With a fresh job, the new job starts after the reset, so its first raises are not lost to a Core Services restart.

*Alternative:* the review's order (reset, close, re-snapshot). It has the race above, small as it is, since `iff.alerts.bulk` carries only verdict changes.

### D4: A fresh job: stop, empty the job's topics, start

With `REPLACE=fresh`, the script saves the spec, labels and annotations of the BeamSqlStatementSet and deletes the resource. The operator's delete handler cancels the job and lets the resource go only after Flink confirmed the cancellation. The script then removes every record of the three topics the job writes and reads back. The saved object stays in a directory of mode 0700, as a file of mode 0600, until the job runs again. For each partition it reads the end offset (`kafka-get-offsets.sh`), runs `kafka-delete-records.sh` up to that offset, and checks that the start offset equals it. After the reset of Core Services it creates the statementset again from the saved object, so the release's labels and annotations stay, and waits until it is `RUNNING` with all its tasks and its readers of the topics it reads from the latest offset (`iff.ngsild.entities`, `iff.ngsild.attributes`) hold their partitions, as their partition metrics show: a record written before a reader holds its partition is never read. No topic, KafkaTopic resource or other topic is touched; `iff.ngsild.entities` keeps its records and its owner.

*Why delete records rather than recreate the topics:* the three topics use deletion by retention, not compaction, so Kafka accepts deleting records. The call is synchronous and reports the new start offset. It keeps the topic ID, the partitions, the config and the KafkaTopic resource. Recreating means deleting the KafkaTopics: Strimzi's finalizer deletes the topic asynchronously, the broker's `auto.create.topics.enable: true` can bring a name back with broker defaults, and `flink-deploy` scales the entity operator around such deletions. That is the wait the first proposal needed (its D3), and the review asks to avoid touching topics where possible.

*Reading the snapshot:* the validation reads `iff.ngsild.entities` and `iff.ngsild.attributes` from the latest offset (`create_ngsild_tables.py`, `create_core_tables.py`), so a fresh job sees an entity and its attributes only through the re-snapshot that follows its start. A reader places itself at the latest offset only when its partition is assigned, which on a loaded platform can come after the job reports all tasks running. A snapshot record written before that is never read, and the job keeps a verdict without it, e.g. a count of 0 for a satisfied property, until the next periodic snapshot. The start step therefore completes only once the new job's readers of these topics hold their partitions, which their partition metrics show; only then is the re-snapshot triggered. The first platform run of the e2e suite showed this: a satisfied count alert came back open after a fresh resync.

*Alternatives for stopping and starting:*
- **`helmfile apply` to create the statementset again.** helmfile upgrades only when helm-diff finds a difference between the release and the chart, so a statementset deleted by hand would not come back.
- **Cancel the job through the Flink REST API.** The operator's timer finds it cancelled and deploys a new job at its next run (lines 438-446), possibly before the topics are emptied.
- **A spec change with `updateStrategy: none`.** The operator cancels and deploys right away, with no point in between to empty the topics.

### D5: Restore from a checkpoint: accepted, refused today

A restore keeps the job's state, so its topics must keep the records since the checkpoint and are not emptied; the other steps run as with a fresh job. The platform can't do this today:
- checkpointing is off unless the chart was built with `CHECKPOINT=true`, and retained checkpoints are not configured (externalization disabled, verified);
- the statementset has no field naming a checkpoint or savepoint to start from;
- the only savepoint path in the operator is the `savepoint` update strategy, which shacl2flink doesn't use, and it passes the location in a form the submit job doesn't read (Context).

The command accepts `REPLACE=checkpoint RESTORE_FROM=<path>` and refuses it before the first step, naming these three gaps. Supporting it needs a statementset field for the path, which the operator passes on as a setting map, retained checkpoints for the validation, and topics that still hold the records since the checkpoint (retention is one hour). That belongs to #1042. Until then, a job that Flink restored by itself, after a failover with checkpointing on, is resynced with `REPLACE=none`.

*Alternatives:*
- **Leave the option out until it works.** The review asks for one entry point that covers this case; accepting the option fixes the interface now.
- **Restore by stopping with a savepoint through the operator's update strategy.** It restores only the state at the moment of the stop, not an older checkpoint taken before the state went stale, which is what the watchdog's repair note is about. It also fails as written today.

### D6: Close by filter, after a settle time only when the job was stopped

The close step reaches Alerta through a port-forward to the `alerta` service, authenticated with `Authorization: Key` and the key from the secret `alerta`. It calls `PUT /api/_bulk/alerts/status?service=SHACL Validator&status=open&status=assign&status=ack&status=shelved&status=blackout&status=expired&status=unknown`, every status but closed, with status `closed` and a text naming the resync; the list of statuses is the form the e2e suites already use to find alerts, while a negated `status!=closed` matched nothing in the first platform run. It repeats while the answer changed alerts (at most 1000 per call), treats 404 as "nothing left", reports how many alerts it closed, fails when a call matches nothing while alerts are not closed, and confirms with the same filter on `GET /api/alerts` that the total is 0. When the job was stopped, the step first waits until Alerta has received no SHACL alert for a settle time (`from-date=<now - settle>`, default 30 s). Raises the stopped job wrote just before it stopped then reach Alerta before the close and not after it. While the validation runs, a raise is live and no settle time can be waited for, nor is one needed (D3).

Closing, not deleting, keeps the history: a still violated alert comes back with its history, which shows the resync. Acknowledgements are lost, and an alert shelved before it was closed comes back shelved (`CLS-2`).

*Alternatives:* `DELETE /api/_bulk/alerts` (loses the history); `PUT /api/_bulk/alerts/action` (a Celery task that must be polled); one request per alert; a `normal` raise per key through `iff.alerts` (needs the keys and goes through the filter the reset empties).

### D7: Reset Core Services by its restart nonce

The reset sets `spec.restartNonce` of the FlinkSessionJob `core-services-job` to a new value. With `upgradeMode: stateless` the operator cancels the job and submits it again with a new job ID, so there is nothing to restore. The step waits until the FlinkSessionJob reports a new job ID in state `RUNNING` and Flink lists exactly one running job `Core Services` with all its tasks and no restored checkpoint, as `test/wait-for-flink-jobs.sh` checks. Then it waits until the new job's reader of `iff.alerts.bulk`, which starts at the latest offset (`CoreServices.java`), holds its partition, as its partition metric shows (Flink names the topic `iff_alerts_bulk`), as the start step does for the validation's readers (D4); a raise written before that would never be forwarded. Only then does it take the end offsets of Core Services' topics that the wait step measures from (D9). The restart also sends the attributes still in `iff.ngsild.attributes` to Scorpio again, as every Core Services restart does; the README says so next to what an operator loses.

*Alternatives:* suspend and resume (`spec.job.state`, two changes for the same restart); delete and recreate the FlinkSessionJob (it belongs to the sql-core release); a TTL on the filter state (changes Core Services for every alert).

### D8: Re-snapshot, with the periodic restart left running

The step deletes the kafka-connect pods as `flink-deploy` does. The resync takes the time T0 at which it began. A snapshot counts when the log shows `Snapshot step 1 - Preparing` after T0 followed by `Snapshot ended with SnapshotResult [status=COMPLETED`, per connector, the markers the watchdog uses.

The `kafka-connect-restart` CronJob is not suspended. Right after the step's deletion the pods are younger than `TEST_TIME` (at least 60 s), so the CronJob leaves them alone while the snapshot runs. A deletion by the CronJob between T0 and the step only adds a snapshot, which counts, being after T0. If one cuts a snapshot short, which takes a snapshot longer than `TEST_TIME`, the step waits for a completed one within its time limit.

*Alternatives:*
- **Suspend the CronJob during the resync.** If the resync dies while it is suspended, the refreshes stop, the state TTL passes without one, and the watchdog latches an inconsistency that needs a fresh job. Resuming in a trap doesn't cover a killed shell.
- **Restart the connectors instead of the pod** (Connect REST, or the KafkaConnector restart annotation). Strimzi's network policy keeps the Connect REST API to the operator (watchdog, check 4). Whether a connector restart takes a complete snapshot with `snapshot.mode: always` has not been checked, while the pod deletion is what `flink-deploy` and the CronJob already do.

### D9: Processed: snapshots completed, no records left for a quiet period, then a marker in Alerta

After every connector completed a snapshot after T0, the step reads the end offset `E` of every partition of every topic the three consumers read: `iff.ngsild.public.entity` (debezium-bridge); `iff.ngsild.entities`, `iff.ngsild.attributes`, `iff.rdf` and the three tables (validation); `iff.alerts.bulk`, `iff.ngsild.attributes` and `iff.ngsild.attributes_insert` (Core Services). The sources are taken from the jobs' vertices, not from a fixed list. It then polls every few seconds. A poll is quiet when:
- the debezium-bridge's group has lag 0 (it commits; verified);
- every Kafka source vertex of the validation job and of Core Services reports `pendingRecords` 0;
- each source's `currentOffset` is at least `E - 1` on every partition (a partition with `E` 0 needs nothing).
The step completes when the polls stay quiet for a quiet period, default 30 s, far above the measured latency of the validation (about 1 s) and of Core Services' window (about 3 s). Live traffic doesn't stop it: `pendingRecords` 0 means a consumer keeps up, and `E` is fixed at the end of the snapshot.

Then the step writes a marker record to `iff.alerts`, behind the records of Core Services, and waits until Alerta has it. The marker is an alert of resource `shacl-validation`, event `ResyncMarker`, service `System`, severity `normal`, with T0 as its value, written with `kafka-console-producer.sh` in the broker pod. The step looks it up with `GET /api/alerts?resource=shacl-validation&event=ResyncMarker` and checks its value. `iff.alerts` has one partition (verified), and the alerta-bridge posts its records one at a time in offset order. `eachMessage` is awaited, `autoCommit` is off, and after a failed post the bridge pauses, throws and gets the same record again (`KafkaBridge/alerta/app.js:69-107`). It only skips a record that Alerta refuses for good (400, 415). So once the marker is in Alerta, every record written before it was posted or refused. With more partitions there would be one marker per partition. The marker arrives closed, as every alert of severity `normal` does, and is not a SHACL alert, so the close step and the scenarios on SHACL alerts don't see it.

Consumer group offsets in Kafka can't serve for the two Flink jobs: without checkpointing their sources commit nothing, and no group of theirs exists in Kafka (verified). `records-lag-max` is `NaN` without a recent fetch.

The alerta-bridge's group can't serve either, and its standing lag is not a backlog. The bridge commits by hand, and only once more than `kafkaCommitThreshold` records are waiting for a commit (`app.js:104-106`; 200, `helm/values.yaml.gotmpl:193`), or on a failed post. There is no time-based commit. It also commits the offset of the last posted record, not the next one. On the local platform the committed offset stayed at 4622 across every reading, while the end offset of `iff.alerts` went from 4738 at the first reading to 4760, then held still through samples every 30 s over five minutes. That is a lag of 116, then 138, always below 200. Over the same time the bridge logged no failed or refused post since it started two days earlier, and it never restarted. A real backlog would show as failed posts, since a post that doesn't fail moves on to the next record within its request timeout (2 s). So the committed offset can stay up to 200 records behind for as long as no 201st record comes, which after a small resync can be hours. The e2e test also checks what reached Alerta.

*Alternatives:*
- **A fixed wait after the snapshot.** A guess that is too short on a large model and too long on a small one.
- **A sentinel record through the whole pipeline.** Needs code in the validation or Core Services. The marker covers the last hop only, where no code is needed, and the quiet period the hops before it.
- **Consumer group lag for all consumers.** Not available for the Flink jobs, as above. For the alerta-bridge it would need a commit on a timer or after each post, a change to the bridge that this change leaves out. With such a commit, "committed offset reaches the end offset taken after the quiet period" would do and the marker could go.
- **Alerta's count of open SHACL alerts stable for a quiet period.** A stalled bridge gives a stable count too, and live raises move it.
- **No SHACL alert received in Alerta for a quiet period.** Never holds under live traffic, and a stalled bridge passes it as well.
- **Also require low busy and backpressure times of every vertex.** Possible as an addition if the e2e runs show records still inside the job after the sources are idle. Not taken now, since the quiet period covers the measured latency.

### D10: The degraded state: the command marks, the watchdog reports

The command keeps its marks in the watchdog's ConfigMap `platform-watchdog-state`: `resync_since` (T0), `resync_step` (`<n>/<total> <name>`), `resync_deadline` (T0 plus what the steps can take: each wait and each single call by its limit, the stop, reset and start steps with both of their waits, the topic emptying per topic, plus a margin) and, on a failure, `resync_failed` (step and reason). It posts `ValidationConsistency` itself at the start of every step and on a failure, so the warning is there before the first alert is closed. The text is the one the watchdog derives from the marks:
- `DEGRADED -- RESYNC IN PROGRESS since <T0>, step <n>/<total> <name>: the SHACL alerts are incomplete until the resync has completed.`
- `RESYNC FAILED in step <n>/<total> <name> at <t>: <reason>. The SHACL alerts may be incomplete or stale; run make shacl-resync again.` with the note when the validation doesn't run.
On success it removes all four marks and starts one watchdog run from the CronJob (`kubectl create job --from=cronjob/platform-watchdog`). The normal state then comes from the watchdog's own judgement, which also knows a kept inconsistency. If that job can't be created, the next scheduled run, at most two minutes later, does the same.

The watchdog reads the marks on every run:
- a kept inconsistency comes first;
- then `resync_failed`, or `resync_since` with `resync_deadline` passed, gives critical, naming the step;
- then `resync_since` gives the warning;
- otherwise it judges as today.
Before it posts `ValidationConsistency`, it reads the `resync_*` keys again, so a run that read its state before the first step doesn't post "consistent" over the resync's warning. Its `persist` leaves out the `resync_*` keys, so a run never writes back marks it read while the command changed them. A mark goes into the alert as text without quotes, backslashes or control characters, which the command strips as well. The names don't end in `.start` or `.done`, so `observe_anew` leaves them alone. The command needs rights to patch the ConfigMap and create a Job, which an operator running `make` has; the watchdog's Role is unchanged.

*Alternatives:*
- **The command posts, the watchdog doesn't know.** The watchdog's next run, within two minutes, overwrites the warning with its own verdict, typically "consistent".
- **The watchdog derives everything from the marks, the command posts nothing.** The warning comes up to two minutes late, after the close step may already have run.
- **A separate event, such as `ValidationResync`.** Two alerts about one state; the review asks for the consistency alert.
- **A ConfigMap of the command's own** that the watchdog only reads. Cleaner ownership, but one more object in the chart and one more name in the watchdog's Role, against one exclusion in `persist`.

### D11: The watchdog's repair names the resync

The repair text of `ValidationConsistency` names `make shacl-resync REPLACE=fresh` and its steps in their order. The checkpoint note says "instead of the resync". A resync without replacement doesn't end an inconsistency, since the job keeps its state; the fresh job does, through the watchdog's "Emptied after it".

### D12: `iff.ngsild.entities` is left alone

The resync neither undeploys nor deploys, so it doesn't touch the topic or its KafkaTopic. The first proposal's `helm.sh/resource-policy: keep` and the change to `flink-deploy` are dropped; the topic's ownership is #1038.

## Conflicts with existing specifications

- `helm/platform-watchdog`, *Repair of an inconsistent state*, requires four steps in which the SHACL alerts are deleted after the new job started. That removes real raises of the new job, which a sparse leaf with an unchanged verdict needn't send again, and loses the history. This change modifies it to name the resync (D11). Alternative: keep the text and only add the command, so the alert would describe a repair that differs from the supported one.
- `helm/platform-watchdog`, *Flink not readable*, *Rebuilding validation state* and *Late refresh*, each require a report of `ValidationConsistency` that a running resync would contradict. During a fresh replacement the statementset reports no job, the first refresh completes before the re-snapshot is processed, and a refresh may be late when the resync starts. This change modifies each to give way to the resync report. Alternative: one added requirement that takes precedence over them, which leaves three requirements whose text is no longer true as written.
- Issue #1035 asks for a redeploy that undeploys the chart and waits for its topics to be deleted, and its acceptance criterion 6 asks that an undeploy keep `iff.ngsild.entities`. The resync replaces the redeploy (D1, following the review) and deletes no topic. Criterion 6 is about the undeploy, which this change doesn't touch, and moves to #1038. The Pull Request states this.

No other specification covers the deploy targets or the topics; `contracts/*` are not affected.

## Risks / Trade-offs

- [A resync loses acknowledgements and the open time of alerts that stay violated] → Stated in the proposal and the README; the history keeps what happened.
- [A fresh job raises from partial data before the snapshot has gone through, so alerts can flap] → That is the degraded state the warning reports; it ends only when processed.
- [With a fresh job the validation doesn't run between the stop and the start] → Short (a Core Services restart); a failure in between says so and names the command (D2).
- [Core Services sends the retained attribute window to Scorpio again] → As every Core Services restart; values and `observedAt` are unchanged; in the README.
- [The marker is one more alert in Alerta, and one more writer of `iff.alerts`] → It is of service `System`, arrives closed and carries the resync's start; the alerta-bridge treats it like any other record.
- [The quiet period is a heuristic] → Far above the measured latencies, overridable; the e2e test checks the alerts after it.
- [A raise of a stopped job reaches Alerta after the settle time] → The settle time is far above Core Services' window and overridable.
- [The command is killed and leaves its marks] → `resync_deadline` makes the watchdog report it critical, naming the step; the next resync replaces the marks.
- [The watchdog run started by the command overlaps a scheduled run] → Both judge from the same reads and patch the same keys; the marks are left out of `persist`.

## Migration Plan

Deploy the alerta chart with the new watchdog before the first resync. With the old watchdog, the command's warning is overwritten within two minutes and the marks are ignored, and the old repair text stays. The resync itself needs no migration: it changes no chart or topic.

## Open Questions

- The README says that a deploy over a running validation needs `make shacl-resync REPLACE=fresh` to clear replayed raises. Should `flink-deploy` also print that hint, or check for it? Or should the resync accept a KMS and deploy it in place of the stop and start?
- The settle time (30 s), the quiet period (30 s) and the time limits were first guesses; the e2e runs in the flink shard measured them (af0f90cc). Without a replacement the resync took 147 s: reset 44 s, re-snapshot 18 s (12 s from the deletion of the Connect pods to each connector's completed snapshot), wait 77 s (quiet from about 40 s after the snapshot, marker in Alerta at once). With a fresh job and the alerta-bridge held back for a minute it took 370 s: stop and empty 57 s, reset 43 s, start 104 s, re-snapshot 18 s (13 s), wait 139 s (marker 66 s behind the held-back bridge). Every default limit is at least three times the step it bounds, so the defaults stay; the e2e suite's tighter start limit went from 300 s to 420 s. The settle time never bound (the close came 57 s after the stop) and the quiet period lies far above the measured catch-up, so both stay at 30 s. A large model can take much longer to snapshot and to process, which is why the defaults are well above these values.
- Should the alerta-bridge commit on a timer, so that its group lag could replace the marker? That is a bridge change for an issue of its own.
