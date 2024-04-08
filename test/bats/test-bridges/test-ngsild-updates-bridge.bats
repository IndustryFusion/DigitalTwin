#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
SKIP= # set =skip to skip all test (and only comment out $SKIP from the test you are interested in)
NAMESPACE=iff
USERSECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAKURL=http://keycloak.local/auth/realms
UPSERT_FILTER=/tmp/UPSERT_FILTER
UPSERT_FILTER_TIMESTAMPED=/tmp/UPSERT_FILTER_TIMESTAMPED
UPSERT_FILTER_OVERWRITE=/tmp/UPSERT_FILTER_OVERWRITE
UPSERT_FILTER_NON_OVERWRITE=/tmp/UPSERT_FILTER_NON_OVERWRITE
UPSERT_2_ENTITIES=/tmp/UPSERT_2_ENTITIES
UPSERT_2_ENTITIES2=/tmp/UPSERT_2_ENTITIES2
UPDATE_FILTER=/tmp/UPDATE_FILTER
UPDATE_FILTER_NO_OVERWRITE=/tmp/UPDATE_FILTER_NO_OVERWRITE
UPDATE_2_ENTITIES=/tmp/UPDATE_2_ENTITIES
UPDATE_2_ENTITIES2=/tmp/UPDATE_2_ENTITIES2
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
KAFKACAT_NGSILD_UPDATES_TOPIC=iff.ngsild-updates
FILTER_ID=urn:filter-test:12345
CUTTER_ID=urn:plasmacutter-test:12345
RECEIVED_ENTITY=/tmp/RECEIVED_ENTITY
FILTER_TYPE=https://industry-fusion.com/types/v0.9/filter_test
PLASMACUTTER_TYPE=https://industry-fusion.com/types/v0.9/plasmacutter_test
cat << EOF | tr -d '\n' > ${UPSERT_FILTER}
{
    "op": "upsert",
    "overwriteOrReplace": "false",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "${FILTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "datasetId": "https://example.com/source1",
          "type": "Property",
          "value": "0.9",
          "unitCode": "unitCode"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "datasetId": "@none",
          "object": "urn:filterCartridge-test:12345"
        }
      }
    ]
}
EOF

cat << EOF | tr -d '\n' > ${UPSERT_FILTER_TIMESTAMPED}
{
    "op": "upsert",
    "overwriteOrReplace": "false",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "${FILTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFFF",
          "observedAt": "2024-01-08T01:01:28.172Z"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "datasetId": "https://example.com/source1",
          "value": "0.9",
          "observedAt": "2024-01-08T01:01:28.512Z"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "datasetId": "https://example.com/source2",
          "object": "urn:filterCartridge-test:12345",
          "observedAt": "2024-01-08T01:02:28.0Z"
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
        "type": "${FILTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "value": "0.1",
          "datasetId": "https://example.com/source1"
        },
        "https://industry-fusion.com/types/v0.9/strength2": {
          "type": "Property",
          "value": "0.1",
          "datasetId": "@none"
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:22345",
          "datasetId": "https://example.com/source3"
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
        "type": "${FILTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFF",
          "datasetId": "@none"
        },
        "https://industry-fusion.com/types/v0.9/strength": [
          {
          "type": "Property",
          "datasetId": "https://example.com/source1",
          "value": "0.1"
          },
          {
            "type": "Property",
            "value": "0.9"
          }
        ],
        "https://industry-fusion.com/types/v0.9/strength2": {
          "type": "Property",
          "value": "0.5",
          "datasetId": "https://example.com/source4"
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
        "type": "${FILTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFF"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "datasetId": "https://example.com/source1",
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
        "type": "${FILTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "datasetId": "@none",
          "value": "ON"
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "datasetId": "https://example.com/source1",
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

get_iso_timestamp(){
  echo '"'"$(date +"%Y-%m-%dT%T.%3NZ" -u)"'"'
}

timestamp_upsert_2_entities(){
  timestamp=$(get_iso_timestamp)
  cat << EOF | tr -d '\n' > ${UPSERT_2_ENTITIES}
{
    "op": "upsert",
    "overwriteOrReplace": "false",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "${FILTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFFF",
          "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "datasetId": "https://example.com/source1",
          "value": "0.9",
          "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:12345",
          "observedAt": ${timestamp}
        }
      },
      {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${CUTTER_ID}",
        "type": "${PLASMACUTTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
        "type": "Property",
        "value": "OFF",
        "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasWorkpiece": {
        "type": "Relationship",
        "object": "urn:workpiece-test:12345",
        "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasFilter": {
        "type": "Relationship",
        "object": "urn:filter-test:12345",
        "observedAt": ${timestamp}
        }
      }
    ]
}
EOF
}

