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
# The restart of Kafka Connect at the end of `make flink-deploy`
# (semantic-model/shacl2flink/restart_connect.sh): it waits until the deployed
# validation job runs and reads its entities and attributes, and restarts
# Kafka Connect only then, or fails without restarting it. kubectl and curl
# are stubs. The statementset goes through the states listed in
# ${STATE}/ss.<n>.json, one per read of it, the last one staying; a state
# names its job and whether the job runs all its tasks and holds the
# partitions of its readers. Every call is logged in order.

# shellcheck disable=SC2030,SC2031  # per-test env is intentionally test-local
# shellcheck disable=SC2154  # stderr is assigned by run --separate-stderr

bats_require_minimum_version 1.5.0

SCRIPT="${BATS_TEST_DIRNAME}/../../semantic-model/shacl2flink/restart_connect.sh"
MAKEFILE="${BATS_TEST_DIRNAME}/../../semantic-model/shacl2flink/Makefile"

setup() {
    WORK="$(mktemp -d)"
    export WORK
    export STATE="${WORK}/state"
    export CALLS="${WORK}/calls.log"
    mkdir -p "${WORK}/bin" "${STATE}"
    : > "${CALLS}"

    cat > "${WORK}/bin/kubectl" <<'STUB'
#!/bin/bash
args="$*"
args=${args#-n iff }
echo "kubectl ${args}" >> "${CALLS}"
current() { cat "${STATE}/current.json"; }
case "${args}" in
    "get beamsqlstatementset shacl-validation --ignore-not-found -o name")
        [ -z "${STUB_GET_FAIL:-}" ] || exit 1
        ls "${STATE}"/ss.*.json >/dev/null 2>&1 && echo "beamsqlstatementset.industry-fusion.com/shacl-validation"
        exit 0 ;;
    "get beamsqlstatementset shacl-validation -o json")
        n=$(( $(cat "${STATE}/reads" 2>/dev/null || echo 0) + 1 ))
        echo "$n" > "${STATE}/reads"
        f="${STATE}/ss.${n}.json"
        [ -e "$f" ] || f=$(ls "${STATE}"/ss.*.json | sort -t. -k2 -n | tail -1)
        cp "$f" "${STATE}/current.json"
        echo "the statementset is $(jq -r '"\(.status.state) \(.status.job_id)"' "$f")" >> "${CALLS}"
        cat "$f" ;;
    "get beamsqlstatementset shacl-validation -o jsonpath={.status.state} {.status.job_id}")
        current | jq -r '"\(.status.state // "") \(.status.job_id // "")"' ;;
    "port-forward "*)
        echo "$$" >> "${STATE}/forwards"
        exec sleep 600 3>&- ;;
    "delete pod -l app.kubernetes.io/instance=kafka-connect --wait=false")
        [ -z "${STUB_DELETE_FAIL:-}" ] || exit 1
        echo 'pod "kafka-connect-connect-0" deleted' ;;
    *)
        echo "unexpected kubectl ${args}" >&2
        exit 1 ;;
esac
STUB

    cat > "${WORK}/bin/curl" <<'STUB'
#!/bin/bash
out=/dev/stdout url=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o) out=$2; shift ;;
        -w|-m|-X|-H|--data-binary) shift ;;
        http*) url=$1 ;;
    esac
    shift
