# Design

## Context

What Flink runs for a shacl2flink package is not a file shacl2flink writes.
`make build` writes resources -- `BeamSqlTable`, `BeamSqlView`,
`BeamSqlStatementSet` and ConfigMaps holding the statements -- and `make helm`
turns them into the `shacl` chart, whose values (topic names, bootstrap
servers, state TTLs, the CDC password) are filled in at deployment. The
operator (`FlinkSqlServicesOperator`) composes each statement set into one
request -- SQL settings, table DDL (generated from the `BeamSqlTable` fields:
connector, columns, watermark, primary key), view DDL, the statements from the
ConfigMaps -- and posts it to the SQL Gateway. The SQL Gateway
(`FlinkSqlGateway`, a Node server) writes the request to a file and runs
`submitjob/job.py` with `flink run --python`: a PyFlink 1.20.4
`TableEnvironment` that registers the Python UDFs, applies the settings, runs
the DDL and executes the statement set.

Flink sees the statements for the first time there. On an update the operator
has already cancelled the running job; on a rejection the gateway answers 500,
the operator sets `DEPLOYMENT_FAILURE` and retries every 30 seconds with the
same request, and Flink's message is only in the gateway's log.

## Decisions

### D1 — One validator, in the SQL Gateway

The validator is a mode of the SQL Gateway's job submission: the same
`TableEnvironment`, the same UDF registration and the same connector jars,
with the same Flink -- the image's 1.20.4.

- *Alternative:* validate in shacl2flink with its own `apache-flink`.
  Rejected: shacl2flink pins 1.17.2, has no connector jars, and would have to
  repeat the gateway's composition and UDF registration; two copies drift, and
  the check would no longer be "what Flink runs".
- *Alternative:* Flink's native SQL gateway, which runs as a sidecar of the
  FlinkDeployment. Rejected: it exists only in a running cluster, so it cannot
  serve the build-time check.
- *Alternative:* an offline SQL parser (e.g. sqlglot, Calcite on its own).
  Rejected: neither is Flink's planner, so neither knows Flink's functions,
  connectors or UDFs; a statement that parses but cannot be planned would pass.

### D2 — Parse and plan, do not execute

Validation runs what `job.py` runs up to the job: register the UDFs, apply the
settings, run the table and view DDL (catalog operations only), add every
statement to a statement set and have Flink `explain` it. Explaining plans the
whole statement set, sources and sinks included, without submitting it. UDF
registration errors, which `job.py` prints and ignores today, fail the
validation.

- *Alternative:* explain each statement on its own. Rejected: it misses errors
  that only appear in the statement set as a whole, and repeats the planning
  of shared views.
- *Alternative:* only parse. Rejected: an unknown column or function parses.

Planning creates the connectors' sources and sinks, which must not open
connections; task 1.4 verifies it for the Kafka, Upsert-Kafka and Postgres CDC
connectors with unreachable addresses.

### D3 — A validation endpoint beside the deploy endpoint

The SQL Gateway gets `POST /v1/sessions/session/validate`, taking the same body
as the deploy endpoint. It answers 200 when everything validates, and 422 with
the first rejected item -- its kind (setting, table, view, statement), position
and text -- and Flink's message otherwise. It runs the validator with the
image's Python, not with `flink run`, so no cluster is involved. The same
validator is a command line entry of the image (`job.py --validate <file>`)
for the build-time check.

- *Alternative:* a flag on the deploy endpoint. Rejected: a forgotten flag
  deploys.

### D4 — Build time: render as deployed, compose as the operator does

A shacl2flink target (`make validate-flink`) builds the package, renders the
`shacl` chart with its default values (`helm template`; a placeholder for the
CDC password, which the chart otherwise looks up in the cluster), and the
`sql-core` chart whose core tables the statements use, composes the
requests with the operator's own composition functions, and runs the SQL
Gateway image's validator on them in one container, so the JVM starts once.

- *Alternative:* validate the files of `make build` without Helm. Rejected:
  settings and view hints carry Helm values, so what Flink runs differs.
- *Alternative:* reimplement the composition in shacl2flink. Rejected: the
  check would test a copy, not the operator.

### D5 — Deployment: validate before cancelling

The operator validates a statement set before it cancels the running job (on
an update) or submits it (on a create). A rejection sets the state
`VALIDATION_FAILED` and a status field with Flink's message, leaves the
running job alone, and records a digest of the composed request, so the same
statements are not validated again until the statement set or a ConfigMap it
names changes (a ConfigMap change leaves the statement set's generation as
it is).
`flink-deploy` also runs the build-time check before it applies the chart, to
fail before anything changes in the cluster.

- *Alternative:* keep `DEPLOYMENT_FAILURE` and the 30-second retry. Rejected:
  the cause stays hidden in the gateway's log and the retries cannot succeed.
- *Alternative:* validate only in `flink-deploy`. Rejected: other ways of
  applying the chart would still cancel a job for statements Flink rejects.

## Risks

- **Startup time.** Each validation starts a JVM (tens of seconds). The
  build-time check validates all statement sets of a package in one run; at
  deployment it is once per update.
- **Connectors that connect while planning.** If a connector opens a
  connection when its source or sink is created, validation would need the
  service. Task 1.4 checks it; such a table would need a planning-only
  substitute, which this change would then specify.
- **UDF code runs during validation.** It is the code the deployment runs, in
  the same image; validation adds no new code path for it.
- **A new state.** `VALIDATION_FAILED` is new for consumers of the statement
  set's status (bats tests, the platform watchdog); task 2.3 checks them.

## Conflicts with existing documentation

- shacl2flink's requirements pin `apache-flink==1.17.2`, the platform runs
  1.20.4. This change does not use shacl2flink's pin; aligning it is a
  follow-up.
- `helm/values.yaml.gotmpl` still names `flink.imageTag: 1.16.1`; the image
  actually deployed is the SQL Gateway image (`flink:1.20.4`). Not changed
  here.

## Follow-up

- Align shacl2flink's `apache-flink` with the platform's Flink version.
