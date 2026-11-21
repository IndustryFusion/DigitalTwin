# Design

## Context

The watchdog is a CronJob of the alerta chart (`platform-watchdog.yaml`), a bash script on the kubectl image, running every two minutes and posting to Alerta over `/dev/tcp`, so that it depends on none of the components it watches. The `kafka-connect-restart` CronJob restarts the Connect pods every half TTL, read from the deployed statementset, and the restart makes Debezium re-snapshot its tables; the debezium-bridge sends every row again into the topics the validation reads. The Flink chart enables no checkpointing, the sources of the views start at the latest offset, and `table.exec.state.ttl` expires the state of the views' dedup while the joins behind them are pinned.

The Connect REST API is closed to other pods by the network policy Strimzi creates. The watchdog image has no curl and no Kafka client.

## Goals / Non-Goals

**Goals:**
- Tell a consistent validation state from one that a refresh repairs and one that only a redeployment repairs, and say which in the alert.
- Notice a refresh that did not happen, whatever kept it from happening.

**Non-Goals:**
- Repairing anything: the watchdog reports, the operator acts.
- Comparing the alerts in Alerta with the verdicts of the validation; that is downstream of the validation state and a check of its own.
- Turning on checkpointing.

## Decisions

### D1: A refresh is a snapshot that completed, read from the Connect log

Debezium logs the start (`Snapshot step 1 - Preparing`) and the end (`Snapshot ended with SnapshotResult [status=COMPLETED`) of each snapshot, with the connector in the log context (`[<connector>|task-0]`). The watchdog reads the logs of the Connect pods and takes, per connector, the last start followed by a completed end. A snapshot that fails or a task that dies leaves no completed end.

*Alternatives:*
- The age of the Connect pods, as before: a restart without a complete snapshot looks the same as a good one (#973).
- The Connect REST API (connector offsets, task state): closed by the network policy, and it shows no completion time.
- Counting records on the topics: needs a Kafka client, and a full count per run.

### D2: When the state was emptied, from Flink

The watchdog reads the job of the statementset from the Flink REST API: its start time, the latest entry of its exception history (a failover), and the latest restored checkpoint. A failover after which no checkpoint was restored empties the state. A JobManager restart relaunches the job from its HA metadata without state unless a checkpoint is restored, so the start time of the JobManager container counts as well when it is later than the job's start and no checkpoint was restored after it. The rule holds whether the relaunched job keeps its start time and exception history or not.

An answer counts only when it is one: the job with its start time, the exception history and the checkpoint counts; an empty body or an error body is no answer.

*Alternative:* the statementset's timestamps; the operator writes `createdOn` on creation only and `updatedOn` on one update path, so a redeployment and a JobManager restart can't be told apart from them.

### D3: The judgement

With TTL the deployed state TTL and `ref` the start of the previous complete refresh of a connector (or the time the state was emptied, if no refresh started after it):
- *inconsistent* when a complete refresh ends more than TTL after `ref`, or more than TTL has passed since `ref` without one, and the job had state then (`ref` not before the state was emptied);
- *rebuilding* when a connector has no complete refresh that started after the state was emptied;
- *refresh late* when its last complete refresh started more than TTL/2 plus 240 s ago (the restarter's grace, as in the check this replaces);
- *consistent* otherwise.

The bound uses the start of the earlier refresh and the end of the later one, so that a key re-sent early in one snapshot and late in the next still counts.

### D4: Inconsistent is latched until the state is emptied

Once inconsistent, the finding is kept with the time the state was last emptied. It ends only when the state is emptied after it; a later refresh does not end it, because the second row in the pinned join stays. The alert is critical with `timeout: 0` and is posted on every run, so an alert closed by hand is raised again.

*Alternative:* report each run's view only, closing with the next good refresh: the alert would close while the validation stays wrong.

### D5: Findings kept in a ConfigMap of the watchdog

The Connect pods are replaced every half TTL, and their logs with them, so the start of the previous refresh is gone when the next one completes. The watchdog keeps, per connector, the start and end of the last complete refresh, when the state was last emptied and why, the latched finding, and since when it observes, in `platform-watchdog-state`. The chart creates it empty and keeps it on upgrades; the Role allows `get` and `patch` on that name only. A refresh before the first observed run is never taken as a gap: every gap and every age is measured from no earlier than when the watchdog began observing, and a state emptied before that is judged from then on, not reported as rebuilding. The watchdog also keeps its last run: after more than a quarter of the TTL without one, a Connect pod and its log may have come and gone unseen, so it observes anew. The patch sends the keys it dropped as `null`, since a merge patch keeps what it leaves out.

*Alternative:* no memory, the logs only: a gap that spans a pod restart is invisible.

### D6: One alert in four states

`ValidationConsistency` on the statementset carries the state in its severity, value and text: critical (inconsistent), warning (rebuilding, refresh late) or normal (consistent). The texts name the cause, the times, and the repair: for *rebuilding* and *refresh late* a refresh (restarting kafka-connect, or waiting for the restarter), for *inconsistent* redeploying the statementset, restarting Core Services, deleting the open SHACL alerts and a complete refresh.

*Alternative:* one event per state: an operator would have to close the old one when the state changes.

### D7: Connector state from the KafkaConnector status

Strimzi writes the connector's and its tasks' states into the KafkaConnector status, which the watchdog reads with kubectl. A connector or task not `RUNNING` is critical at once, before the refresh window is affected.

### D8: Judging only with full knowledge

The watchdog judges the consistency only when it can read the job from Flink (with the JobManager's start), the Connect pods and their logs, its own ConfigMap, and for each connector a complete refresh since it began observing; a failed kubectl read is no answer, a Connect pod still starting has no log yet, and a ConfigMap that can't be written (it writes the run's time first) is reported like one that can't be read. A span without knowledge shorter than a quarter of the TTL is like a skipped run; only a longer one makes it observe anew. Without the job it keeps posting an inconsistency it kept and otherwise warns that the consistency can't be assessed; once it reads the job again it observes anew, like after a gap in its own runs. Without its ConfigMap it posts no `ValidationConsistency`, so the alert stays as it was, and warns with `WatchdogState` instead. A connector without a complete refresh since observing began is a warning until a TTL has passed without one.

*Alternative:* judge with what is left (the kept reset, a held gap, this run's log alone). Each such path needs its own rules for what is known, and every one of them can raise or clear a critical alert on a guess.

## Risks / Trade-offs

- The log lines are Debezium's; a Debezium upgrade that changes them makes every refresh look missing, which shows as *refresh late* and then *inconsistent*, not as silence. The tests pin the lines the watchdog expects.
- A JobManager restart that restores a checkpoint is not an emptied state; with checkpointing off, every JobManager restart is.
- The watchdog judges the validation state, not what reached Alerta: alerts left open by a fault downstream are not reported.
