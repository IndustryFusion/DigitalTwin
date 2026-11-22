# Delta for Platform Watchdog

## ADDED Requirements

### Requirement: Kafka Connect pods
The watchdog SHALL report `ConnectPods` on `kafka-connect`: critical at the next run when kafka-connect has no running pod, normal while one runs or is starting. A pod created less than five minutes ago SHALL count as starting, and a run that sees no running or starting pod SHALL look once more after a short wait before it judges. When the pods can't be listed, it SHALL post nothing.

#### Scenario: No running pod
- **WHEN** kafka-connect has no pod, or only a pod older than five minutes whose container doesn't run
- **THEN** `ConnectPods` is critical at that run

#### Scenario: Restarted by the restarter
- **WHEN** the Connect pod was replaced less than five minutes ago and its container hasn't started yet
- **THEN** `ConnectPods` is normal

#### Scenario: Between delete and create
- **WHEN** a run sees no running or starting pod, and a new pod appears before the second look
- **THEN** `ConnectPods` is normal

#### Scenario: Running again
- **WHEN** a Connect pod runs again after the alert
- **THEN** `ConnectPods` is normal and closes

### Requirement: The replaced pod-age check
The watchdog SHALL post `ResyncRecency` on `kafka-connect` as normal on every run, so that an alert of the replaced pod-age check left open from before is closed.

#### Scenario: An open alert of the replaced check
- **WHEN** a `ResyncRecency` alert on `kafka-connect` is open after the upgrade
- **THEN** the next run closes it
