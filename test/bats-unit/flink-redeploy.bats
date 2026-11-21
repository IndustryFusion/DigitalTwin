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
# The redeploy of the SHACL validation (semantic-model/shacl2flink/
# flink_redeploy.sh): its four steps in their order, the waits within them
# and how a failed step stops it. kubectl, make and curl are stubs that keep
# the platform's state in files: make flink-undeploy and flink-deploy change
# it, kubectl reads it, curl answers as Alerta.

# shellcheck disable=SC2030,SC2031  # per-test env is intentionally test-local

bats_require_minimum_version 1.5.0

SCRIPT="${BATS_TEST_DIRNAME}/../../semantic-model/shacl2flink/flink_redeploy.sh"

setup() {
    WORK="$(mktemp -d)"
    export WORK
    export STATE="${WORK}/state"
    export CALLS="${WORK}/calls.log"
    mkdir -p "${WORK}/bin" "${STATE}"
    : > "${CALLS}"

    cat > "${WORK}/bin/kubectl" <<'EOF'
#!/bin/bash
args="$*"
args=${args#-n iff }
echo "kubectl ${args}" >> "${CALLS}"
count() { local n; n=$(( $(cat "${STATE}/$1" 2>/dev/null || echo 0) + 1 )); echo "$n" > "${STATE}/$1"; echo "$n"; }
case "${args}" in
    "get kafkatopic iff.ngsild.entities --ignore-not-found -o json")
        cat "${STATE}/shared_topic" 2>/dev/null || true ;;
    "get kafkatopic "*" --ignore-not-found -o name")
        name=${args#get kafkatopic }; name=${name%% *}
        if [ -e "${STATE}/kafkatopic.${name}" ]; then
            n=$(count "linger.${name}")
            if [ -f "${STATE}/deleted" ] && [ "$n" -gt "${STUB_KAFKATOPIC_LINGER:-0}" ] && [ -z "${STUB_TOPICS_STUCK:-}" ]; then
                rm -f "${STATE}/kafkatopic.${name}"
            else
                echo "kafkatopic.kafka.strimzi.io/${name}"
            fi
        fi ;;
    "get beamsqlstatementset shacl-validation --ignore-not-found -o name")
        [ -e "${STATE}/statementset" ] && echo "beamsqlstatementset/shacl-validation"; true ;;
    "get beamsqlstatementset shacl-validation -o jsonpath="*)
        [ -e "${STATE}/statementset" ] || exit 1
        echo "RUNNING ss-1" ;;
    "exec my-cluster-nodes-0 -- sh -c "*"kafka-topics.sh"*"--list"*)
        n=$(count broker_lists)
        cat "${STATE}/broker_topics"
        if [ -n "${STUB_TOPICS_STUCK:-}" ] || [ "$n" -le "${STUB_BROKER_LINGER:-0}" ]; then
            cat "${STATE}/broker_lingering" 2>/dev/null || true
        fi ;;
    "get secret alerta -o jsonpath="*)
        printf testkey | base64 ;;
    "port-forward "*)
        exec sleep 600 3>&- ;;
    "get flinksessionjob core-services-job -o jsonpath={.status.jobStatus.jobId} {.status.jobStatus.state}")
        echo "$(cat "${STATE}/cs_job") RUNNING" ;;
    "get flinksessionjob core-services-job -o jsonpath={.status.jobStatus.jobId}")
        cat "${STATE}/cs_job" ;;
    "get flinksessionjob core-services-job -o jsonpath={.spec.restartNonce}")
        cat "${STATE}/cs_nonce" 2>/dev/null || true ;;
    "patch flinksessionjob core-services-job --type merge -p "*)
        echo "${args##* }" > "${STATE}/cs_patch"
        [ -n "${STUB_CS_STUCK:-}" ] || echo "cs-$(count restarts)" > "${STATE}/cs_job" ;;
    "get pods -l component=jobmanager -o jsonpath="*)
        echo flink-jobmanager-0 ;;
    "exec flink-jobmanager-0 -c flink-main-container -- curl -s http://localhost:8081/jobs/overview")
        cs=$(cat "${STATE}/cs_job")
        ss=""
        [ -e "${STATE}/statementset" ] && ss=$(printf ',{"jid":"ss-1","name":"shacl-validation","state":"RUNNING","start-time":%s,"tasks":{"running":5,"total":5}}' "$(cat "${STATE}/ss_start")")
        printf '{"jobs":[{"jid":"%s","name":"Core Services","state":"RUNNING","start-time":1,"tasks":{"running":3,"total":3}}%s]}\n' "${cs}" "${ss}" ;;
    "exec flink-jobmanager-0 -c flink-main-container -- curl -s http://localhost:8081/jobs/"*"/checkpoints")
        echo '{"counts":{"restored":0,"completed":0}}' ;;
    "get pods -l app.kubernetes.io/instance=kafka-connect -o jsonpath="*)
        echo "kafka-connect-0 2026-11-21T10:00:00Z" ;;
    "logs pod/kafka-connect-0")
        cat "${STATE}/connect.log" 2>/dev/null || true ;;
    "get secret -l owner=helm,name=shacl -o jsonpath="*)
        cat "${STATE}/release" 2>/dev/null || true ;;
    *)
        echo "unexpected kubectl ${args}" >&2
        exit 1 ;;
