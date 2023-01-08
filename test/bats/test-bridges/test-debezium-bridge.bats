#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
NAMESPACE=iff
USERSECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAKURL=http://keycloak.local/auth/realms
CUTTER=/tmp/CUTTER
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
KAFKACAT_ATTRIBUTES=/tmp/KAFKACAT_ATTRIBUTES
KAFKACAT_ATTRIBUTES_TOPIC=iff.ngsild.attributes
KAFKACAT_ENTITY_CUTTER=/tmp/KAFKACAT_ENTITY_CUTTER
KAFKACAT_ENTITY_CUTTER_SORTED=/tmp/KAFKACAT_ENTITY_CUTTER_SORTED
KAFKACAT_ENTITY_CUTTER_NAME=cutter_test
KAFKACAT_ENTITY_CUTTER_TOPIC=iff.ngsild.entities.${KAFKACAT_ENTITY_CUTTER_NAME}
KAFKACAT_ENTITY_PLASMACUTTER=/tmp/KAFKACAT_ENTITY_PLASMACUTTER
KAFKACAT_ENTITY_PLASMACUTTER_SORTED=/tmp/KAFKACAT_ENTITY_PLASMACUTTER_SORTED
KAFKACAT_ENTITY_PLASMACUTTER_NAME=plasmacutter_test
KAFKACAT_ENTITY_PLASMACUTTER_TOPIC=iff.ngsild.entities.${KAFKACAT_ENTITY_PLASMACUTTER_NAME}
PLASMACUTTER_ID=urn:plasmacutter-test:12345
cat << EOF > ${CUTTER}
{
    "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    "id": "${PLASMACUTTER_ID}",
    "type": "https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}",
    "https://industry-fusion.com/types/v0.9/state": {
      "type": "Property",
      "value": "OFF"
    },
    "https://industry-fusion.com/types/v0.9/hasWorkpiece": [
        {
            "type": "Relationship",
            "object": "urn:workpiece-test:12345"
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
            }
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
            "value": "OFF"
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


compare_create_attributes() {
    cat << EOF | diff "$1" - >&3
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/hasFilter",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship",\
"https://uri.etsi.org/ngsi-ld/hasObject":"urn:filter-test:12345","nodeType":"@id","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship",\
"https://uri.etsi.org/ngsi-ld/hasObject":"urn:workpiece-test:12345",\
"nodeType":"@id","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship",\
"https://uri.etsi.org/ngsi-ld/hasObject":"urn:workpiece-test:23456",\
"nodeType":"@id","index":1}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/jsonValueArray",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"https://uri.etsi.org/ngsi-ld/hasValue":"{\"https://industry-fusion.com/types/v0.9/my\":[{\"@value\":\"json1\"}]}",\
"nodeType":"@json","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/jsonValueArray",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"https://uri.etsi.org/ngsi-ld/hasValue":"{\"@type\":[\"https://industry-fusion.com/types/v0.9/myJsonType\"],\"https://industry-fusion.com/types/v0.9/my\":[{\"@value\":\"json2\"}]}",\
"nodeType":"@json","valueType":["https://industry-fusion.com/types/v0.9/myJsonType"],"index":1}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValue",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/jsonValue",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"https://uri.etsi.org/ngsi-ld/hasValue":"{\"@type\":[\"https://industry-fusion.com/types/v0.9/myJsonType\"],\"https://industry-fusion.com/types/v0.9/my\":[{\"@value\":\"json\"}]}",\
"nodeType":"@json","valueType":["https://industry-fusion.com/types/v0.9/myJsonType"],"index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/multiState","type":"https://uri.etsi.org/ngsi-ld/Property",\
"https://uri.etsi.org/ngsi-ld/hasValue":"OFF","nodeType":"@value","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/multiState",\
"type":"https://uri.etsi.org/ngsi-ld/Property","https://uri.etsi.org/ngsi-ld/hasValue":"ON",\
"nodeType":"@value","valueType":"https://industry-fusion.com/types/v0.9/multiStateType","index":1}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"entityId":"${PLASMACUTTER_ID}",\
"name":"https://industry-fusion.com/types/v0.9/state",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"https://uri.etsi.org/ngsi-ld/hasValue":"OFF","nodeType":"@value","index":0}
EOF
}

compare_delete_attributes() {
    cat << EOF | diff "$1" - >&3
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasFilter","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece","index":1}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray","index":1}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValue","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState","index":0}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState","index":1}
{"id":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state","index":0}
EOF
}

