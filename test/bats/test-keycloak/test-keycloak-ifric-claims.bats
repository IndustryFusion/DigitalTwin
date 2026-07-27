#!/usr/bin/env bats
# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# shellcheck disable=SC2005

NAMESPACE=iff
USER_SECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAK_URL=http://keycloak.local/auth

# Known test values — distinct from any real deployment values
TEST_COMPANY_ID="urn:ifric:ifx-eur-com-own-test-00000000-1111-1111-1111-111111111111"
TEST_FACTORY_ID="urn:ifric:ifx-eur-loc-fac-test-00000000-2222-2222-2222-222222222222"
TEST_COMPANY_ID_UPDATED="urn:ifric:ifx-eur-com-own-test-00000000-1111-1111-1111-111111111112"
TEST_FACTORY_ID_UPDATED="urn:ifric:ifx-eur-loc-fac-test-00000000-2222-2222-2222-222222222223"

# State persisted across setup → @test → teardown
_admin_token=""
_client_uuid=""
_orig_company_id=""
_orig_factory_id=""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

get_realm_user_password() {
    kubectl -n "${NAMESPACE}" get "${USER_SECRET}" -o jsonpath='{.data.password}' | base64 -d
}

get_admin_token() {
    local admin_user admin_password
    admin_user=$(kubectl -n "${NAMESPACE}" get secret/keycloak-initial-admin \
        -o jsonpath='{.data.username}' | base64 -d)
    admin_password=$(kubectl -n "${NAMESPACE}" get secret/keycloak-initial-admin \
        -o jsonpath='{.data.password}' | base64 -d)
    curl -sf -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
        -d "grant_type=password" \
        -d "client_id=admin-cli" \
        -d "username=${admin_user}" \
        -d "password=${admin_password}" \
        | jq -r '.access_token'
}

get_scorpio_token() {
    local password
    password=$(get_realm_user_password)
    curl -sf -d "client_id=${CLIENT_ID}" \
        -d "username=${USER}" \
        -d "password=${password}" \
        -d "grant_type=password" \
        "${KEYCLOAK_URL}/realms/${NAMESPACE}/protocol/openid-connect/token" \
        | jq -r '.access_token'
}

get_client_uuid() {
    local admin_token="$1"
    curl -sf \
        -H "Authorization: Bearer ${admin_token}" \
        "${KEYCLOAK_URL}/admin/realms/${NAMESPACE}/clients?clientId=${CLIENT_ID}" \
        | jq -r '.[0].id'
}

get_all_mappers() {
    local admin_token="$1" client_uuid="$2"
    curl -sf \
        -H "Authorization: Bearer ${admin_token}" \
        "${KEYCLOAK_URL}/admin/realms/${NAMESPACE}/clients/${client_uuid}/protocol-mappers/models"
}

# Upsert a hardcoded-claim mapper: PUT if the mapper already exists, POST otherwise.
upsert_mapper() {
    local admin_token="$1" client_uuid="$2" name="$3" value="$4"
    local mappers existing_id payload

    mappers=$(get_all_mappers "${admin_token}" "${client_uuid}")
    existing_id=$(echo "${mappers}" \
        | jq -r ".[] | select(.name == \"${name}\") | .id // \"\"")

    payload=$(jq -n \
        --arg name  "${name}" \
        --arg value "${value}" \
        '{name: $name,
          protocol: "openid-connect",
          protocolMapper: "oidc-hardcoded-claim-mapper",
          config: {
            "claim.value":            $value,
            "userinfo.token.claim":   "true",
            "id.token.claim":         "true",
            "access.token.claim":     "true",
            "claim.name":             $name,
            "jsonType.label":         "String",
            "access.tokenResponse.claim": "false"
          }}')

    if [ -n "${existing_id}" ] && [ "${existing_id}" != "null" ]; then
        payload=$(echo "${payload}" | jq --arg id "${existing_id}" '. + {id: $id}')
        curl -sf -X PUT \
            -H "Authorization: Bearer ${admin_token}" \
            -H "Content-Type: application/json" \
            "${KEYCLOAK_URL}/admin/realms/${NAMESPACE}/clients/${client_uuid}/protocol-mappers/models/${existing_id}" \
            -d "${payload}"
    else
        curl -sf -X POST \
            -H "Authorization: Bearer ${admin_token}" \
            -H "Content-Type: application/json" \
            "${KEYCLOAK_URL}/admin/realms/${NAMESPACE}/clients/${client_uuid}/protocol-mappers/models" \
            -d "${payload}"
    fi
}

