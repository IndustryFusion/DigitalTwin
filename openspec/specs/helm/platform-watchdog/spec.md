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
When the watchdog can't read the validation job, because Flink doesn't answer or the statementset reports no job, it SHALL NOT judge the consistency: it SHALL neither raise nor end an inconsistency, SHALL keep posting an inconsistency it kept, and otherwise SHALL warn that the consistency can't be assessed, naming the cause. After a long span without the job it SHALL observe anew.

#### Scenario: Flink down with a kept inconsistency
- **WHEN** the watchdog can't read the job while it keeps an inconsistency
- **THEN** `ValidationConsistency` stays critical

#### Scenario: Flink down otherwise
- **WHEN** the watchdog can't read the job and keeps no inconsistency
- **THEN** `ValidationConsistency` is a warning that the consistency can't be assessed, naming whether Flink doesn't answer or the statementset reports no job, and no inconsistency is raised

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
The alert of an inconsistent state SHALL name the repair: redeploy the statementset, restart Core Services, delete the open SHACL alerts and run a complete refresh. It SHALL say whether a checkpoint taken before the state went stale could restore a consistent state instead.

#### Scenario: The repair
- **WHEN** the state is inconsistent
- **THEN** the alert names the four steps of the repair

#### Scenario: No checkpoint
- **WHEN** the job has completed no checkpoint
- **THEN** the alert says that no checkpoint can restore the state

#### Scenario: A checkpoint before the state went stale
- **WHEN** the job completed a checkpoint before the window was missed
- **THEN** the alert names the latest such checkpoint as a way to restore a consistent state

### Requirement: Rebuilding validation state
When the state was emptied after the watchdog began observing and no complete refresh of every connector started after it, the watchdog SHALL report `ValidationConsistency` as a warning that names when and why the state was emptied, that no checkpoint restored it, and by when the next refresh is due. Once every connector completed a refresh that started after it, the watchdog SHALL report the state as consistent.

#### Scenario: After a failover
- **WHEN** the job failed over without a checkpoint and no complete refresh followed yet
- **THEN** the alert is a warning that says the validation is rebuilding and when the refresh is due

#### Scenario: The refresh comes
- **WHEN** every connector completed a refresh that started after the state was emptied
- **THEN** the alert is normal and closes

#### Scenario: The refresh does not come
- **WHEN** no complete refresh followed within the TTL after the state was emptied
- **THEN** the state is inconsistent

### Requirement: Late refresh
When the last complete refresh of a connector started more than half the TTL plus 240 s ago (two runs of the restarter's two-minute schedule), and less than the TTL, the watchdog SHALL report `ValidationConsistency` as a warning that names the connector and when its window closes.

#### Scenario: Overdue
- **WHEN** a connector's last complete refresh started more than half the TTL plus 240 s ago, and less than the TTL
- **THEN** the alert is a warning naming the connector and when the window closes

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
