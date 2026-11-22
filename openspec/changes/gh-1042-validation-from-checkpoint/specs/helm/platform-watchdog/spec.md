# Delta for Platform Watchdog

## ADDED Requirements

### Requirement: Restored validation state
When the validation job starts, fails over or is relaunched by a JobManager restart and restores a checkpoint, the watchdog SHALL judge the restored state from the last complete refresh before that checkpoint: consistent when less than the deployed TTL had passed since that refresh started, and inconsistent otherwise. It SHALL keep, for each recorded checkpoint, when that refresh started and whether the state was inconsistent at its completion.

#### Scenario: A failover restored from a checkpoint
- **WHEN** the validation job fails over and restores its latest checkpoint within a minute
- **THEN** `ValidationConsistency` stays normal, with no rebuilding warning, and the next window is measured from the refresh before that checkpoint

#### Scenario: A restore by the resync
- **WHEN** the resync restores a restorable checkpoint
- **THEN** after the resync the watchdog reports the state as consistent, naming the restored checkpoint

#### Scenario: A restore past the TTL
- **WHEN** Flink restores the job after an outage, from a checkpoint whose last complete refresh before it started longer ago than the deployed TTL
- **THEN** `ValidationConsistency` is critical as an inconsistent state, naming the checkpoint, the refresh and the TTL

#### Scenario: A record for each checkpoint
- **WHEN** the statementset's status lists a completed checkpoint
- **THEN** by its next run the watchdog keeps when the last complete refresh before it started, and whether an inconsistency was held then

### Requirement: Restorable checkpoint
While the validation state is not inconsistent, `ValidationConsistency` SHALL name the newest recorded checkpoint that is restorable, computed by the same rules as the resync, and until when it stays restorable; or that none is, with the reason; or that it can't be assessed and why.

#### Scenario: Restorable
- **WHEN** the state is consistent and a recorded checkpoint of the deployed fingerprint is restorable
- **THEN** the normal alert's text names that checkpoint and `restorable until` a time, which is the earlier of the times the state rule and the replay rule stop holding

#### Scenario: The time moves on
- **WHEN** the next checkpoint is recorded and becomes the newest restorable one
- **THEN** the next run names it, with a later time

#### Scenario: None restorable
- **WHEN** no recorded checkpoint is restorable
- **THEN** the text says so and names the rule each newest candidate fails

#### Scenario: Retention unknown
- **WHEN** a topic the validation reads has no KafkaTopic resource
- **THEN** the text gives the time by the state rule only and names the topic whose retention is unknown

#### Scenario: No job
- **WHEN** no validation job runs
- **THEN** the text says that the restorability can't be assessed and that the resync computes it

## MODIFIED Requirements

### Requirement: Repair of an inconsistent state
The alert of an inconsistent state SHALL name the repair `make shacl-resync REPLACE=fresh`, by its steps in their order, and SHALL say why no checkpoint restores a consistent state: a checkpoint taken before the state went stale holds keys whose last refresh is older than the TTL, and one taken after holds the inconsistent state. It SHALL NOT name a checkpoint restore.

#### Scenario: The repair
- **WHEN** the state is inconsistent
- **THEN** the alert names `make shacl-resync REPLACE=fresh` and its steps in their order

#### Scenario: No checkpoint
- **WHEN** the state is inconsistent and the job has completed no checkpoint
- **THEN** the alert says that no checkpoint can restore the state

#### Scenario: A checkpoint before the state went stale
- **WHEN** the state is inconsistent and the job completed a checkpoint before the window was missed
- **THEN** the alert says that this checkpoint can't restore a consistent state because of the TTL, and names neither `REPLACE=checkpoint` nor `REPLACE=auto`

### Requirement: Rebuilding validation state
When the state was emptied after the watchdog began observing and no complete refresh of every connector started after it, the watchdog SHALL warn, naming when and why the state was emptied, that no checkpoint restored it, and by when the next refresh is due. It SHALL name `make shacl-resync REPLACE=auto` and the checkpoint it would restore with its time, or that it would start fresh. After a complete refresh of every connector it SHALL report it as consistent.

#### Scenario: After a failover
- **WHEN** the job failed over without a checkpoint and no complete refresh followed yet
- **THEN** the alert is a warning that says the validation is rebuilding and when the refresh is due

#### Scenario: A lost job with a restorable checkpoint
- **WHEN** the validation is rebuilding after its job was lost and started empty, and a recorded checkpoint of the deployed fingerprint is restorable
- **THEN** the warning names `make shacl-resync REPLACE=auto`, that checkpoint and until when it is restorable

#### Scenario: None restorable
- **WHEN** the validation is rebuilding and no recorded checkpoint is restorable
- **THEN** the warning names `make shacl-resync REPLACE=auto`, says that it would start fresh, and that the refresh rebuilds the state by its due time

#### Scenario: The refresh comes
- **WHEN** every connector completed a refresh that started after the state was emptied
- **THEN** the alert is normal and closes

#### Scenario: The refresh does not come
- **WHEN** no complete refresh followed within the TTL after the state was emptied
- **THEN** the state is inconsistent

### Requirement: Late refresh
When the last complete refresh of a connector started more than the deployed refresh period, capped at half the TTL, plus 240 s ago (two runs of the restarter's two-minute schedule), and less than the TTL, the watchdog SHALL report `ValidationConsistency` as a warning that names the connector and when its window closes.

#### Scenario: Overdue
- **WHEN** a connector's last complete refresh started more than the refresh period plus 240 s ago, and less than the TTL
- **THEN** the alert is a warning naming the connector and when the window closes

#### Scenario: A TTL longer than twice the refresh period
- **WHEN** the TTL is one day, the refresh period 30 minutes, and a connector's last complete refresh started 40 minutes ago
- **THEN** the alert is a warning naming the connector
