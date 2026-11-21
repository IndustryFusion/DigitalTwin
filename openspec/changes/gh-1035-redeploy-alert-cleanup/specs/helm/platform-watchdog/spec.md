# Delta for Platform Watchdog

## MODIFIED Requirements

### Requirement: Repair of an inconsistent state
The alert of an inconsistent state SHALL name the repair: the redeploy of the validation, by its command, which undeploys the statementset, closes the open SHACL alerts, restarts Core Services without state and deploys the statementset with a complete refresh, in this order. It SHALL say whether a checkpoint taken before the state went stale could restore a consistent state instead.

#### Scenario: The repair
- **WHEN** the state is inconsistent
- **THEN** the alert names the redeploy command and its four steps in their order

#### Scenario: No checkpoint
- **WHEN** the job has completed no checkpoint
- **THEN** the alert says that no checkpoint can restore the state

#### Scenario: A checkpoint before the state went stale
- **WHEN** the job completed a checkpoint before the window was missed
- **THEN** the alert names the latest such checkpoint as a way to restore a consistent state
