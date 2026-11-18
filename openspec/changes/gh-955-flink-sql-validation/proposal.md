# Proposal

Issue: #955

## Why

The Flink SQL that shacl2flink generates is first parsed by Flink when it is
deployed. Nothing checks it before: the unit and SQL tests run the SQLite
variant of the same statements, and the Flink variant differs from it (dialect
macros, `{% if sqlite %}` branches in the templates, Helm values filled in at
deployment).

A Flink-only error therefore passes every local test and the `Build` workflow.
It shows up in a deployment, and at the worst moment: the operator cancels the
running job before it submits the new statements, so a statement Flink rejects
leaves **no job running at all**. The operator then retries every 30 seconds
with the same statements; the statement set's state is `DEPLOYMENT_FAILURE`,
and Flink's error message is only in the SQL Gateway's log. In #954 this cost
a 30-minute wait in the K8s tests (`POSITION(a || b IN c)`, which Flink's
parser rejects).

## What Changes

- **One validator, Flink's own.** The SQL Gateway gets a validation mode: it
  takes the same request the operator sends to deploy -- SQL settings, table
  and view DDL, the statement set -- and has Flink parse and plan all of it,
  with the connectors and user-defined functions it deploys with, without
  starting a job and without connecting to Kafka or a database. It answers
  with the first statement Flink rejects and Flink's message.
- **At build time.** A shacl2flink `make` target validates the statements a
  package compiles to, rendered as they would be deployed, with the SQL
  Gateway image of the platform; the `Build` workflow runs it for the
  packages it builds, so a Flink-only error fails the pull request in minutes.
- **At deployment.** The operator validates a statement set before it cancels
  the running job or submits anything. Statements that do not validate are
  not deployed, the running job keeps running, and the statement set's status
  carries Flink's message.

## Capabilities

### New Capabilities
- `shacl2flink/flink-sql-validation`: Generated Flink SQL is validated by
  Flink before it is deployed -- what is validated, against which Flink, what
  a rejection reports, and when a deployment is refused.

### Modified Capabilities

None. No specification describes the deployment of shacl2flink's statements
yet; this change specifies only the validation.

## Impact

- `FlinkSqlGateway`: a validation mode of the job submission (`submitjob`)
  and an endpoint for it.
- `FlinkSqlServicesOperator`: the statement-set handlers validate before they
  cancel or submit; a new status field for the rejection message.
- `semantic-model/shacl2flink`: a `make` target that validates a package's
  rendered statements; README.
- `Build` workflow: the target runs for the packages the workflow builds.
- Contract between components: no change to `contracts/*`. The internal
  interface between the operator and the SQL Gateway gains the validation
  endpoint; the deploy endpoint is unchanged.

## Out of Scope

- Checking that a deployed job produces the right results; the K8s and
  end-to-end tests do that.
- Changing what shacl2flink generates.
- Upgrading shacl2flink's own `apache-flink` pin (1.17.2, used only for the
  UDF modules' imports) to the platform's 1.20.4; see the design.
- Statement sets that do not come from shacl2flink: they are validated at
  deployment like any other (the operator does not know their origin), but
  only shacl2flink gets a build-time check.
