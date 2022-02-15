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

@test "verify postgres operator is up and running" {


    run try "at most 20 times every 60s to get pod named 'postgres-operator' and verify that 'status' is 'running'"
    [ "$status" -eq 0 ]

}

@test "verify the strimzi kafka operators is up and running" {

    run try "at most 10 times every 30s to get pod named 'strimzi-cluster-operator' and verify that 'status' is 'running'"
    [ "$status" -eq 0 ]

}

@test "verify the keycloak operator is up and running" {

    run try "at most 10 times every 30s to get pod named 'keycloak-operator' and verify that 'status' is 'running'"
    [ "$status" -eq 0 ]

}