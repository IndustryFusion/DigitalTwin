# helm/platform-watchdog Specification

## Purpose
Defines what the platform watchdog decides about the consistency of the streaming SHACL validation and the Debezium connectors that feed it, and how it reports that in Alerta, so that an operator knows whether the validation is consistent, needs a refresh, or needs a redeployment.

## Requirements

### Requirement: Complete refreshes
The watchdog SHALL determine, for each Debezium connector feeding the validation, the last refresh that completed, with the time it started and the time it completed, from the connector's log. A restart of the Connect pods SHALL NOT count as a refresh.

#### Scenario: A refresh that dies halfway
- **WHEN** a connector's snapshot starts and does not complete, for example because its task failed
- **THEN** it does not count as a refresh, and the last complete refresh stays the one before

#### Scenario: Young pods without a refresh
- **WHEN** the Connect pods were restarted on schedule but a connector completed no snapshot since
- **THEN** the watchdog does not report the refresh as on time

### Requirement: Emptied validation state
The watchdog SHALL determine when the state of the validation job was last emptied: when the job started, when it failed over, or when the Flink JobManager restarted, each unless a checkpoint was restored then. It SHALL read this from the Flink REST API and the JobManager pod.

#### Scenario: A failover without a checkpoint
- **WHEN** the validation job fails over and no checkpoint is restored
- **THEN** the time of the failover is when the state was last emptied

#### Scenario: A failover restored from a checkpoint
- **WHEN** the validation job fails over and restores a checkpoint
- **THEN** the state does not count as emptied

#### Scenario: A JobManager restart
- **WHEN** the JobManager restarts after the job started and no checkpoint is restored
- **THEN** the time of the restart is when the state was last emptied

### Requirement: Flink not readable
When the watchdog can't read the validation job, because Flink doesn't answer or the statementset reports no job, it SHALL NOT judge the consistency: it SHALL neither raise nor end an inconsistency, SHALL keep posting an inconsistency it kept, and otherwise SHALL warn that the consistency can't be assessed, naming the cause, unless it reports a resync. After a long span without the job it SHALL observe anew.

#### Scenario: Flink down with a kept inconsistency
- **WHEN** the watchdog can't read the job while it keeps an inconsistency
- **THEN** `ValidationConsistency` stays critical

#### Scenario: Flink down otherwise
- **WHEN** the watchdog can't read the job, keeps no inconsistency and no resync is marked
- **THEN** `ValidationConsistency` is a warning that the consistency can't be assessed, naming whether Flink doesn't answer or the statementset reports no job, and no inconsistency is raised

#### Scenario: No job during a resync
- **WHEN** the statementset reports no job because a resync stopped it, and the watchdog keeps no inconsistency
- **THEN** `ValidationConsistency` reports the resync, and no inconsistency is raised

#### Scenario: Flink answers again
- **WHEN** the watchdog can read the job again after it could not for more than a quarter of the TTL
- **THEN** it observes anew from that run, and takes no gap from the time it could not read the job

#### Scenario: One unreadable run
- **WHEN** the watchdog could not read the job or a Connect log for a shorter span
- **THEN** it judges on as after a skipped run, so a window missed across that span is still found

### Requirement: Inconsistent validation state
When a key can have gone longer than the deployed state TTL without a complete refresh while the job had state, the watchdog SHALL raise a critical alert `ValidationConsistency` on the statementset that does not time out, measured from the start of the previous complete refresh, or from when the state was emptied if no refresh followed it. The alert SHALL stay until the state has been emptied, also when closed by hand.

#### Scenario: A missed window
- **WHEN** a complete refresh ends more than the TTL after the start of the previous complete refresh
- **THEN** the alert is critical, without timeout, and names the connector and the times

#### Scenario: No refresh within the TTL
- **WHEN** more than the TTL has passed since the start of the last complete refresh, and none followed
- **THEN** the alert is critical already, before any refresh comes

#### Scenario: The next refresh
- **WHEN** a complete refresh follows after the window was missed
- **THEN** the alert stays critical

#### Scenario: Closed by hand
- **WHEN** an operator closes the alert while the state has not been emptied
- **THEN** the next run raises it again

#### Scenario: Emptied after it
- **WHEN** the state is emptied after the window was missed, by a redeployment, a failover or a JobManager restart
- **THEN** the inconsistency ends, and the watchdog reports the state as rebuilding

### Requirement: Repair of an inconsistent state
The alert of an inconsistent state SHALL name the repair: the resync of the SHACL alerts with a fresh validation job, by its command, which stops the job, empties its topics, closes the open SHACL alerts, restarts Core Services without state, starts the job and waits until a complete refresh has been processed. It SHALL say whether a checkpoint taken before the state went stale could restore a consistent state instead.

#### Scenario: The repair
- **WHEN** the state is inconsistent
- **THEN** the alert names the resync command with a fresh job and its steps in their order

#### Scenario: No checkpoint
- **WHEN** the job has completed no checkpoint
- **THEN** the alert says that no checkpoint can restore the state

#### Scenario: A checkpoint before the state went stale
- **WHEN** the job completed a checkpoint before the window was missed
- **THEN** the alert names the latest such checkpoint as a way to restore a consistent state

### Requirement: Rebuilding validation state
When the state was emptied after the watchdog began observing and no complete refresh of every connector started after it, the watchdog SHALL report `ValidationConsistency` as a warning that names when and why the state was emptied, that no checkpoint restored it, and by when the next refresh is due. Once every connector completed a refresh that started after it, the watchdog SHALL report the state as consistent. While a resync is marked, it SHALL report the resync instead.

