# Kafka Bridges

1. Alerta bridge, a service which listens at a specific Kafka topic and forwards the data to Alerta.
2. NgsildUpdates bride, a service which listens at a specific Kafka topic and forwards data to the scorpio/Ngsild broker.
3. DebeziumBridge, a service which listens to debezium updates on ngsild entities and forward them to specific topics.
4. Timescaledb Bridge, a service which listens at specific Kafka topic and forwards data to timescaledb(tsdb) running in postgres database

## Alerta Bridge

This service listens to the topic defined in the values file of `helmfile` in `kafkaBridge.ngsildUpdates.listenTopic` adn defaults to `iff.alerts.` Example message is shown below:

```
{
    "resource": "test",
    "event": "test",
    "environment": "Development",
    "service": [ "Digital Twin" ],
    "severity": "critical",
    "customer": "customerB"
}
```

Note that the object has to be sent to kafka without `\n`, e.g. assuming that this is stored in `alerta.json` you can send it with `kafkacat` like this:

```
cat alerta.json | tr -d '\n' | kafkacat -P -t iff.alerts -b my-cluster-kafka-bootstrap:9092
```

## NgsildUpdates Bridge

This service listen to the topic defined in the values file of `helmfile` in `kafkaBridge.ngsildUpdates.listenTopic` and defaults to `iff.ngsildUpdates`. The JSON object expects 3 fields:

* op - can be "update" or "upsert"
  * update is using the `entitiyOperations/update` NGSI-LD endpoint. With this endpoint existing entities can be updated.
  * upsert is using the `entitiyOperations/upsert` NGSI-LD endpoint. With this endpoint new entities can be created or an existing one can be updated.
* overwriteOrReplace - "true" or true, "false" or fals
  * This flag influences the behavior of the update or upsert operation. If `op=update` then it sets the `options=overwrite` parameter if it is `true`. If `op=upsert` then it sets the `options=replace` parameter if `false` and the `options=update` parameter if `true`.
* entities: Array of valid [NGSI-LD](https://www.etsi.org/deliver/etsi_gs/CIM/001_099/009/01.05.01_60/gs_CIM009v010501p.pdf) entities

Example request

```
{
    "op": "update",
    "overwriteOrReplace": "true",
    "entities": [
      {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "urn:filter:1",
        "type": "https://industry-fusion.com/types/v0.9/filter",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "value": "0.4"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge:1"
        }
      }
    ]
}
```

Note that the object has to be sent to kafka without `\n`, e.g. assuming that this is stored in `ngsildUpdates.json` you can send it with `kafkacat` like this:

```
cat ngsildUpdates.json | tr -d '\n' | kafkacat -P -t iff.alerts -b my-cluster-kafka-bootstrap:9092
```


## Debezium Bridge

The debezium bridge maps the updates from the NGSILD entity tabe to StreamingSQL tables.
Concept TBD.

## TimescaledDB Bridge

This service which listens at specific Kafka topic ("entityTopic": "iff.ngsild.entities","attributeTopic": "iff.ngsild.attributes") and forwards NGSI-LD data to timescaledb(tsdb) running in postgres database.

* entities: Array of valid [NGSI-LD](https://www.etsi.org/deliver/etsi_gs/CIM/001_099/009/01.05.01_60/gs_CIM009v010501p.pdf) entities

Data stored in the hypertable "entities" and "attributes" of timescaledb database "tsdb" in below format as per received data on kafka topic  "entityTopic": "iff.ngsild.entities","attributeTopic": "iff.ngsild.attributes" respectively:

```
tsdb=# \dt
          List of relations
 Schema |    Name    | Type  | Owner
--------+------------+-------+-------
 public | attributes | table | ngb
 public | entities   | table | ngb

tsdb=# select * from entities;
                   id                   |         observedAt         |         modifiedAt         |           type           | deleted
----------------------------------------+----------------------------+----------------------------+--------------------------+---------
 urn:iff:test1:PGtOQmSFbpSHk0VyIkvrtOgG | 2025-02-20 22:45:00.683+00 | 2025-02-20 22:45:00.683+00 | https://example.com/type | f

tsdb=# select * from attributes;
                                             id                                             | parentId |         observedAt         |         modifiedAt         |                entityId                |                     attributeId                     |               attributeType               | datasetId | nodeType |                                                                        value                                                                        |                valueType                | unitCode | lang | deleted
--------------------------------------------------------------------------------------------+----------+----------------------------+----------------------------+----------------------------------------+-----------------------------------------------------+-------------------------------------------+-----------+----------+-----------------------------------------------------------------------------------------------------------------------------------------------------+-----------------------------------------+----------+------+---------
 urn:iff:test2:Nn8LlSw7W0Dy71NvCjMdVwGh\https://industry-fusion.com/types/v0.9/relationship |          | 2025-02-20 22:44:50.199+00 | 2025-02-20 22:44:50.199+00 | urn:iff:test2:Nn8LlSw7W0Dy71NvCjMdVwGh | https://industry-fusion.com/types/v0.9/relationship | https://uri.etsi.org/ngsi-ld/Relationship | @none     | @id      | urn:iff:test3:Nn8LlSw7W0Dy71NvCjMdVwGh                                                                                                              |                                         |          |      | f
 urn:iff:test4:gGSfSuCAbIQW0kdfFDTfOcEY\https://industry-fusion.com/types/v0.9/state        |          | 2025-02-20 22:44:55.454+00 | 2025-02-20 22:44:55.454+00 | urn:iff:test4:gGSfSuCAbIQW0kdfFDTfOcEY | https://industry-fusion.com/types/v0.9/state        | https://uri.etsi.org/ngsi-ld/Property     | @none     | @value   | 1                                                                                                                                                   | http://www.w3.org/2001/XMLSchema#string |          |      | f
 urn:iff:test5:mVTt9EQzgkTBwrzemFUrBonE\https://industry-fusion.com/types/v0.9/geoproperty  |          | 2025-02-20 22:45:05.898+00 | 2025-02-20 22:45:05.898+00 | urn:iff:test5:mVTt9EQzgkTBwrzemFUrBonE | https://industry-fusion.com/types/v0.9/geoproperty  | https://uri.etsi.org/ngsi-ld/GeoProperty  | @none     | @json    | {"@type":["https://purl.org/geojson/vocab#Point"],"https://purl.org/geojson/vocab#coordinates":[{"@list":[{"@value":13.3698},{"@value":52.5163}]}]} | https://purl.org/geojson/vocab#Point    |          |      | f
(3 rows)
 
```