timestamp_upsert_2_entities2(){
  timestamp=$(get_iso_timestamp)
  cat << EOF | tr -d '\n' > ${UPSERT_2_ENTITIES2}
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
          "value": "O",
          "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "datasetId": "https://example.com/source1",
          "value": "0.422",
          "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:02345",
          "observedAt": ${timestamp}
        }
      },
      {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${CUTTER_ID}",
        "type": "${PLASMACUTTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
        "type": "Property",
        "value": "OFFON",
        "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasWorkpiece": {
        "type": "Relationship",
        "object": "urn:workpiece-test:02345",
        "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasFilter": {
        "type": "Relationship",
        "object": "urn:filter-test:02345",
        "observedAt": ${timestamp}
        }
      }
    ]
}
EOF
}

timestamp_update_2_entities(){
  timestamp=$(get_iso_timestamp)
  cat << EOF | tr -d '\n' > ${UPDATE_2_ENTITIES}
{
    "op": "update",
    "overwriteOrReplace": "true",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "${FILTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OFF",
          "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "datasetId": "https://example.com/source1",
          "value": "1.0",
          "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:22345",
          "observedAt": ${timestamp}
        }
      },
      {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${CUTTER_ID}",
        "type": "${PLASMACUTTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
        "type": "Property",
        "value": "ON",
        "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasWorkpiece": {
        "type": "Relationship",
        "object": "urn:workpiece-test:22345",
        "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasFilter": {
        "type": "Relationship",
        "object": "urn:filter-test:22345",
        "observedAt": ${timestamp}
        }
      }
    ]
}
EOF
}

timestamp_update_2_entities2(){
  timestamp=$(get_iso_timestamp)
  cat << EOF | tr -d '\n' > ${UPDATE_2_ENTITIES2}
{
    "op": "update",
    "overwriteOrReplace": "true",
    "entities": [
        {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${FILTER_ID}",
        "type": "${FILTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
          "type": "Property",
          "value": "OF",
          "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/strength": {
          "type": "Property",
          "datasetId": "https://example.com/source1",
          "value": "1.0",
          "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasCartridge": {
          "type": "Relationship",
          "object": "urn:filterCartridge-test:32345",
          "observedAt": ${timestamp}
        }
      },
      {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
        "id": "${CUTTER_ID}",
        "type": "${PLASMACUTTER_TYPE}",
        "https://industry-fusion.com/types/v0.9/state": {
        "type": "Property",
        "value": "ONN",
        "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasWorkpiece": {
        "type": "Relationship",
        "object": "urn:workpiece-test:32345",
        "observedAt": ${timestamp}
        },
        "https://industry-fusion.com/types/v0.9/hasFilter": {
        "type": "Relationship",
        "object": "urn:filter-test:22345",
        "observedAt": ${timestamp}
        }
      }
    ]
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_inserted_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "${FILTER_TYPE}",
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
    "datasetId": "https://example.com/source1",
    "value" : "0.9"
  }
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_inserted_entity_timestamped() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id": "urn:filter-test:12345",
  "type": "https://industry-fusion.com/types/v0.9/filter_test",
  "https://industry-fusion.com/types/v0.9/hasCartridge": {
    "type": "Relationship",
    "datasetId": "https://example.com/source2",
    "object": "urn:filterCartridge-test:12345",
    "observedAt": "2024-01-08T01:02:28.0Z"
  },
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFFF",
    "observedAt": "2024-01-08T01:01:28.172Z"
  },
  "https://industry-fusion.com/types/v0.9/strength": {
    "type": "Property",
    "datasetId": "https://example.com/source1",
    "value": "0.9",
    "observedAt": "2024-01-08T01:01:28.512Z"
  }
}

EOF
}

