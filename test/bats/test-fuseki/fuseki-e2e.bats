#!/usr/bin/env bats

NAMESPACE=iff
CLIENT_SECRET_NAME=secret/keycloak-client-secret-fuseki
CLIENT_ID=fuseki
KEYCLOAK_URL=http://keycloak.local/auth/realms
FUSEKI_URL=http://fuseki.local
REALM=iff

SHACL_TTL="${BATS_TEST_DIRNAME}/../../../semantic-model/shacl2flink/docs/files/shacl.ttl"
KNOWLEDGE_TTL="${BATS_TEST_DIRNAME}/../../../semantic-model/shacl2flink/docs/files/knowledge.ttl"

GRAPH_BASE="${FUSEKI_URL}/${REALM}"
SHACL_GRAPH="${GRAPH_BASE}/shacl.ttl"
KNOWLEDGE_GRAPH="${GRAPH_BASE}/knowledge.ttl"
GSP_ENDPOINT="${FUSEKI_URL}/${REALM}/data"
SPARQL_ENDPOINT="${FUSEKI_URL}/${REALM}/sparql"

# ── helpers ──────────────────────────────────────────────────────────────────

get_client_secret() {
    kubectl -n "${NAMESPACE}" get "${CLIENT_SECRET_NAME}" \
        -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d
}

get_token() {
    local secret
    secret=$(get_client_secret)
    curl -sf \
        -d "client_id=${CLIENT_ID}" \
        -d "client_secret=${secret}" \
        -d "grant_type=client_credentials" \
        "${KEYCLOAK_URL}/${REALM}/protocol/openid-connect/token" \
        | jq -r ".access_token"
}

upload_graph() {
    local token="$1" file="$2" graph_uri="$3"
    curl -s -o /dev/null -w "%{http_code}" \
        -X PUT \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: text/turtle" \
        --data-binary @"${file}" \
        "${GSP_ENDPOINT}?graph=${graph_uri}"
}

get_graph() {
    local token="$1" graph_uri="$2"
    curl -s \
        -H "Authorization: Bearer ${token}" \
        -H "Accept: text/turtle" \
        "${GSP_ENDPOINT}?graph=${graph_uri}"
}

get_graph_status() {
    local token="$1" graph_uri="$2"
    curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer ${token}" \
        -H "Accept: text/turtle" \
        "${GSP_ENDPOINT}?graph=${graph_uri}"
}

sparql_query() {
    local token="$1" query="$2"
    curl -sf -G \
        -H "Authorization: Bearer ${token}" \
        -H "Accept: application/sparql-results+json" \
        --data-urlencode "query=${query}" \
        "${SPARQL_ENDPOINT}"
}

sparql_query_status() {
    local token="$1" query="$2"
    curl -s -o /dev/null -w "%{http_code}" -G \
        -H "Authorization: Bearer ${token}" \
        -H "Accept: application/sparql-results+json" \
        --data-urlencode "query=${query}" \
        "${SPARQL_ENDPOINT}"
}

# ── tests ─────────────────────────────────────────────────────────────────────

@test "obtain fuseki service account token" {
    echo "keycloak token url: ${KEYCLOAK_URL}/${REALM}/protocol/openid-connect/token"
    echo "secret k8s ref:     ${NAMESPACE}/${CLIENT_SECRET_NAME}"

    local secret
    secret=$(get_client_secret) \
        || { echo "FAIL: kubectl could not read ${CLIENT_SECRET_NAME} in ns ${NAMESPACE}"; false; }
    echo "client_secret length: ${#secret}"
    [ -n "${secret}" ] || { echo "FAIL: client secret is empty"; false; }

    local token
    token=$(get_token) \
        || { echo "FAIL: curl to keycloak token endpoint failed (check keycloak.local resolves and keycloak is up)"; false; }
    echo "token length: ${#token}"
    [ -n "${token}" ]   || { echo "FAIL: token is empty"; false; }
    [ "${token}" != "null" ] || { echo "FAIL: token is 'null' — wrong client_id/secret or realm"; false; }
}

@test "upload shacl.ttl to iff realm" {
    echo "source file:   ${SHACL_TTL}"
    echo "graph store:   ${GSP_ENDPOINT}"
    echo "graph uri:     ${SHACL_GRAPH}"

    [ -f "${SHACL_TTL}" ] || { echo "FAIL: source file not found at ${SHACL_TTL}"; false; }

    local token
    token=$(get_token) || { echo "FAIL: could not obtain token"; false; }

    local http_code
    http_code=$(upload_graph "${token}" "${SHACL_TTL}" "${SHACL_GRAPH}")
    echo "HTTP status: ${http_code}"
    # 201 = created, 200 = replaced existing graph
    [[ "${http_code}" == "200" || "${http_code}" == "201" ]] \
        || { echo "FAIL: expected 200 or 201, got ${http_code} (401=auth failed, 403=wrong role, 405=write not enabled, 500=traefik/proxy error)"; false; }
}

@test "upload knowledge.ttl to iff realm" {
    echo "source file:   ${KNOWLEDGE_TTL}"
    echo "graph uri:     ${KNOWLEDGE_GRAPH}"

    [ -f "${KNOWLEDGE_TTL}" ] || { echo "FAIL: source file not found at ${KNOWLEDGE_TTL}"; false; }

    local token
    token=$(get_token) || { echo "FAIL: could not obtain token"; false; }

    local http_code
    http_code=$(upload_graph "${token}" "${KNOWLEDGE_TTL}" "${KNOWLEDGE_GRAPH}")
    echo "HTTP status: ${http_code}"
    [[ "${http_code}" == "200" || "${http_code}" == "201" ]] \
        || { echo "FAIL: expected 200 or 201, got ${http_code}"; false; }
}

