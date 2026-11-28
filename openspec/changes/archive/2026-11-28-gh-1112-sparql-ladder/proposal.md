# Two methods to compile SPARQL: classic and, as alpha, ladder

Issue: #1112

## Why

Every SPARQL constraint or rule of a KMS becomes a SQL statement of its own, so the validation job grows with their number. Measured on Flink 1.20.4 with copies of the kms constraints: 4 constraints run in 39 tasks, 64 in 474 tasks with 4,066 threads, and their throughput collapses from 32 on. About 10 queries are no problem. A KMS with many more needs a job whose size does not depend on the number of queries.

## What Changes

- shacl2flink has two methods to compile SPARQL. `classic`, today's, stays the default and its output stays unchanged. `ladder` is new, alpha, and used only when asked for (`make … SPARQL_ENGINE=ladder`).
- `ladder` turns all SPARQL constraints and rules of the KMS into data, which one fixed set of joins evaluates.
- A query `ladder` does not support fails the build. Nothing falls back silently.
- Both methods report the same for the queries both support, texts of the alerts included; the tests compare them. `classic` is the one of gh-1107-sparql-compilation and gh-1111-sparql-concat, so this change is implemented after both.

The switch to `ladder` as the default, and the removal of `classic`, are a later change.

## Capabilities

### New Capabilities
- `shacl2flink/sparql-compilation`: the methods to compile SPARQL constraints and rules, how one is chosen, what they have in common and what the alpha method does not support.

### Modified Capabilities

None.

## Impact

- `semantic-model/shacl2flink`: the compiler, the Makefile, the README, tests.
- `FlinkSqlGateway`: the image contains the functions the `ladder` SQL calls; the submit job registers them. A `classic` job does not use them.
- No contract between components changes: alerts, constructed attributes, topics, tables and replication slots are the same.

## Out of Scope

- Making `ladder` the default, removing `classic`.
- Adding or removing a query without redeploying.
- The user-defined SPARQL functions (`statetime`, `hash`), `UNION`, `FILTER` inside `OPTIONAL`, a `FILTER` on outer variables inside `NOT EXISTS`.
- What `classic` compiles and `ladder` does not: it is refused by name.
- The state TTL pins missing in the SQL of `classic`.
- The SHACL property constraints: they are data already.
