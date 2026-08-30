-- A top-1 ROW_NUMBER over ONE key. The view holds exactly one row, so
-- COUNT(*) over it must be 1 for ever. No joins, no watermarks, no TTL.
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
    SELECT *, ROW_NUMBER() OVER (PARTITION BY `id` ORDER BY `ts` DESC) AS rn
    FROM t) WHERE rn = 1;
