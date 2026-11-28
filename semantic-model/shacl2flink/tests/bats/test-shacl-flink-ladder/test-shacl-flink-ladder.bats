#!/usr/bin/env bats
#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# The SPARQL method of the deployed validation (SPARQL_ENGINE, alpha ladder).
# Driven by `make test-flink-e2e` right after its deploy of tests/e2e-kms, with
# either method: the other suites would pass with both, so only the deployed
# SQL shows which one runs, and only the running job's plan shows whether the
# planner copied a level of the ladder.

SHACL2FLINK="${BATS_TEST_DIRNAME}/../../.."
NAMESPACE=${NAMESPACE:-iff}
STATEMENTSET=shacl-validation
KUBECTL_LIMIT=${KUBECTL_LIMIT:-60}

k() {
    timeout "${KUBECTL_LIMIT}" kubectl -n "${NAMESPACE}" "$@"
}

progress() {  # a line in the CI log as it happens, findable by its tag
    echo "# [ladder-e2e] $(date -u +%H:%M:%S) $*" >&3
}

# flink_get <path>: the Flink REST API, through the JobManager's pod
flink_get() {
    local jm
    jm=$(k get pods -l component=jobmanager -o jsonpath='{.items[0].metadata.name}') || return 1
    k exec "${jm}" -c flink-main-container -- curl -s -g -m 10 "http://localhost:8081$1"
}

@test "the validation deployed is compiled with the SPARQL method asked for" {
    local found
    found=$(k get configmap -o yaml | grep -c 'sparql_route(' || true)
    progress "SPARQL_ENGINE=${SPARQL_ENGINE:-classic}: ${found} lines call the ladder's functions"
    if [ "${SPARQL_ENGINE:-classic}" = ladder ]; then
        [ "${found}" -gt 0 ]
    else
        [ "${found}" -eq 0 ]
    fi
}

@test "the ladder's job joins as often as the build says, no level copied" {
    # The planner copies a level when a step may be reused, which doubles the
    # joins with every level (Functions.Barrier); checked on every Flink here.
    [ "${SPARQL_ENGINE:-classic}" = ladder ] || skip "SPARQL_ENGINE=ladder only"
    local job expected found plan="${BATS_FILE_TMPDIR}/plan.json"
    job=$(k get beamsqlstatementset "${STATEMENTSET}" -o jsonpath='{.status.job_id}')
    flink_get "/jobs/${job}/plan" > "${plan}"
    expected=$(cat "${SHACL2FLINK}/output/sparql-ladder-joins.txt")
    found=$(python3 "${SHACL2FLINK}/sparql_ladder_joins.py" "${plan}")
    progress "job ${job}: ${found} ladder joins in the plan, ${expected} built"
    [ -n "${expected}" ] && [ "${found}" = "${expected}" ]
}
