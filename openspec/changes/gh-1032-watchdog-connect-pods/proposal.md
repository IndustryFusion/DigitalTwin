Issue: #1032

## Why

#1021 replaced the watchdog's pod-age check `ResyncRecency` with `ValidationConsistency`, which follows the Debezium snapshots that completed. Two things the old check covered are no longer covered (noted in the reviews of #1021: https://github.com/IndustryFusion/DigitalTwin/pull/1021#pullrequestreview-5995294100, note 3, and https://github.com/IndustryFusion/DigitalTwin/pull/1021#pullrequestreview-5996243771, note 3):

- With no running kafka-connect pod, the old check went critical at once. Now it shows only as a late refresh after half the state TTL, and the KafkaConnector status can't stand in for it: it stays `RUNNING` across a Connect restart.
- An open `ResyncRecency` alert from before the upgrade is never closed, since nothing posts that event any more.

## What Changes

- A new check `ConnectPods` on `kafka-connect`: critical at the next run when kafka-connect has no running pod, normal while one runs or is starting. A pod the restarter has just replaced counts as starting for five minutes, and a moment without any pod is looked at once more before it counts.
- The watchdog posts `ResyncRecency` on `kafka-connect` as normal on every run, which closes an alert of the replaced check left open.

## Capabilities

### New Capabilities

### Modified Capabilities
- `helm/platform-watchdog`: new requirements **Kafka Connect pods** and **The replaced pod-age check**.

## Out of Scope

- Restarting kafka-connect; the watchdog reports, the restarter and the operator act.
- Watching other deployments' pods; the bridges have their own check.

## Impact

- Component: the platform watchdog in `helm/charts/alerta/templates/platform-watchdog.yaml`, and its tests in `test/bats-unit`.
- No contract between components changes; the alert events are the watchdog's own (`ConnectPods` is new, `ResyncRecency` only closes).
