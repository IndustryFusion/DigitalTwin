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
    `ts` TIMESTAMP(3) METADATA FROM 'timestamp' VIRTUAL,
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
`ts` FROM (
  SELECT *,
ROW_NUMBER() OVER (PARTITION BY `id`, `datasetId`
ORDER BY ts DESC) AS rownum
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