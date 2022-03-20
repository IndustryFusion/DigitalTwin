#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi

NAMESPACE=iff
USERSECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAKURL=http://keycloak.local/auth/realms
UPSERT_FILTER=/tmp/UPSERT_FILTER
UPSERT_FILTER_OVERWRITE=/tmp/UPSERT_FILTER_OVERWRITE
UPSERT_FILTER_NON_OVERWRITE=/tmp/UPSERT_FILTER_NON_OVERWRITE
UPSERT_2_ENTITIES=/tmp/UPSERT_2_ENTITIES
UPDATE_FILTER=/tmp/UPDATE_FILTER
UPDATE_FILTER_NO_OVERWRITE=/tmp/UPDATE_FILTER_NO_OVERWRITE
UPDATE_2_ENTITIES=/tmp/UPDATE_2_ENTITIES
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
KAFKACAT_NGSILD_UPDATES_TOPIC=iff.ngsildUpdates
FILTER_ID=urn:filter-test:12345
CUTTER_ID=urn:plasmacutter-test:12345
RECEIVED_ENTITY=/tmp/RECEIVED_ENTITY

cat << EOF | tr -d '\n' > ${UPSERT_FILTER}
{
    "op": "upsert",
    "overwriteOrReplace": "false",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "https://industry-fusion.com/types/v0.9/filter",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "value": "0.9"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:12345"
        }
      }
    ]
}
EOF

cat << EOF | tr -d '\n' > ${UPSERT_FILTER_OVERWRITE}
{
    "op": "upsert",
    "overwriteOrReplace": "true",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "https://industry-fusion.com/types/v0.9/filter",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "value": "0.1"
        },
        "https://industry-fusion.com/types/v0.9/strength2": {
          "type": "Property",
          "value": "0.1"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:22345"
        }
      }
    ]
}
EOF

cat << EOF | tr -d '\n' > ${UPSERT_FILTER_NON_OVERWRITE}
{
    "op": "upsert",
    "overwriteOrReplace": false,
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "https://industry-fusion.com/types/v0.9/filter",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "value": "0.1"
        },
        "https://industry-fusion.com/types/v0.9/strength2": {
          "type": "Property",
          "value": "0.5"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:22345"
        }
      }
    ]
}
EOF

cat << EOF | tr -d '\n' > ${UPDATE_FILTER}
{
    "op": "update",
    "overwriteOrReplace": "true",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "https://industry-fusion.com/types/v0.9/filter",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "value": "0.5"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:22345"
        }
      }
    ]
}
EOF

cat << EOF | tr -d '\n' > ${UPDATE_FILTER_NO_OVERWRITE}
{
    "op": "update",
    "overwriteOrReplace": false,
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "https://industry-fusion.com/types/v0.9/filter",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "ON"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "value": "0.75"
        },
        "https://industry-fusion.com/types/v0.9/strength2": {
          "type": "Property",
          "value": "1.0"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:72345"
        }
      }
    ]
}
EOF

cat << EOF | tr -d '\n' > ${UPSERT_2_ENTITIES}
{
    "op": "upsert",
    "overwriteOrReplace": "false",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "https://industry-fusion.com/types/v0.9/filter",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "value": "0.9"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:12345"
        }
      },
      {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${CUTTER_ID}",
        "type": "https://industry-fusion.com/types/v0.9/plasmacutter",
        "https://industry-fusion.com/types/v0.9/state": {
        "type": "Property",
        "value": "OFF"
        },
        "https://industry-fusion.com/types/v0.9/hasWorkpiece": {
        "type": "Relationship",
        "object": "urn:workpiece-test:12345"
        },
        "https://industry-fusion.com/types/v0.9/hasFilter": {
        "type": "Relationship",
        "object": "urn:filter-test:12345"
        }
      }
    ]
}
EOF