@test "retrieve shacl.ttl from iff realm and verify content" {
    local token
    token=$(get_token) || { echo "FAIL: could not obtain token"; false; }

    local http_code
    http_code=$(get_graph_status "${token}" "${SHACL_GRAPH}")
    echo "HTTP status for GET graph: ${http_code}"
    [ "${http_code}" -eq 200 ] \
        || { echo "FAIL: expected 200, got ${http_code} — graph may not exist yet (run upload test first)"; false; }

    local body
    body=$(get_graph "${token}" "${SHACL_GRAPH}")
    echo "body (first 5 lines):"
    echo "${body}" | head -5

    echo "${body}" | grep -q "cutterTemperatureWithMinMaxShape" \
        || { echo "FAIL: 'cutterTemperatureWithMinMaxShape' not found in response body"; false; }
    echo "${body}" | grep -q "shacl#NodeShape" \
        || { echo "FAIL: 'shacl#NodeShape' not found — body may use unexpected serialization"; false; }
}

@test "retrieve knowledge.ttl from iff realm and verify content" {
    local token
    token=$(get_token) || { echo "FAIL: could not obtain token"; false; }

    local http_code
    http_code=$(get_graph_status "${token}" "${KNOWLEDGE_GRAPH}")
    echo "HTTP status for GET graph: ${http_code}"
    [ "${http_code}" -eq 200 ] \
        || { echo "FAIL: expected 200, got ${http_code}"; false; }

    local body
    body=$(get_graph "${token}" "${KNOWLEDGE_GRAPH}")
    echo "body (first 5 lines):"
    echo "${body}" | head -5

    echo "${body}" | grep -q "Cutter" \
        || { echo "FAIL: 'Cutter' not found in response body"; false; }
    echo "${body}" | grep -q "owl:Class" \
        || { echo "FAIL: 'owl:Class' not found in response body"; false; }
}

@test "sparql select query returns node shapes from shacl graph" {
    local token
    token=$(get_token) || { echo "FAIL: could not obtain token"; false; }

    local query result
    query="SELECT ?shape WHERE { GRAPH <${SHACL_GRAPH}> { ?shape a <http://www.w3.org/ns/shacl#NodeShape> } } LIMIT 10"
    result=$(sparql_query "${token}" "${query}") \
        || { echo "FAIL: sparql query returned non-2xx (check ${SPARQL_ENDPOINT} is reachable with token)"; false; }

    echo "SPARQL result binding count: $(echo "${result}" | jq '.results.bindings | length')"
    echo "${result}" | jq -e '.results.bindings | length > 0' \
        || { echo "FAIL: query returned 0 bindings — shacl graph may be empty or query wrong"; false; }
}

@test "sparql select query returns classes from knowledge graph" {
    local token
    token=$(get_token) || { echo "FAIL: could not obtain token"; false; }

    local query result
    query="SELECT ?cls WHERE { GRAPH <${KNOWLEDGE_GRAPH}> { ?cls a <http://www.w3.org/2002/07/owl#Class> } } LIMIT 10"
    result=$(sparql_query "${token}" "${query}") \
        || { echo "FAIL: sparql query returned non-2xx"; false; }

    echo "SPARQL result binding count: $(echo "${result}" | jq '.results.bindings | length')"
    echo "${result}" | jq -e '.results.bindings | length > 0' \
        || { echo "FAIL: query returned 0 bindings — knowledge graph may be empty"; false; }
}

@test "request with invalid token is rejected on graph store endpoint" {
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer this.is.not.a.valid.jwt" \
        -H "Accept: text/turtle" \
        "${GSP_ENDPOINT}?graph=${SHACL_GRAPH}")
    echo "HTTP status with invalid token: ${http_code}"
    [ "${http_code}" -eq 401 ] \
        || { echo "FAIL: expected 401, got ${http_code} (500=ForwardAuth unreachable, 200=auth not enforced)"; false; }
}

@test "request with invalid token is rejected on sparql endpoint" {
    local query="SELECT ?s WHERE { ?s ?p ?o } LIMIT 1"
    local http_code
    http_code=$(sparql_query_status "this.is.not.a.valid.jwt" "${query}")
    echo "HTTP status with invalid token: ${http_code}"
    [ "${http_code}" -eq 401 ] \
        || { echo "FAIL: expected 401, got ${http_code}"; false; }
}

@test "unauthenticated request to graph store endpoint is rejected" {
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Accept: text/turtle" \
        "${GSP_ENDPOINT}?graph=${SHACL_GRAPH}")
    echo "HTTP status without token: ${http_code}"
    [ "${http_code}" -eq 401 ] \
        || { echo "FAIL: expected 401, got ${http_code} (500=ForwardAuth unreachable, 200=auth not enforced)"; false; }
}

@test "unauthenticated request to sparql endpoint is rejected" {
    local query="SELECT ?s WHERE { ?s ?p ?o } LIMIT 1"
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -G \
        -H "Accept: application/sparql-results+json" \
        --data-urlencode "query=${query}" \
        "${SPARQL_ENDPOINT}")
    echo "HTTP status without token: ${http_code}"
    [ "${http_code}" -eq 401 ] \
        || { echo "FAIL: expected 401, got ${http_code}"; false; }
}
