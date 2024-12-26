#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
SKIP= # set =skip to skip all test (and only remove $SKIP from the test you are interested in)
IFFNAMESPACE=iff
POSTGRES_POD=acid-cluster-0
POSTGRES_USERNAME=ngb
POSTGRES_DATABASE=tsdb
POSTGRES_SECRET=ngb.acid-cluster.credentials.postgresql.acid.zalan.do
ENTITY=/tmp/entity.txt
ATTRIBUTES_PROPERTY=/tmp/property.txt
ATTRIBUTES_PROPERTY2=/tmp/property2.txt
ATTRIBUTES_RELATIONSHIP=/tmp/relationship.txt
ATTRIBUTES_TOPIC=iff.ngsild.attributes
ENTITIES_TOPIC=iff.ngsild.entities
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
RANDOMID=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 24; echo)
URN=urn:iff:test1:${RANDOMID}
URN2=urn:iff:test2:${RANDOMID}
URN3=urn:iff:test3:${RANDOMID}
URN4=urn:iff:test4:${RANDOMID}
STATE=https://industry-fusion.com/types/v0.9/state
REL=https://industry-fusion.com/types/v0.9/relationship
IDSTATE="${URN}\\\\${STATE}"
IDSTATE2="${URN4}\\\\${STATE}"
IDREL="${URN2}\\\\${REL}"
VALUE="state"
VALUE2="1"
PROPERTY=https://uri.etsi.org/ngsi-ld/Property
RELATIONSHIP=https://uri.etsi.org/ngsi-ld/Relationship
POSTGRES_PASSWORD=$(kubectl -n ${IFFNAMESPACE} get secret/${POSTGRES_SECRET} -o jsonpath='{.data.password}'| base64 -d)
TSDB_RESULT=/tmp/TSDB_RESULT

cat << EOF > ${ATTRIBUTES_PROPERTY}
{
    "id": "${IDSTATE}",
    "entityId": "${URN}",
    "name": "${STATE}",
    "type": "${PROPERTY}",
    "attributeValue": "${VALUE}",
    "nodeType": "@id",
    "datasetId": "@none"
}
EOF

cat << EOF > ${ATTRIBUTES_PROPERTY2}
{
    "id": "${IDSTATE2}",
    "entityId": "${URN4}",
    "name": "${STATE}",
    "type": "${PROPERTY}",
    "attributeValue": "${VALUE2}",
    "nodeType": "@value",
    "valueType": "http://www.w3.org/2001/XMLSchema#string",
    "index": 0
}
EOF

cat << EOF > ${ATTRIBUTES_RELATIONSHIP}
{
    "id": "${IDREL}",
    "entityId": "${URN2}",
    "name": "${REL}",
    "type": "${RELATIONSHIP}",
    "attributeValue": "${URN3}",
    "nodeType": "@id",
    "index": 0
}
EOF

cat << EOF > ${ENTITY}
{
    "id": "${URN}",
    "type": "https://example.com/type"
}
EOF

# send data to kafka bridge
# $1: file to send
# $2: kafka topic
send_to_kafka_bridge() {
    tr -d '\n' <"$1" | kafkacat -P -t "$2" -b "${KAFKA_BOOTSTRAP}"
}

# receive datapoints
# $1: payload to post
get_datapoints() {
    urn=$1
    targetfile=$2
    echo 'select json_agg(t) from public.attributes as t where t."entityId" = ' \'"$urn"\' ';' | \
        PGPASSWORD=${POSTGRES_PASSWORD} psql -t -h localhost -U ${POSTGRES_USERNAME} -d ${POSTGRES_DATABASE} -A | \
        jq -S 'map(del(.modifiedAt, .observedAt))' >"$targetfile"
}


# receive entity datapoints
# $1: payload to post
get_entity_datapoints() {
    urn=$1
    targetfile=$2
    echo 'select json_agg(t) from public.entities as t where t."id" = ' \'"$urn"\' ';' | \
        PGPASSWORD=${POSTGRES_PASSWORD} psql -t -h localhost -U ${POSTGRES_USERNAME} -d ${POSTGRES_DATABASE} -A | \
        jq -S 'map(del(.modifiedAt, .observedAt))' >"$targetfile"
}

