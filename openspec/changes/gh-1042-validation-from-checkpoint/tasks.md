# Tasks

Implementation starts after #1036 (#1035) is merged; task 6.1 needs it archived.

## 1. Checkpoint settings in shacl2flink

- [ ] 1.1 Make checkpointing the default (`CHECKPOINT ?= true`) and add to the validation's settings the mode, retention on cancellation, `num-retained` from a new value `flink.checkpointsRetained` (default 3), incremental checkpoints and `min-pause` (D1, D8); verify with `semantic-model/shacl2flink/tests/test_utils.py`: the settings with checkpointing, none of them without, `shacl-constraints` unchanged
- [ ] 1.2 Drop `execution.savepoint.ignore-unclaimed-state` from the validation's settings (D3); verify with the same tests
- [ ] 1.3 Set the annotation `industry-fusion.com/topics-reset-at` on the statementset in `flink-deploy` after the KafkaTopics are recreated (D6); verify with a bats-unit test of the Makefile target with stubbed `kubectl`, and on the platform by reading the annotation after `make flink-deploy`
- [ ] 1.4 Check on Flink 1.20.4 that the 1.20 key names are accepted per job and reported by `/jobs/<id>/checkpoints/config`; verify by the "Deployed by default" platform test (5.1)

## 2. Operator

- [ ] 2.1 Add `spec.restoreFrom` to the v1alpha4 CRD (D2); verify `kubectl explain bsqls.spec.restoreFrom` on the platform and the CRD test of the operator
- [ ] 2.2 Pass `restoreFrom` and the savepoint location as the submission's top-level `restoreFrom`, once per `metadata.generation`, record `status.restoredFrom`, clear `status.location` and `status.checkpoints` in `create`, and report a failed restore as `DEPLOYMENT_FAILURE` without an empty start (D2, D5); verify with unit tests in `FlinkSqlServicesOperator/test`: field passed on the first submission, not on a resubmission of the same generation, passed again for a new generation, savepoint location passed as the field and no `SET` string, failure reported
- [ ] 2.3 Compute the fingerprint and set `execution.checkpointing.dir` from `/jobmanager/config` unless the spec sets it, and write `status.fingerprint` (D4); verify with unit tests: stable for the same submission, independent of `restoreFrom` and `execution.checkpointing.*`, changed by a statement, a table DDL, parallelism or Flink version
- [ ] 2.4 Record the latest completed checkpoints in `status.checkpoints` from `/jobs/<id>/checkpoints`, bounded as in D5, and the restored path; verify with unit tests on stubbed Flink answers (new checkpoint first, bound kept, entries kept when the job ends, no patch when unchanged)
- [ ] 2.5 Update `FlinkSqlServicesOperator/README.md` (field, savepoint path, status); verify by review

## 3. Gateway and submit job

- [ ] 3.1 Accept `restoreFrom` in the submission, refuse a malformed path with `400` naming the field, and run `flink run -s <path> --python job.py`, never with `-n` (D2, D3); verify with `FlinkSqlGateway/test/testGateway.js`: command with and without the field, malformed paths refused, no `-n`
- [ ] 3.2 Keep `job.py` reading settings as maps and fail with a clear message on a non-map entry; verify with a unit test of `job.py` with a stubbed table environment

## 4. The resync

- [ ] 4.1 In the resync script of #1035, implement `REPLACE=checkpoint` with optional `RESTORE_FROM`: candidates, topics-reset time, retention read from Kafka with `RESTORE_MARGIN`, refusal messages, restore with the topics kept and `status.checkpoints` carried over (D6); verify with bats-unit tests on stubbed `kubectl`, Kafka tools and Flink REST: newest fitting chosen, given path chosen, fingerprint mismatch refused, too old refused with age and limit, before topics reset refused, path not recorded refused, none recorded refused, nothing changed on any refusal
- [ ] 4.2 Set the topics-reset annotation in the fresh resync after emptying the topics; verify with a bats-unit test
- [ ] 4.3 Prune checkpoint directories after a successful resync (D7); verify with bats-unit tests on a stubbed object store (kept: the running job's, the listed ones, the restored one until the first checkpoint; removed: unlisted of the fingerprint, other fingerprints older than the retention) and on the platform by listing the fingerprint directory
- [ ] 4.4 Update the resync README section: when to restore, the rule for the age, what a refusal says; verify by review

## 5. Platform tests

- [ ] 5.1 Add `test/bats` or `semantic-model/shacl2flink/tests/bats` cases to the e2e suite run by `test-flink-e2e`: checkpointing reported as deployed ("Deployed by default"), a completed checkpoint listed in the status, and the checkpoint still present after a cancel; verify they pass in the `flink` shard
- [ ] 5.2 E2E restore: with the e2e KMS deployed and its known violations open, wait for a recorded checkpoint, repair one violation and delete one violating entity, break the state (cancel the job through Flink REST so the operator starts it empty, and close the SHACL alerts), run `make shacl-resync REPLACE=checkpoint`; verify the restored path is reported, the topics weren't emptied, and the open SHACL alerts equal the model's current violations with the same severity and text, without the repaired and deleted ones ("Restored after the state was lost", "Changes in the gap")
- [ ] 5.3 E2E refusal after a KMS change: deploy a variant of the e2e KMS with one shape changed, run the resync with a restore; verify the refusal before the first step, unchanged job ID, alerts and topic offsets ("After a KMS change"); then run with `RESTORE_FROM` set to an old path and verify "A path not recorded" or the fingerprint refusal
- [ ] 5.4 E2E too old: run the resync with `RESTORE_MARGIN` set so that the limit is below the checkpoint's age; verify the refusal names age and limit and nothing changed ("Too old")
- [ ] 5.5 E2E restore claims all state: create a statementset naming a checkpoint of another fingerprint; verify the job doesn't run and the status reports it ("State of another statementset")
- [ ] 5.6 Keep `test-shacl-flink-e2e`, `test-shacl-flink-scorpio-e2e`, the #1035 resync tests, the watchdog tests and `test/bats-unit` passing; verify the Build workflow and every K8s e2e shard are green

## 6. Cost and specs

- [ ] 6.1 After #1035 is archived, add the MODIFIED delta of `shacl2flink/alert-resync` *Restore from a checkpoint* as drafted in the design (*Dependency on #1035*); verify `openspec validate --all --strict`
- [ ] 6.2 Measure the cost on the e2e KMS as in D9 (intervals 10 s, 1 min, 5 min; incremental on and off; off as the baseline) and on a larger deployed KMS where available; verify the table in the shacl2flink README with state size, checkpointed size, duration, alignment, busy and back-pressured time, storage, restore time and alert latency, and the default interval set from it
- [ ] 6.3 Run `openspec validate gh-1042-validation-from-checkpoint --strict` and `openspec validate --all --strict`; verify both pass
