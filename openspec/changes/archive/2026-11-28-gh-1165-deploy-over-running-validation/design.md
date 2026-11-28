# Design

## Context

`make flink-deploy` runs `make helm`, whose `submit-postgres-tables` pipes three generated files into Postgres:
- `rdf.postgres`: `DROP TABLE IF EXISTS rdf`, `CREATE TABLE`, then all rows;
- `ngsild.postgres`: `DROP TABLE IF EXISTS` and `CREATE TABLE` for `constraint_table` and `constraint_combination_table`;
- `shacl-constraints.postgres`: all rows of those two tables.

Then it deletes the KafkaTopic resources of `ngsild-kafka.yaml` and `rdf-kafka.yaml` while the Strimzi entity operator is scaled down, so that the topics themselves survive. It applies the generated chart with `helmfile -f helmfile-shacl.yaml apply`, deploys the Fuseki graphs, and runs `restart_connect.sh`. That script waits until the deployed job reads `iff.ngsild.entities` and `iff.ngsild.attributes`, and only then restarts Kafka Connect (#1114).

The validation job reads the two constraint tables with the `postgres-cdc` connector (primary key `id`, the named replication slots `constraint_slot` and `constraint_combination_slot`). A dropped table produces no delete events, so a running job receives the refilled rows as new inserts on top of the rows it holds. `rdf` reaches the job through Debezium and the upsert topic `iff.rdf`, with stable keys.

The generated statement set has `updateStrategy: none`, and its statements sit in ConfigMaps. When only the statements change, its spec stays the same, and the operator keeps the running job.

`make shacl-resync REPLACE=fresh` (`shacl2flink/alert-resync`) already replaces a running job without touching the release:
1. It checks its preconditions before any step: the watchdog's state ConfigMap, one partition of `iff.alerts`, and no other resync running.
2. It deletes only the statement set. The operator's delete handler cancels the job and lets the object go only once Flink confirmed the cancellation, and the resync waits for both.
3. It empties the job's three topics, keeping them and their topic IDs.
4. It closes the SHACL alerts and resets Core Services.
5. It creates the saved statement set again, and waits until the new job runs and its readers are placed.
6. It re-snapshots, and waits until that has been processed.

The e2e suite `test-shacl-flink-deploy` holds the operator back (`--replicas=0`) until the new statement set appears. It asserts that Kafka Connect restarts once, after the new job started, and that the job reads what that restart published.

## Goals / Non-Goals

**Goals:**
- Deploying the same package over a running, consistent validation leaves the job and its verdicts alone.
- Deploying anything else gives the verdicts and alerts of a fresh deployment, without manual steps. That includes repeating a deploy that failed or was interrupted.
- Keep the #1114 order (Connect restarts only once the deployed job reads), the topics and their IDs, and the resync's preconditions.

**Non-Goals:**
- Keeping state across a changed package (#1042), shorter deploys, and any change to the tables' schemas, topics or the alert format.

## Decisions

### D1: The fingerprint covers the deployed validation as it is rendered

It is a SHA-256, in a fixed order, over:
- the shacl release as `helmfile -f helmfile-shacl.yaml template` renders it, with the deploy's own environment and values: the statement set, the statement ConfigMaps and the table definitions;
- the three `.postgres` files.

Rendering with the same helmfile and values the install uses covers what helm fills in at install time, such as the checkpoint interval and the parallelism. So a change to any of them is a change of the fingerprint, and "the same package rewrites nothing" holds without exceptions. The chart's `lookup` calls render placeholders offline, the same ones every time, so the rendering stays deterministic; a unit test pins that.

Alternatives considered:
- *Hashing the inputs (shapes, knowledge, context):* misses a compiler change that alters the statements, which is exactly the case that leaves old statements running today.
- *Hashing the unrendered build output, or plain `helm template` without the deploy's values:* misses the values. The operator would then replace the job on its own for a values change, which contradicts the requirement.
- *Comparing the tables row by row in Postgres:* needs database access before every decision, and misses statement changes.

### D2: The fingerprint is a ConfigMap of the deploy, tied to the job

The deploy keeps the ConfigMap `shacl-validation-fingerprint`, outside the release. It holds the fingerprint and the job ID it was written for, and the deploy writes it with `kubectl apply` as its last step, only on success. The replace path deletes it before its resync starts. An interrupted or failed replacement therefore leaves none, and the next deploy replaces again.

"Unchanged" requires the kept fingerprint to equal the new one *and* the kept job ID to be the running job. If something else replaced the job, for example a resync with a fresh job or the operator after a spec change, the next deploy replaces as well.

Alternatives considered:
- *An annotation on the statement set (the first version of this design):* the operator's update handler has no field filter, and kopf counts annotations as changes. So annotating the statement set cancels the job and submits it again, right after the deploy, which breaks the #1114 order. Filtering the handler to `spec` would be an operator change beyond this issue.
- *The annotation in the chart:* it goes live with the apply, before the resync, so an interrupted deploy would be taken as unchanged forever. The operator problem applies too.
- *The watchdog's state ConfigMap:* it belongs to the watchdog and the resync, and the fingerprint isn't their state.
- *A row in Postgres:* a database read for a question about the deployment.

### D3: The replacement is a resync mode, not a destroy

The resync gets the replacement `REPLACE=package`. It runs its stop, close and reset steps, then an install step, then its start, re-snapshot and processed steps.

The install step runs while no job reads the tables and Core Services has been reset. It writes the tables and runs `helmfile -f helmfile-shacl.yaml sync`. `sync` upgrades the release even when its manifest is unchanged, so it recreates the statement set that the stop deleted with kubectl. `apply` would see no diff and create nothing, for example for a knowledge-only change or a rerun after an interruption.

The start step waits for the new statement set instead of re-creating a saved one. Package mode never keeps a stopped statement set. A kept one from an earlier failed resync is discarded, and it doesn't refuse the run. If a package resync fails while no job runs, its message names `make flink-deploy`, not `REPLACE=fresh`: a fresh restart would run the old statements on the new tables. The resync's deadline, after which the watchdog takes a still-running resync as failed, includes the install step's limit.

The deploy then takes one of two paths:

- **Unchanged:** the kept fingerprint equals the new one, the kept job ID is the running job, and the job runs with all its tasks. The deploy writes no table and skips the deletion of the KafkaTopic resources, which a chart apply without a diff would not create again. It applies the chart (a no-op), deploys the Fuseki graphs and runs `restart_connect.sh` as today. The job ID stays the same.
- **Replace:** anything else. The deploy deletes the fingerprint ConfigMap, runs `shacl_resync.sh REPLACE=package` with the install, deploys the Fuseki graphs, and writes the ConfigMap with the new job ID.

Because the replacement goes through the resync:
- topics and their IDs stay;
- its preconditions are checked before anything is stopped;
- a second deploy is refused while a resync runs;
- the re-snapshot is the single Connect restart after the new job's readers are placed (#1114).

`check-release-keeps-topics.sh` isn't needed: nothing is destroyed. `make helm` builds the chart and stops writing the tables; `submit-postgres-tables` stays a target for manual use.

Alternatives considered:
- *`helmfile destroy`, then write and apply:* with Strimzi running it deletes the topics, `iff.rdf` among them. That breaks the resync's "topics kept", and a quick re-apply races Strimzi's pending deletion. A pre-#1038 release would lose `iff.ngsild.entities`.
- *`REPLACE=fresh`, then write the tables, then apply:* the stop and the start are one command, with no point between them for the tables. It also restarts the old statement set.
- *An in-place diff of the tables:* constraint ids are positions in the generated package, so the old statements would read renumbered rows. It doesn't replace the statements either.

### D4: Change data capture after the rewrite

A job started after the tables were rewritten reads each row once on k3d. After `flink-undeploy` and a deploy that rewrote the tables, a fresh job's source emitted 5068 rows for 5068. Its first snapshot covers the table, and streaming begins at the snapshot's position, not at the slot's older one.

The e2e assertion (task 3.2: source rows equal table rows after the replacement) keeps that true. If it ever fails, the install step drops the two replication slots before writing the tables, and the new job creates them again.

### D5: The deploy suite's busy operator, and what it no longer covers

In the replace path the old statement set is deleted, which needs the operator. So the suite can't hold the operator back before the deploy. It holds it back from the moment the old statement set is gone, so that the install creates the new one while the operator is away, and lets it back `HOLD` seconds after the new statement set exists. Holding it only once the new one exists would race the operator's create handler, which acts within seconds. That shows that the resync's start step waits for the new job and its readers, and that Connect restarts only after them.

It no longer covers the race of #1114 itself: a statement set still reporting `RUNNING` for the old job after its spec changed. On the replace path that can't occur, because the old object is gone and the new one has no status until the operator acts. On the unchanged path the statement set doesn't change. `restart_connect.sh`'s check that the operator has taken over the statement set therefore no longer runs on a replacing deploy. It stays for the unchanged path and for manual use, and its unit test keeps it covered.

### D6: Knowledge a new package drops is removed from iff.rdf with tombstones

Task 5.1 showed that `iff.rdf` keeps every knowledge triple any earlier package had. On k3d, after packages were replaced, it held 6,368 keys and not one tombstone, while the rdf table held 238 rows. The install rewrites the table with `DROP TABLE`, `CREATE TABLE` and `INSERT`. A dropped table produces no delete events, and the rdf connector's `ExtractNewRecordState` drops deletes and tombstones anyway (its defaults). The validation reads `iff.rdf` as an upsert table, always from the earliest offset, so a new job saw every triple ever deployed. That applies to `main` too, after any package change.

The install step therefore ends with `drop_removed_knowledge`:
- It reads the keys of the new rdf table from Postgres.
- It reads `iff.rdf` from its earliest offset to the end offset taken just before, exactly that many records. The read ends on a topic that is written to meanwhile, and a short read fails the step.
- It writes a tombstone for every key whose last record is live and that the table lacks. The tombstone carries the key's own bytes, produced by the console producer with `null.marker` (Kafka 3.2 and later). The comparison parses the JSON keys on both sides.
- An empty or unreadable table fails the step, so a broken read can never remove the whole knowledge.

Tombstones, not a truncation of the topic:
- A tombstone is the delete signal of the upsert table, so it also reaches a job that is already running.
- It works under any cleanup policy. `iff.rdf` is auto-created with `delete`.
- It doesn't race a reader.
- It leaves the re-snapshot as it is.

Deleting rows in the table instead would not reach `iff.rdf` at all, because the connector drops the events.

Measured on k3d: the first replacement of tonight wrote 6,154 tombstones, and the topic then held exactly the 214 keys of the new table as live. The next replacement with the same knowledge wrote none.

This doesn't change what #1152 needs. #1152 is about the re-snapshot sending unchanged rows again; the tombstones only remove keys that left the table.

## Risks / Trade-offs

- **A changed package costs the resync,** about 3 minutes on k3d, where an unchanged one costs nothing. Today's manual workaround is longer.
- **The deploy now needs what the resync needs:** Alerta, Core Services and the platform watchdog's state ConfigMap, also on a first deploy. Where they're missing, the deploy fails before it stops anything, with the resync's message. The shacl2flink README states this requirement.
- **The first deploy after this change replaces the validation once:** there is no fingerprint ConfigMap yet. Intended.
- **The ConfigMap outside the release:** `flink-undeploy` deletes it as well, so an undeployed validation keeps no stale fingerprint. Deleted by hand, the next deploy replaces, which is the safe direction.
- **Deleted knowledge triples:** the resync empties only the job's three topics. Whether `iff.rdf` keeps a triple that a changed package removed is checked on the cluster (task 3.3). If it does, the install step empties `iff.rdf` as well.