cat << EOF | tr -d '\n' > ${UPDATE_2_ENTITIES}
{
    "op": "update",
    "overwriteOrReplace": "true",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "https://industry-fusion.com/types/v0.9/filter",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "value": "1.0"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:22345"
        }
      },
      {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${CUTTER_ID}",
        "type": "https://industry-fusion.com/types/v0.9/plasmacutter",
        "https://industry-fusion.com/types/v0.9/state": {
        "type": "Property",
        "value": "ON"
        },
        "https://industry-fusion.com/types/v0.9/hasWorkpiece": {
        "type": "Relationship",
        "object": "urn:workpiece-test:22345"
        },
        "https://industry-fusion.com/types/v0.9/hasFilter": {
        "type": "Relationship",
        "object": "urn:filter-test:22345"
        }
      }
    ]
}
EOF


# compare entity with reference
# $1: file to compare with
compare_inserted_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "https://industry-fusion.com/types/v0.9/filter",
  "https://industry-fusion.com/types/v0.9/hasCartridge" : {
    "type" : "Relationship",
    "object" : "urn:filterCartridge-test:12345"
  },
  "https://industry-fusion.com/types/v0.9/state" : {
    "type" : "Property",
    "value" : "OFFF"
  },
  "https://industry-fusion.com/types/v0.9/strength" : {
    "type" : "Property",
    "value" : "0.9"
  },
  "@context" : [ "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld" ]
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_upserted_overwritten_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "https://industry-fusion.com/types/v0.9/filter",
  "https://industry-fusion.com/types/v0.9/hasCartridge" : {
    "type" : "Relationship",
    "object" : "urn:filterCartridge-test:22345"
  },
  "https://industry-fusion.com/types/v0.9/state" : {
    "type" : "Property",
    "value" : "OFF"
  },
  "https://industry-fusion.com/types/v0.9/strength" : {
    "type" : "Property",
    "value" : "0.1"
  },
  "https://industry-fusion.com/types/v0.9/strength2": {
    "type": "Property",
    "value": "0.1"
  },
  "@context" : [ "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld" ]
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_upserted_non_overwritten_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "https://industry-fusion.com/types/v0.9/filter",
  "https://industry-fusion.com/types/v0.9/hasCartridge" : {
    "type" : "Relationship",
    "object" : "urn:filterCartridge-test:22345"
  },
  "https://industry-fusion.com/types/v0.9/state" : {
    "type" : "Property",
    "value" : "OFF"
  },
  "https://industry-fusion.com/types/v0.9/strength" : {
    "type" : "Property",
    "value" : "0.1"
  },
  "https://industry-fusion.com/types/v0.9/strength2": {
    "type": "Property",
    "value": "0.5"
  },
  "@context" : [ "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld" ]
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_updated_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "https://industry-fusion.com/types/v0.9/filter",
  "https://industry-fusion.com/types/v0.9/hasCartridge" : {
    "type" : "Relationship",
    "object" : "urn:filterCartridge-test:22345"
  },
  "https://industry-fusion.com/types/v0.9/state" : {
    "type" : "Property",
    "value" : "OFF"
  },
  "https://industry-fusion.com/types/v0.9/strength" : {
    "type" : "Property",
    "value" : "0.5"
  },
  "@context" : [ "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld" ]
}
EOF
}


