#!/usr/bin/env bats

# shellcheck disable=SC2005

DEBUG=${DEBUG:-false}
SKIP=
NAMESPACE=iff
USER_SECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAK_URL=http://keycloak.local/auth/realms
PLASMACUTTER_ID=urn:plasmacutter-test:12345
PLASMACUTTER_ID_2=urn:plasmacutter-test:123456
CUTTER=/tmp/CUTTER
CUTTER_MERGE=/tmp/CUTTER_MERGE
CUTTER_QUERY=/tmp/CUTTER_QUERY
CUTTER_BATCH=/tmp/CUTTER_BATCH
CUTTER_MERGE_BATCH=/tmp/CUTTER_MERGE_BATCH

# Function definitions
get_password() {
    kubectl -n ${NAMESPACE} get ${USER_SECRET} -o jsonpath='{.data.password}' | base64 -d
}

get_token() {
    curl -d "client_id=${CLIENT_ID}" -d "username=${USER}" -d "password=$password" -d 'grant_type=password' "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" | jq ".access_token" | tr -d '"'
}

create_ngsild() {
    curl -vv -X POST -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entities/ -H "Content-Type: application/ld+json"
}

create_ngsild_batch() {
    curl -vv -X POST -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entityOperations/upsert -H "Content-Type: application/ld+json"
}

delete_ngsild() {
    curl -vv -X DELETE -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Content-Type: application/ld+json"
}

merge_patch_ngsild() {
    curl -vv -X PATCH -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entities/"$3" -H "Content-Type: application/ld+json"
}

merge_patch_ngsild_batch() {
    curl -vv -X POST -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entityOperations/merge -H "Content-Type: application/ld+json"
}

query_ngsild() {
    curl -s -X GET -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Accept: application/json"
}

setup() {
    if [ "$DEBUG" != "true" ]; then
        echo "This test works only in debug mode. Set DEBUG=true."
        exit 1
    fi
}

# Create CUTTER file
cat << EOF > ${CUTTER}
{
 "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
 "id": "${PLASMACUTTER_ID}",
 "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test",
 "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "ON",
    "unitCode": "Binary"
 },
 "https://industry-fusion.com/types/v0.9/hasFilter": {
    "type": "Relationship",
    "object": "urn:filter-test:12345"
  }
}
EOF

# Update the entity with a new state value
cat << EOF > ${CUTTER_MERGE}
{
  "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
  "https://industry-fusion.com/types/v0.9/hasFilter": {
    "type": "Relationship",
    "object": "urn:ngsi-ld:null"
  },
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFF"
  }
}
EOF

# Create 2 cutters
cat << EOF > ${CUTTER_BATCH}
[
{
 "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
 "id": "${PLASMACUTTER_ID}",
 "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test",
 "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "ON",
    "unitCode": "Binary"
 },
 "https://industry-fusion.com/types/v0.9/hasFilter": {
    "type": "Relationship",
    "object": "urn:filter-test:12345"
  }
},
{
 "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
 "id": "${PLASMACUTTER_ID_2}",
 "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test",
 "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "ONN",
    "unitCode": "Binary"
 },
 "https://industry-fusion.com/types/v0.9/hasFilter": {
    "type": "Relationship",
    "object": "urn:filter-test:12346"
  }
}
]
EOF

# Run merge on two cutters
cat << EOF > ${CUTTER_MERGE_BATCH}
[
{
 "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
 "id": "${PLASMACUTTER_ID}",
 "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OF"
 }
},
{
 "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
 "id": "${PLASMACUTTER_ID_2}",
 "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFF"
 },
 "https://industry-fusion.com/types/v0.9/hasFilter": {
    "type": "Relationship",
    "object": "urn:filter-test:12347"
  }
}
]
EOF

compare_merge_patch() {
    cat << EOF | jq | diff "$1" - >&3
{
  "id": "${PLASMACUTTER_ID}",
  "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test",
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFF",
    "unitCode": "Binary"
  }
}
EOF
}

compare_merge_patch_batch_second() {
    cat << EOF | jq | diff "$1" - >&3
{
 "id": "${PLASMACUTTER_ID_2}",
 "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test",
 "https://industry-fusion.com/types/v0.9/hasFilter": {
    "type": "Relationship",
    "object": "urn:filter-test:12347"
  },
 "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFF",
    "unitCode": "Binary"
 }  
}
EOF
}

@test "verify merge patch behaviour" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    create_ngsild "$token" "$CUTTER"
    sleep 2
    merge_patch_ngsild "$token" "$CUTTER_MERGE" "$PLASMACUTTER_ID"
    sleep 2
    query_ngsild "$token" "$PLASMACUTTER_ID" | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${CUTTER_QUERY}
    delete_ngsild "$token" "$PLASMACUTTER_ID"

    run compare_merge_patch ${CUTTER_QUERY}
    [ "$status" -eq 0 ]
}

@test "verify merge patch behaviour with batch processing" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    delete_ngsild "$token" "$PLASMACUTTER_ID_2" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    create_ngsild_batch "$token" "$CUTTER_BATCH"
    sleep 2
    merge_patch_ngsild_batch "$token" "$CUTTER_MERGE_BATCH"
    sleep 2
    query_ngsild "$token" "$PLASMACUTTER_ID_2" | jq 'del( ."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn" )' >${CUTTER_QUERY}
    delete_ngsild "$token" "$PLASMACUTTER_ID"
    delete_ngsild "$token" "$PLASMACUTTER_ID_2"

    run compare_merge_patch_batch_second ${CUTTER_QUERY}
    [ "$status" -eq 0 ]
}
