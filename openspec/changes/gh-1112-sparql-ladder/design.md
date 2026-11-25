## Context

`classic` translates every query into a SQL statement with its own joins. The property constraints are data already (`constraint_table`); the SPARQL part is not. No archived spec covers it. The pending `shacl2flink/sparql-expressions` (gh-1107-sparql-compilation, gh-1111-sparql-concat) defines what an expression means; it holds for both methods, and the ladder refuses what it cannot answer that way.

## Goals / Non-Goals

**Goals:** a job independent of the number of queries; identical results; `classic` untouched; removal of one method later without trace in the other.

**Non-Goals:** see "Out of Scope" in the proposal.

## Decisions

### Queries are rows, one ladder of joins evaluates them
Entities, attributes and knowledge are facts `(source, predicate, subject, object, time)`. Each triple pattern is a row. A query is a tree of joins over its patterns, planned as low as possible. Level j of the ladder joins its left and right rows on `(tree node, key of the shared variables)`. The level's work (kind of join, condition, next key) travels with the left row, so one `LEFT JOIN` per level does inner joins, `OPTIONAL` and `NOT EXISTS` for all queries.
*Alternatives:* one template per query shape: 17 shapes in 19 queries, no gain. Left-deep trees: more levels for the same work. A DataStream operator: not deployable through the SQL path of the platform.

### Expressions are data, evaluated by functions in the gateway image
Python functions buffer up to a second per level. The Java functions need Flink's jars only; a second implementation in Python serves SQLite. Both run the same test vectors.
*Alternatives:* rendering conditions as SQL: grows with the queries again.

### The step functions are declared non-deterministic
They are deterministic. Declared so, the planner pushes the filters of a level's readers into it and copies the level per reader, which doubles the joins with every level; a table function prevents the reuse too. The join count is checked on Flink for every Flink upgrade.

### `$this` is there before the first pattern
A query which starts with `OPTIONAL` gets the pattern "the target is an entity" as its left side. Without it the first `OPTIONAL` would become the left side itself and so be required, and entities would be dropped without a word.

### The text of an alert is the one of `classic`
The values in a message are written as `classic` writes them: the lexical form, also of the result of an expression (#1166). *Alternative:* a form of its own: the same KMS would give other alerts after a switch.

### Values carry their datatype, as in `classic`
A value of the ladder keeps whether it is a number, a text, a truth value or an IRI, and every operation reads and writes it as `classic` does: a text and a number do not compare, an error in a condition makes the result unbound. The parity test compares with the `classic` compiler as it is, so a change there shows up as a difference.
*Alternative:* comparing literals that look like numbers as numbers and the rest by their text. Simpler, but it answers queries differently from `classic` and from SPARQL, so moving a KMS over would change its alerts.

### The rows are stored in `rdf`
Under predicates of their own. The table is delivered, re-snapshotted and read with CDC already.
*Alternatives:* a table of its own needs a replication slot, which holds WAL back on every platform that does not use `ladder`. Literals in the SQL: the SQL grows.

### Only facts a pattern asks for enter the state
Attribute names and predicates are filtered before the first join. So a new attribute needs a new build, as today.

### Aggregates run in a second ladder without pins
They read the history of attributes, which is unbounded. The first ladder is pinned (`STATE_TTL` 0) including the outer join and the group.

## Risks / Trade-offs

- Latency: more hops than `classic` → +30 to +90 ms at Flink's default buffer timeout in most measurements, +230 ms in one, +10 ms at 5 ms.
- Below about 16 queries `ladder` costs more CPU per update → `classic` is the default.
- One job for all queries: one expensive query slows the others.
- Separator of the bindings is U+0001; it is removed from values.
- Planner behaviour → the join count check above.
- Two queries of one shape share one event, the worst one wins; `classic` writes them over each other.

### The ladder runs end to end in a shard of its own
The `ladder` run of the end-to-end suites deploys the same KMS with the switch set. In a shard of its own it runs beside the flink shard and adds no time to it, at the cost of one more runner.
*Alternative:* both runs in the flink shard: one runner, but the shard takes about twice as long.

## Migration Plan

Redeploy with the switch set or not; the rows are replaced with the `rdf` table. Needs the gateway image of this change. Rollback: deploy without the switch.

## Open Questions

- When `ladder` becomes the default, and whether `classic` stays available then.
