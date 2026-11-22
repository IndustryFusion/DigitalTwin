Issue: #1033

## Why

The end-to-end test of the platform watchdog (`test/bats/test-jobs/platform-watchdog.bats`, added in #1021) runs in the `broker` shard, which deploys no `shacl-validation` statementset, and in the nightly before the validation is deployed. Both times the watchdog reports that the consistency can't be assessed and the test takes that branch, so reading the reset from Flink and finding the refreshes are never checked against a real cluster: a wrong Flink host or port, or a changed JobManager label, would still pass (noted in the review of #1021: https://github.com/IndustryFusion/DigitalTwin/pull/1021#pullrequestreview-5996633037, note 3).

## What Changes

- shacl2flink's platform end-to-end test (`make test-flink-e2e`), which deploys a validation statementset, runs the suites against it and removes it again, also runs the watchdog's end-to-end test while the validation is deployed. It runs in the `flink` shard of pull requests and in the nightly.
- There the test requires the statementset, and asserts that the watchdog read the reset from Flink and found a complete refresh of both connectors.
- A change to the watchdog's end-to-end test also selects the `flink` shard; a change to `helm/charts/alerta/` already does.

## Capabilities

### New Capabilities

### Modified Capabilities
- `ci/pull-request-tests`: new requirement **The watchdog judged against a deployed validation**.

## Out of Scope

- Moving the suite `test-jobs` to another shard; it stays in `broker`, where the watchdog's test keeps its branch without the validation.
- New scenarios of the watchdog itself; they are in the spec `openspec/specs/helm/platform-watchdog` and in `test/bats-unit/platform-watchdog-alerts.bats`.

## Impact

- Components: the shard selection of the K8s end-to-end workflow (`.github/scripts/e2e-shards.sh`, tests in `test/bats-unit`), shacl2flink's `test-flink-e2e` target, and the watchdog's end-to-end test.
- No contract between components changes.