esac
EOF

    cat > "${WORK}/bin/make" <<'EOF'
#!/bin/bash
echo "make $* @$(date +%s.%N)" >> "${CALLS}"
stamp() { date -u -d "@$1" '+%Y-%m-%d %H:%M:%S'; }
case "$1" in
    flink-undeploy)
        [ -z "${STUB_UNDEPLOY_FAIL:-}" ] || exit 1
        # The KafkaTopics and topics go asynchronously (kubectl and the
        # broker list drop them), the rest at once.
        rm -f "${STATE}/statementset" "${STATE}/release"
        touch "${STATE}/deleted"
        grep -q constraint "${STATE}/broker_topics" && grep constraint "${STATE}/broker_topics" > "${STATE}/broker_lingering"
        grep -v constraint "${STATE}/broker_topics" > "${STATE}/broker_topics.new" || true
        mv "${STATE}/broker_topics.new" "${STATE}/broker_topics" ;;
    flink-deploy)
        [ -z "${STUB_DEPLOY_FAIL:-}" ] || exit 1
        now=$(date +%s)
        touch "${STATE}/statementset"
        echo "$(( (now - 2) * 1000 ))" > "${STATE}/ss_start"
        echo "1 ${STUB_RELEASE_STATUS:-deployed}" > "${STATE}/release"
        snap=$(( now - ${STUB_SNAPSHOT_AGE:-1} ))
        : > "${STATE}/connect.log"
        for c in entity-table-connector rdf-table-connector; do
            printf '%s,217 INFO [%s|task-0] Snapshot step 1 - Preparing (x)\n' "$(stamp "${snap}")" "$c" >> "${STATE}/connect.log"
            [ -n "${STUB_SNAPSHOT_INCOMPLETE:-}" ] || \
                printf '%s,374 INFO [%s|task-0] Snapshot ended with SnapshotResult [status=COMPLETED, offset=x] (x)\n' "$(stamp "${now}")" "$c" >> "${STATE}/connect.log"
        done ;;
    *) exit 2 ;;
esac
EOF

    cat > "${WORK}/bin/curl" <<'EOF'
#!/bin/bash
out=/dev/stdout method=GET url=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o) out=$2; shift ;;
        -X) method=$2; shift ;;
        -w|-H|--data-binary) shift ;;
        http*) url=$1 ;;
    esac
    shift
