# Tasks

## 1. The test with the validation deployed

- [x] 1.1 `test-flink-e2e` runs the watchdog's end-to-end test with `VALIDATION_DEPLOYED=true` before removing the validation, and fails when it fails (D1); verify in the `flink` shard of this pull request ("Validation deployed")
  - `semantic-model/shacl2flink/Makefile`: after shacl2flink's suites and before `flink-undeploy`, `VALIDATION_DEPLOYED=true bats …/test-jobs/platform-watchdog.bats || rc=1`.
- [x] 1.2 With `VALIDATION_DEPLOYED=true` the test requires the statementset, the reset and the refreshes of both connectors (D2); verify in the `flink` shard ("Validation deployed") and by its assertions on the reset ("Flink not reachable from the watchdog")
  - `test/bats/test-jobs/platform-watchdog.bats`: the statementset must exist, `reset` in `platform-watchdog-state` must be a time, both `*.done` keys must be no older than the running Connect pod's start (the watchdog runs again for up to five minutes while a fresh pod's snapshot runs), and the consistency must not be `unknown`. Without Flink the watchdog sets no reset and reports `unknown`, so the test fails.

## 2. Shard selection

- [x] 2.1 The watchdog's end-to-end test selects `broker` and `flink` (D3); verify with a test of the shard selection in `test/bats-unit/e2e-shards.bats` ("A change to the watchdog's end-to-end test")
  - *a change to the watchdog's end-to-end test runs broker and flink*; another file of `test-jobs` still selects only `broker`.

## 3. Checks

- [x] 3.1 Run the tests without a cluster and shellcheck as the Build workflow does; verify all pass
  - `bats test/bats-unit`: 82 tests pass; shellcheck of the bats suites and of `e2e-shards.sh` passes.
- [x] 3.2 Verify that this pull request runs the `broker` and `flink` shards and that the `flink` shard's log shows the watchdog's test passing with the validation deployed
  - All three shards ran (the shard script changed). In the `flink` shard, `test-flink-e2e` printed "the platform watchdog with the validation deployed", the test passed, and then the validation was removed.
