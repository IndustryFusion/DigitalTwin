#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
SKIP=skip
NAMESPACE=iff
USERSECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAKURL=http://keycloak.local/auth/realms
CUTTER=/tmp/CUTTER
CUTTER_TIMESTAMPED=/tmp/CUTTER_TIMESTAMPED
CUTTER_DATASETID=/tmp/CUTTER_DATASETID
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
KAFKACAT_ATTRIBUTES=/tmp/KAFKACAT_ATTRIBUTES
KAFKACAT_ATTRIBUTES_TOPIC=iff.ngsild.attributes
KAFKACAT_ENTITY_CUTTER=/tmp/KAFKACAT_ENTITY_CUTTER
KAFKACAT_ENTITY_CUTTER_SORTED=/tmp/KAFKACAT_ENTITY_CUTTER_SORTED
KAFKACAT_ENTITY_CUTTER_NAME=cutter_test
KAFKACAT_ENTITY_CUTTER_TOPIC=iff.ngsild.entities
KAFKACAT_ENTITY_PLASMACUTTER=/tmp/KAFKACAT_ENTITY_PLASMACUTTER
KAFKACAT_ENTITY_PLASMACUTTER_SORTED=/tmp/KAFKACAT_ENTITY_PLASMACUTTER_SORTED
KAFKACAT_ENTITY_PLASMACUTTER_NAME=plasmacutter_test
KAFKACAT_ENTITY_PLASMACUTTER_TOPIC=iff.ngsild.entities
PLASMACUTTER_ID=urn:plasmacutter-test:12345
cat << EOF > ${CUTTER}
{
    "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    "id": "${PLASMACUTTER_ID}",
    "type": "https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}",
    "https://industry-fusion.com/types/v0.9/state": [
        {
            "type": "Property",
            "value": "ON"
        },
        {
            "type": "Property",
            "value": "OFF"
        }
    ],
    "https://industry-fusion.com/types/v0.9/hasWorkpiece": [
        {
            "type": "Relationship",
            "object": "urn:workpiece-test:12345",
            "datasetId": "urn:workpiece-test:12345-ZZZ"
        },
        {
            "type": "Relationship",
            "object": "urn:workpiece-test:23456"
        }
    ],
    "https://industry-fusion.com/types/v0.9/hasFilter": {
      "type": "Relationship",
      "object": "urn:filter-test:12345"
    },
    "https://industry-fusion.com/types/v0.9/jsonValue": {
        "type": "Property",
        "value": {
            "type": "https://industry-fusion.com/types/v0.9/myJsonType",
            "https://industry-fusion.com/types/v0.9/my": "json"
        }
    },
    "https://industry-fusion.com/types/v0.9/jsonValueArray": [
        {
            "type": "Property",
            "value": {
                "https://industry-fusion.com/types/v0.9/my": "json1"
            },
            "datasetId": "urn:json-value-test:json1"
        },
        {
            "type": "Property",
            "value": {
                "type": "https://industry-fusion.com/types/v0.9/myJsonType",
                "https://industry-fusion.com/types/v0.9/my": "json2"
            }
        }
    ],
    "https://industry-fusion.com/types/v0.9/multiState": [
        {
            "type": "Property",
            "value": "OFF",
            "datasetId": "urn:multistate-test:off"
        },
        {
            "type": "Property",
            "value": {
                "@value": "ON",
                "type": "https://industry-fusion.com/types/v0.9/multiStateType"
            }
        }
    ]
}
EOF

cat << EOF > ${CUTTER_TIMESTAMPED}
{
    "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    "id": "${PLASMACUTTER_ID}",
    "type": "https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}",
    "https://industry-fusion.com/types/v0.9/state": [
        {
            "type": "Property",
            "value": "OFF",
            "observedAt": "2023-01-08T01:11:35.99Z"
        },
        {
            "type": "Property",
            "value": "ON",
            "datasetId": "urn:state-test:on",
            "observedAt": "2023-01-08T01:10:35.555Z"
        }
    ],
    "https://industry-fusion.com/types/v0.9/hasWorkpiece": [
        {
            "type": "Relationship",
            "object": "urn:workpiece-test:12345",
            "observedAt": "2023-05-19T01:19:35Z"
        }
    ],
    "https://industry-fusion.com/types/v0.9/hasFilter": {
      "type": "Relationship",
      "object": "urn:filter-test:12345",
      "observedAt": "2023-01-08T01:11:35.100Z"
    }
}
EOF

cat << EOF > ${CUTTER_DATASETID}
{
    "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    "id": "${PLASMACUTTER_ID}",
    "type": "https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}",
    "https://industry-fusion.com/types/v0.9/state": [
        {
            "type": "Property",
            "value": "ON",
            "datasetId": "urn:state_on"
        },
        {
            "type": "Property",
            "value": "OFF",
            "datasetId": "urn:state_off"
        },
        {
            "type": "Property",
            "value": "ONN",
            "datasetId": "2urn:state_on"
        },
        {
            "type": "Property",
            "value": "MAYBE"
        },
        {
            "type": "Property",
            "value": "OFFOFF",
            "datasetId": "+=-urn:state_off"
        }
    ]
}
EOF