# compare entity with reference
# $1: file to compare with
compare_updated_no_overwrite_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "https://industry-fusion.com/types/v0.9/filter",
  "https://industry-fusion.com/types/v0.9/hasCartridge" : {
    "type" : "Relationship",
    "object" : "urn:filterCartridge-test:12345"
  },
  "https://industry-fusion.com/types/v0.9/state" : {
    "type" : "Property",
    "value" : "OFFF"
  },
  "https://industry-fusion.com/types/v0.9/strength" : {
    "type" : "Property",
    "value" : "0.9"
  },
  "https://industry-fusion.com/types/v0.9/strength2" : {
    "type" : "Property",
    "value" : "1.0"
  },
  "@context" : [ "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld" ]
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_cutter_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id": "${CUTTER_ID}",
  "type": "https://industry-fusion.com/types/v0.9/plasmacutter",
  "https://industry-fusion.com/types/v0.9/hasFilter": {
    "type": "Relationship",
    "object": "urn:filter-test:12345"
  },
  "https://industry-fusion.com/types/v0.9/hasWorkpiece": {
    "type": "Relationship",
    "object": "urn:workpiece-test:12345"
  },
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFF"
  },
  "@context": [
    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
  ]
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_update_cutter_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id": "${CUTTER_ID}",
  "type": "https://industry-fusion.com/types/v0.9/plasmacutter",
  "https://industry-fusion.com/types/v0.9/hasFilter": {
    "type": "Relationship",
    "object": "urn:filter-test:22345"
  },
  "https://industry-fusion.com/types/v0.9/hasWorkpiece": {
    "type": "Relationship",
    "object": "urn:workpiece-test:22345"
  },
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "ON"
  },
  "@context": [
    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
  ]
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_updated_filter_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "https://industry-fusion.com/types/v0.9/filter",
  "https://industry-fusion.com/types/v0.9/hasCartridge" : {
    "type" : "Relationship",
    "object" : "urn:filterCartridge-test:22345"
  },
  "https://industry-fusion.com/types/v0.9/state" : {
    "type" : "Property",
    "value" : "OFF"
  },
  "https://industry-fusion.com/types/v0.9/strength" : {
    "type" : "Property",
    "value" : "1.0"
  },
  "@context" : [ "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld" ]
}
EOF
}

get_password() {
    kubectl -n ${NAMESPACE} get ${USERSECRET} -o jsonpath='{.data.password}' 2>/dev/null| base64 -d
}
get_token() {
    curl -d "client_id=${CLIENT_ID}" -d "username=${USER}" -d "password=$password" -d 'grant_type=password' "${KEYCLOAKURL}/${NAMESPACE}/protocol/openid-connect/token" 2>/dev/null| jq ".access_token"| tr -d '"'
}

# get ngsild entity
# $1: auth token
# $2: id of entity
get_ngsild() {
    curl -X GET -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Content-Type: application/ld+json" 2>/dev/null
}

# deletes ngsild entity
# $1: auth token
# $2: id of entity to delete
delete_ngsild() {
    curl -X DELETE -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Content-Type: application/ld+json" 2>/dev/null
}

setup() {
    # shellcheck disable=SC2086
    (exec ${SUDO} kubefwd -n iff -l app.kubernetes.io/name=kafka svc  >/dev/null 2>&1) &
    echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    sleep 2
}
teardown(){
    echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    ${SUDO} killall kubefwd
}


@test "verify ngsild-update bridge is inserting ngsi-ld entitiy" {

    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_inserted_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is upserting and overwriting ngsi-ld entitiy" {
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    run compare_inserted_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER_OVERWRITE}
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    run compare_upserted_overwritten_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    delete_ngsild "${token}" ${FILTER_ID}
}

@test "verify ngsild-update bridge is upserting and non-overwriting ngsi-ld entitiy" {
    # This test is not working properlty the entityOperations/upsert?options=update should only update existing
    # property not create new ones
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    run compare_inserted_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER_NON_OVERWRITE}
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    run compare_upserted_non_overwritten_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    delete_ngsild "${token}" ${FILTER_ID}
}

@test "verify ngsild-update bridge is updating ngsi-ld entitiy" {

    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPDATE_FILTER}
    echo "# Sent update object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq  'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_updated_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is updating with noOverwrite option ngsi-ld entitiy" {
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPDATE_FILTER_NO_OVERWRITE} 
    echo "# Sent update object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_updated_no_overwrite_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is upserting 2 entities" {
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_2_ENTITIES}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_inserted_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    get_ngsild "${token}" ${CUTTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${CUTTER_ID}
    run compare_cutter_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is updating 2 entities" {
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_2_ENTITIES} 
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPDATE_2_ENTITIES}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_updated_filter_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    get_ngsild "${token}" ${CUTTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${CUTTER_ID}
    run compare_update_cutter_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}