done
path=/${url#http://*/}
echo "curl GET ${path}" >> "${CALLS}"
answer() { printf '%s' "$2" > "${out}"; printf '%s' "$1"; }
job=$(jq -r '.status.job_id // empty' "${STATE}/current.json" 2>/dev/null)
tasks=$(jq -r '.stub.tasks // "5/5"' "${STATE}/current.json" 2>/dev/null)
topics=$(jq -r '.stub.placed // "iff.ngsild.entities iff.ngsild.attributes"' "${STATE}/current.json" 2>/dev/null)
case "${path}" in
    /config) answer 200 '{}' ;;
    /jobs/overview)
        answer 200 "$(jq -nc --arg j "${job}" --arg t "${tasks}" \
            '{jobs: ([{jid: "cs-0", name: "Core Services", state: "RUNNING", tasks: {running: 3, total: 3}}]
              + (if $j == "" then [] else [{jid: $j, name: "iff/shacl-validation", state: "RUNNING",
                 tasks: {running: ($t | split("/")[0] | tonumber), total: ($t | split("/")[1] | tonumber)}}] end))}')" ;;
    /jobs/*/vertices/v-src/metrics)
        ids='{"id":"0.Source__x[1].pendingRecords"}'
        for t in ${topics}; do
            ids="${ids},{\"id\":\"0.Source__x[1].KafkaSourceReader.topic.${t//./_}.partition.0.currentOffset\"}"
        done
        answer 200 "[${ids}]" ;;
    /jobs/*)
        answer 200 '{"state":"RUNNING","vertices":[{"id":"v-src","name":"Source: x"}]}' ;;
    *) answer 404 '{}' ;;
esac
STUB
    chmod +x "${WORK}/bin/"*
    export PATH="${WORK}/bin:${PATH}"
    export VALIDATION_POLL=0.1
    export VALIDATION_CONNECT_TIMEOUT=2
    export VALIDATION_START_TIMEOUT=5
}

teardown() {
    rm -rf "${WORK}"
}

# ss <n> <state> <job> <handled spec> [stub json]: the n-th read of the
# statementset. Its spec is {"v":2}; the operator last handled <handled spec>.
ss() {
    jq -n --arg state "$2" --arg job "$3" --argjson handled "$4" --argjson stub "${5:-{\}}" \
        '{metadata: {name: "shacl-validation",
            annotations: {"kopf.zalando.org/last-handled-configuration": ({spec: $handled} | tojson)}},
          spec: {v: 2},
          status: ({state: $state} + (if $job == "" then {} else {job_id: $job} end)),
          stub: $stub}' > "${STATE}/ss.$1.json"
}

line() {  # the number of the first line of the calls log matching it, 0 if none
    local n
    n=$(grep -n -m1 -F -- "$1" "${CALLS}" | cut -d: -f1)
    echo "${n:-0}"
}

@test "over a running validation: Kafka Connect is restarted only once the new job runs and reads" {
    # the old job still reports RUNNING before the operator has handled the new spec
    ss 1 RUNNING ss-0 '{"v":1}'
    ss 2 RUNNING ss-0 '{"v":1}'
    ss 3 UPDATING ss-0 '{"v":2}'
    ss 4 INITIALIZED "" '{"v":2}'
    ss 5 DEPLOYING ss-1 '{"v":2}'
    ss 6 RUNNING ss-1 '{"v":2}' '{"tasks": "2/5"}'
    ss 7 RUNNING ss-1 '{"v":2}' '{"placed": "iff.ngsild.entities"}'
    ss 8 RUNNING ss-1 '{"v":2}'
    run bash "${SCRIPT}"
    echo "${output}"
    cat "${CALLS}"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"the job ss-1 reads; restarting Kafka Connect"* ]]
    restart=$(line "delete pod -l app.kubernetes.io/instance=kafka-connect --wait=false")
    [ "${restart}" -gt "$(line "the statementset is RUNNING ss-1")" ]
    [ "${restart}" -gt "$(grep -n -F "curl GET /jobs/ss-1/vertices/v-src/metrics" "${CALLS}" | tail -1 | cut -d: -f1)" ]
    # read eight times: never restarted on an earlier state
    [ "$(cat "${STATE}/reads")" -eq 8 ]
    [ "$(grep -c -F "delete pod" "${CALLS}")" -eq 1 ]
    [ "$(line "curl GET /jobs/ss-0")" -eq 0 ]
}

@test "a deployment that changed nothing: the running job is kept and Kafka Connect restarted" {
    ss 1 RUNNING ss-0 '{"v":2}'
    run bash "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"the job ss-0 reads; restarting Kafka Connect"* ]]
    [ "$(line "delete pod")" -gt 0 ]
}

@test "the first deployment: the statementset without a job yet" {
    ss 1 INITIALIZED "" '{"v":2}'
    ss 2 DEPLOYMENT_FAILURE "" '{"v":2}'
    ss 3 RUNNING ss-1 '{"v":2}'
    run bash "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"the job ss-1 reads"* ]]
}

@test "the operator never takes the deployed statementset over: fails in time, Kafka Connect left alone" {
    ss 1 RUNNING ss-0 '{"v":1}'
    export VALIDATION_START_TIMEOUT=1
    run --separate-stderr bash "${SCRIPT}"
    echo "${stderr}"
    [ "${status}" -ne 0 ]
    [[ "${stderr}" == *"Kafka Connect not restarted: the shacl-validation job running and reading not reached within 1s: the operator has not taken over the deployed statementset yet, it reports RUNNING"* ]]
    [[ "${stderr}" == *"make restart-connect"* ]]
    [ "$(line "delete pod")" -eq 0 ]
}

@test "a statementset that never handled any spec counts as not taken over" {
    jq -n '{metadata: {name: "shacl-validation"}, spec: {v: 2}, status: {state: "RUNNING", job_id: "ss-0"}}' \
        > "${STATE}/ss.1.json"
    export VALIDATION_START_TIMEOUT=1
    run --separate-stderr bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${stderr}" == *"the operator has not taken over the deployed statementset yet"* ]]
    [ "$(line "delete pod")" -eq 0 ]
}

@test "a job that never runs all its tasks: fails naming it, Kafka Connect left alone" {
    ss 1 RUNNING ss-1 '{"v":2}' '{"tasks": "4/5"}'
    export VALIDATION_START_TIMEOUT=1
    run --separate-stderr bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${stderr}" == *"the job ss-1 doesn't run with all its tasks yet"* ]]
    [ "$(line "delete pod")" -eq 0 ]
}

@test "a reader that never gets its partition: fails naming the topic, Kafka Connect left alone" {
    ss 1 RUNNING ss-1 '{"v":2}' '{"placed": "iff.ngsild.entities"}'
    export VALIDATION_START_TIMEOUT=1
    run --separate-stderr bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${stderr}" == *"no reader of the job ss-1 has a partition of: iff.ngsild.attributes"* ]]
    [ "$(line "delete pod")" -eq 0 ]
}

@test "a statementset stuck in a state that is not RUNNING: fails naming the state" {
    ss 1 DEPLOYMENT_FAILURE "" '{"v":2}'
    export VALIDATION_START_TIMEOUT=1
    run --separate-stderr bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${stderr}" == *"the statementset reports DEPLOYMENT_FAILURE"* ]]
    [ "$(line "delete pod")" -eq 0 ]
}

@test "no statementset deployed: fails at once" {
    run --separate-stderr bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${stderr}" == *"no validation statementset shacl-validation is deployed in iff"* ]]
    [ "$(line "delete pod")" -eq 0 ]
    [ "$(line "port-forward")" -eq 0 ]
}

@test "the statementset can't be read: fails at once" {
    ss 1 RUNNING ss-0 '{"v":2}'
    export STUB_GET_FAIL=1
    run --separate-stderr bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${stderr}" == *"the statementset shacl-validation can't be read"* ]]
    [ "$(line "delete pod")" -eq 0 ]
}

@test "the Connect pods can't be deleted: fails saying so" {
    ss 1 RUNNING ss-0 '{"v":2}'
    export STUB_DELETE_FAIL=1
    run --separate-stderr bash "${SCRIPT}"
    [ "${status}" -ne 0 ]
    [[ "${stderr}" == *"the Connect pods can't be deleted"* ]]
}

@test "no port-forward is left behind" {
    ss 1 RUNNING ss-0 '{"v":2}'
    run bash "${SCRIPT}"
    [ "${status}" -eq 0 ]
    [ -s "${STATE}/forwards" ]
    sleep 0.2
    while read -r pid; do
        if kill -0 "${pid}" 2>/dev/null; then echo "port-forward ${pid} still runs"; false; fi
    done < "${STATE}/forwards"
}

@test "flink-deploy restarts Kafka Connect through restart-connect only, after the deployment" {
    # Since #1165 flink-deploy decides in deploy_validation.sh: over an
    # unchanged validation it restarts Connect through restart-connect, after
    # the chart and the Fuseki graphs; a replacement restarts it in the
    # resync's re-snapshot (deploy-validation.bats).
    recipe=$(awk '/^flink-deploy:/ { on = 1; next } on && /^[^\t]/ { exit } on' "${MAKEFILE}")
    echo "${recipe}"
    [ "$(grep -c "delete pod" <<<"${recipe}")" -eq 0 ]
    grep -q "./deploy_validation.sh" <<<"${recipe}"
    deploy="$(dirname "${MAKEFILE}")/deploy_validation.sh"
    [ "$(grep -c "delete pod" "${deploy}")" -eq 0 ]
    # shellcheck disable=SC2016  # the script's text, with the variable as written
    restart=$(grep -n '"$MAKE" restart-connect' "${deploy}" | cut -d: -f1)
    [ -n "${restart}" ]
    [ "${restart}" -gt "$(grep -n "helmfile-shacl.yaml apply" "${deploy}" | cut -d: -f1)" ]
    # shellcheck disable=SC2016
    [ "${restart}" -gt "$(grep -n '"$MAKE" fuseki-deploy-kms' "${deploy}" | head -1 | cut -d: -f1)" ]
    awk '/^restart-connect:/ { on = 1; next } on && /^[^\t]/ { exit } on' "${MAKEFILE}" | grep -q "restart_connect.sh"
}
