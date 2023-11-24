## Getting MQTT notifications from subscriptions
Requirements: [Docker](https://docs.docker.com/get-docker/) (with the [docker-compose plugin](https://docs.docker.com/compose/install/linux/#install-using-the-repository)), curl, git, [mosquitto](https://mosquitto.org/download/), mosquitto-clients

For ease of deployment, we will deploy the ScorpioBroker using one of the docker-compose files present in the repository.

First, clone the repository:

 ```
 git clone https://github.com/ScorpioBroker/ScorpioBroker.git && cd ScorpioBroker
```

Then, checkout the latest release branch, 4.1.10 at the time of this example:

```
git checkout quarkus-release/4.1.10
```

Now we can deploy the ScorpioBroker using docker-compose, pulling necessary images from Docker Hub:

```
docker-compose -f ./compose-files/docker-compose-java-aaio-kafka.yml up -d
```

Using the examples from the ScorpioBroker's [documentation](https://scorpio.readthedocs.io/en/latest/mqtt.html), we will first create an entity:

```
curl http://localhost:9090/ngsi-ld/v1/entities/ -s -S -H 'Content-Type: application/json' -d '{
  "id": "urn:ngsi-ld:Vehicle:A135",
  "type": "Vehicle",
  "brandName": {
    "type": "Property",
    "value": "BMW"
  },
  "speed": [
    {
      "type": "Property",
      "value": 55,
      "datasetId": "urn:ngsi-ld:Property:speedometerA4567-speed",
      "source": {
        "type": "Property",
        "value": "Speedometer"
      }
    },
    {
      "type": "Property",
      "value": 11,
      "datasetId": "urn:ngsi-ld:Property:gpsA4567-speed",
      "source": {
        "type": "Property",
        "value": "GPS"
      }
    },
    {
      "type": "Property",
      "value": 10,
      "source": {
        "type": "Property",
        "value": "CAMERA"
      }
    }
  ]
}'
```

This command will create Vehicle type entity with multiple properties. We will subscribe to the brandName property with the following command. This subscription will notify us when the brandName property is not 'BMW':

```
 curl http://localhost:9090/ngsi-ld/v1/subscriptions -s -S -H 'Content-Type: application/json' -d '{
  "id": "urn:ngsi-ld:Subscription:22",
  "type": "Subscription",
  "entities": [
    {
      "id": "urn:ngsi-ld:Vehicle:A135",
      "type": "Vehicle"
    }
  ],
  "watchedAttributes": [
    "brandName"
  ],
  "q": "brandName!=BMW",
  "notification": {
    "attributes": [
      "brandName"
    ],
    "format": "keyValues",
    "endpoint": {
      "uri": "mqtt://broker.hivemq.com:1883/notifyDigitalTwin",
      "accept": "application/json"
    }
  }
}'
```

We use the public broker of HiveMQ as our MQTT broker, but we still need to subscribe to the topic "notifyDigitalTwin" using the mosquitto_sub utility (installed with the mosquitto-clients package):

```
mosquitto_sub -h broker.hivemq.com -p 1883 -t notifyDigitalTwin -v
```

Now, we have subscribed to the topic that will get the notification. In another terminal, run the following command to trigger the notification by changing the brandName property:

```
curl http://localhost:9090/ngsi-ld/v1/entities/urn:ngsi-ld:Vehicle:A135/attrs -s -S -H 'Content-Type: application/json' -d '{
  "brandName":{
      "type":"Property",
      "value":"Mercedes"
 }
}'
```

This will trigger a notification like this to be sent to the topic with the new state of the entity: 

```
{
  "body": {
    "id": "notification:-8443350506182602984",
    "type": "Notification",
    "subscriptionId": "urn:ngsi-ld:Subscription:22",
    "notifiedAt": "2023-11-17T13:18:47.165000Z",
    "data": [
      {
        "id": "urn:ngsi-ld:Vehicle:A135",
        "type": "Vehicle",
        "brandName": {
          "type": "Property",
          "value": "Mercedes"
        },
        "speed": [
          {
            "type": "Property",
            "datasetId": "urn:ngsi-ld:Property:speedometerA4567-speed",
            "source": {
              "type": "Property",
              "value": "Speedometer"
            },
            "value": 55
          },
          {
            "type": "Property",
            "datasetId": "urn:ngsi-ld:Property:gpsA4567-speed",
            "source": {
              "type": "Property",
              "value": "GPS"
            },
            "value": 11
          },
          {
            "type": "Property",
            "source": {
              "type": "Property",
              "value": "CAMERA"
            },
            "value": 10
          }
        ]
      }
    ]
  }
}
```
