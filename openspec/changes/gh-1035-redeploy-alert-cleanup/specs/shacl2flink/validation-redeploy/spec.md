# Delta for Validation Redeploy

## Purpose

Defines how the SHACL validation is redeployed on the platform so that afterwards exactly the alerts of the constraints violated now are open in Alerta, whatever the type of the constraint, and which topics undeploying the validation may delete.

## ADDED Requirements

### Requirement: One command, four steps in order
The redeploy SHALL run from one command, with the KMS chosen as for a deploy. It SHALL run these steps in this order: undeploy the validation, close the SHACL alerts, restart Core Services without state, deploy the validation. A step SHALL start only after the step before it has completed, and the command SHALL report the start and the end of each step.

#### Scenario: The order
- **WHEN** the redeploy runs on a platform with the validation deployed
- **THEN** its output reports the four steps starting and ending in this order, each step starting after the previous one ended, and it exits with status 0

#### Scenario: Nothing deployed before
- **WHEN** the redeploy runs on a platform without the validation deployed
- **THEN** the undeploy step completes without error and the redeploy runs the other steps as usual

### Requirement: A failed step stops the redeploy
When a step fails, or does not complete within its time limit, the redeploy SHALL stop without starting a later step, exit with a non-zero status and name the step that failed. Running the redeploy again SHALL complete it.

#### Scenario: Alerta unreachable
- **WHEN** Alerta can't be reached during the redeploy
- **THEN** the redeploy exits with a non-zero status, its message names the step that closes the SHACL alerts, Core Services runs the same job as before and the validation is not deployed

#### Scenario: Topics not deleted in time
- **WHEN** a topic of the validation still exists when the undeploy step's time limit has passed
- **THEN** the redeploy exits with a non-zero status, names the undeploy step and the topic, and no alert has been closed

#### Scenario: Run again
- **WHEN** the redeploy is run again after a failed step, with the cause removed
- **THEN** it completes all four steps and exits with status 0

### Requirement: Nothing of the previous job is replayed
The undeploy step SHALL complete only when the validation job is cancelled and the topics the validation owns, `constraint_trigger_table`'s included, no longer exist in Kafka. The validation deployed by the redeploy SHALL read no record that the previous job wrote.

#### Scenario: Topics deleted
- **WHEN** the undeploy step has completed
- **THEN** the statementset is gone, and neither its KafkaTopic resources nor the topics of `constraint_table`, `constraint_combination_table` and `constraint_trigger_table` exist

#### Scenario: A raise of the previous job
- **GIVEN** a raise record of the previous job in `constraint_trigger_table` for a constraint that is satisfied now
- **WHEN** the redeploy has completed
- **THEN** `constraint_trigger_table` holds no record for that resource and constraint, and no alert is open for it

### Requirement: Shared topics stay
Undeploying the validation, alone or within the redeploy, and deploying it SHALL NOT delete a topic that another component writes or reads. In particular `iff.ngsild.entities` SHALL stay, with its records, while the bridges keep running.

#### Scenario: iff.ngsild.entities kept
- **WHEN** the redeploy runs
- **THEN** the KafkaTopic of `iff.ngsild.entities` exists throughout, its topic ID in Kafka is the same afterwards, and a record written to it before the redeploy can still be read afterwards

#### Scenario: Undeploy alone
- **WHEN** the validation is undeployed without being deployed again
- **THEN** `iff.ngsild.entities` still exists

#### Scenario: Deployed before this rule
- **GIVEN** a deployed validation whose undeploy would still delete `iff.ngsild.entities`
- **WHEN** the redeploy runs
- **THEN** it stops before the undeploy step with a non-zero status and a message saying to deploy the validation once first, and nothing has been undeployed

### Requirement: Only SHACL alerts are closed
The close step SHALL close every alert of service `SHACL Validator` that is not closed, whatever its status, and SHALL change no other alert. It SHALL begin only after Alerta has received no SHACL alert for a settle time following the undeploy, and SHALL complete only when no SHACL alert is left that is not closed.

#### Scenario: Every status
- **GIVEN** SHACL alerts that are open, acknowledged, shelved and expired
- **WHEN** the close step has completed
- **THEN** all of them are closed

#### Scenario: Other alerts
- **GIVEN** an open alert of another service, such as the platform watchdog's alerts of service `System`
- **WHEN** the redeploy has completed
- **THEN** that alert has the same status and severity as before, and its history has no entry from the redeploy

#### Scenario: Many alerts
- **GIVEN** more SHACL alerts that are not closed than Alerta changes in one request
- **WHEN** the close step has completed
- **THEN** none of them is left that is not closed

#### Scenario: A raise in flight
- **GIVEN** a raise of the previous job that reaches Alerta shortly after the job was cancelled
- **WHEN** the close step has completed
- **THEN** that alert is closed

### Requirement: Core Services restarts without state
The restart step SHALL replace the running Core Services job with a new job that restores no state, and SHALL complete only when exactly one Core Services job runs with all its tasks. After it, Core Services SHALL forward the first alert it receives for each resource and event, even when its severity and text equal those it forwarded before the restart.

#### Scenario: A new job
- **WHEN** the restart step has completed
- **THEN** Flink runs exactly one job named `Core Services`, with another job ID than before, all its tasks running and no checkpoint restored

#### Scenario: An unchanged raise is forwarded
- **GIVEN** a raise that Core Services forwarded before the restart
- **WHEN** the same raise, with the same severity and text, arrives after the restart step
- **THEN** Core Services forwards it to Alerta

### Requirement: Deploy with a complete snapshot
The deploy step SHALL deploy the validation and start a complete Debezium snapshot of the tables it reads. It SHALL complete only when the validation job runs with all its tasks and every Debezium connector feeding it has completed a snapshot that started after the job started.

#### Scenario: Deployed and fed
- **WHEN** the deploy step has completed
- **THEN** the statementset's job runs with all its tasks, and the log of each Debezium connector shows a snapshot that started after the job started and completed

### Requirement: Alerts after the redeploy
After the redeploy, the SHACL alerts that are not closed SHALL be exactly those of the constraints that the current entities violate. This SHALL hold for count constraints and for every other constraint type.

#### Scenario: A count constraint satisfied now
- **GIVEN** an open alert of a count constraint that the entity satisfies now, and its raise in `constraint_trigger_table`
- **WHEN** the redeploy has completed
- **THEN** the alert is closed

#### Scenario: Another constraint type satisfied now
- **GIVEN** an open alert of a value constraint that the entity satisfies now, and its raise in `constraint_trigger_table`
- **WHEN** the redeploy has completed
- **THEN** the alert is closed

#### Scenario: Still violated
- **GIVEN** an open alert of a constraint that the entity still violates
- **WHEN** the redeploy has completed
- **THEN** within two minutes the alert is open, with the same severity and text, and its history shows it was closed by the redeploy and opened again

#### Scenario: An entity that no longer exists
- **GIVEN** an open alert and a raise in `constraint_trigger_table` for an entity that no longer exists
- **WHEN** the redeploy has completed
- **THEN** the alert is closed, and it is still closed two minutes later
