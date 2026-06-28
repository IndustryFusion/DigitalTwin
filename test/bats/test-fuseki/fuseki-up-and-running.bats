#!/usr/bin/env bats

load "../lib/utils"
load "../lib/detik"

# shellcheck disable=SC2034
DETIK_CLIENT_NAME="kubectl"
# shellcheck disable=SC2034
DETIK_CLIENT_NAMESPACE="iff"
# shellcheck disable=SC2034
DETIK_DEBUG="true"

@test "verify that fuseki is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'fuseki-[^a]' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run verify "there is 1 ingress named 'fuseki-ingress'"
    [ "$status" -eq 0 ]
}

@test "verify that fuseki-auth is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'fuseki-auth' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]
}

@test "verify that fuseki PVC is bound" {
    run try "at most 10 times every 30s to find 1 persistentvolumeclaim named 'fuseki-data' with 'status.phase' being 'Bound'"
    [ "$status" -eq 0 ]
}

@test "verify that fuseki keycloak client secret exists" {
    run try "at most 10 times every 60s to get secret named 'keycloak-client-secret-fuseki' and verify that 'metadata.name' is 'keycloak-client-secret-fuseki'"
    [ "$status" -eq 0 ]
}
