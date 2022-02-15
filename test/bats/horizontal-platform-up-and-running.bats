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

load "lib/utils"
load "lib/detik"

DETIK_CLIENT_NAME="kubectl"
DETIK_CLIENT_NAMESPACE="iff"

DETIK_DEBUG="true"


@test "verify that minio-tenant is up and running" {

    run try "at most 30 times every 60s to get pod named 'iff-minio-tenant' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run verify "'status' is 'running' for pod named 'iff-minio-tenant'"
    [ "$status" -eq 0 ]

}
@test "verify that postgres is up and running" {

    run try "at most 30 times every 60s to get pods named 'acid-cluster' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run verify "'status' is 'running' for pods named 'acid-cluster'"
    [ "$status" -eq 0 ]

    run verify "there are 2 pods named '^acid-cluster'"
    [ "$status" -eq 0 ]

}
@test "very that keycloak is up and running" {

    run try "at most 30 times every 60s to get pods named 'keycloak-0' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run verify "'status' is 'running' for pods named 'keycloak-0'"
    [ "$status" -eq 0 ]

    run verify "'spec.externalName' is 'acid-cluster.iff.svc.cluster.local' for svc named 'keycloak-postgresql'"
    [ "$status" -eq 0 ]

    run verify "there is 1 pod named 'keycloak-0'"
    [ "$status" -eq 0 ]

    run try "at most 10 times every 60s to get secret named 'keycloak-client-secret-alerta-ui' and verify that 'metadata.name' is 'keycloak-client-secret-alerta-ui'"
    [ "$status" -eq 0 ]

    run try "at most 10 times every 60s to get secret named 'credential-iff-realm-user-iff' and verify that 'metadata.name' is 'credential-iff-realm-user-iff'"
    [ "$status" -eq 0 ]

    run verify "there is 1 secret named 'credential-keycloak'"
    [ "$status" -eq 0 ]

}
@test "very that kafka is up and running" {

    run try "at most 30 times every 60s to get pods named 'kafka-0' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run verify "'status' is 'running' for pods named 'kafka-0'"
    [ "$status" -eq 0 ]

    run verify "'status' is 'running' for pods named 'zookeeper-0'"
    [ "$status" -eq 0 ]

    run verify "'status.containerStatuses[0].ready' is 'true' for pods named 'zookeeper-0'"
    [ "$status" -eq 0 ]

}
@test "verify that flink is up and running" {

    run try "at most 30 times every 60s to get pod named 'flink-jobmanager' and verify that 'status.containerStatuses[*].ready' is 'true,true'"
    [ "$status" -eq 0 ]

    run verify "'status' is 'running' for pod named 'flink-jobmanager'"
    [ "$status" -eq 0 ]

    run try "at most 2 times every 30s to get pod named 'flink-taskmanager' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run verify "'status' is 'running' for pod named 'flink-taskmanager'"
    [ "$status" -eq 0 ]

    run verify "'status.containerStatuses[0].ready' is 'true' for pod named 'beamservices-operator'"
    [ "$status" -eq 0 ]

    run verify "'status' is 'running' for pod named 'beamservices-operator'"
    [ "$status" -eq 0 ]

}
@test "verify that scorpio is up and running" {

    run try "at most 30 times every 60s to get pod named 'config-server' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to get pod named 'eureka' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to get pod named 'at-context-server' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to get pod named 'gateway' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to get pod named 'history-manager' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to get pod named 'entity-manager' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to get pod named 'subscription-manager' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to get pod named 'query-manager' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to get pod named 'registry-manager' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to get pod named 'storage-manager' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]
}
@test "verify that beamservices operator is up and running" {

    run try "at most 30 times every 60s to get pod named 'beamservices-operator' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]
}
@test "verify that alerta is up and running" {

    run try "at most 30 times every 60s to get pod named 'alerta' and verify that 'status.containerStatuses[0].ready' is 'true'"
    [ "$status" -eq 0 ]
}
