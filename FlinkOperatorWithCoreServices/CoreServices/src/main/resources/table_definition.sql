CREATE TABLE attributes (
    `id` STRING,
    `parentId` STRING,
    `entityId` STRING,
    `name` STRING,
    `nodeType` STRING,
    `valueType` STRING,
    `type` STRING,
    `attributeValue` STRING,
    `datasetId` STRING,
    `unitCode` STRING,
    `lang` STRING,
    `deleted` BOOLEAN,
    `synced` BOOLEAN,
    -- The EVENT time, carried in the payload by debeziumBridge. It used to be
    -- put in the Kafka record timestamp, which meant retention.ms -- a
    -- wall-clock STORAGE policy -- was applied to an event time: the kms model
    -- observes at 2024-02-28, so every attribute record was born older than any
    -- retention and was deleted on contact. `ts` is the write time now.
    `observedAt` TIMESTAMP(3),
    `ts` TIMESTAMP(3) METADATA FROM 'timestamp' VIRTUAL,
    -- Arrival order, to break ties on the event time. debeziumBridge stamps a DELETE
    -- with the timestamp of the value it deletes -- deliberately the same one,
    -- so that a re-creation observed at the same instant can still win. Event
    -- time therefore cannot separate a value from its own delete, and neither
    -- can it separate the two re-emissions a snapshot produces. The offset is
    -- strictly monotonic per partition, so it settles exactly those ties and
    -- nothing else: `ts` stays the primary ordering, this is only the
    -- tiebreaker beneath it.
    `offset` BIGINT METADATA VIRTUAL,
    -- The WATERMARK stays. Unlike the shacl tables, this one IS windowed:
    -- sql_statements.sql tumbles over it, and a window needs a rowtime.
    WATERMARK FOR ts AS ts
) WITH (
  'connector' = 'kafka',
  'topic' = 'iff.ngsild.attributes',
  'json.fail-on-missing-field' = 'False',
  'json.ignore-parse-errors' = 'True',
  'properties.bootstrap.servers' = 'my-cluster-kafka-bootstrap:9092',
  'scan.startup.mode' = 'earliest-offset',
  'format' = 'json'
);


CREATE TABLE attributes_insert (
    `id` STRING,
    `parentId` STRING,
    `entityId` STRING,
    `name` STRING,
    `nodeType` STRING,
    `valueType` STRING,
    `type` STRING,
    `attributeValue` STRING,
    `datasetId` STRING,
    `unitCode` STRING,
    `lang` STRING,
    `deleted` BOOLEAN,
    `synced` BOOLEAN,
    `ts` TIMESTAMP(3) METADATA FROM 'timestamp' VIRTUAL,
    WATERMARK FOR ts AS ts,
    PRIMARY KEY (`id`, `datasetId`) NOT ENFORCED
) WITH (
  'topic' = 'iff.ngsild.attributes_insert',
    'connector' = 'upsert-kafka',
    'value.format' = 'json',
    'value.json.fail-on-missing-field' = 'False',
    'value.json.ignore-parse-errors' = 'True',
    'key.format' = 'json',
    'properties.bootstrap.servers' = 'my-cluster-kafka-bootstrap:9092'
);

CREATE TABLE attributes_writeback (
    `id` STRING,
    `parentId` STRING,
    `entityId` STRING,
    `name` STRING,
    `nodeType` STRING,
    `valueType` STRING,
    `type` STRING,
    `attributeValue` STRING,
    `datasetId` STRING,
    `unitCode` STRING,
    `lang` STRING,
    `deleted` BOOLEAN,
    `synced` BOOLEAN,
    PRIMARY KEY (`id`, `datasetId`) NOT ENFORCED
) WITH (
  'topic' = 'iff.ngsild.attributes',
    'connector' = 'upsert-kafka',
    'value.format' = 'json',
    'value.json.fail-on-missing-field' = 'False',
    'value.json.ignore-parse-errors' = 'True',
    'key.format' = 'json',
    'properties.bootstrap.servers' = 'my-cluster-kafka-bootstrap:9092'
);

CREATE VIEW `attributes_view` AS
SELECT
`id`,
`parentId`,
`entityId`,
`name`,
`nodeType`,
`valueType`,
`type`,
 `attributeValue`,
`datasetId`,
`deleted`,
`synced`,
`observedAt`,
`ts` FROM (
  SELECT *,
ROW_NUMBER() OVER (PARTITION BY `id`, `datasetId`
-- ts first, offset only to settle a tie. A value and its delete carry the
-- SAME ts by design, so without this the winner is whichever the operator
-- happened to keep. Mirrors attributes_view in the sql-core chart.
ORDER BY COALESCE(`observedAt`, `ts`) DESC, `offset` DESC) AS rownum
FROM `attributes` )
WHERE rownum = 1;

CREATE TABLE ngsild_updates (
  `op` STRING,
  `overwriteOrReplace` Boolean,
  `noForward` Boolean,
  `entities` STRING
) WITH (
  'connector' = 'kafka',
  'topic' = 'iff.ngsild-updates',
  'properties.bootstrap.servers' = 'my-cluster-kafka-bootstrap:9092',
  'scan.startup.mode' = 'latest-offset',
  'format' = 'json'
);

CREATE TABLE `alerts` (
    `resource` STRING,
    `event` STRING,
    `environment` STRING,
    `service` ARRAY < STRING >,
    `severity` STRING,
    `customer` STRING,
    `text` STRING,
    PRIMARY KEY (resource, event) NOT ENFORCED
) WITH (
    'connector' = 'kafka',
    'format' = 'json',
    'json.fail-on-missing-field' = 'False',
    'json.ignore-parse-errors' = 'True',
    'properties.bootstrap.servers' = 'my-cluster-kafka-bootstrap:9092',
    'scan.startup.mode' = 'latest-offset',
    'topic' = 'iff.alerts'
);

CREATE TABLE `alerts_bulk` (
    `resource` STRING,
    `event` STRING,
    `environment` STRING,
    `service` ARRAY < STRING >,
    `severity` STRING,
    `customer` STRING,
    `text` STRING,
    watermark FOR ts AS ts - INTERVAL '0.0' SECONDS,
    `ts` TIMESTAMP(3) METADATA
    FROM
        'timestamp' VIRTUAL,
        PRIMARY KEY (resource, event) NOT ENFORCED
) WITH (
    'connector' = 'upsert-kafka',
    'value.format' = 'json',
    'value.json.fail-on-missing-field' = 'False',
    'value.json.ignore-parse-errors' = 'True',
    'key.format' = 'json',
    'properties.bootstrap.servers' = 'my-cluster-kafka-bootstrap:9092',
    'topic' = 'iff.alerts.bulk'
);