#### Scenario: After a failover
- **WHEN** the job failed over without a checkpoint and no complete refresh followed yet
- **THEN** the alert is a warning that says the validation is rebuilding and when the refresh is due

#### Scenario: The refresh comes
- **WHEN** every connector completed a refresh that started after the state was emptied, and no resync is marked
- **THEN** the alert is normal and closes

#### Scenario: The refresh comes during a resync
- **WHEN** every connector completed a refresh that started after the state was emptied, while a resync is marked as running
- **THEN** the alert stays a warning that reports the resync

#### Scenario: The refresh does not come
- **WHEN** no complete refresh followed within the TTL after the state was emptied
- **THEN** the state is inconsistent

### Requirement: Late refresh
When the last complete refresh of a connector started more than half the TTL plus 240 s ago (two runs of the restarter's two-minute schedule), and less than the TTL, the watchdog SHALL report `ValidationConsistency` as a warning that names the connector and when its window closes, unless it reports a resync.

#### Scenario: Overdue
- **WHEN** a connector's last complete refresh started more than half the TTL plus 240 s ago, and less than the TTL, and no resync is marked
- **THEN** the alert is a warning naming the connector and when the window closes

#### Scenario: Overdue during a resync
- **WHEN** a connector's refresh is overdue while a resync is marked as running
- **THEN** the alert reports the resync

### Requirement: Findings across runs
The watchdog SHALL keep the refreshes it saw, when the state was last emptied and an inconsistency it raised in a ConfigMap of its own, so that a gap is judged also when the Connect pods holding the log were replaced in between. It SHALL judge only what it can know: a refresh before the first run that observed the platform SHALL NOT be taken as a gap.

#### Scenario: Installed on a running platform
- **WHEN** the watchdog runs for the first time long after the job started
- **THEN** it reports the state as consistent if the last complete refresh is within the TTL, and raises no inconsistency for the time before it observed: a gap or the age of a refresh is measured from no earlier than its first run

#### Scenario: No refresh seen yet
- **WHEN** the state was emptied before the watchdog began observing and no complete refresh is in the log
- **THEN** `ValidationConsistency` is a warning that no complete refresh was seen yet, and the state is inconsistent once more than the TTL passed since the watchdog began observing without one

#### Scenario: A gap in the watchdog's runs
- **WHEN** the watchdog did not run for more than a quarter of the TTL
- **THEN** it observes anew from that run, as on a first run, and takes no gap from the time it did not run

#### Scenario: ConfigMap not readable
- **WHEN** the watchdog can't read its ConfigMap
- **THEN** it does not judge the consistency and posts no `ValidationConsistency`, so the alert stays as it was, and it reports `WatchdogState` as a warning that its kept state can't be read; once it can read it again, `WatchdogState` is normal

### Requirement: Connector state
The watchdog SHALL report each Debezium connector feeding the validation as `ConnectorState`: critical when the connector or one of its tasks is not `RUNNING`, a warning when the KafkaConnector does not exist, normal when all are. It SHALL read the state from the KafkaConnector resources.

#### Scenario: A failed task
- **WHEN** a connector reports `RUNNING` and its task `FAILED`
- **THEN** `ConnectorState` of that connector is critical and names both states

#### Scenario: A connector that does not exist
- **WHEN** a KafkaConnector the watchdog watches does not exist
- **THEN** `ConnectorState` of that connector is a warning that it was not found

#### Scenario: A connector that can't be read
- **WHEN** reading a KafkaConnector fails for another reason than that it does not exist
- **THEN** the watchdog posts no `ConnectorState` for it, so the alert stays as it was

#### Scenario: Running again
- **WHEN** the connector and its tasks are `RUNNING`
- **THEN** `ConnectorState` is normal and closes

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

### Requirement: Resync in progress
While the resync marks itself as running, the watchdog SHALL report `ValidationConsistency` as a warning that the SHACL validation is degraded, a resync is in progress and the SHACL alerts are incomplete, naming the step and when the resync began. A kept inconsistency SHALL take precedence. When it writes its own state, the watchdog SHALL leave the resync's marks as they are.

#### Scenario: During a resync
- **WHEN** a resync is marked as running in a step and its time limit has not passed
- **THEN** `ValidationConsistency` is a warning that names the resync, the step and its start

#### Scenario: With a kept inconsistency
- **WHEN** a resync is marked as running while the watchdog keeps an inconsistency
- **THEN** `ValidationConsistency` stays critical as an inconsistency

#### Scenario: The marks are kept
- **WHEN** the resync changes its marks while a watchdog run is in progress
- **THEN** after that run the marks are those the resync wrote last

#### Scenario: After the resync
- **WHEN** the resync has removed its marks
- **THEN** the watchdog's next run reports `ValidationConsistency` from its own judgement

### Requirement: Failed resync
When the resync marked itself as failed, or its marked time limit has passed while it is still marked as running, the watchdog SHALL report `ValidationConsistency` as critical, naming the step and that the SHACL alerts may be incomplete or stale, until a later resync removes the marks. A kept inconsistency SHALL take precedence.

#### Scenario: Failed
- **WHEN** the resync marked itself as failed in a step
- **THEN** `ValidationConsistency` is critical and names that step and the command to run again

#### Scenario: Ended without a word
- **WHEN** the resync is still marked as running in a step after its marked time limit has passed
- **THEN** `ValidationConsistency` is critical, says that the resync did not complete in time and names that step

#### Scenario: Closed by hand
- **WHEN** an operator closes the critical alert while the failure is still marked
- **THEN** the next run raises it again

#### Scenario: A later resync completes
- **WHEN** a resync completes after a failed one
- **THEN** `ValidationConsistency` reports the watchdog's own judgement again