# compare entity with reference
# $1: file to compare with
compare_upserted_overwritten_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "${FILTER_TYPE}",
  "https://industry-fusion.com/types/v0.9/hasCartridge" : {
    "type" : "Relationship",
    "datasetId": "https://example.com/source3",
    "object" : "urn:filterCartridge-test:22345"
  },
  "https://industry-fusion.com/types/v0.9/state" : {
    "type" : "Property",
    "value" : "OFF"
  },
  "https://industry-fusion.com/types/v0.9/strength" : {
    "type" : "Property",
    "datasetId": "https://example.com/source1",
    "value" : "0.1"
  },
  "https://industry-fusion.com/types/v0.9/strength2": {
    "type": "Property",
    "value": "0.1"
  }
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_upserted_non_overwritten_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "${FILTER_TYPE}",
  "https://industry-fusion.com/types/v0.9/hasCartridge" : {
    "type" : "Relationship",
    "object" : "urn:filterCartridge-test:22345"
  },
  "https://industry-fusion.com/types/v0.9/state" : {
    "type" : "Property",
    "value" : "OFF"
  },
  "https://industry-fusion.com/types/v0.9/strength" : [
    {
      "type" : "Property",
      "datasetId": "https://example.com/source1",
      "value" : "0.1"
    },
    {
      "type": "Property",
      "value": "0.9"
    }

  ],
  "https://industry-fusion.com/types/v0.9/strength2": {
    "type": "Property",
    "datasetId": "https://example.com/source4",
    "value": "0.5"
  }
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_updated_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "${FILTER_TYPE}",
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
    "datasetId": "https://example.com/source1",
    "value" : "0.5"
  }
}
EOF
}


# compare entity with reference
# $1: file to compare with
compare_updated_no_overwrite_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "${FILTER_TYPE}",
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
    "datasetId": "https://example.com/source1",
    "value" : "0.9"
  },
  "https://industry-fusion.com/types/v0.9/strength2" : {
    "type" : "Property",
    "value" : "1.0"
  }
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_cutter_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id": "${CUTTER_ID}",
  "type": "${PLASMACUTTER_TYPE}",
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
  }
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_update_cutter_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id": "${CUTTER_ID}",
  "type": "${PLASMACUTTER_TYPE}",
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
  }
}
EOF
}

# compare entity with reference
# $1: file to compare with
compare_updated_filter_entity() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id" : "${FILTER_ID}",
  "type" : "${FILTER_TYPE}",
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
    "datasetId": "https://example.com/source1",
    "value" : "1.0"
  }
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

# deletes ngsild entity
# $1: auth token
# $2: id of entity to delete
try_delete_ngsild() {
    curl -X DELETE -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Content-Type: application/ld+json" 2>/dev/null || true
}

setup() {
    # shellcheck disable=SC2086
    [ $DEBUG = "true" ] || (exec ${SUDO} kubefwd -n iff -l app.kubernetes.io/name=kafka svc  >/dev/null 2>&1) &
    echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    sleep 2
}
teardown(){
    echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    [ $DEBUG = "true" ] || ${SUDO} killall kubefwd
}