# Delete a mapper by name; no-op if it does not exist.
delete_mapper_by_name() {
    local admin_token="$1" client_uuid="$2" name="$3"
    local mappers mapper_id

    mappers=$(get_all_mappers "${admin_token}" "${client_uuid}")
    mapper_id=$(echo "${mappers}" \
        | jq -r ".[] | select(.name == \"${name}\") | .id // \"\"")

    if [ -n "${mapper_id}" ] && [ "${mapper_id}" != "null" ]; then
        curl -sf -X DELETE \
            -H "Authorization: Bearer ${admin_token}" \
            "${KEYCLOAK_URL}/admin/realms/${NAMESPACE}/clients/${client_uuid}/protocol-mappers/models/${mapper_id}"
    fi
}

# Decode a claim from the JWT payload (base64url → JSON).
get_jwt_claim() {
    local token="$1" claim="$2"
    local payload pad
    payload=$(echo "${token}" | cut -d'.' -f2 | tr '_-' '/+')
    pad=$(( (4 - ${#payload} % 4) % 4 ))
    while [ "${pad}" -gt 0 ]; do
        payload="${payload}="
        pad=$(( pad - 1 ))
    done
    echo "${payload}" | base64 -d 2>/dev/null | jq -r ".\"${claim}\""
}

# ---------------------------------------------------------------------------
# Setup: snapshot originals, install known test values before every test.
# Teardown: restore originals (runs even when a test fails).
# ---------------------------------------------------------------------------

setup() {
    local mappers
    _admin_token=$(get_admin_token)
    _client_uuid=$(get_client_uuid "${_admin_token}")

    mappers=$(get_all_mappers "${_admin_token}" "${_client_uuid}")
    _orig_company_id=$(echo "${mappers}" \
        | jq -r '.[] | select(.name == "ifric_company_id") | .config["claim.value"] // ""')
    _orig_factory_id=$(echo "${mappers}" \
        | jq -r '.[] | select(.name == "ifric_factory_id") | .config["claim.value"] // ""')

    upsert_mapper "${_admin_token}" "${_client_uuid}" "ifric_company_id" "${TEST_COMPANY_ID}"
    upsert_mapper "${_admin_token}" "${_client_uuid}" "ifric_factory_id" "${TEST_FACTORY_ID}"
}

teardown() {
    if [ -n "${_orig_company_id}" ]; then
        upsert_mapper "${_admin_token}" "${_client_uuid}" "ifric_company_id" "${_orig_company_id}"
    else
        delete_mapper_by_name "${_admin_token}" "${_client_uuid}" "ifric_company_id"
    fi
    if [ -n "${_orig_factory_id}" ]; then
        upsert_mapper "${_admin_token}" "${_client_uuid}" "ifric_factory_id" "${_orig_factory_id}"
    else
        delete_mapper_by_name "${_admin_token}" "${_client_uuid}" "ifric_factory_id"
    fi
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@test "scorpio token contains ifric_company_id claim" {
    local token
    token=$(get_scorpio_token)
    [ "$(get_jwt_claim "${token}" "ifric_company_id")" = "${TEST_COMPANY_ID}" ]
}

@test "scorpio token contains ifric_factory_id claim" {
    local token
    token=$(get_scorpio_token)
    [ "$(get_jwt_claim "${token}" "ifric_factory_id")" = "${TEST_FACTORY_ID}" ]
}

@test "ifric claims reflect updated mapper values" {
    upsert_mapper "${_admin_token}" "${_client_uuid}" "ifric_company_id" "${TEST_COMPANY_ID_UPDATED}"
    upsert_mapper "${_admin_token}" "${_client_uuid}" "ifric_factory_id" "${TEST_FACTORY_ID_UPDATED}"

    local token
    token=$(get_scorpio_token)
    [ "$(get_jwt_claim "${token}" "ifric_company_id")" = "${TEST_COMPANY_ID_UPDATED}" ]
    [ "$(get_jwt_claim "${token}" "ifric_factory_id")" = "${TEST_FACTORY_ID_UPDATED}" ]
}
