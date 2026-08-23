INSERT INTO ngsild_updates
SELECT
  'update',
  true,
  true,
  '[{"id":"' || id || '",' || LISTAGG(attributeagg) || '}]'
FROM (
  SELECT
    window_start,
    window_end,
    entityId AS id,
    '"' || name || '":[' || LISTAGG(indexagg) || ']' AS attributeagg
  FROM (
    SELECT
      window_start,
      window_end,
      entityId,
      name,

      /* build the JSON fragment for this attribute */
      '{'
      /* The EVENT time. This used to read `ts`, which was observedAt only
         because the bridge put it in the record stamp. `ts` is the write time
         now, so reading it here would stamp every attribute written back to
         Scorpio with the moment we happened to forward it. */
      || '"observedAt":"' 
         || DATE_FORMAT(COALESCE(`observedAt`, `ts`), 'yyyy-MM-dd''T''HH:mm:ss.') 
         || CAST(EXTRACT(MILLISECOND FROM COALESCE(`observedAt`, `ts`)) AS STRING) || 'Z",'
      || '"type":"' || type || '",'
      || '"datasetId":"' 
         || IF(datasetId IS NOT NULL, datasetId, '@none') || '"'
      || CASE
           WHEN type LIKE '%/Relationship' THEN
             ',"object":"' || attributeValue || '"'
           WHEN type LIKE '%/JsonProperty' THEN
             ',"json":' || attributeValue
           WHEN type LIKE '%/ListProperty' THEN
             ',"valueList":'
             || IF(deleted = TRUE, '[]', attributeValue)
           WHEN type LIKE '%/GeoProperty'
             OR type LIKE '%/Property' THEN
             /* differentiate @id, @json, @value, or default */
             CASE
               WHEN nodeType = '@id' THEN
                 ',"value":{"@id":"' || attributeValue || '"}'
               WHEN nodeType = '@json' THEN
                 ',"value":' || attributeValue
               WHEN nodeType = '@value' THEN
                 ',"value":' || attributeValue
               ELSE
                 ',"value":"' || attributeValue || '"'
             END
           ELSE
             /* fallback */
             ',"value":"' || attributeValue || '"'
         END
      || '}'
      AS indexagg

    FROM (
      SELECT
        *,
        ROW_NUMBER() OVER (
          PARTITION BY entityId, name, datasetId, window_start, window_end
          /* The window is one millisecond and `ts` is its descriptor, so every
             row in a window shares the same ts and ORDER BY ts alone is a
             TOTAL tie for a key -- the winner was whichever row the operator
             happened to hold. That matters most for the case this pipeline
             exists to carry: a value and its delete are stamped with the same
             timestamp on purpose, so they land in the SAME window and the
             writeback picked between them arbitrarily. The offset is strictly
             monotonic per partition, so it resolves the tie by arrival without
             disturbing the event-time ordering above it. */
          ORDER BY COALESCE(`observedAt`, `ts`) DESC, `offset` DESC
        ) AS row_num
      FROM TABLE(
        TUMBLE(
          TABLE attributes,
          DESCRIPTOR(ts),
          INTERVAL '0.001' SECOND
        )
      )
      WHERE
        entityId   IS NOT NULL
        AND parentId IS NULL
        AND (synced IS NULL OR synced = FALSE)
    ) AS ranked_data
    WHERE row_num = 1
  ) AS filtered_data
  GROUP BY window_start, window_end, entityId, name
) AS aggregated
GROUP BY window_start, window_end, id;

insert into
    attributes_writeback
select
    id,
    parentId,
    entityId,
    name,
    nodeType,
    valueType,
    `type`,
    `attributeValue`,
    `datasetId`,
    `unitCode`,
    `lang`,
    `deleted`,
    `synced`
from
    (
        select
            id,
            last_value(parentId) as parentId,
            last_value(entityId) as entityId,
            last_value(name) as name,
            last_value(nodeType) as nodeType,
            last_value(valueType) as valueType,
            last_value(`type`) as `type`,
            last_value(`attributeValue`) as `attributeValue`,
            `datasetId` as `datasetId`,
            last_value(`unitCode`) as `unitCode`,
            last_value(`lang`) as `lang`,
            last_value(`deleted`) as `deleted`,
            last_value(`synced`) as `synced`,
            TUMBLE_START(
                ts,
                INTERVAL '0.001' SECOND
            ),
            TUMBLE_END(
                ts,
                INTERVAL '0.001' SECOND
            )
        from
            attributes_insert
        group by
            `id`,
            `datasetId`,
            TUMBLE(
                ts,
                INTERVAL '0.001' SECOND
            )
    );
