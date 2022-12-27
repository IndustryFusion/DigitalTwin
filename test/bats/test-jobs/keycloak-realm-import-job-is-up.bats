#!/usr/bin/env bats

load "../lib/utils"
load "../lib/detik"

# shellcheck disable=SC2034 # needed by detik libraries
DETIK_CLIENT_NAME="kubectl"
# shellcheck disable=SC2034
DETIK_CLIENT_NAMESPACE="iff"

@test "verify that keycloak-realm-import job is up and running" {

    run try "at most 30 times every 10s to find 1 job named 'iff-keycloak-realm-import' with 'metadata.ownerReferences[0].kind' being 'KeycloakRealmImport'"
    [ "$status" -eq 0 ]

}