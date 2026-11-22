# Design

## Context

A standard platform install deploys no `shacl-validation` statementset. Only shacl2flink's `test-flink-e2e` target deploys one, from a throwaway KMS, runs its suites against it and removes it; the `flink` shard and the nightly both run that target after the platform suites. The watchdog's end-to-end test runs with the platform suites (suite `test-jobs`, shard `broker`), so it never sees the validation deployed.

Conflict with existing specs: *Pull requests run the K8s test in shards* says every suite belongs to exactly one shard. That still holds: the suite `test-jobs` stays in `broker`; the target runs one test file of it once more, as part of shacl2flink's test, as it runs its own suites.

## Goals / Non-Goals

**Goals:**
- Run the watchdog's end-to-end test once with the validation deployed, in pull requests and in the nightly, and fail it there when the reset or the refreshes are not found.

**Non-Goals:**
- Waiting for a refresh after the reset: a fresh deploy is still rebuilding, which the test already accepts.

## Decisions

### D1: The test runs inside `test-flink-e2e`

After its own suites and before removing the validation, `test-flink-e2e` runs the watchdog's end-to-end test with `VALIDATION_DEPLOYED=true`. Its result counts towards the target's.

*Alternatives:*
- Deploy the validation in the `broker` shard for the test: a second deploy of shacl2flink's KMS and its Fuseki upload in a shard that doesn't run shacl2flink otherwise.
- A step of its own in the workflows between deploy and undeploy: the deploy and the undeploy are inside the target, and both workflows would need the same change.

### D2: The test is told the validation is deployed

With `VALIDATION_DEPLOYED=true` the test requires the statementset, asserts that the watchdog's state holds the reset it read from Flink and that it judged the consistency, and that the complete refreshes of both connectors it recorded are no older than the start of the running Connect pod, which snapshots both connectors when it starts. Refreshes an earlier pod's log left in the state therefore don't count. When the pod has just been restarted and its snapshot still runs, the test runs the watchdog again, every 30 seconds for up to five minutes. Without `VALIDATION_DEPLOYED`, the test keeps following what the platform has.

*Alternative for the refreshes:* clear the recorded refreshes before the test's run. On the next run, the watchdog would then measure the gap from the reset and could latch a false inconsistency on a platform that has run longer than the state TTL.

*Alternative:* follow the platform in both places: a deploy that failed or a statementset of another name would make the test take the branch without validation and pass.

### D3: The test's own file selects the `flink` shard

The path `test/bats/test-jobs/platform-watchdog.bats` selects `broker` and `flink`; other files of the suite still select only `broker`. `helm/charts/alerta/` already selects both.

*Alternative:* select `flink` for the whole suite directory: every change to another job's test would run the shard.

## Risks / Trade-offs

- The `flink` shard and the nightly take about a minute longer: one watchdog run.
- A failure of the watchdog's test now fails shacl2flink's end-to-end step, whose log names the test.