compare_create_attributes_timestamps() {
    cat << EOF | diff "$1" - >&3
1673140235555
1673140295100
1673140295990
1684459175000
EOF
}

compare_create_attributes() {
    cat << EOF | diff "$1" - >&3
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/hasFilter",\
"datasetId":"@none",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship",\
"attributeValue":"urn:filter-test:12345","nodeType":"@id","index":0,"synced":true}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"datasetId":"@none",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship",\
"attributeValue":"urn:workpiece-test:23456",\
"nodeType":"@id","index":0,"synced":true}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"datasetId":"urn:workpiece-test:12345-ZZZ",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship",\
"attributeValue":"urn:workpiece-test:12345",\
"nodeType":"@id","index":1,"synced":true}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/jsonValueArray",\
"datasetId":"@none",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"{\"@type\":[\"https://industry-fusion.com/types/v0.9/myJsonType\"],\"https://industry-fusion.com/types/v0.9/my\":[{\"@value\":\"json2\"}]}",\
"nodeType":"@json","valueType":["https://industry-fusion.com/types/v0.9/myJsonType"],"index":0,"synced":true}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/jsonValueArray",\
"datasetId":"urn:json-value-test:json1",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"{\"https://industry-fusion.com/types/v0.9/my\":[{\"@value\":\"json1\"}]}",\
"nodeType":"@json","index":1,"synced":true}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValue",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/jsonValue",\
"datasetId":"@none",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"{\"@type\":[\"https://industry-fusion.com/types/v0.9/myJsonType\"],\"https://industry-fusion.com/types/v0.9/my\":[{\"@value\":\"json\"}]}",\
"nodeType":"@json","valueType":["https://industry-fusion.com/types/v0.9/myJsonType"],"index":0,"synced":true}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/multiState",\
"datasetId":"@none",\
"type":"https://uri.etsi.org/ngsi-ld/Property","attributeValue":"ON",\
"nodeType":"@value","valueType":"https://industry-fusion.com/types/v0.9/multiStateType","index":0,"synced":true}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/multiState",\
"datasetId":"urn:multistate-test:off",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"OFF","nodeType":"@value","index":1,"synced":true}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/state",\
"datasetId":"@none",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"OFF","nodeType":"@value","index":0,"synced":true}
EOF
}

compare_delete_attributes() {
    cat << EOF | diff "$1" - >&3
{"id":"urn:plasmacutter-test:12345\\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"name":"https://industry-fusion.com/types/v0.9/hasFilter","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Relationship","datasetId":"@none",\
"nodeType":"@id","index":0,"deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"name":"https://industry-fusion.com/types/v0.9/hasWorkpiece","entityId":"urn:plasmacutter-test:12345",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship","datasetId":"@none",\
"nodeType":"@id","index":0,"deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"name":"https://industry-fusion.com/types/v0.9/hasWorkpiece","entityId":"urn:plasmacutter-test:12345",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship","datasetId":"urn:workpiece-test:12345-ZZZ",\
"nodeType":"@id","index":1,"deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\https://industry-fusion.com/types/v0.9/jsonValueArray","name":"https://industry-fusion.com/types/v0.9/jsonValueArray","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Property","datasetId":"@none","nodeType":"@json","index":0,"deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\https://industry-fusion.com/types/v0.9/jsonValueArray","name":"https://industry-fusion.com/types/v0.9/jsonValueArray","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Property","datasetId":"urn:json-value-test:json1","nodeType":"@json","index":1,"deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\https://industry-fusion.com/types/v0.9/jsonValue","name":"https://industry-fusion.com/types/v0.9/jsonValue","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Property","datasetId":"@none","nodeType":"@json","index":0,"deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\https://industry-fusion.com/types/v0.9/multiState","name":"https://industry-fusion.com/types/v0.9/multiState","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Property","datasetId":"@none","nodeType":"@value","index":0,"deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\https://industry-fusion.com/types/v0.9/multiState","name":"https://industry-fusion.com/types/v0.9/multiState","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Property","datasetId":"urn:multistate-test:off","nodeType":"@value","index":1,"deleted":true,"synced":true}
{"id":"urn:plasmacutter-test:12345\\\\https://industry-fusion.com/types/v0.9/state","name":"https://industry-fusion.com/types/v0.9/state","entityId":"urn:plasmacutter-test:12345","type":"https://uri.etsi.org/ngsi-ld/Property","datasetId":"@none","nodeType":"@value","index":0,"deleted":true,"synced":true}
EOF
}

# compare_create_cutter() {
#     cat << EOF | jq -S | diff "$1" - >&3
# {"id":"${PLASMACUTTER_ID}","type":"https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}"}
# EOF
# }

# compare_delete_cutter() {
#     cat << EOF | jq -S | diff "$1" - >&3
# {"https://industry-fusion.com/types/v0.9/state":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
# "https://industry-fusion.com/types/v0.9/jsonValue":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValue",\
# "https://industry-fusion.com/types/v0.9/jsonValueArray":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray",\
# "https://industry-fusion.com/types/v0.9/multiState": "${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState",\
# "https://industry-fusion.com/types/v0.9/hasFilter":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasFilter",\
# "https://industry-fusion.com/types/v0.9/hasWorkpiece":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
# "id":"${PLASMACUTTER_ID}"}
# EOF
# }

