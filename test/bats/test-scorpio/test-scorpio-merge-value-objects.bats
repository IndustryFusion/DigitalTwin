#!/usr/bin/env bats
#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Scorpio merges value objects as a whole: a declared double, an IRI value and
# a language-tagged string merged through merge entity and batch merge, into an
# existing attribute and into a new one, keep their @type, @id and @language.
#
# NGSILD_URL and TOKEN point the suite at another broker; without TOKEN it gets
# one from the platform's Keycloak.

NAMESPACE=iff
USER_SECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAK_URL=${KEYCLOAK_URL:-http://keycloak.local/auth/realms}
NGSILD_URL=${NGSILD_URL:-http://ngsild.local}
CONTEXT=https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld
T=https://industry-fusion.com/types/v0.9
XSD_DOUBLE=http://www.w3.org/2001/XMLSchema#double
IRI_VALUE=urn:state-test:running
ENTITY_PATCH=urn:merge-value-objects-test:patch
ENTITY_BATCH=urn:merge-value-objects-test:batch
BODY=/tmp/MERGE_VALUE_OBJECTS_BODY
RESULT=/tmp/MERGE_VALUE_OBJECTS_RESULT

get_password() {
    kubectl -n ${NAMESPACE} get ${USER_SECRET} -o jsonpath='{.data.password}' | base64 -d
}

get_token() {
    if [ -n "${TOKEN:-}" ]; then
        echo "${TOKEN}"
        return
    fi
    local password
    password=$(get_password)
    curl -s -d "client_id=${CLIENT_ID}" -d "username=${USER}" -d "password=${password}" -d 'grant_type=password' \
        "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" | jq -r ".access_token"
}

# request <token> <method> <path> [body file]: prints the HTTP status
request() {
    local data=()
    [ -n "${4:-}" ] && data=(-d @"$4")
    curl -s -o /dev/null -w '%{http_code}' -X "$2" -H "Authorization: Bearer $1" \
        -H "Content-Type: application/ld+json" "${data[@]}" "${NGSILD_URL}/ngsi-ld/v1$3"
}

query_entity() {
    curl -s -H "Authorization: Bearer $1" -H "Accept: application/json" "${NGSILD_URL}/ngsi-ld/v1/entities/$2"
}

# An entity whose three attributes hold plain numbers
create_body() {
    cat << EOF
{
  "@context": "${CONTEXT}",
  "id": "$1",
  "type": "${T}/merge_value_objects_test",
  "${T}/temperature": {"type": "Property", "value": 20},
  "${T}/state": {"type": "Property", "value": 1},
  "${T}/label": {"type": "Property", "value": 2}
}
EOF
}

# The three value objects, into the existing attributes and into new ones
merge_attributes() {
    cat << EOF
  "${T}/temperature": {"type": "Property", "value": {"@value": 80, "@type": "${XSD_DOUBLE}"}},
  "${T}/state": {"type": "Property", "value": {"@id": "${IRI_VALUE}"}},
  "${T}/label": {"type": "Property", "value": {"@value": "Schneidkopf", "@language": "de"}},
  "${T}/newTemperature": {"type": "Property", "value": {"@value": 80, "@type": "${XSD_DOUBLE}"}},
  "${T}/newState": {"type": "Property", "value": {"@id": "${IRI_VALUE}"}},
  "${T}/newLabel": {"type": "Property", "value": {"@value": "Schneidkopf", "@language": "de"}}
EOF
}

# The GET compacts @type, @id and @language to type, id and language; both are accepted
check_values() {
    jq -e --arg t "${T}" --arg xsd "${XSD_DOUBLE}" --arg iri "${IRI_VALUE}" '
        def v: .value;
        def typ: v | (.["@type"] // .type);
        def val: v | (.["@value"] // .value);
        ([.[$t + "/temperature"], .[$t + "/newTemperature"]]
            | all(typ == $xsd and val == 80))
        and ([.[$t + "/state"], .[$t + "/newState"]]
            | all(v | (.["@id"] // .id) == $iri))
        and ([.[$t + "/label"], .[$t + "/newLabel"]]
            | all(val == "Schneidkopf" and (v | (.["@language"] // .language)) == "de"))
    ' "$1"
}

setup() {
    token=$(get_token)
}

teardown() {
    request "$token" DELETE "/entities/${ENTITY_PATCH}" > /dev/null || true
    request "$token" DELETE "/entities/${ENTITY_BATCH}" > /dev/null || true
}

@test "merge entity keeps the @type, @id and @language of merged values" {
    request "$token" DELETE "/entities/${ENTITY_PATCH}" > /dev/null || true
    create_body "${ENTITY_PATCH}" > ${BODY}
    [ "$(request "$token" POST /entities/ ${BODY})" = 201 ]
    printf '{\n  "@context": "%s",\n%s\n}\n' "${CONTEXT}" "$(merge_attributes)" > ${BODY}
    run request "$token" PATCH "/entities/${ENTITY_PATCH}" ${BODY}
    echo "merge entity: ${output}" >&3
    [ "$output" = 204 ]
    query_entity "$token" "${ENTITY_PATCH}" > ${RESULT}
    jq . ${RESULT} >&3
    run check_values ${RESULT}
    [ "$status" -eq 0 ]
}

@test "batch merge keeps the @type, @id and @language of merged values" {
    request "$token" DELETE "/entities/${ENTITY_BATCH}" > /dev/null || true
    create_body "${ENTITY_BATCH}" > ${BODY}
    [ "$(request "$token" POST /entities/ ${BODY})" = 201 ]
    printf '[{\n  "@context": "%s",\n  "id": "%s",\n%s\n}]\n' "${CONTEXT}" "${ENTITY_BATCH}" "$(merge_attributes)" > ${BODY}
    run request "$token" POST /entityOperations/merge ${BODY}
    echo "batch merge: ${output}" >&3
    [ "$output" = 204 ]
    query_entity "$token" "${ENTITY_BATCH}" > ${RESULT}
    jq . ${RESULT} >&3
    run check_values ${RESULT}
    [ "$status" -eq 0 ]
}
