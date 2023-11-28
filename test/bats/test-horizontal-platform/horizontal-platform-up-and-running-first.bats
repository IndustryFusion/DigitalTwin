#!/usr/bin/env bats
# Copyright (c) 2022 Intel Corporation
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
#

load "../lib/utils"
load "../lib/detik"

# shellcheck disable=SC2034 # these variables are used by detik
DETIK_CLIENT_NAME="kubectl"
# shellcheck disable=SC2034
DETIK_CLIENT_NAMESPACE="iff"
# shellcheck disable=SC2034
DETIK_DEBUG="true"


@test "verify that minio-tenant is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'iff-minio-tenant' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

}
@test "verify that postgres is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'acid-cluster' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run verify "there is 1 pod named '^acid-cluster'"
    [ "$status" -eq 0 ]

}
@test "very that keycloak is up and running" {
    run try "at most 30 times every 60s to find 1 job named 'iff-keycloak-realm-import' with 'status.conditions[0].type' being 'Complete'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 60s to find 1 pod named 'keycloak-0' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run verify "'spec.db.host' is 'acid-cluster.iff.svc.cluster.local' for keycloaks named 'keycloak'"
    [ "$status" -eq 0 ]

    run verify "there is 1 pod named 'keycloak-0'"
    [ "$status" -eq 0 ]

    run try "at most 10 times every 60s to get secret named 'keycloak-client-secret-alerta-ui' and verify that 'metadata.name' is 'keycloak-client-secret-alerta-ui'"
    [ "$status" -eq 0 ]

    run try "at most 10 times every 60s to get secret named 'credential-iff-realm-user-iff' and verify that 'metadata.name' is 'credential-iff-realm-user-iff'"
    [ "$status" -eq 0 ]

    run verify "there is 1 secret named 'keycloak-initial-admin'"
    [ "$status" -eq 0 ]

    run verify "there is 1 ingress named 'keycloak-iff-ingress'"
    [ "$status" -eq 0 ]
}
@test "verify that redis is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'redis' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

}