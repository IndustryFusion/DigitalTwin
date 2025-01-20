# MQTT bridge

## Run locally for debugging

First scale down current mqtt-bridge deployment in Kubernetes

    kubectl -n iff scale deployment/mqtt-bridge --replicas=0

Then Retrieve client secret for MQTT

    MQTT_CLIENT_SECRET=$(kubectl -n iff get secrets keycloak-client-secret-mqtt-broker -o jsonpath='{.data.CLIENT_SECRET}'| base64 -d | xargs echo)


Intercept and replace with telepresence

    telepresence intercept mqtt-bridge -p 3025

Start app with secret

    node ./app.js