@test "verify ngsild-update bridge is inserting ngsi-ld entitiy" {
    $SKIP
    password=$(get_password)
    # shellcheck disable=SC2030
    token=$(get_token)
    try_delete_ngsild "${token}" ${FILTER_ID}
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' | jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_inserted_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is upserting and overwriting ngsi-ld entitiy" {
    $SKIP
    password=$(get_password)
    # shellcheck disable=SC2030
    token=$(get_token)
    try_delete_ngsild "${token}" ${FILTER_ID}
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)'  >${RECEIVED_ENTITY}
    run compare_inserted_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER_OVERWRITE}
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)'  >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_upserted_overwritten_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is upserting and non-overwriting ngsi-ld entitiy" {
    $SKIP
    # This test is not working properlty the entityOperations/upsert?options=update should only update existing
    # property but Quarkus
    # Currently the test is not changing the object. We leave it in in case in future this API is working correctly
    # And will be detected by this.
    # Update: In Scorpio Version 3.0.11 the program behaviour changed again but it is still not quite aligned
    # with the NGSI-LD documentations, therefore we tweaked the test case to work with the current behaviour.
    # When this test fails in the future, we will know that the behaviour has changed again.
    password=$(get_password)
    # shellcheck disable=SC2030
    token=$(get_token)
    delete_ngsild "${token}" ${FILTER_ID}
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2

    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    run compare_inserted_entity ${RECEIVED_ENTITY}
    rm ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER_NON_OVERWRITE}
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_upserted_non_overwritten_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is updating ngsi-ld entitiy" {
    $SKIP
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPDATE_FILTER}
    echo "# Sent update object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_updated_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is updating with noOverwrite option ngsi-ld entitiy" {
    $SKIP
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    password=$(get_password)
    token=$(get_token)
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPDATE_FILTER_NO_OVERWRITE} 
    echo "# Sent update object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_updated_no_overwrite_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is upserting 2 entities" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "${token}" ${CUTTER_ID} || echo "${CUTTER_ID} already deleted"
    delete_ngsild "${token}" ${FILTER_ID} || echo "${FILTER_ID} already deleted"
    timestamp_upsert_2_entities
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_2_ENTITIES}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2  
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_inserted_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    get_ngsild "${token}" ${CUTTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${CUTTER_ID}
    run compare_cutter_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is updating 2 entities" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "${token}" ${CUTTER_ID} || echo "${CUTTER_ID} already deleted"
    delete_ngsild "${token}" ${FILTER_ID} || echo "${FILTER_ID} already deleted"
    timestamp_upsert_2_entities
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_2_ENTITIES}
    timestamp_update_2_entities
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPDATE_2_ENTITIES}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_updated_filter_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    get_ngsild "${token}" ${CUTTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${CUTTER_ID}
    run compare_update_cutter_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is updating many entities in order" {
    $SKIP
    password=$(get_password)
    # shellcheck disable=SC2030
    token=$(get_token)
    delete_ngsild "${token}" ${CUTTER_ID} || echo "${CUTTER_ID} already deleted"
    delete_ngsild "${token}" ${FILTER_ID} || echo "${FILTER_ID} already deleted"
    timestamp_upsert_2_entities
    timestamp_upsert_2_entities2
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_2_ENTITIES}
    timestamp_update_2_entities
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPDATE_2_ENTITIES}
    timestamp_upsert_2_entities2
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_2_ENTITIES2}
    timestamp_update_2_entities2
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPDATE_2_ENTITIES2}
    timestamp_update_2_entities
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPDATE_2_ENTITIES}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${FILTER_ID}
    run compare_updated_filter_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
    get_ngsild "${token}" ${CUTTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )'| jq 'del(..|.observedAt?)' >${RECEIVED_ENTITY}
    delete_ngsild "${token}" ${CUTTER_ID}
    run compare_update_cutter_entity ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}

@test "verify ngsild-update bridge is inserting ngsi-ld entitiy with right timestamp" {
    $SKIP
    password=$(get_password)
    # shellcheck disable=SC2030
    token=$(get_token)
    delete_ngsild "${token}" ${FILTER_ID}
    delete_ngsild "${token}" ${CUTTER_ID}
    kafkacat -P -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${UPSERT_FILTER_TIMESTAMPED}
    echo "# Sent upsert object to ngsi-ld-updates-bridge, wait some time to let it settle"
    sleep 2
    get_ngsild "${token}" ${FILTER_ID} | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${RECEIVED_ENTITY}
    run compare_inserted_entity_timestamped ${RECEIVED_ENTITY}
    [ "$status" -eq 0 ]
}