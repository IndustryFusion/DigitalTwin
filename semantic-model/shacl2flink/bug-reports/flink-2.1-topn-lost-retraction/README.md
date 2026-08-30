# Top-N loses its retractions: `COUNT(*)` over a top-1 view returns 2 (Flink 2.1+)

**Affects** Flink 2.1.0 and 2.3.0 (measured); 2.2 and `master` carry the same
code. **Not** 1.20.4 (measured).
**Component** Table SQL / Planner.
**Impact** Silent wrong results. No error, no warning, the job stays healthy.
**Fix** `flink-fix.patch` next to this file — two lines, verified.

---

## The example

One table, one key, two rows. No joins, no watermarks, no state TTL, no
mini-batch. Paste this into the SQL client of 1.20.4 and of 2.3.0.

```sql
SET 'execution.runtime-mode' = 'streaming';
SET 'parallelism.default' = '1';

CREATE TABLE t (
  `id`  STRING,
  `val` STRING,
  `ts`  TIMESTAMP(3)
) WITH (
  'connector' = 'kafka', 'topic' = 't',
  'properties.bootstrap.servers' = 'kafka:9092',
  'scan.startup.mode' = 'earliest-offset', 'value.format' = 'json'
);

CREATE TABLE rowcount (
  `k`   INT,
  `cnt` BIGINT,
  PRIMARY KEY (`k`) NOT ENFORCED
) WITH (
  'connector' = 'upsert-kafka', 'topic' = 'rowcount',
  'properties.bootstrap.servers' = 'kafka:9092',
  'key.format' = 'json', 'value.format' = 'json'
);

-- keep the row with the SMALLEST ts per id
CREATE TEMPORARY VIEW v AS
  SELECT `id`, `val` FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY `id` ORDER BY `ts` ASC) AS rn
    FROM t) WHERE rn = 1;

-- v holds exactly one row per id, and there is only one id,
-- so this can only ever be 1.
INSERT INTO rowcount SELECT 1 AS k, COUNT(*) AS cnt FROM v;
```

Then insert two rows, waiting for the first to be processed:

```sql
INSERT INTO t VALUES ('a1', 'X', TIMESTAMP '2026-01-01 10:00:10');
INSERT INTO t VALUES ('a1', 'Y', TIMESTAMP '2026-01-01 10:00:05');
```

The second row has a *smaller* `ts`, so under `ORDER BY ts ASC` it becomes the
new top-1 and the previous row must be retracted.

## Expected vs observed

`v` contains one row for `a1` at every point in time, so `cnt` must be 1.

```
Flink 1.20.4   {"k":1,"cnt":1}
               null
               {"k":1,"cnt":1}          <-- correct

Flink 2.3.0    {"k":1,"cnt":1}
               null
               {"k":1,"cnt":2}          <-- WRONG: two rows at rank 1 for one key
```

## The one-word control

Change `ASC` to `DESC` (and swap the two timestamps so the second row is still
the new winner). Nothing else changes:

| `ORDER BY ts …` | 1.20.4 | 2.3.0 |
|---|---|---|
| `ASC` | `cnt = 1` | **`cnt = 2`** |
| `DESC` | `cnt = 1` | `cnt = 1` |

A single keyword decides whether the query is correct.

---

## Why this is a bug and not "use the deduplication pattern"

Flink's [Deduplication] page requires the order key to be a time attribute:

> `ORDER BY time_attr [asc|desc]`: Specifies the ordering column, **it must be
> a time attribute**.

`ts` here is an ordinary `TIMESTAMP(3)`, so this query is not a deduplication.
It is a [Top-N] — `ROW_NUMBER() ... WHERE rn = 1` over an arbitrary order key —
and that page states the contract this query is entitled to:

> The TopN query is **Result Updating**. Flink SQL will sort the input data
> stream according to the order key, so if the top N records have been changed,
> the changed ones will be sent as **retraction/update records** to downstream.

The top-1 record *did* change, and no retraction was sent. Rewriting the query
as a real deduplication (a single time attribute) avoids it, and that is a fine
recommendation for efficiency — but it does not make a supported Top-N query
returning `COUNT(*) = 2` over a one-row view correct.

[Deduplication]: https://nightlies.apache.org/flink/flink-docs-master/docs/dev/table/sql/queries/deduplication/
[Top-N]: https://nightlies.apache.org/flink/flink-docs-master/docs/dev/table/sql/queries/topn/

---

## Root cause

`EXPLAIN CHANGELOG_MODE` shows it without running anything. Both versions plan
the *same* operator — a `Rank`, never a `Deduplicate` — but declare different
changelog modes:

```
1.20.4  Rank(strategy=[AppendFastStrategy], rankType=[ROW_NUMBER],
             rankRange=[rankStart=1, rankEnd=1], partitionBy=[id],
             orderBy=[ts ASC], changelogMode=[I,UB,UA,D])
2.3.0   ... same plan ..., changelogMode=[I])
```

`FlinkChangelogModeInferenceProgram.scala`, a branch added in 2.1 and absent in
2.0 and earlier:

