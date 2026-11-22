# Tasks

Order: #1036 (#1035) is merged and archived first. Then rebase this change: add the `alert-resync` delta (8.1), and copy *Repair*, *Rebuilding* and *Late refresh* of `helm/platform-watchdog` again from the archived text and add this change's sentences (8.2). Implementation starts after that.

## 1. Checkpoint settings and annotations in shacl2flink

- [ ] 1.1 Make checkpointing the default (`CHECKPOINT ?= true`). Add to the validation's settings the mode, retention on cancellation, `num-retained` from a new value `flink.checkpointsRetained` (default 3), incremental checkpoints and `min-pause` (D1, D8). Verify with `semantic-model/shacl2flink/tests/test_utils.py`: the settings are there with checkpointing and absent without, and `shacl-constraints` is unchanged
- [ ] 1.2 Drop `execution.savepoint.ignore-unclaimed-state` from the validation's settings (D3); verify with the same tests
- [ ] 1.3 Write the statementset annotations (D10, D11):
  - `industry-fusion.com/read-topics`: the Kafka topics of the tables the statements read;
  - `refresh-period`, `restore-throughput`, `restore-start-allowance` and `restore-margin`, from new helm values `flink.refreshPeriod` (`1800 s`), `flink.restoreThroughput`, `flink.restoreStartAllowance` and `flink.restoreMargin`.

  Verify with unit tests: for the e2e KMS the read topics are `iff.ngsild.attributes`, `iff.ngsild.entities`, `iff.rdf` and the trigger topic, without `attributes_insert` and the `postgres-cdc` tables. Also verify that the TTL and retention values in `helm/values.yaml.gotmpl` and the environment files are unchanged (diff)
- [ ] 1.4 Set `industry-fusion.com/topics-reset-at` in `flink-deploy` after the KafkaTopics are recreated (D6). Verify with a bats-unit test of the target with stubbed `kubectl`, and on the platform by reading the annotation after `make flink-deploy`
- [ ] 1.5 Check on Flink 1.20.4 that the 1.20 key names are accepted per job and reported by `/jobs/<id>/checkpoints/config`; verify by the platform test "Deployed by default" (7.1)

## 2. Refresh period

- [ ] 2.1 Make the restarter restart the Connect pods once they are older than `min(refreshPeriod, ttl/2) − max(60 s, ttl/100)`, and log when the cap applies (D11). Rewrite the values and restarter comments that tie the refresh to `ttl/2`. Verify with bats-unit tests of the restarter script on stubbed pod ages and annotations:
  - defaults give 1740 s, as today ("Defaults");
  - a TTL of one day with the default period gives 1740 s ("A longer TTL");
  - a period above half the TTL is capped and logged ("A period above half the TTL")

## 3. Operator

- [ ] 3.1 Add `spec.restoreFrom` to the v1alpha4 CRD (D2); verify with `kubectl explain bsqls.spec.restoreFrom` on the platform and the operator's CRD test
- [ ] 3.2 Pass `restoreFrom` and the savepoint location as the submission's top-level `restoreFrom`, once per `metadata.generation`. Record `status.restoredFrom`, clear `status.location` and `status.checkpoints` in `create`, and report a failed restore as `DEPLOYMENT_FAILURE` without an empty start (D2, D5). Verify with unit tests in `FlinkSqlServicesOperator/test`:
  - the field is passed on the first submission, not on a resubmission of the same generation, and again for a new generation;
  - the savepoint location is passed as the field, with no `SET` string;
  - a failure is reported
- [ ] 3.3 Compute the fingerprint with deprecated keys mapped to their 1.20 names, set `execution.checkpointing.dir` from `/jobmanager/config` unless the spec sets it, and write `status.fingerprint` (D4). Verify with unit tests:
  - it is stable for the same submission;
  - it doesn't change with `restoreFrom`, any `execution.checkpointing.*` setting, incremental or full, or the legacy `state.backend.incremental`;
  - it changes with a statement, a table DDL, parallelism, `state.backend`, a RocksDB option or the Flink version
- [ ] 3.4 Record the latest completed checkpoints in `status.checkpoints` from `/jobs/<id>/checkpoints`, bounded as in D5, with the per-topic source offsets of the same timer run, and the restored path. Verify with unit tests on stubbed Flink answers: a new checkpoint comes first with its offsets summed per topic, the bound is kept, entries stay when the job ends, and nothing is patched when nothing changed
- [ ] 3.5 Update `FlinkSqlServicesOperator/README.md` (field, savepoint path, status, fingerprint); verify by review

## 4. Gateway and submit job

- [ ] 4.1 Accept `restoreFrom` in the submission, refuse a malformed path with `400` naming the field, and run `flink run -s <path> --python job.py`, never with `-n` (D2, D3). Verify with `FlinkSqlGateway/test/testGateway.js`: the command with and without the field, malformed paths refused, no `-n`
- [ ] 4.2 Keep `job.py` reading settings as maps and fail with a clear message on a non-map entry; verify with a unit test of `job.py` with a stubbed table environment

## 5. The resync and pruning

