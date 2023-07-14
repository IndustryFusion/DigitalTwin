#!/usr/bin/env bats

load "../lib/utils"
load "../lib/detik"

# shellcheck disable=SC2034 # needed by detik libraries
DETIK_CLIENT_NAME="kubectl"
# shellcheck disable=SC2034
DETIK_CLIENT_NAMESPACE="iff"

@test "verify that OLM install-plan is up" {

    run try "at most 30 times every 10s to get installplans named 'install-.*' and verify that 'spec.approval' is 'Manual'"
    [ "$status" -eq 0 ]

}