```scala
case rank: StreamPhysicalRank if RankUtil.isDeduplication(rank) =>
  val insertOnly = children.forall(ChangelogPlanUtils.isInsertOnly)
  val providedTrait =
    if (insertOnly && RankUtil.outputInsertOnlyInDeduplicate(
          tableConfig, RankUtil.keepLastDeduplicateRow(rank.orderKey))) {
      ModifyKindSetTrait.INSERT_ONLY
    } else ModifyKindSetTrait.ALL_CHANGES
```

`RankUtil.scala`:

```scala
/** Whether the given rank is logically a deduplication. */
def isDeduplication(rank: Rank): Boolean =
  !rank.outputRankNumber && rank.rankType == RankType.ROW_NUMBER && isTop1(rank.rankRange)

def keepLastDeduplicateRow(orderKey: RelCollation): Boolean = {
  // order by timeIndicator desc ==> lastRow, otherwise is firstRow
  if (orderKey.getFieldCollations.size() != 1) return false   // multi-column: gives up
  orderKey.getFieldCollations.get(0).direction.isDescending
}

def outputInsertOnlyInDeduplicate(config: ReadableConfig, keepLastRow: Boolean): Boolean =
  !keepLastRow && !config.get(ExecutionConfigOptions.TABLE_EXEC_MINIBATCH_ENABLED)
```

Two things go wrong together.

1. **`isDeduplication` is the wrong guard.** It checks only *ROW_NUMBER, top-1,
   no rank column* — never that the sort is on a time attribute, i.e. never
   that the query actually *is* a deduplication. Whether a rank really runs as
   a `StreamExecDeduplicate` is decided by `canConvertToDeduplicate`, which
   additionally requires `sortOnTimeAttributeOnly`. The changelog branch skips
   that check, so a deduplication-only optimisation is applied to Top-N.
2. **`keepLastDeduplicateRow` conflates "no" with "don't know."** It returns
   `false` both for keep-first and for a multi-column key it cannot classify,
   and `outputInsertOnlyInDeduplicate` reads that `false` as the positive claim
   "this is keep-first", which genuinely is insert-only.

So on an ordinary column the shortcut fires for `ORDER BY x ASC` (keepLast is
false because the direction is ascending) and for any multi-column order key
(keepLast is false because it gave up). Only single-column `DESC` escapes, and
only by accident — which is exactly the one-word control above.

Note `outputInsertOnlyInDeduplicate` also returns false whenever mini-batch is
enabled, so **turning mini-batch on hides the bug**, which makes it look
mini-batch-dependent when it is not.

---

## Fix

`flink-fix.patch`, against the `release-2.3.0` tag. It restores the invariant
that only a rank which really runs as a `StreamExecDeduplicate` may claim to be
insert-only, reusing the predicate `canConvertToDeduplicate` already relies on:

```scala
val sortOnTimeAttributeOnly =
  RankUtil.sortOnTimeAttributeOnly(rank.orderKey, rank.getInput.getRowType)

if (insertOnly && sortOnTimeAttributeOnly && RankUtil.outputInsertOnlyInDeduplicate(
      tableConfig, RankUtil.keepLastDeduplicateRow(rank.orderKey)))
```

plus making that existing helper visible (it was `private`). Since
`sortOnTimeAttributeOnly` already demands a single proctime/rowtime sort field,
this closes the ascending case and the multi-column case at once.

`canConvertToDeduplicate` itself is deliberately not called here: it consults
`ChangelogPlanUtils.inputInsertOnly`, which Flink's own
`FlinkRelMdModifiedMonotonicity` documents as unreliable while the
modifyKindSet trait is still being computed. The `insertOnly` value already
derived from the visited children serves that purpose.

Verified by building `flink-table-planner` from the patched 2.3.0 tag and
swapping the jar into `flink:2.3.0` (drop `lib/flink-table-planner-loader-*.jar`,
put the planner jar in `lib/`):

| check | result |
|---|---|
| `ORDER BY ts ASC` | `cnt = 1` — fixed |
| multi-column `ORDER BY ts DESC, seq DESC` | fixed |
| genuine keep-first dedup on `PROCTIME()` | plan unchanged: `Deduplicate(keep=[FirstRow], key=[id], order=[PROCTIME], outputInsertOnly=[true])`, byte-identical to stock |
| `DeduplicateTest`, `ChangelogModeInferenceTest`, `RankTest` | 93 tests, 0 failures |
| `DeduplicateITCase` | 50 tests, 0 failures, 6 skipped |

The third row is what matters for not regressing the 2.1 optimisation: the case
it was written for still produces exactly the same plan.

---

## Versions

| Flink | result | how established |
|---|---|---|
| 1.20.4 | correct | run |
| 2.1.0 | wrong | run |
| 2.3.0 | wrong | run |
| 2.3.0 + patch | correct | run |
| 1.19, 1.20, 2.0 | expected correct | source: the branch does not exist |
| 2.1, 2.2, 2.3, master | expected wrong | source: the branch is present |

Flink 2.0.0 could not be measured: this query shape does not plan there at all,
failing with an unrelated `java.lang.AssertionError: Relational expression
rel#…:LogicalProject … belongs to a different planner than is currently being
used`.

Reproducer scripts sit next to this file: `kafka_setup.sh`, then
`run-minimal.sh <flink-image> <label> <kafka-connector-jar-url>`.