compare_create_plasmacutter() {
    cat << EOF | jq -S | diff "$1" - >&3
{"id":"${PLASMACUTTER_ID}","type":"https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}"}
EOF
}

compare_delete_plasmacutter() {
    cat << EOF | jq -S | diff "$1" - >&3
{"id":"${PLASMACUTTER_ID}","type": "https://industry-fusion.com/types/v0.9/plasmacutter_test","deleted":true}
EOF
}

compare_create_attributes_datasetid() {
    cat << EOF | LC_ALL="en_US.UTF-8" sort | diff "$1" - >&3
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/state",\
"datasetId":"@none",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"MAYBE","nodeType":"@value","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/state",\
"datasetId":"+=-urn:state_off",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"OFFOFF","nodeType":"@value","index":1}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/state",\
"datasetId":"2urn:state_on",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"ONN","nodeType":"@value","index":2}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/state",\
"datasetId":"urn:state_off",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"OFF","nodeType":"@value","index":3}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/state",\
"datasetId":"urn:state_on",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"attributeValue":"ON","nodeType":"@value","index":4}
EOF
}

get_password() {
    kubectl -n ${NAMESPACE} get ${USERSECRET} -o jsonpath='{.data.password}'| base64 -d
}
get_token() {
    curl -d "client_id=${CLIENT_ID}" -d "username=${USER}" -d "password=$password" -d 'grant_type=password' "${KEYCLOAKURL}/${NAMESPACE}/protocol/openid-connect/token"| jq ".access_token"| tr -d '"'
}

# create ngsild entity
# $1: auth token
# $2: filename which contains entity to create
create_ngsild() {
    curl -vv -X POST -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entities/ -H "Content-Type: application/ld+json"
}


# deletes ngsild entity
# $1: auth token
# $2: id of entity to delete
delete_ngsild() {
    curl -vv -X DELETE -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Content-Type: application/ld+json"
}

setup() {
    # shellcheck disable=SC2086
    [ $DEBUG = "true" ] || (exec ${SUDO} kubefwd -n iff -l app.kubernetes.io/name=kafka svc) &
    echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    sleep 3
    echo "# create needed kafka topics to make sure that consumers will not fail first time"
    echo "--------------------------New Test------------------" | kafkacat -P -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
    echo "--------------------------New Test------------------" | kafkacat -P -t ${KAFKACAT_ENTITY_CUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP}
    echo "--------------------------New Test------------------" | kafkacat -P -t ${KAFKACAT_ENTITY_PLASMACUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP}
}
teardown(){
    echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    [ $DEBUG = "true" ] || ${SUDO} killall kubefwd
}


@test "verify debezium bridge sends updates to attributes and entities topics when entity is created" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    echo "# token: $token"
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    #(exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_CUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_CUTTER}) &
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_PLASMACUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_PLASMACUTTER}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    create_ngsild "$token" "$CUTTER"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    #jq -S < ${KAFKACAT_ENTITY_CUTTER} > ${KAFKACAT_ENTITY_CUTTER_SORTED}
    jq -S < ${KAFKACAT_ENTITY_PLASMACUTTER} > ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]

    # echo "# Compare CUTTER Entity"
    # run compare_create_cutter ${KAFKACAT_ENTITY_CUTTER_SORTED}
    # [ "$status" -eq 0 ]

    echo "# Compare PLASMACUTTER Entity"
    run compare_create_plasmacutter ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    [ "$status" -eq 0 ]
}

@test "verify debezium bridge sends updates to attributes and entity topics when entity is deleted" {
    #$SKIP
    password=$(get_password)
    token=$(get_token)
    create_ngsild "$token" "$CUTTER" || echo "Could not creatattributee $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_CUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_CUTTER}) &
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_PLASMACUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_PLASMACUTTER}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    delete_ngsild "$token" "$PLASMACUTTER_ID"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    sleep 2
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -S < ${KAFKACAT_ENTITY_CUTTER} > ${KAFKACAT_ENTITY_CUTTER_SORTED}
    jq -S < ${KAFKACAT_ENTITY_PLASMACUTTER} > ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    run compare_delete_attributes ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]

    # run compare_delete_cutter ${KAFKACAT_ENTITY_CUTTER_SORTED}
    # [ "$status" -eq 0 ]

    run compare_delete_plasmacutter ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    [ "$status" -eq 0 ]
}

@test "verify debezium bridge sends updates to attributes with correct Kafka timestamps" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    echo "# token: $token"
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -f '%T\n' -o end >${KAFKACAT_ATTRIBUTES}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    create_ngsild "$token" "$CUTTER_TIMESTAMPED"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes_timestamps ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]

}

@test "verify debezium bridge sorts attributes based on their datasetIds" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    create_ngsild "$token" "$CUTTER_DATASETID"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes_datasetid ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]
}