- [ ] 5.1 Implement the two rules and the catch-up estimate as one shared, sourced script, so the resync and the watchdog compute the same (D10). Verify with bats-unit tests on fixed inputs:
  - state rule just inside (one minute) and just outside (one minute), and the reason naming refresh, TTL, catch-up and margin ("Just inside the state rule", "Just outside the state rule");
  - replay rule at one minute inside and outside a one-hour retention, naming the topic ("Just inside and outside the replay rule");
  - the smaller of `shaclTtl` and `viewTtl` taken;
  - catch-up from backlog, snapshot records and throughput, the timer-lag addition, and a growth of exactly ten minutes for ten minutes of throughput ("Catch-up grows with the backlog");
  - the lower of the configured and the observed throughput;
  - a missing refresh, snapshot or offsets record fails ("A refresh not recorded");
  - `restorable until` as `min(t_a, t_b)` with backlog growth, checked against a step-by-step recomputation
- [ ] 5.2 In the resync script of #1035, implement `REPLACE=checkpoint` with optional `RESTORE_FROM`, and `REPLACE=auto` (D6). This covers the candidates, the topics-reset time, the inconsistency mark, the rules, the refusal and choice messages, and the restore with the topics kept and `status.checkpoints` carried over. Verify with bats-unit tests on stubbed `kubectl`, Kafka tools, Flink REST and the watchdog's ConfigMap:
  - the newest restorable checkpoint is chosen, and a given path is chosen;
  - `auto` restores when one passes, printing the checkpoint and its time ("Automatic, restorable");
  - `auto` runs as fresh when none passes, printing the reason per candidate and exiting 0 ("Automatic, none restorable");
  - refused with `checkpoint`: fingerprint mismatch, not restorable (rule and numbers named), a topic shortened after the checkpoint, taken while inconsistent, before the topics were reset, a path not recorded, none recorded;
  - nothing changed on any refusal
- [ ] 5.3 Set the topics-reset annotation in the fresh resync after emptying the trigger topic; verify with a bats-unit test
- [ ] 5.4 Add `make shacl-checkpoints-prune` and run it after a successful resync and in `flink-deploy` after the new job's first checkpoint (D7). Verify with bats-unit tests on a stubbed object store:
  - kept: the running job's, the listed ones, the restored one until the first checkpoint;
  - removed: unlisted of the fingerprint, other fingerprints, those before the topics reset.

  On the platform, list the validation's directory after a KMS change deployed without a resync ("After a KMS change" of pruning)
- [ ] 5.5 Update the resync README: `REPLACE=checkpoint` and `REPLACE=auto`, the two rules, what a refusal or a fallback says; verify by review

## 6. Watchdog

- [ ] 6.1 Keep per checkpoint the last refresh before it, the inconsistency mark, and for the last refresh the source records and the lowest rate. Judge a restored state by the state rule (D13, *Restored validation state*). Verify with tests in `test/bats-unit` of the watchdog script on stubbed Flink, `kubectl` and Connect logs:
  - a failover restored within a minute stays normal, without a rebuilding warning;
  - a resync restore is reported consistent, naming the checkpoint;
  - a restore past the TTL is critical, naming checkpoint, refresh and TTL;
  - the record is kept for a new checkpoint by the next run, marked when an inconsistency was held, and dropped when the checkpoint is no longer listed
- [ ] 6.2 Report `restorable until` in `ValidationConsistency` with the shared rules, the backlog from the running job's source positions and the retention from KafkaTopics; add `get`/`list` on `kafkatopics` to the Role (*Restorable checkpoint*). Verify with tests: "Restorable" (time equals the shared script's `min(t_a, t_b)`), "The time moves on", "None restorable", "Retention unknown", "No job"
- [ ] 6.3 The repair names `make shacl-resync REPLACE=fresh` with the TTL reason (*Repair of an inconsistent state*); verify with tests "The repair", "No checkpoint", "A checkpoint before the state went stale" (neither `REPLACE=checkpoint` nor `REPLACE=auto` in the text)
- [ ] 6.4 The rebuilding warning names `REPLACE=auto` with the checkpoint it would restore or that it would start fresh (*Rebuilding validation state*). Verify with tests "A lost job with a restorable checkpoint" and "None restorable", and that "After a failover", "The refresh comes" and "The refresh does not come" still pass
- [ ] 6.5 Late refresh measured against the effective refresh period (*Late refresh*); verify with tests "Overdue" and "A TTL longer than twice the refresh period"
- [ ] 6.6 On a deployed platform, run the watchdog once with a recorded checkpoint and once after a restore by the resync. Verify with `test/bats/test-jobs/platform-watchdog.bats` that `ValidationConsistency` names `restorable until`, and after the restore is normal naming the restored checkpoint

## 7. Platform tests

