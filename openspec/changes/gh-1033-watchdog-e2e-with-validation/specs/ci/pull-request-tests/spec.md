# Delta for Pull Request Tests

## ADDED Requirements

### Requirement: The watchdog judged against a deployed validation
The platform watchdog's end-to-end test SHALL also run while a validation statementset is deployed, in the pull request shard that deploys one and in the nightly full test. There it SHALL fail unless the statementset exists, the watchdog read the reset from Flink, and found a complete refresh of both Debezium connectors. A change to that test or to the watchdog's chart SHALL select that shard.

#### Scenario: Flink not reachable from the watchdog
- **WHEN** the watchdog can't read the validation job from Flink while the validation is deployed
- **THEN** the end-to-end test fails in that shard and in the nightly

#### Scenario: Validation deployed
- **WHEN** the validation is deployed and the watchdog reads the reset from Flink and finds a complete refresh of both connectors
- **THEN** the end-to-end test passes there

#### Scenario: A change to the watchdog's end-to-end test
- **WHEN** a pull request changes only the watchdog's end-to-end test
- **THEN** the shard with the platform suites and the shard that deploys the validation run