done
echo "curl ${method} ${url} @$(date +%s.%N)" >> "${CALLS}"
if [ -n "${STUB_ALERTA_DOWN:-}" ]; then printf 000; exit 7; fi
count() { local n; n=$(( $(cat "${STATE}/$1" 2>/dev/null || echo 0) + 1 )); echo "$n" > "${STATE}/$1"; echo "$n"; }
answer() { printf '%s' "$2" > "${out}"; printf '%s' "$1"; }
case "${method} ${url}" in
    "PUT "*"/api/_bulk/alerts/status?"*)
        if [ "$(count puts)" -le "${STUB_PUT_PAGES:-1}" ]; then
            answer 200 '{"status":"ok","count":1000}'
        else
            answer 404 '{"status":"error","message":"not found"}'
        fi ;;
    "GET "*"/api/alerts?"*"from-date="*)
        if [ "$(count settle_queries)" -le "${STUB_SETTLE_BUSY:-0}" ]; then
            answer 200 '{"status":"ok","total":2,"alerts":[]}'
        else
            answer 200 '{"status":"ok","total":0,"alerts":[]}'
        fi ;;
    "GET "*"/api/alerts?service=SHACL%20Validator&status!=closed&page-size=1")
        answer 200 "{\"status\":\"ok\",\"total\":${STUB_LEFT_OPEN:-0},\"alerts\":[]}" ;;
    "GET "*"/api/alerts?page-size=1")
        answer 200 '{"status":"ok","total":0,"alerts":[]}' ;;
    *) answer 400 '{}' ;;
esac
EOF
    chmod +x "${WORK}/bin/"*
    export PATH="${WORK}/bin:${PATH}"
    export MAKE="${WORK}/bin/make"

    # A deployed validation: its statementset, its topics and the shared
    # topic, kept by helm; Core Services running its first job.
    touch "${STATE}/statementset"
    echo 1000 > "${STATE}/ss_start"
    echo "1 deployed" > "${STATE}/release"
    for t in constraint-table constraint-combination-table constraint-trigger-table; do
        touch "${STATE}/kafkatopic.iff.ngsild.flink.${t}"
    done
    printf '%s\n' iff.ngsild.entities iff.alerts.bulk iff.ngsild.flink.constraint_table \
        iff.ngsild.flink.constraint_combination_table iff.ngsild.flink.constraint_trigger_table \
        > "${STATE}/broker_topics"
    shared_topic shacl keep
    echo cs-0 > "${STATE}/cs_job"

    export ALERTA_LOCAL_PORT=1
    export REDEPLOY_POLL=0.1
    export REDEPLOY_SETTLE=1
    export REDEPLOY_UNDEPLOY_TIMEOUT=5
    export REDEPLOY_SETTLE_TIMEOUT=5
    export REDEPLOY_ALERTA_TIMEOUT=1
    export REDEPLOY_CLOSE_TIMEOUT=5
    export REDEPLOY_RESTART_TIMEOUT=2
    export REDEPLOY_DEPLOY_TIMEOUT=2
    export REDEPLOY_COMMAND="make flink-redeploy KMS=../kms/default"
}

teardown() {
    rm -rf "${WORK}"
}

# shared_topic <release> <resource policy>: the KafkaTopic of iff.ngsild.entities
shared_topic() {
    jq -n --arg r "$1" --arg p "$2" '{metadata: {name: "iff.ngsild.entities", annotations:
        ({"meta.helm.sh/release-name": $r} + (if $p == "" then {} else {"helm.sh/resource-policy": $p} end))}}' \
        > "${STATE}/shared_topic"
}

# line <pattern>: the number of the first line of the calls log matching it, 0 if none
line() {
    grep -n -m1 -F -- "$1" "${CALLS}" | cut -d: -f1 || true
}

calls() {
    grep -c -F -- "$1" "${CALLS}" || true
}

STEPS='step 1/4 undeploy the validation: started
step 1/4 undeploy the validation: done
step 2/4 close the SHACL alerts: started
step 2/4 close the SHACL alerts: done
step 3/4 restart Core Services: started
step 3/4 restart Core Services: done
step 4/4 deploy the validation: started
step 4/4 deploy the validation: done'

