# Proposal

Issue: #975

## Why

The platform watchdog's resync check decides from the age of the newest kafka-connect pod whether the Debezium refresh happened in time. #973 showed that a pod restarted on schedule does not mean the tables were re-sent: a snapshot task failed with `OutOfMemoryError`, the pods were young, and the check reported a healthy resync while Flink state expired unrefreshed and relationship counts grew ("Found 9 relationships instead of [0, 1]").

A missed refresh window is also not repaired by the next refresh. The validation dedups its views in state that expires after the deployed state TTL, ahead of joins whose state is pinned; a key sent again after its state expired enters the pinned join as a second row. From that moment only emptying the state repairs the validation, so the alert has to say so and stay. And the state is emptied without any snapshot gap too: the Flink chart enables no checkpointing, so a failover or a JobManager restart starts the validation empty, the same as a new deployment, until the next complete refresh. The comment on #975 adds both to the issue.

## What Changes

- The watchdog follows the Debezium refreshes that completed, per connector, from the Connect log, instead of the age of the Connect pods.
- It determines when the validation state was last emptied: the job's start, a failover, or a JobManager restart, each without a restored checkpoint, read from the Flink REST API and the JobManager pod.
- It keeps what it saw across runs in a ConfigMap of its own.
- It raises one alert, `ValidationConsistency` on the statementset, in one of four states:
  - *inconsistent*: a key can have gone longer than the state TTL without a complete refresh while the job had state. Critical, without timeout, kept until the state has been emptied, also when closed by hand; it names the repair and a checkpoint that could restore a consistent state, if one exists.
  - *rebuilding*: the state was emptied and no complete refresh followed yet; it says when one is due.
  - *refresh late*: a refresh is overdue while the window is still open.
  - *consistent*: otherwise; it closes the alert.
- It reports a Debezium connector whose connector or tasks are not `RUNNING`, from the KafkaConnector status.
- The pod-age check (`ResyncRecency`) is replaced; its tests are replaced by tests of the new states.

## Capabilities

### New Capabilities
- `helm/platform-watchdog`: what the platform watchdog decides about the consistency of the streaming validation and the connectors feeding it, and how it reports it in Alerta.

### Modified Capabilities

## Impact

- `helm/charts/alerta/templates/platform-watchdog.yaml`: the script, its Role (pod logs, its own ConfigMap, KafkaConnectors) and the new ConfigMap `platform-watchdog-state`.
- `test/bats-unit/platform-watchdog-alerts.bats`: the resync tests become tests of the consistency states and the connector check.
- No new dependency; the watchdog keeps using the kubectl image, bash and jq.
- Operators see `ValidationConsistency` and `ConnectorState` instead of `ResyncRecency`.
