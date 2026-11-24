# Delta for Platform Watchdog

## MODIFIED Requirements

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

## ADDED Requirements

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
