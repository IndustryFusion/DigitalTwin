# Design

## Context

**How the validation is deployed today.** `semantic-model/shacl2flink/Makefile` builds the chart into `helm/charts/shacl` (`make helm`; the chart is generated, it is not in git) and deploys it with `helm/helmfile-shacl.yaml`, one release `shacl`. `flink-deploy` scales the Strimzi entity operator down, deletes the KafkaTopic resources of `output/ngsild-kafka.yaml` and `output/rdf-kafka.yaml`, applies the helmfile, scales the entity operator up, uploads the KMS to Fuseki, runs the bats suite `test-shacl-flink-deployment` and deletes the kafka-connect pods. The deletion before the deploy comes from d0020c3b ("Strimzi ... creates KafkaTopic CR for every topic it finds on Kafka"), written for the bidirectional topic operator. `flink-undeploy` runs `helmfile destroy` twice ("to make sure that there are no kafkatopics left"), checks that the statementset is gone (`test-shacl-flink-undeploy`) and removes the KMS from Fuseki. `test-flink-e2e` deploys a throwaway KMS (`tests/e2e-kms`), runs `test-shacl-flink-e2e` and `test-shacl-flink-scorpio-e2e`, and undeploys again; it runs in the `flink` shard of `k8s-e2e.yaml` and in `k8s-tests.yaml`.

The helmfile apply in `flink-deploy` is written `./helmfile ... apply || make enable-strimzi`, so its exit status is that of `enable-strimzi`; a failed apply is noticed only by the bats check after it.

**Topics of the shacl release.** On a local k3d platform, `helm get manifest shacl` lists four KafkaTopics: `iff.ngsild.entities`, `iff.ngsild.flink.constraint-table`, `iff.ngsild.flink.constraint-trigger-table` and `iff.ngsild.flink.constraint-combination-table` (all four written by `create_ngsild_tables.py` into `ngsild-kafka.yaml`), besides the BeamSqlTables, the view, the UDFs, a ConfigMap and the BeamSqlStatementSet `shacl-validation`. `kubectl get kafkatopic` shows `iff.ngsild.entities` annotated with `meta.helm.sh/release-name: shacl`. `helm/charts/kafka-bridges/templates/bridge-topics.yaml` declares the same topic, but only when a `lookup` finds no KafkaTopic of that name. The debezium-bridge writes it (`entityTopicPrefix`) and the timescaledb-bridge reads it (`timescaledb.entityTopic`, `bridge-configmap.yaml`). So undeploying the shacl release deletes a topic of the bridges, which answers the question at the end of the comment on #1027.

Strimzi runs 0.45.1 on the platform (entity operator image), with the unidirectional topic operator: every KafkaTopic carries the finalizer `strimzi.io/topic-operator`, which the operator removes after it has deleted the topic in Kafka. Deleting the resource therefore deletes the topic, asynchronously. The brokers run with `auto.create.topics.enable: true` (`helm/charts/kafka/templates/KafkaCluster.yaml`).

**Statementsets.** `FlinkSqlServicesOperator/beamsqlstatementsetoperator.py` cancels the Flink job of a BeamSqlStatementSet in its delete handler and lets the resource go only once Flink confirms the cancellation, so `test-shacl-flink-undeploy` waiting for the statementset to disappear means the job is cancelled.