@test "the four steps run in their order, each after the previous ended" {
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(grep '^step ' <<<"${output}")" = "${STEPS}" ]
    # what each step does comes after what the step before did
    undeploy=$(line "make flink-undeploy")
    topics=$(grep -n -F "kafka-topics.sh" "${CALLS}" | tail -1 | cut -d: -f1)
    close=$(line "curl PUT")
    restart=$(line "kubectl patch flinksessionjob")
    deploy=$(line "make flink-deploy")
    [ "${undeploy}" -lt "${topics}" ]
    [ "${topics}" -lt "${close}" ]
    [ "${close}" -lt "${restart}" ]
    [ "${restart}" -lt "${deploy}" ]
    # the steps after the undeploy wait for its end: no alert touched before
    # the topics are gone
    [ "$(sed -n "1,${topics}p" "${CALLS}" | grep -c '^curl' || true)" -eq 0 ]
    [ "$(cat "${STATE}/cs_job")" = "cs-1" ]
    [ "$(cat "${STATE}/cs_patch")" = '{"spec":{"restartNonce":1}}' ]
}

@test "the KMS arguments reach flink-undeploy and flink-deploy" {
    run bash "${SCRIPT}" KMS=../kms/other
    [ "$status" -eq 0 ]
    [ "$(calls "make flink-undeploy KMS=../kms/other")" -eq 1 ]
    [ "$(calls "make flink-deploy KMS=../kms/other")" -eq 1 ]
}

@test "nothing deployed before: the undeploy completes and the other steps run as usual" {
    rm -f "${STATE}/statementset" "${STATE}/release" "${STATE}"/kafkatopic.* "${STATE}/shared_topic"
    grep -v constraint "${STATE}/broker_topics" > "${STATE}/t" && mv "${STATE}/t" "${STATE}/broker_topics"
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(grep '^step ' <<<"${output}")" = "${STEPS}" ]
}

@test "deployed before the shared topic was kept: stops before anything is undeployed" {
    shared_topic shacl ""
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    # shellcheck disable=SC2154  # stderr is assigned by run --separate-stderr
    [[ "${stderr}" == *"redeploy stopped before step 1/4"* ]]
    [[ "${stderr}" == *"Deploy the validation once first with make flink-deploy"* ]]
    [[ "${output}" != *"step 1/4"* ]]
    [ "$(calls "make ")" -eq 0 ]
    [ -e "${STATE}/statementset" ]
}

@test "a shared topic of another release does not stop the redeploy" {
    shared_topic kafka-bridges ""
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
}

@test "the undeploy step waits while a KafkaTopic or a topic in Kafka is left" {
    export STUB_KAFKATOPIC_LINGER=3 STUB_BROKER_LINGER=3
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(calls "kubectl get kafkatopic iff.ngsild.flink.constraint-trigger-table")" -gt 3 ]
    [ "$(calls "kafka-topics.sh")" -gt 3 ]
}

@test "topics not deleted in time: fails in step 1, names the topic, closes no alert" {
    export STUB_TOPICS_STUCK=1 REDEPLOY_UNDEPLOY_TIMEOUT=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 1/4 undeploy the validation"* ]]
    [[ "${stderr}" == *"iff.ngsild.flink.constraint-trigger-table"* ]]
    [[ "${output}" != *"step 2/4"* ]]
    [ "$(calls "curl")" -eq 0 ]
    [ "$(calls "patch flinksessionjob")" -eq 0 ]
    [ "$(calls "make flink-deploy")" -eq 0 ]
}

@test "a topic left in Kafka after its KafkaTopic is gone fails step 1 with its name" {
    export STUB_BROKER_LINGER=1000 REDEPLOY_UNDEPLOY_TIMEOUT=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 1/4"*"topic left in Kafka: iff.ngsild.flink.constraint_table"* ]]
    [ "$(calls "curl")" -eq 0 ]
}

@test "a failed make flink-undeploy fails step 1 and says the platform runs without validation" {
    export STUB_UNDEPLOY_FAIL=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 1/4 undeploy the validation: make flink-undeploy failed"* ]]
    [[ "${stderr}" == *"the platform runs without SHACL validation until the redeploy is run again"*"make flink-redeploy KMS=../kms/default"* ]]
    [ "$(calls "curl")" -eq 0 ]
}

