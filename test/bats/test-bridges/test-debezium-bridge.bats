#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi

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
KAFKACAT_ENTITY_CUTTER_TOPIC=iff.ngsild.entities.cutter
KAFKACAT_ENTITY_PLASMACUTTER=/tmp/KAFKACAT_ENTITY_PLASMACUTTER
KAFKACAT_ENTITY_PLASMACUTTER_TOPIC=iff.ngsild.entities.plasmacutter
PLASMACUTTER_ID=urn:plasmacutter:1
cat << EOF > ${CUTTER}
{
    "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
    "id": "${PLASMACUTTER_ID}",
    "type": "https://industry-fusion.com/types/v0.9/plasmacutter",
    "https://industry-fusion.com/types/v0.9/state": {
      "type": "Property",
      "value": "OFF"
    },
    "https://industry-fusion.com/types/v0.9/hasWorkpiece": {
      "type": "Relationship",
      "object": "urn:workpiece:1"
    },
    "https://industry-fusion.com/types/v0.9/hasFilter": {
      "type": "Relationship",
      "object": "urn:filter:1"
    }
}
EOF


compare_create_attributes() {
    cat << EOF | diff "$1" - >&3
{"id":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/state",\
"entityId":"urn:plasmacutter:1",\
"synchronized":true,\
"name":"https://industry-fusion.com/types/v0.9/state",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"https://uri.etsi.org/ngsi-ld/hasValue":"OFF","index":0}
{"id":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"entityId":"urn:plasmacutter:1",\
"synchronized":true,\
"name":"https://industry-fusion.com/types/v0.9/hasFilter",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship",\
"https://uri.etsi.org/ngsi-ld/hasObject":"urn:filter:1","index":0}
{"id":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"entityId":"urn:plasmacutter:1",\
"synchronized":true,\
"name":"https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"type":"https://uri.etsi.org/ngsi-ld/Relationship",\
"https://uri.etsi.org/ngsi-ld/hasObject":"urn:workpiece:1",\
"index":0}
EOF
}

compare_delete_attributes() {
    cat << EOF | diff "$1" - >&3
{"id":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/state","index":0}
{"id":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/hasFilter","index":0}
{"id":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/hasWorkpiece","index":0}
EOF
}

compare_create_cutter() {
    cat << EOF | diff "$1" - >&3
{"https://industry-fusion.com/types/v0.9/state":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/state",\
"https://industry-fusion.com/types/v0.9/hasFilter":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"https://industry-fusion.com/types/v0.9/hasWorkpiece":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"id":"urn:plasmacutter:1","type":"https://industry-fusion.com/types/v0.9/plasmacutter"}
EOF
}

compare_delete_cutter() {
    cat << EOF | diff "$1" - >&3
{"id":"urn:plasmacutter:1"}
EOF
}

compare_create_plasmacutter() {
    cat << EOF | diff "$1" - >&3
{"https://industry-fusion.com/types/v0.9/state":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/state",\
"https://industry-fusion.com/types/v0.9/hasFilter":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/hasFilter",\
"https://industry-fusion.com/types/v0.9/hasWorkpiece":"urn:plasmacutter:1\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",\
"id":"urn:plasmacutter:1","type":"https://industry-fusion.com/types/v0.9/plasmacutter"}
EOF
}

compare_delete_plasmacutter() {
    cat << EOF | diff "$1" - >&3
{"id":"urn:plasmacutter:1"}
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
    (exec ${SUDO} kubefwd -n iff -l app.kubernetes.io/name=kafka svc) &
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
    ${SUDO} killall kubefwd
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
    run compare_create_attributes ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]

    run compare_create_cutter ${KAFKACAT_ENTITY_CUTTER}
    [ "$status" -eq 0 ]

    run compare_create_plasmacutter ${KAFKACAT_ENTITY_PLASMACUTTER}
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
    run compare_delete_attributes ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]

    run compare_delete_cutter ${KAFKACAT_ENTITY_CUTTER}
    [ "$status" -eq 0 ]

    run compare_delete_plasmacutter ${KAFKACAT_ENTITY_PLASMACUTTER}
    [ "$status" -eq 0 ]
}