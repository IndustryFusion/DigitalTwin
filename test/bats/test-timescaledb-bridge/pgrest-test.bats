#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
SKIP= # set =skip to skip all test (and only remove $SKIP from the test you are interested in)
NAMESPACE=iff
USER_SECRET=secret/credential-iff-realm-user-iff
USER=realm_user
KEYCLOAK_URL=http://keycloak.local/auth/realms
CLIENT_ID="scorpio"
PGREST_URL=pgrest.local
POSTGRES_USERNAME=dbreader
POSTGRES_DATABASE=tsdb
POSTGRES_SECRET=dbreader.acid-cluster.credentials.postgresql.acid.zalan.do
ATTRIBUTES_PROPERTY=/tmp/property.txt
ATTRIBUTES_PROPERTY2=/tmp/property2.txt
ATTRIBUTES_TOPIC=iff.ngsild.attributes
ENTITIES_OBJECT=/tmp/entity.txt
ENTITIES_TOPIC=iff.ngsild.entities
ENTITY_TYPE=https://example.com/type
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
RANDOMID=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 24; echo)
URN=urn:iff:test1:${RANDOMID}
URN2=urn:iff:test2:${RANDOMID}
URN3=urn:iff:test3:${RANDOMID}
STATE=https://industry-fusion.com/types/v0.9/state
IDSTATE="${URN}\\\\${STATE}"
IDSTATE2="${URN2}\\\\${STATE}"
VALUE="state"
VALUE2="1"
PROPERTY=https://uri.etsi.org/ngsi-ld/Property
POSTGRES_PASSWORD=$(kubectl -n ${NAMESPACE} get secret/${POSTGRES_SECRET} -o jsonpath='{.data.password}'| base64 -d)
TSDB_RESULT=/tmp/TSDB_RESULT
TSDBTABLE=attributes
ENTITYTABLE=entities

cat << EOF > ${ATTRIBUTES_PROPERTY}
{
    "id": "${IDSTATE}",
    "entityId": "${URN}",
    "name": "${STATE}",
    "type": "${PROPERTY}",
    "attributeValue": "${VALUE}",
    "nodeType": "@value",
    "datasetId": "@none"}
EOF

cat << EOF > ${ATTRIBUTES_PROPERTY2}
{
    "id": "${IDSTATE2}",
    "entityId": "${URN2}",
    "name": "${STATE}",
    "type": "${PROPERTY}",
    "attributeValue": "${VALUE2}",
    "nodeType": "@value",
    "valueType": "http://www.w3.org/2001/XMLSchema#string",
    "datasetId": "@none"
}
EOF

cat << EOF > ${ENTITIES_OBJECT}
{
    "id": "${URN3}",
    "type": "${ENTITY_TYPE}"
}
EOF

get_password() {
    kubectl -n ${NAMESPACE} get ${USER_SECRET} -o jsonpath='{.data.password}' | base64 -d
}

get_token() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${CLIENT_ID}" \
        -d "grant_type=password" \
        -d "username=${USER}" \
        -d "password=${password}" \
        | jq ".access_token" | tr -d '"'
}


# send data to kafka bridge
# $1: file to send
# $2: kafka topic
send_to_kafka_bridge() {
    tr -d '\n' <"$1" | kafkacat -P -t "$2" -b "${KAFKA_BOOTSTRAP}"
}

# receive datapoints
# $1: payload to post
# get_datapoints() {
#     urn=$1
#     targetfile=$2
#     echo 'select json_agg(t) from public.entityhistories as t where t."entityId" = ' \'"$urn"\' ';' | \
#         PGPASSWORD=${POSTGRES_PASSWORD} psql -t -h localhost -U ${POSTGRES_USERNAME} -d ${POSTGRES_DATABASE} -A | \
#         jq -S 'map(del(.modifiedAt, .observedAt))' >"$targetfile"
# }


check_tsdb_sample() {
    URN=$2
    cat << EOF | diff "$1" - >&3
[
  {
    "attributeId": "https://industry-fusion.com/types/v0.9/state",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "$URN",
    "id": "${IDSTATE2}",
    "lang": null,
    "nodeType": "@value",
    "parentId": null,
    "unitType": null,
    "value": "$VALUE2",
    "valueType": "http://www.w3.org/2001/XMLSchema#string"
  }
]
EOF
}

check_entity_sample() {
    URN=$2
    cat << EOF | diff "$1" - >&3
[
  {
    "deleted": false,
    "id": "$URN3",
    "type": "${ENTITY_TYPE}"
  }
]
EOF
}

get_samples() {
    
    url=$1
    token=$2
    urn=$3
    result=$4
    if [ -z "$token" ]; then
        HEADER="''"
    else
        HEADER="Authorization: Bearer $token"
    fi
    curl http://"${url}"/"${TSDBTABLE}"?entityId=like."$urn" -H "$HEADER" | \
        jq -S 'map(del(.modifiedAt, .observedAt))' >"$result"
}

get_entity_samples() {
    
    url=$1
    token=$2
    urn=$3
    result=$4
    if [ -z "$token" ]; then
        HEADER="''"
    else
        HEADER="Authorization: Bearer $token"
    fi
    curl http://"${url}"/"${ENTITYTABLE}"?id=like."$urn" -H "$HEADER" | \
        jq -S 'map(del(.modifiedAt, .observedAt))' >"$result"
}

get_error_samples() {
    
    url=$1
    token=$2
    urn=$3
    result=$4
    if [ -z "$token" ]; then
        HEADER="''"
    else
        HEADER="Authorization: Bearer $token"
    fi
    curl http://"${url}"/"${TSDBTABLE}"?entityId=like."$urn" -H "$HEADER" | \
        jq -S >"$result"
}

check_error_code() {
    obj=$(cat "$1")
    echo "$obj"| jq .code
}

setup() {
    # shellcheck disable=SC2086
    [ "$DEBUG" = "true" ] || (exec ${SUDO} kubefwd -n ${NAMESPACE} -l "app.kubernetes.io/name in (kafka)" svc) &
    echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    sleep 3
}
teardown(){
    echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    [ "$DEBUG" = "true" ] || ${SUDO} killall kubefwd
}

@test "verify pgrest rejecting anonymous request" {
    $SKIP
    echo "# Sending property to Kafka"
    send_to_kafka_bridge ${ATTRIBUTES_PROPERTY} ${ATTRIBUTES_TOPIC}
    echo "# Now receiving sample"
    get_error_samples "$PGREST_URL" "" "$URN" "$TSDB_RESULT"
    run check_error_code "$TSDB_RESULT" "PGRST302"
    [ "$status" -eq "0" ]
}

@test "verify timescaledb-bridge is forwarding entity" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    echo "# token $token"
    echo "# Sending entity to Kafka"
    send_to_kafka_bridge ${ENTITIES_OBJECT} ${ENTITIES_TOPIC}
    sleep 2
    echo "# Now receiving sample"
    get_entity_samples "$PGREST_URL" "$token" "$URN3" "$TSDB_RESULT"
    run check_entity_sample "$TSDB_RESULT" "$URN2"
    [ "$status" -eq "0" ]
}

@test "verify timescaledb-bridge is forwarding iri Property" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    echo "# token $token"
    echo "# Sending property to Kafka"
    send_to_kafka_bridge ${ATTRIBUTES_PROPERTY2} ${ATTRIBUTES_TOPIC}
    sleep 2
    echo "# Now receiving sample"
    get_samples "$PGREST_URL" "$token" "$URN2" "$TSDB_RESULT"
    run check_tsdb_sample "$TSDB_RESULT" "$URN2"
    [ "$status" -eq "0" ]
}
