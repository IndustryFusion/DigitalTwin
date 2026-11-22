# Design

## Context

The watchdog runs every two minutes, as the `kafka-connect-restart` CronJob does; the restarter deletes the Connect pod every half state TTL, and Strimzi creates a new one within seconds. For a moment there is therefore no pod, or one that is still starting. The watchdog already lists the Connect pods to read their logs.

No conflict with existing specs or component documentation: the new requirements add an alert of their own and leave `ValidationConsistency` and `ConnectorState` as they are.

## Goals / Non-Goals

**Goals:**
- Raise at the next run that kafka-connect has no running pod, without raising it for the restarter's own restart.
- Close an alert of the replaced check.

**Non-Goals:**
- Telling why the pod doesn't run; the alert names the place to look.

## Decisions

### D1: Running, starting or none, from the pods

The check lists the kafka-connect pods with their creation time and the start of their container. One with a started container is running; one created less than five minutes ago without a started container is starting; otherwise there is none (no pod, or only pods that never got their container running, such as a crashing one). A pod list that can't be read posts nothing.

*Alternatives:*
- The KafkaConnect resource's ready condition: it changes with every restart and reconciliation, and it doesn't say whether a pod is merely starting.
- Keep the time of the last running pod in the watchdog's ConfigMap and alert after a span without one: more state for what the pod's own age already says.

### D2: A moment without a running pod is looked at again

When the list shows no running or starting pod, the check lists the pods once more after 20 seconds and judges from that second list, so that a run between the restarter's delete and Strimzi's create raises nothing, also while the old pod is still listed as terminating.

*Alternative:* treat no pod as starting: a kafka-connect scaled to zero or failing to schedule would never be raised.

### D3: Close the replaced check's alert on every run

The watchdog posts `ResyncRecency` on `kafka-connect` as normal on every run. Alerta keeps one alert per resource and event, so this closes an open one and leaves a closed one as it is.

*Alternative:* post it once, kept in the ConfigMap: a platform upgraded while the ConfigMap couldn't be written would keep the old alert.

## Risks / Trade-offs

- A run that sees no running or starting pod waits 20 seconds longer.
- A pod caught in a crash loop counts as running while its container is up, so `ConnectPods` can open and close with its restarts; that it crashes shows in the restarts of the pod.
- On a platform that never had the replaced check, every run posts a closed `ResyncRecency` alert again.
- A pod that keeps crashing within five minutes of each restart counts as starting until five minutes have passed; then it is raised.
