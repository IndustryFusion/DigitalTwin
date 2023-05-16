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


@test "verify that flink is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'flink-jobmanager' with 'status.containerStatuses[*].ready' being 'true,true'"
    [ "$status" -eq 0 ]

    run try "at most 2 times every 30s to find 1 pod named 'flink-taskmanager' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 2 times every 30s to find 1 pod named 'beamservices-operator' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

}

@test "verify that beamservices operator is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'beamservices-operator' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]
}

@test "verify that bridges are up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'alerta-bridge' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 60s to find 1 pod named 'debezium-bridge' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 60s to find 1 pod named 'ngsild-updates-bridge' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]

    run try "at most 30 times every 60s to find 1 pod named 'timescaledb-bridge' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]
}

@test "verify that the core services are up" {
    run try "at most 30 times every 60s to find 1 bsqls named 'core-services' with 'status.state' being 'RUNNING'"
    [ "$status" -eq 0 ]

}
@test "verify that emqx is up and running" {
    run try "at most 30 times every 60s to find 1 pod named 'emqx-core' with 'status.containerStatuses[0].ready' being 'true'"
    [ "$status" -eq 0 ]
}