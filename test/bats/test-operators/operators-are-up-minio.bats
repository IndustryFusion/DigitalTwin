#!/usr/bin/env bats

load "../lib/utils"
load "../lib/detik"

# shellcheck disable=SC2034 # needed by detik libraries
DETIK_CLIENT_NAME="kubectl"
# shellcheck disable=SC2034
DETIK_CLIENT_NAMESPACE="minio-operator"

@test "verify that minio-operator is up and running" {

    run try "at most 10 times every 30s to get pod named 'minio-operator' and verify that 'status' is 'running'"
    [ "$status" -eq 0 ]

}