- [ ] 7.1 Add cases to the e2e suite run by `test-flink-e2e`: checkpointing reported as deployed ("Deployed by default"), a completed checkpoint listed in the status with offsets, and the checkpoint still there after a cancel ("Cancelled"); verify they pass in the `flink` shard
- [ ] 7.2 E2E restore within the computed limits. With the e2e KMS deployed with today's defaults and its known violations open:
  - wait for a recorded checkpoint that the watchdog reports `restorable until` a time at least 10 minutes ahead;
  - repair one violation and delete one violating entity;
  - break the state: cancel the job through Flink REST so the operator starts it empty, and close the SHACL alerts;
  - run `make shacl-resync REPLACE=checkpoint` before that time.

  Verify:
  - the restored path is reported and the trigger topic wasn't emptied;
  - the open SHACL alerts equal the model's current violations with the same severity and text, without the repaired and deleted ones ("Restored after the state was lost", "Changes in the gap", "The latest restorable checkpoint");
  - the measured catch-up is below the estimate (recorded for 8.3);
  - the `postgres-cdc` sources of the constraint tables continued (open question on the replication slot)
- [ ] 7.3 E2E refusal after a topic's retention was shortened: after a checkpoint is recorded, wait until it is a few minutes old and set the retention of `iff.ngsild.attributes` below its age through its KafkaTopic. Then run `make shacl-resync REPLACE=checkpoint`, and verify the refusal before the first step naming the topic, its retention and the age, with an unchanged job ID, alerts and offsets ("A topic shortened after the checkpoint"). Restore the retention afterwards
- [ ] 7.4 E2E `REPLACE=auto` falling back to fresh: deploy with `shaclTtl` and `viewTtl` of `900 s` and a refresh period of `300 s`, wait until the state rule fails for every recorded checkpoint, and run `make shacl-resync REPLACE=auto`. Verify the reason per checkpoint in the output, a fresh job, the topics emptied, exit 0, and the alerts equal the violations ("Automatic, none restorable"). On the same deployment, run `REPLACE=auto` right after a checkpoint and verify it restores ("Automatic, restorable")
- [ ] 7.5 E2E refusal after a KMS change: deploy a variant of the e2e KMS with one shape changed, then run the resync with a restore. Verify the refusal before the first step and an unchanged job ID, alerts and topic offsets ("After a KMS change"); then run with `RESTORE_FROM` set to the old path and verify "A path not recorded" or the fingerprint refusal
- [ ] 7.6 E2E restore claims all state, and the backend: create a statementset naming a checkpoint of another fingerprint, and verify that the job doesn't run and the status reports it ("State of another statementset"). Redeploy with incremental checkpoints off and verify the same fingerprint and a restore ("Another interval"); redeploy with `NOROCKSDB=true` and verify a new fingerprint ("Another state backend")
- [ ] 7.7 E2E outage within the limits, with the example sizing: deploy with TTL `1 d` and the read topics' retention `1 d`, stop the Flink JobManager and TaskManager for 70 minutes (HA data kept), start them again and wait for the next refresh. Verify "Restored after an outage within the limits", that the watchdog stays consistent ("A failover restored from a checkpoint"), and that refreshes kept every 30 minutes ("A longer TTL")
- [ ] 7.8 Keep `test-shacl-flink-e2e`, `test-shacl-flink-scorpio-e2e`, the #1035 resync tests, the watchdog tests and `test/bats-unit` passing; verify that the Build workflow and every K8s e2e shard are green

## 8. Specs, documentation and cost

- [ ] 8.1 After #1035 is archived, add the MODIFIED delta of `shacl2flink/alert-resync` *Restore from a checkpoint* as drafted in the design (*Dependency on #1035*); verify with `openspec validate --all --strict`
- [ ] 8.2 After #1036 is archived, copy *Repair of an inconsistent state*, *Rebuilding validation state* and *Late refresh* again from `main` into this change's watchdog delta, add this change's sentences, and keep each text at 500 characters or less; verify with `openspec validate gh-1042-validation-from-checkpoint --strict`
- [ ] 8.3 Measure on the e2e KMS as in D9:
  - today's settings with checkpoint intervals 10 s, 1 min and 5 min, incremental on and off, and checkpointing off as the baseline;
  - the example sizing TTL `1 d` and retention `1 d`: state size, RocksDB live data, topic sizes on disk, Core Services' resend after a reset;
  - from the restore tests, restore and catch-up times against the estimate;
  - on a larger deployed KMS where one is available.

  Verify the table in the shacl2flink README, the default interval set from it, and the defaults of `restoreThroughput`, `restoreStartAllowance` and `restoreMargin` set so the estimate is above every measured catch-up
- [ ] 8.4 Write the sizing guide in the shacl2flink README (D14):
  - for a wanted outage tolerance `D`, `TTL > D + refresh period + 240 s + catch-up + margin` for both TTLs, retention of every read topic `> D + margin`, and checkpoint interval and refresh period small against `D`;
  - the cost of each: ghost state of keys no longer refreshed and state size, Kafka disk mostly for `iff.ngsild.attributes` (up to twice the retention through #978) and Core Services' resend, checkpoint I/O and alignment, snapshot load;
  - today's defaults (a tolerance of about 20 minutes in the worst case, under an hour at best) and the example with the numbers of 8.3.

  Verify by review, and by computing the example's limits with the shared script of 5.1
- [ ] 8.5 Run `openspec validate gh-1042-validation-from-checkpoint --strict` and `openspec validate --all --strict`; verify both pass