**The re-snapshot.** Both Debezium connectors (`entity-table-connector`, `rdf-table-connector`, `helm/charts/kafka/templates/kafkaConnector.yml`) run with `snapshotMode: always` (`helm/values.yaml.gotmpl`): every restart of the Connect pods is a complete snapshot. The `kafka-connect-restart` CronJob restarts them every half TTL (`connect-restarter.yaml`), and `flink-deploy` restarts them once at its end. The platform watchdog (#975, `helm/charts/alerta/templates/platform-watchdog.yaml`) reads the end of a complete snapshot per connector from the Connect log (`Snapshot step 1 - Preparing`, `Snapshot ended with SnapshotResult [status=COMPLETED`), takes the start of the statementset's job as the moment the state was emptied, reports *rebuilding* until each connector completed a snapshot after it, and ends a latched inconsistency then (`helm/platform-watchdog`, "Emptied after it").

**Core Services.** `CoreServices.java` reads `iff.alerts.bulk` with `OffsetsInitializer.latest()` and writes `iff.alerts`; between them a session window (200 ms by default) and `AlertsFilter`, which keeps the last severity and text per key in keyed state and passes a record only when one of them changed. The issue's context says it reads `iff.alerts`; it reads `iff.alerts.bulk`. The same job runs the SQL of `sql_statements.sql`, which reads `iff.ngsild.attributes` from the earliest offset (`table_definition.sql`) and writes `iff.ngsild-updates`. It runs as the FlinkSessionJob `core-services-job` (`helm/charts/sql-core/templates/core-services-job.yaml`) with `upgradeMode: stateless`. The reconciled spec on the platform has `restartNonce` at the level of `spec`, beside `job`, not inside `job`. The Flink kubernetes operator 1.14 generates a new job ID for every submission that is not a retry (`SessionJobReconciler`, `JobID.generate()`). The session cluster has Kubernetes HA (`high-availability.storageDir: s3://flink/recovery`), whose checkpoint store is per job ID; Core Services enables no checkpointing and the FlinkDeployment sets no checkpoint interval, so a nonce restart has nothing to restore.

**Alerta.** The platform runs `alerta/alerta-web:9.0.4` (`helm/values.yaml.gotmpl`, and the deployment on the platform); the chart's `appVersion` 8.1.0 is outdated. Every SHACL alert is published by `sql_insert_constraint_in_alerts` (`lib/shacl_properties_to_sql.py`), and by the SPARQL and construct variants, with `service` `['SHACL Validator']` and `environment` `'Development'`; the watchdog posts `service` `["System"]`. The API of 9.0.4 (`alerta/views/bulk.py`) has `PUT /api/_bulk/alerts/status` with a filter in the query, synchronous, changing at most 1000 alerts per call (`Alert.find_all`, `page_size=1000`) and answering 404 when nothing matches; `PUT /api/_bulk/alerts/action` hands its work to a Celery task; `DELETE /api/_bulk/alerts` deletes. A filter `service=X` matches alerts whose service list contains X, `status!=closed` excludes closed ones, `from-date` filters on the last receive time (`database/backends/postgres/utils.py`). In the alarm model (`models/alarms/alerta.py`) a closed alert that receives a raise is opened again (`CLS-3`), or shelved again if it was shelved before it was closed (`CLS-2`). Tests and the watchdog authenticate with `Authorization: Key` and the `alerta-admin-key` of the secret `alerta` (`test-shacl-flink-scorpio-e2e.bats`, `test/bats/test-jobs/platform-watchdog.bats`).

## Goals / Non-Goals

**Goals:**
- After a redeploy, exactly the alerts of the constraints violated now are open, for every constraint type, with the leaves kept sparse.
- One command, a fixed order, a clear failure.
- Undeploying the validation leaves the bridges' topic alone.

**Non-Goals:**
- Changing the generated SQL or Core Services code.
- A cleanup after failovers or JobManager restarts.
- Keeping acknowledgements and shelving across a redeploy.

## Decisions

### D1: Clean up at the redeploy, not in the verdicts

The validation keeps emitting only violations. The redeploy removes everything that could bring a raise of the previous job back (its topics, the alerts in Alerta, the alerts filter of Core Services) and lets the new job raise what is violated now.

*Alternatives:*
- **Ok verdicts per group, as in the closed #1027.** Rejected in the comment on #1027: the count checks would write a verdict for every entity and count constraint, so the trigger table and every statement reading it grow from the number of violations to entities × count constraints. That is the traffic 704bb30f moved away from ("every sample is triggering either an alert or resets it", answered there by the bulk filter in Core Services), and the circuit template in `lib/shacl_properties_to_sql.py` relies on it: "`needed_count` is always taken from the static edge list, never from observed triggers, which is what lets leaves stay sparse and emit only violations". It also covers only the counts, while the other leaves are sparse too and escape the replay only because their transient raises happen to be retracted while the job converges.
- **A generation sweep in Core Services.** Core Services would tag the alerts it forwards with the generation of the validation and close those of older generations once the new one has converged. The validation never says when it has converged, and a sparse leaf never confirms a satisfied key, so "not raised by the new generation" only means "satisfied" after a complete snapshot has gone through the job, a moment Core Services can't see. It also needs Core Services to talk to Alerta, which it doesn't (it only writes `iff.alerts`), and code in a component this change doesn't otherwise touch.
- **An operator pre-step writing tombstones.** Before the deploy, a step would write a tombstone into `constraint_trigger_table` for every key it holds, so the replay brings no raise back. It removes the replay but not the alerts already open in Alerta, nor the state of the alerts filter; the step needs a Kafka client reading the whole topic, which costs as much as deleting it. Deleting the topics is what `flink-undeploy` does already.
- **A sweep by the platform watchdog.** The watchdog would compare the SHACL alerts with the verdicts and close the stale ones. The watchdog reports and doesn't repair (#975 design, non-goals), comparing alerts with verdicts was left out of it as "a check of its own", it has no Kafka client (kubectl image, `/dev/tcp`), and it runs every two minutes beside a live validation, so a close would race real raises.
- **A shorter retention of `constraint_trigger_table` (#978).** Makes the replay smaller and closes nothing.

### D2: The entry point: a make target and a script in shacl2flink

`make flink-redeploy` in `semantic-model/shacl2flink`, taking `KMS` (or `SHACL`, `KNOWLEDGE`, `MODEL`) like `flink-deploy`, runs a script beside `fuseki_kms.sh` that executes the four steps. The script prints `step <n>/4 <name>: started` and `... done`, runs each step as a function under `set -euo pipefail`, and on a failure prints `redeploy failed in step <n>/4 <name>: <reason>` and exits non-zero. Every wait has a time limit, overridable by an environment variable, and exceeding it is a failure. The steps reuse the existing targets: `flink-undeploy` for step 1 and `flink-deploy` for step 4, with the waits of D3 and D7 around them.

The steps are safe to repeat: undeploying what isn't deployed, closing when nothing is open and restarting Core Services all succeed, so after a failure the operator runs the command again. A failure after step 1 leaves the validation undeployed; the watchdog then reports that the consistency can't be assessed, as it does whenever the statementset is missing.

*Alternatives:*
- **Make `flink-deploy` always do this.** It also deploys on a fresh platform and in `test-flink-e2e`, where closing alerts and restarting Core Services is wrong or slow; and an operator should choose to lose acknowledgements.
- **A Helm hook Job in the shacl chart.** Needs Alerta's key and rights on the FlinkSessionJob of another release inside the shacl chart; hooks can't order against the Core Services restart and the waits, and they run in the generated chart.
- **A script under `test/` or `helm/`.** The deploy targets and the KMS selection are in shacl2flink; the redeploy belongs next to them.

### D3: Undeploy: wait until the topics are gone in Kafka

Step 1 runs `flink-undeploy`, waits until the statementset is gone (the job is then cancelled, see Context), until the KafkaTopic resources of `constraint_table`, `constraint_combination_table` and `constraint_trigger_table` are gone (the topic operator's finalizer is removed only after the topic was deleted in Kafka), and finally until the three topics are missing from the broker's topic list (`kafka-topics.sh --list` in the broker pod, the way `tools/ttl_test.py` runs the Kafka tools there). The topic list is checked because the deletion in Kafka is asynchronous, and with automatic topic creation a client asking for the topic would recreate it; the new topic would be empty and hold nothing to replay.

*Alternative:* trust `helmfile destroy` alone, as `flink-undeploy` does (twice): it returns before the topics are deleted, and a deploy right after it can meet a topic that is still being deleted.

### D4: iff.ngsild.entities stays

The KafkaTopic of `iff.ngsild.entities` written by shacl2flink gets the annotation `helm.sh/resource-policy: keep`, so `helmfile destroy` leaves it, and `flink-deploy` no longer deletes it before the deploy (it moves out of the set of KafkaTopics deleted there). A kept resource keeps its release annotations, so the next install of the release `shacl` takes it over again; `bridge-topics.yaml` renders it only when none exists, so the kafka-bridges release doesn't conflict either.

*Alternatives:*
- **Drop the topic from the shacl chart and leave it to kafka-bridges.** On a platform where the shacl release owns it, as on the local k3d platform, the next apply of the shacl release would delete it; and kafka-bridges creates it only on its next apply.
- **Let it be deleted and recreated.** The timescaledb-bridge loses the records it hasn't read and the bridges write to a topic that is gone until automatic creation brings it back with broker defaults.

### D5: Close, by filter, after a settle time

Step 2 reaches Alerta through a port-forward to the `alerta` service, as `fuseki_kms.sh` reaches Fuseki, authenticated with `Authorization: Key` and the key from the secret `alerta` like the tests. It first waits until Alerta has received no alert of service `SHACL Validator` for a settle time (`GET /api/alerts?service=SHACL Validator&from-date=<now - settle>`, default 30 s), so that raises the cancelled job wrote shortly before it stopped, still passing Core Services' window and the alerta-bridge, are in Alerta before the cleanup and not after it. Then it calls `PUT /api/_bulk/alerts/status?service=SHACL Validator&status!=closed` with status `closed` and a text naming the redeploy, repeats while the answer changed alerts (at most 1000 per call), treats 404 as "nothing left", and confirms with `GET /api/alerts?service=SHACL Validator&status!=closed` that the total is 0.

Closing, not deleting, keeps the history: a closed alert that is raised again is opened again, so an alert that is still violated comes back with its history, which shows the redeploy. Acknowledgements are lost, and an alert shelved before it was closed comes back shelved (`CLS-2`). The watchdog's repair text says "delete"; it changes with D8.

*Alternatives:*
- **`DELETE /api/_bulk/alerts`.** Loses the history of every SHACL alert.
- **`PUT /api/_bulk/alerts/action`.** Queues a Celery task; whether it ran must be polled, and it needs a worker.
- **One request per alert.** Same result, one request per alert instead of one per thousand.
- **Posting a `normal` raise per key through `iff.alerts`.** Needs the list of keys, which is the list of alerts to close, and goes through the alerts filter that step 3 resets.
- **Close after the deploy (the order of the watchdog's repair today).** Closes the new job's real raises, and the new job doesn't raise them again while they stay violated.

### D6: Restart Core Services by its restart nonce

Step 3 sets `spec.restartNonce` of the FlinkSessionJob `core-services-job` to a new value. With `upgradeMode: stateless` the operator cancels the job and submits it again, without a savepoint and with a new job ID, so neither a savepoint nor the HA checkpoint store has anything to restore. The step waits until the FlinkSessionJob reports a new job ID in state `RUNNING` and Flink lists exactly one running job `Core Services` with all its tasks, which is what `test/wait-for-flink-jobs.sh` checks, duplicates included, and until no checkpoint of the new job was restored.

The restart has to complete before step 4: Core Services starts at the latest offset of `iff.alerts.bulk`, so a raise written before it runs is never forwarded. Once its tasks run, the new validation needs a helm apply, its submission and a snapshot before it writes its first raise. Core Services also reads `iff.ngsild.attributes` from the earliest offset, so the restart sends the attributes still in that topic to Scorpio again, as every Core Services restart does, the watchdog's manual repair included.

*Alternatives:*
- **Suspend and resume (`spec.job.state`).** Two changes for the same stateless restart.
- **Delete and recreate the FlinkSessionJob.** It belongs to the sql-core release; recreating it by hand drifts from the release.
- **A TTL on the alerts filter state.** Changes Core Services for every alert, while the problem is only the redeploy.

### D7: Deploy and wait for the snapshot

Step 4 runs `flink-deploy` and checks the helmfile apply's own result instead of the status of `enable-strimzi`. `flink-deploy` ends by deleting the kafka-connect pods, which starts a complete snapshot of both connectors. The step then waits until the statementset's job runs with all its tasks and, for each connector, the Connect log shows `Snapshot step 1 - Preparing` after the job's start, followed by `Snapshot ended with SnapshotResult [status=COMPLETED` — the markers the watchdog uses. When the step ends, every entity and the knowledge have been fed to the new job; the watchdog moves from *rebuilding* to *consistent* on its next run.

*Alternative:* end with `flink-deploy`; the command would report success before the alerts are meaningful, and the e2e test couldn't tell a slow snapshot from a missing raise.

### D8: The watchdog names the command

The repair text of `ValidationConsistency` names `make flink-redeploy` and its four steps in their order, and the checkpoint note says "instead of the redeploy" instead of "instead of steps 1 and 4".

## Conflicts with existing specifications

`helm/platform-watchdog`, *Repair of an inconsistent state*, requires the alert to name four steps: redeploy the statementset, restart Core Services, delete the open SHACL alerts, run a complete refresh. In that order the alerts are deleted after the new job has started, which removes raises of the new job that are real, and they come back only if the refresh makes the job emit them again, which a sparse leaf with an unchanged verdict needn't do; deleting also loses the history. This change modifies that requirement (D8). An alternative is to keep the watchdog text and only add the command; then the alert would describe a repair that differs from the supported one.

No other specification covers the deploy targets or the topics; `contracts/*` are not affected.

## Risks / Trade-offs

- [The redeploy loses acknowledgements and the open time of alerts that stay violated] → Stated in the proposal; the history keeps what happened.
- [A raise of the cancelled job reaches Alerta after the settle time] → The settle time is far above the 200 ms window of Core Services; it can be raised by an environment variable; the close step's own check runs after the settle time.
- [The redeploy takes longer than `flink-deploy`: a complete undeploy, a Core Services restart and a complete snapshot] → It is a deliberate operation; the e2e suite runs it once.
- [During the redeploy there is no validation] → As with `flink-undeploy` followed by `flink-deploy` today.
- [Core Services sends the retained attribute window to Scorpio again] → Same as every Core Services restart; values and `observedAt` are unchanged.
- [Strimzi deletes topics asynchronously and automatic creation can bring a name back] → D3 waits for the deletion in Kafka; a recreated topic is empty.

## Migration Plan

On a platform whose shacl release owns `iff.ngsild.entities`, the first deploy with this change adds the annotation of D4 to the existing resource. The first redeploy must therefore be preceded by a deploy with the new chart, or the redeploy's step 1 deletes the topic once more; the redeploy checks the annotation before step 1 and stops if it is missing.

## Open Questions

- Does `flink-deploy` still need to delete the KafkaTopics before deploying, now that the unidirectional topic operator no longer creates resources for topics it finds? Left as is apart from `iff.ngsild.entities`.
- Should `flink-deploy` refuse to deploy over a running validation and point to `flink-redeploy`, since that is the case that replays old raises?
- The settle time of D5 (30 s) and the time limits of the waits are first guesses, to be checked against the e2e runs.