@test "Alerta unreachable: fails in step 2, Core Services keeps its job, nothing is deployed" {
    export STUB_ALERTA_DOWN=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 2/4 close the SHACL alerts: Alerta not reachable"* ]]
    [[ "${stderr}" == *"the platform runs without SHACL validation until the redeploy is run again"*"make flink-redeploy"* ]]
    [[ "${output}" != *"step 3/4"* ]]
    [ "$(calls "patch flinksessionjob")" -eq 0 ]
    [ "$(cat "${STATE}/cs_job")" = "cs-0" ]
    [ "$(calls "make flink-deploy")" -eq 0 ]
    [ ! -e "${STATE}/statementset" ]
}

@test "the close step waits while SHACL alerts arrive, then closes" {
    export STUB_SETTLE_BUSY=3
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "from-date=")" -eq 4 ]
    last_settle=$(grep -n -F "from-date=" "${CALLS}" | tail -1 | cut -d: -f1)
    [ "${last_settle}" -lt "$(line "curl PUT")" ]
}

# at <pattern>: the time of the first call matching it
at() {
    grep -m1 -F -- "$1" "${CALLS}" | sed 's/.* @//'
}

@test "the close step does not begin before the settle time has passed since the undeploy" {
    # No SHACL alert arrives at all, and still the close waits the settle time.
    export REDEPLOY_SETTLE=2
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    awk -v u="$(at "make flink-undeploy")" -v c="$(at "curl PUT")" 'BEGIN { exit !(c - u >= 2) }'
}

@test "the close step repeats the bulk call until Alerta answers 404, with the SHACL filter" {
    export STUB_PUT_PAGES=3
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "curl PUT")" -eq 4 ]
    [ "$(calls "curl PUT http://127.0.0.1:1/api/_bulk/alerts/status?service=SHACL%20Validator&status!=closed")" -eq 4 ]
    # one more call than pages: the 404 is the end, not an error
    [ "$(calls "curl GET http://127.0.0.1:1/api/alerts?service=SHACL%20Validator&status!=closed&page-size=1")" -eq 1 ]
}

@test "nothing to close: the first 404 is nothing left" {
    export STUB_PUT_PAGES=0
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "curl PUT")" -eq 1 ]
}

@test "the close step fails when SHACL alerts are left that are not closed" {
    export STUB_LEFT_OPEN=2
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 2/4 close the SHACL alerts: 2 SHACL alerts are still not closed"* ]]
    [ "$(calls "patch flinksessionjob")" -eq 0 ]
}

@test "Core Services not restarted in time: fails in step 3 and deploys nothing" {
    export STUB_CS_STUCK=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 3/4 restart Core Services: one new Core Services job running not reached within 2s"* ]]
    [ "$(calls "make flink-deploy")" -eq 0 ]
}

@test "the restart sets a new nonce" {
    echo 7 > "${STATE}/cs_nonce"
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(cat "${STATE}/cs_patch")" = '{"spec":{"restartNonce":8}}' ]
}

@test "a failing helm apply fails step 4" {
    export STUB_RELEASE_STATUS=failed
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 4/4 deploy the validation: the helm apply of the release shacl failed: its latest revision is 1 failed"* ]]
}

@test "a failed make flink-deploy fails step 4" {
    export STUB_DEPLOY_FAIL=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 4/4 deploy the validation: make flink-deploy failed"* ]]
}

@test "the deploy step waits for a completed snapshot of every connector" {
    export STUB_SNAPSHOT_INCOMPLETE=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 4/4"*"entity-table-connector rdf-table-connector"* ]]
}

@test "a snapshot that started before the job does not count" {
    export STUB_SNAPSHOT_AGE=30
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"redeploy failed in step 4/4"*"no completed snapshot since the job started"* ]]
}

@test "run again after a failed step, with the cause removed: completes" {
    export STUB_ALERTA_DOWN=1
    run bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    unset STUB_ALERTA_DOWN
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(grep '^step ' <<<"${output}")" = "${STEPS}" ]
    [ -e "${STATE}/statementset" ]
}
