# Proposal

Issue: #1035

## Why

After a redeploy of the `shacl-validation` statementset, alerts the previous job raised stay open although the new job finds their constraint satisfied (#977). The new job replays the previous job's raises from `constraint_trigger_table`, and the leaf checks are sparse: they write only violations, so nothing overwrites a raise the new job doesn't confirm. An alert that was already open in Alerta is not closed by anything either. In #977, 17 count alerts came back this way within 20 s of the re-snapshot and had to be closed by hand.

Making the count checks write an ok verdict for every group (#1027) was closed in favour of a cleanup at the redeploy, which keeps the leaves sparse and covers every constraint type (https://github.com/IndustryFusion/DigitalTwin/pull/1027#issuecomment-7060900924). That cleanup needs four steps in a fixed order, and a fifth fact the comment asks to check: the shacl chart also declares `iff.ngsild.entities`, which the bridges write and read, so undeploying the chart deletes a topic that is not only the validation's.

## What Changes

- A new command in shacl2flink redeploys the SHACL validation in four steps, in this order, and stops with the name of the step when one fails:
  1. undeploy the validation and wait until its own topics, `constraint_trigger_table`'s included, are deleted in Kafka, so nothing is replayed;
  2. once no SHACL alert has arrived for a settle time, close every SHACL alert in Alerta that is not closed (`service` `SHACL Validator`), and no other alert;
  3. restart the Core Services job without state, so that its alerts filter forwards the new job's raises again, also when severity and text are unchanged;
  4. deploy the validation and wait until a complete Debezium snapshot of the tables it reads has gone through it.
- Undeploying and deploying the validation no longer delete `iff.ngsild.entities`.
- The platform watchdog's alert of an inconsistent validation state names this command as the repair, instead of four manual steps in a different order.
- An end-to-end test on the platform redeploys the e2e KMS and checks the alerts: satisfied ones closed, violated ones open, gone entities not back, other alerts untouched, `iff.ngsild.entities` kept.

## Capabilities

### New Capabilities
- `shacl2flink/validation-redeploy`: how the SHACL validation is redeployed so that afterwards exactly the alerts of the constraints violated now are open, and which topics an undeploy may delete.

### Modified Capabilities
- `helm/platform-watchdog`: the requirement *Repair of an inconsistent state* names the redeploy command and its order.

## Out of Scope

- Ok verdicts for count checks, or any other change to the SQL generated from the shapes; the leaves stay sparse.
- The retention of `constraint_trigger_table` (#978).
- A cleanup for restarts that are not a redeploy: a failover or a JobManager restart empties the state without the cleanup; the watchdog reports these as rebuilding, as today.
- Keeping acknowledgements, shelving or the open history of alerts across the redeploy: an alert that is still violated is closed and opened again.
- Changing `flink-deploy` and `flink-undeploy` beyond keeping `iff.ngsild.entities`, and changing Core Services code.

## Impact

- `semantic-model/shacl2flink`: the `Makefile` (new target, `iff.ngsild.entities` no longer deleted before a deploy), a new script for the steps, the KafkaTopic of `iff.ngsild.entities` written by `create_ngsild_tables.py` kept on undeploy, a new bats suite run by `test-flink-e2e`.
- `helm/charts/alerta/templates/platform-watchdog.yaml`: the repair text of `ValidationConsistency`; `test/bats-unit/platform-watchdog-alerts.bats` follows.
- `test/bats-unit`: tests of the step order and the failure handling of the new script.
- Operators: alerts that are still violated come back as reopened alerts after a redeploy; acknowledgements are lost. Core Services restarts, which sends the attribute window it reads from `iff.ngsild.attributes` to Scorpio again, as any Core Services restart does today.
- No contract between components changes. No new dependency: the script uses kubectl, helmfile, curl and jq like the existing deploy targets and tests.
