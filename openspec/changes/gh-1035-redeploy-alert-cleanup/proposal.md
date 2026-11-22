# Proposal

Issue: #1035

## Why

After a redeploy of the `shacl-validation` statementset, alerts the previous job raised stay open although the new job finds their constraint satisfied (#977). The new job replays the previous job's raises from `constraint_trigger_table`, and the leaf checks are sparse: they write only violations, so nothing overwrites a raise the new job doesn't confirm. An alert that was already open in Alerta is not closed by anything either. In #977, 17 count alerts came back this way within 20 s of the re-snapshot and had to be closed by hand.

Making the count checks write an ok verdict for every group (#1027) was closed in favour of a cleanup, which keeps the leaves sparse and covers every constraint type (https://github.com/IndustryFusion/DigitalTwin/pull/1027#issuecomment-7060900924).

The issue asks for that cleanup as part of a redeploy that undeploys the chart and deletes its topics. The review on #1036 showed that the cleanup doesn't need a redeploy. With the validation running, not restarted, closing the open SHACL alerts, restarting Core Services by its restart nonce and deleting the Connect pod brought every closed alert that was still violated back within 30 s of the snapshot, with the same severity and text, plus one violation Alerta hadn't shown before, and the set stayed stable for 15 minutes. The validation runs with a state TTL (07f3abbe), so unchanged results are passed on again after a re-snapshot. A cleanup tied to a fresh start can't serve a restore from a checkpoint, or alerts that drifted without any restart. The undeploy it needed also made the shacl release give up `iff.ngsild.entities`, which failed the flink shard at the first `flink-deploy` (https://github.com/IndustryFusion/DigitalTwin/actions/runs/44902037744/job/136843080878).

So this change makes the cleanup a resync with one entry point, whatever happened to the validation before, and reports the validation as degraded while it runs.

## What Changes

- A new command in shacl2flink, `make shacl-resync`, brings the SHACL alerts in line with what the validation finds now. It runs these steps in this order and stops with the name of the step when one fails:
  1. mark the validation as degraded: the platform watchdog's `ValidationConsistency` alert becomes a warning that a resync is in progress and the alerts are incomplete, naming the current step;
  2. optionally stop the validation job for a replacement: for a fresh job, empty the topics it writes and reads back (`constraint_trigger_table` and two others) before a new job starts. A restore from a given checkpoint is accepted as an option and refused until the platform supports it;
  3. close every SHACL alert in Alerta that is not closed (`service` `SHACL Validator`), and no other alert;
  4. restart Core Services without state, so that its alerts filter forwards unchanged raises again;
  5. start the fresh job, if the job was stopped;
  6. trigger a complete Debezium re-snapshot, as `flink-deploy` does, with the periodic Connect restart left running;
  7. wait until the snapshot is processed: every connector logged a completed snapshot that started after the resync began, then the debezium-bridge, the validation job and Core Services have read their source topics to the end for a quiet period, and then a marker the command writes behind Core Services' output has reached Alerta through the alerta-bridge;
  8. end the degraded state: `ValidationConsistency` turns normal only now. A failed or timed-out resync leaves it critical, naming the step.
- The platform watchdog reports a running or failed resync from marks the command keeps in the watchdog's ConfigMap, ahead of its rebuilding, late, unknown and consistent reports. As the repair of an inconsistent state it names `make shacl-resync REPLACE=fresh`, instead of four manual steps that delete the alerts after the redeploy.
- An end-to-end test on the platform sets up stale, still violated and foreign alerts, runs the resync once without and once with a fresh job, and checks the alerts and the degraded state.

## Capabilities

### New Capabilities
- `shacl2flink/alert-resync`: how one command brings the SHACL alerts in line with the validation, with or without replacing the job, when the resync counts as processed, and how it marks the validation as degraded meanwhile.

### Modified Capabilities
- `helm/platform-watchdog`: *Repair of an inconsistent state* names the resync with a fresh job; *Flink not readable*, *Rebuilding validation state* and *Late refresh* give way to a running resync; new requirements report a running and a failed resync.

## Out of Scope

- Ok verdicts for count checks, or any other change to the SQL generated from the shapes; the leaves stay sparse.
- Who owns `iff.ngsild.entities`, and the topic deletion in `flink-deploy` and `flink-undeploy`: the resync deletes no topic, and the ownership belongs to #1038. Acceptance criterion 6 of the issue moves there.
- Making the statementset operator start a job from a given checkpoint; the resync only accepts the option and names what is missing.
- The retention of `constraint_trigger_table` (#978).
- Running the resync automatically after a failover, a JobManager restart or a `flink-deploy`; the operator runs it, and the watchdog says when it is needed.
- Keeping acknowledgements, shelving or the open time of alerts across the resync: an alert that is still violated is closed and opened again.
- Changing Core Services code or the bridges.

## Impact

- `semantic-model/shacl2flink`: a new `Makefile` target and a script for the steps; a new bats suite run by `test-flink-e2e`; the README describes the command, what an operator loses, and that a `flink-deploy` over a running validation needs `make shacl-resync REPLACE=fresh` afterwards.
- `helm/charts/alerta/templates/platform-watchdog.yaml`: the resync report from the marks, the repair text, and the watchdog leaving the marks alone when it writes its own state; `test/bats-unit/platform-watchdog-alerts.bats` follows.
- `test/bats-unit`: tests of the step order, the processed check and the failure handling of the script.
- Operators: alerts that are still violated come back as reopened alerts, and acknowledgements are lost. Core Services restarts, which sends the attribute window it reads from `iff.ngsild.attributes` to Scorpio again, as any Core Services restart does. With a fresh job the validation doesn't run between the stop and the start.
- No contract between components changes, and no topic is created or deleted. The command writes one marker record, an alert of service `System`, to `iff.alerts` per resync. No new dependency: the script uses kubectl, curl, jq and the Kafka tools in the broker pod, like the existing deploy targets and tests.
