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
CUTTER=/tmp/CUTTER
CUTTER_MERGE=/tmp/CUTTER_MERGE
CUTTER_QUERY=/tmp/CUTTER_QUERY

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

delete_ngsild() {
    curl -vv -X DELETE -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Content-Type: application/ld+json"
}

merge_patch_ngsild() {
    curl -vv -X PATCH -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entities/"$3" -H "Content-Type: application/ld+json"
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
    "unit": "Binary"
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
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFF"
  },
  "https://industry-fusion.com/types/v0.9/hasFilter": {
    "type": "Relationship",
    "object": "urn:ngsi-ld:null"
   }
}
EOF

compare_merge_patch() {
    # Filter out observedAt and kafkaSyncOn from the input file
    filtered_input=$(jq 'del(.."observedAt", .."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn")' "$1")

    # Create the expected output, filtering out the same keys
    expected_output=$(cat << EOF | jq 'del(.."observedAt", .."https://industry-fusion.com/types/v0.9/metadata/kafkaSyncOn")'
{
  "id": "${PLASMACUTTER_ID}",
  "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test",
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFF",
    "unit": "Binary"
  }
}
EOF
)

    # Perform the diff on the filtered JSON objects
    diff <(echo "$filtered_input" | jq -S) <(echo "$expected_output" | jq -S) >&3
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
    query_ngsild "$token" "$PLASMACUTTER_ID" >${CUTTER_QUERY}
    delete_ngsild "$token" "$PLASMACUTTER_ID"

    run compare_merge_patch ${CUTTER_QUERY}
    [ "$status" -eq 0 ]
}
