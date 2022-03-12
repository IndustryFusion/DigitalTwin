# Kafka Bridges

1. Alerta bridge, a service which listens at a specific Kafka topic and forwards the data to Alerta.
2. NgsildUpdates bride, a service which listens at a specific Kafka topic and forwards data to the scorpio/Ngsild broker.
3. DebeziumBridge, a service which listens to debezium updates on ngsild entities and forward them to specific topics.

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