# check s
# $1: retrieved tsdb objects
# $2: expected tsdb objects
check_tsdb_sample1() {
    URN=$2
    cat << EOF | diff "$1" - >&3
[
  {
    "attributeId": "https://industry-fusion.com/types/v0.9/state",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "$URN",
    "id": "$IDSTATE",
    "lang": null,
    "nodeType": "@id",
    "parentId": null,
    "unitType": null,
    "value": "state",
    "valueType": null
  }
]
EOF
}

# check s
# $1: retrieved tsdb objects
# $2: expected tsdb objects
check_tsdb_sample2() {
    URN=$2
    cat << EOF | diff "$1" - >&3
[
  {
    "attributeId": "https://industry-fusion.com/types/v0.9/relationship",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Relationship",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "$URN",
    "id": "$IDREL",
    "lang": null,
    "nodeType": "@id",
    "parentId": null,
    "unitType": null,
    "value": "$URN3",
    "valueType": null
  }
]
EOF
}

check_tsdb_sample3() {
    URN=$2
    cat << EOF | diff "$1" - >&3
[
  {
    "attributeId": "https://industry-fusion.com/types/v0.9/state",
    "attributeType": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "@none",
    "deleted": false,
    "entityId": "$URN4",
    "id": "$IDSTATE2",
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


# check entity
# $1: retrieved tsdb objects
# $2: expected tsdb objects
check_tsdb_sample4() {
    URN=$2
    cat << EOF | diff "$1" - >&3
[
  {
    "deleted": false,
    "id": "$URN",
    "type": "https://example.com/type"
  }
]
EOF
}

setup() {
    # shellcheck disable=SC2086
    [ "$DEBUG" = "true" ] || (exec ${SUDO} kubefwd -n ${IFFNAMESPACE} -l "app.kubernetes.io/name in (kafka)" svc) &
    (exec kubectl -n ${IFFNAMESPACE}  port-forward pod/${POSTGRES_POD} 5432:5432) &
    echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    sleep 3
}
teardown(){
    echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    [ "$DEBUG" = "true" ] || ${SUDO} killall kubefwd
    killall kubectl || echo "Could not kill port-forwarder. But ok."
}

@test "verify timescaledb-bridge is forwarding iri Property" {
    $SKIP
    echo "# Sending property to Kafka"
    send_to_kafka_bridge ${ATTRIBUTES_PROPERTY} ${ATTRIBUTES_TOPIC}
    sleep 2
    echo "# requesting rows with entityId=$URN"
    get_datapoints "$URN" "$TSDB_RESULT"
    echo "# Now checking result."
    run check_tsdb_sample1 "$TSDB_RESULT" "$URN"
    [ "$status" -eq 0 ]
}

@test "verify timescaledb-bridge is forwarding Relationship" {
    $SKIP
    echo "# Sending relationship to Kafka"
    send_to_kafka_bridge ${ATTRIBUTES_RELATIONSHIP} ${ATTRIBUTES_TOPIC}
    sleep 2
    get_datapoints "$URN2" "$TSDB_RESULT"
    echo "# Now checking result."
    run check_tsdb_sample2 "$TSDB_RESULT" "$URN2"
    [ "$status" -eq "0" ]
}

@test "verify timescaledb-bridge is forwarding value Property" {
    $SKIP
    echo "# Sending property to Kafka"
    send_to_kafka_bridge ${ATTRIBUTES_PROPERTY2} ${ATTRIBUTES_TOPIC}
    sleep 2
    get_datapoints "$URN4" "${TSDB_RESULT}"
    cat "${TSDB_RESULT}"
    echo "# Now checking result."
    run check_tsdb_sample3 "$TSDB_RESULT" "$URN4"
    [ "$status" -eq "0" ]
}

@test "verify timescaledb-bridge is forwarding entity" {
    $SKIP
    echo "# Sending property to Kafka"
    send_to_kafka_bridge ${ENTITY} ${ENTITIES_TOPIC}
    sleep 2
    get_entity_datapoints "$URN" "${TSDB_RESULT}"
    cat "${TSDB_RESULT}"
    echo "# Now checking result."
    run check_tsdb_sample4 "$TSDB_RESULT" "$URN"
    [ "$status" -eq "0" ]
}