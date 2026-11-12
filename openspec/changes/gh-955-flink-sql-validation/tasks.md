# Tasks

## 1. SQL Gateway

- [x] 1.1 Add a validation mode to `FlinkSqlGateway/submitjob/job.py`: register the UDFs (failing on errors), apply the settings, run the table and view DDL, add the statements to a statement set and `explain` it, without executing; report the first rejected item (kind, position, text) and Flink's message; verify with tests for a valid request, a `POSITION(a || b IN c)` statement, an unknown column, an unknown function and a call to a shacl2flink UDF ("A statement Flink rejects", "A statement Flink cannot plan", "User-defined functions"), and that no job is started
- [x] 1.2 Add `POST /v1/sessions/session/validate` to `gateway.js` (200, or 422 with the rejected item and the message), running the validator with the image's Python; verify with the gateway's tests for both answers and that the deploy endpoint is unchanged
- [x] 1.3 Make the validator a command line entry of the image (`job.py --validate <file>`, several requests in one run); verify on the requests of `kms/default`
- [x] 1.4 Verify that validating tables with the Kafka, Upsert-Kafka and Postgres CDC connectors pointed at unreachable addresses passes without opening a connection ("A valid statement set"); if one connects, stop and report before going on

## 2. Operator

- [x] 2.1 Validate in the statement-set handlers before cancelling (update) and before submitting (create); on a rejection set `VALIDATION_FAILED` and the message, leave the running job, and record a digest of the composed request so the same statements are not validated again; verify with the operator's tests for "An update Flink rejects", "A new statement set Flink rejects", "A valid update" and "Fixed after a rejection"
- [x] 2.2 Document the new state and status field in the operator's README; verify the documented fields match the CRD
- [x] 2.3 Check the consumers of the statement set's state (bats tests, platform watchdog) for `VALIDATION_FAILED`; verify they report it as a failure

## 3. shacl2flink

- [x] 3.1 Add `make validate-flink`: build, render the `shacl` chart with its default values (`helm template`, placeholder CDC password) and the `sql-core` chart for the core tables, compose the requests with the operator's composition functions and validate them with the SQL Gateway image in one run; verify on `kms/default` and `tests/e2e-kms` ("A valid statement set", "The same statements as the deployment", "Runtime")
- [x] 3.2 Run the check in `flink-deploy` before the chart is applied; verify that a broken template stops `flink-deploy` before anything is applied
- [x] 3.3 Describe the target in `semantic-model/shacl2flink/README.md`; verify the command runs as written

## 4. CI

- [ ] 4.1 Run `make validate-flink` in the `Build` workflow for the packages it compiles and for `tests/e2e-kms`, after the SQL Gateway image is built; verify that it passes on this pull request and fails on a scratch branch with a template that renders a statement Flink rejects ("A broken template fails the build")

## 5. Integration check

- [ ] 5.1 Run `openspec validate gh-955-flink-sql-validation --strict`, the tests of the gateway, the operator and shacl2flink; verify all pass, that `Build` and `K8s tests` pass on the pull request, and report every scenario's result in the pull request
