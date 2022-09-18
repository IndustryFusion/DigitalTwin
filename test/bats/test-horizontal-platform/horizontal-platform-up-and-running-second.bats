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


@test "very that kafka is up and running" {
    run try "at most 30 times every 60s to find 1 pods named 'kafka-0' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 10 times every 30s to find 1 pod named 'zookeeper-0' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

}
@test "verify that scorpio is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'config-server' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to find 1 pod named 'eureka' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to find 1 pod named 'at-context-server' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to find 1 pod named 'gateway' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to find 1 pod named 'entity-manager' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to find 1 pod named 'query-manager' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 30s to find 1 pod named 'storage-manager' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run verify "there is 1 ingress named 'scorpio-ingress'"
    [ "$status" -eq 0 ]
}

@test "verify that alerta is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'alerta-.[^r][^i]' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run verify "there is 1 ingress named 'alerta-ingress'"
    [ "$status" -eq 0 ]
}