compare_create_cutter() {
    cat << EOF | jq -S | diff "$1" - >&3
{"https://industry-fusion.com/types/v0.9/state":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"https://industry-fusion.com/types/v0.9/jsonValue":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValue",\
"https://industry-fusion.com/types/v0.9/jsonValueArray":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray",\
"https://industry-fusion.com/types/v0.9/multiState": "${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState",\
"https://industry-fusion.com/types/v0.9/hasFilter":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"https://industry-fusion.com/types/v0.9/hasWorkpiece":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"id":"${PLASMACUTTER_ID}","type":"https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}"}
EOF
}

compare_delete_cutter() {
    cat << EOF | jq -S | diff "$1" - >&3
{"https://industry-fusion.com/types/v0.9/state":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"https://industry-fusion.com/types/v0.9/jsonValue":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValue",\
"https://industry-fusion.com/types/v0.9/jsonValueArray":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray",\
"https://industry-fusion.com/types/v0.9/multiState": "${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState",\
"https://industry-fusion.com/types/v0.9/hasFilter":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"https://industry-fusion.com/types/v0.9/hasWorkpiece":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"id":"${PLASMACUTTER_ID}"}
EOF
}

compare_create_plasmacutter() {
    cat << EOF | jq -S | diff "$1" - >&3
{"https://industry-fusion.com/types/v0.9/state":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"https://industry-fusion.com/types/v0.9/jsonValue":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValue",\
"https://industry-fusion.com/types/v0.9/jsonValueArray":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray",\
"https://industry-fusion.com/types/v0.9/multiState": "${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState",\
"https://industry-fusion.com/types/v0.9/hasFilter":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"https://industry-fusion.com/types/v0.9/hasWorkpiece":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"id":"${PLASMACUTTER_ID}","type":"https://industry-fusion.com/types/v0.9/${KAFKACAT_ENTITY_PLASMACUTTER_NAME}"}
EOF
}

compare_delete_plasmacutter() {
    cat << EOF | jq -S | diff "$1" - >&3
{"https://industry-fusion.com/types/v0.9/state":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",\
"https://industry-fusion.com/types/v0.9/jsonValue":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValue",\
"https://industry-fusion.com/types/v0.9/jsonValueArray":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValueArray",\
"https://industry-fusion.com/types/v0.9/multiState": "${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/multiState",\
"https://industry-fusion.com/types/v0.9/hasFilter":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"https://industry-fusion.com/types/v0.9/hasWorkpiece":"${PLASMACUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"id":"${PLASMACUTTER_ID}"}
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


@test "verify debezium bridge sends updates to attributes and entity topics when entity is created" {

    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_CUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_CUTTER}) &
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_PLASMACUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_PLASMACUTTER}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    echo "# token: $token"
    create_ngsild "$token" "$CUTTER"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -S < ${KAFKACAT_ENTITY_CUTTER} > ${KAFKACAT_ENTITY_CUTTER_SORTED}
    jq -S < ${KAFKACAT_ENTITY_PLASMACUTTER} > ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]

    echo "# Compare CUTTER Entity"
    run compare_create_cutter ${KAFKACAT_ENTITY_CUTTER_SORTED}
    [ "$status" -eq 0 ]

    echo "# Compare PLASMACUTTER Entity"
    run compare_create_plasmacutter ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    [ "$status" -eq 0 ]
}

@test "verify debezium bridge sends updates to attributes and entity topics when entity is deleted" {

    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_CUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_CUTTER}) &
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ENTITY_PLASMACUTTER_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ENTITY_PLASMACUTTER}) &
    echo "# launched kafkacat for debezium updates, wait some time to let it connect"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "$token" "$PLASMACUTTER_ID"
    echo "# Sent ngsild updates, sleep 5s to let debezium bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    sleep 2
    sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -S < ${KAFKACAT_ENTITY_CUTTER} > ${KAFKACAT_ENTITY_CUTTER_SORTED}
    jq -S < ${KAFKACAT_ENTITY_PLASMACUTTER} > ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    run compare_delete_attributes ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]

    run compare_delete_cutter ${KAFKACAT_ENTITY_CUTTER_SORTED}
    [ "$status" -eq 0 ]

    run compare_delete_plasmacutter ${KAFKACAT_ENTITY_PLASMACUTTER_SORTED}
    [ "$status" -eq 0 ]
}
