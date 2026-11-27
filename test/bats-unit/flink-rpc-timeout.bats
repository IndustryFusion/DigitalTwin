#!/usr/bin/env bats
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# The validation job deploys some 250 tasks on one TaskManager, longer than
# Flink's default RPC timeout of 10 s. The chart has to raise it, and keep the
# heartbeat timeout above it: the same busy TaskManager answers both.

TEMPLATE="${BATS_TEST_DIRNAME}/../../helm/charts/flink/templates/flink-deployment.yaml"

# The value of a key of flinkConfiguration, in seconds ("60 s", "2 min" or ms).
seconds_of() {
    local value
    value=$(awk -v key="$1:" '$1 == key {sub(/^[^:]*:[ ]*/, ""); gsub(/"/, ""); print; exit}' "${TEMPLATE}")
    [ -n "${value}" ] || return 1
    case "${value}" in
        *" min") echo $(( ${value% min} * 60 )) ;;
        *" s") echo "${value% s}" ;;
        *) echo $(( value / 1000 )) ;;
    esac
}

@test "the RPC timeout is raised above Flink's 10 s default" {
    run seconds_of pekko.ask.timeout
    [ "${status}" -eq 0 ]
    [ "${output}" -ge 60 ]
}

@test "the heartbeat timeout stays above the RPC timeout" {
    ask=$(seconds_of pekko.ask.timeout)
    heartbeat=$(seconds_of heartbeat.timeout)
    [ "${heartbeat}" -gt "${ask}" ]
}

@test "the deprecated akka key is not used beside it" {
    run grep -c 'akka\.ask\.timeout' "${TEMPLATE}"
    [ "${output}" = "0" ]
}
