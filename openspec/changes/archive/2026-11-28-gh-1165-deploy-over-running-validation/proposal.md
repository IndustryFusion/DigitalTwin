# Proposal

Issue: #1165

## Why

`make flink-deploy` over a running SHACL validation gives wrong verdicts. The deploy drops and recreates the Postgres tables `constraint_table` and `constraint_combination_table` and fills them again. The running job reads them through change data capture, which sees the new rows but no deletes for the dropped ones. So each deploy adds one more copy of every constraint to the job: with `kms/default`, the job's combination table source goes from 54 rows to 108 after one deploy. Every relationship count then reports two, three, k times the real number ("Found 2 relationships instead of [1, 1]!").

The same path has the reverse problem. When only the generated SQL changes, the statement set's spec stays the same, so the operator doesn't replace the job: a changed package deployed over a running job keeps running the old SQL against the rewritten tables. Today the only safe way is by hand: `make flink-undeploy`, `make flink-deploy` and `make shacl-resync`.

## What Changes

- **A deployment knows what it deployed.** `make flink-deploy` computes a fingerprint of the validation as it would be deployed: the rendered statement set with its statements and the platform values in it, plus the contents of the tables `constraint_table`, `constraint_combination_table` and `rdf`. It keeps the fingerprint, with the ID of the job it belongs to, in a ConfigMap of its own, written only once a deploy has completed, so an interrupted deploy is replaced again by the next one.
- **The same package over a running validation rewrites nothing.** If the deployed fingerprint equals the new one and the job runs, the tables are not touched and the job is not replaced. Every constraint row stays read once, and the verdicts stay as they are.
- **Anything else replaces the validation, through the resync.** A different fingerprint, a validation without one (deployed before this change), or no running job: the deploy runs the resync with a new kind of replacement, by a new package. The resync stops the job, empties its topics, closes the SHACL alerts and resets Core Services. Then it writes the tables, applies the new chart, starts the new job and re-snapshots. Topics and their IDs stay, and the resync's preconditions and its lock against another resync apply to the deploy too.
- **Kafka Connect** is still restarted only once the deployed job reads its topics (#1114), in both cases.
- A step that fails stops the deploy with the step named. A deploy whose stop step failed writes no table.

## Capabilities

### New Capabilities

- `shacl2flink/validation-deployment`: what `make flink-deploy` guarantees when a validation is deployed, fresh or over a running one: each constraint row read once, the deployed statements and tables belonging together, and the SHACL alerts matching the deployed validation.

### Modified Capabilities

- `shacl2flink/alert-resync`: a third kind of replacement, by a new package. The resync installs the new package (its tables and statement set) between resetting Core Services and starting the job.

## Out of Scope

- Updating the tables in place, so that change data capture sees each change. Constraint ids are positions in the generated package, so a changed package renumbers its rows, and the old statements would read them under the old ids. That doesn't make a changed package take effect either.
- Keeping the validation's state across a changed package (a restore from a checkpoint, #1042).
- The rdf table's own drop and recreate, which reaches the job through Debezium and Kafka with stable keys and doesn't double. It is part of the fingerprint, and a changed knowledge replaces the validation like any other change.
- Faster deploys. A changed package costs a job start and a resync, as today's manual workaround does.

## Impact

- **shacl2flink:** `Makefile` (`flink-deploy`, `helm`, `submit-postgres-tables`), a fingerprint step, `shacl_resync.sh` (the replacement by a new package), and `restart_connect.sh` as it is.
- **helm:** no chart changes. The deploy keeps the fingerprint in a ConfigMap of its own, outside the release; the install runs `helmfile sync`.
- **Operations:** a deploy needs Alerta, Core Services and the platform watchdog, as the resync does.
- **Tests:** unit tests for the fingerprint and the decision, and a Flink e2e test that deploys over a running validation, the same package and then a changed one.
- **Contracts between components:** none change. The tables, topics and alert format stay the same; only when the deploy writes the tables changes.
