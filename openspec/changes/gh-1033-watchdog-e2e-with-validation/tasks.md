# Tasks

## 1. The test with the validation deployed

- [ ] 1.1 `test-flink-e2e` runs the watchdog's end-to-end test with `VALIDATION_DEPLOYED=true` before removing the validation, and fails when it fails (D1); verify in the `flink` shard of this pull request ("Validation deployed")
- [ ] 1.2 With `VALIDATION_DEPLOYED=true` the test requires the statementset, the reset and the refreshes of both connectors (D2); verify in the `flink` shard ("Validation deployed") and by its assertions on the reset ("Flink not reachable from the watchdog")

## 2. Shard selection

- [ ] 2.1 The watchdog's end-to-end test selects `broker` and `flink` (D3); verify with a test of the shard selection in `test/bats-unit/e2e-shards.bats` ("A change to the watchdog's end-to-end test")

## 3. Checks

- [ ] 3.1 Run the tests without a cluster and shellcheck as the Build workflow does; verify all pass
- [ ] 3.2 Verify that this pull request runs the `broker` and `flink` shards and that the `flink` shard's log shows the watchdog's test passing with the validation deployed
