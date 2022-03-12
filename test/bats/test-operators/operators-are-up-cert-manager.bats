#!/usr/bin/env bats

load "../lib/utils"
load "../lib/detik"

# shellcheck disable=SC2034 # needed by detik libraries
DETIK_CLIENT_NAME="kubectl"
# shellcheck disable=SC2034
DETIK_CLIENT_NAMESPACE="operators"

@test "verify that cert-manager is up and running" {

    run try "at most 30 times every 60s to find 3 pods named 'cert-manager' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

}