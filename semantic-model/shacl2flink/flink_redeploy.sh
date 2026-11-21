#!/bin/bash
#
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
# Redeploys the SHACL validation so that afterwards exactly the alerts of the
# constraints violated now are open (`make flink-redeploy`). The leaf checks
# write only violations, so nothing would overwrite a raise of the previous
# job that the new one doesn't confirm. Four steps, in this order:
#
#   1. undeploy the validation and wait until the topics of its own tables are
#      deleted in Kafka, so the new job replays nothing of the previous one;
#   2. once no SHACL alert has arrived for a settle time, close every SHACL
#      alert in Alerta that is not closed, and no other alert;
#   3. restart Core Services without state, so its alerts filter forwards the
#      new job's raises again, also when severity and text are unchanged;
#   4. deploy the validation and wait until a complete Debezium snapshot that
#      started after the new job has gone through it.
#
# A step starts only after the one before it completed. A failed or timed-out
# step stops the redeploy with its name; every step is safe to run again.
#
# Usage: flink_redeploy.sh [make arguments, passed to flink-undeploy and
# flink-deploy]. Run by `make flink-redeploy`, which chooses the KMS as for
# flink-deploy and hands it on to the sub-makes.
#
# Environment (time limits in seconds; exceeding one fails the step):
#   NAMESPACE                    iff
#   REDEPLOY_UNDEPLOY_TIMEOUT    600  statementset and topics gone
#   REDEPLOY_SETTLE              30   no SHACL alert received for this long
#   REDEPLOY_SETTLE_TIMEOUT      600  limit of the wait for the settle time
#   REDEPLOY_ALERTA_TIMEOUT      30   Alerta answering through the port-forward
#   REDEPLOY_CLOSE_TIMEOUT       300  closing the SHACL alerts
#   REDEPLOY_RESTART_TIMEOUT     600  the new Core Services job running
#   REDEPLOY_DEPLOY_TIMEOUT      1200 the new job running and fed by a snapshot
#   REDEPLOY_POLL                5    pause between two checks
#   REDEPLOY_COMMAND             the command named in a failure message

set -euo pipefail

cd "$(dirname "$0")"

NAMESPACE=${NAMESPACE:-iff}
MAKE=${MAKE:-make}
UNDEPLOY_TIMEOUT=${REDEPLOY_UNDEPLOY_TIMEOUT:-600}
SETTLE=${REDEPLOY_SETTLE:-30}
SETTLE_TIMEOUT=${REDEPLOY_SETTLE_TIMEOUT:-600}
ALERTA_TIMEOUT=${REDEPLOY_ALERTA_TIMEOUT:-30}
CLOSE_TIMEOUT=${REDEPLOY_CLOSE_TIMEOUT:-300}
RESTART_TIMEOUT=${REDEPLOY_RESTART_TIMEOUT:-600}
DEPLOY_TIMEOUT=${REDEPLOY_DEPLOY_TIMEOUT:-1200}
POLL=${REDEPLOY_POLL:-5}
COMMAND=${REDEPLOY_COMMAND:-make flink-redeploy $*}

STATEMENTSET=${STATEMENTSET:-shacl-validation}
RELEASE=${RELEASE:-shacl}
SHARED_TOPIC=${SHARED_TOPIC:-iff.ngsild.entities}
# The KafkaTopic resources of the validation's own tables, and their topics
# (helm/values.yaml.gotmpl, kafkaBridge.flink.*Topic).
OWN_KAFKATOPICS=${OWN_KAFKATOPICS:-iff.ngsild.flink.constraint-table iff.ngsild.flink.constraint-combination-table iff.ngsild.flink.constraint-trigger-table}
OWN_TOPICS=${OWN_TOPICS:-iff.ngsild.flink.constraint_table iff.ngsild.flink.constraint_combination_table iff.ngsild.flink.constraint_trigger_table}
KAFKA_POD=${KAFKA_POD:-my-cluster-nodes-0}
ALERTA_SERVICE=${ALERTA_SERVICE:-svc/alerta}
ALERTA_PORT=${ALERTA_PORT:-8080}
SHACL_SERVICE="SHACL Validator"
SHACL_FILTER="service=SHACL%20Validator"
CORE_SERVICES=${CORE_SERVICES:-core-services-job}
CORE_SERVICES_NAME=${CORE_SERVICES_NAME:-Core Services}
CONNECTORS=${CONNECTORS:-entity-table-connector rdf-table-connector}

REASON_FILE=$(mktemp)
DETAIL_FILE=$(mktemp)
trap 'rm -f "$REASON_FILE" "$DETAIL_FILE"' EXIT

# fail <reason>: ends the step it is called in, with this reason
fail() {
    echo "$*" > "$REASON_FILE"
    exit 1
}

# wait_until <deadline> <limit> <what> <check>: runs <check> every POLL
# seconds until it succeeds; <check> prints what is still missing. Fails the
# step once the clock passes <deadline> (epoch seconds), the end of <limit>.
wait_until() {
    local deadline=$1 limit=$2 what=$3 check=$4
    while true; do
        if "$check" > "$DETAIL_FILE"; then
            return 0
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            fail "${what} not reached within ${limit}s: $(cat "$DETAIL_FILE")"
        fi
        sleep "$POLL"
    done
}

kube() {
    kubectl -n "$NAMESPACE" "$@"
}

# The Flink REST API, from inside the JobManager pod as test/wait-for-flink-jobs.sh reads it.
flink_get() {  # flink_get <path>
    local pod
    pod=$(kube get pods -l component=jobmanager -o jsonpath='{.items[0].metadata.name}' 2>/dev/null) || return 1
    [ -n "$pod" ] || return 1
    kube exec "$pod" -c flink-main-container -- curl -s "http://localhost:8081$1" 2>/dev/null
}

broker_topics() {
    kube exec "$KAFKA_POD" -- sh -c \
        "KAFKA_HEAP_OPTS='-Xmx192M' bin/kafka-topics.sh --bootstrap-server localhost:9092 --list" 2>/dev/null
}

# ---------------------------------------------------------------- the check before step 1

# A shacl release deployed before the shared topic was kept would delete it
# when it is undeployed. A deploy with the current chart adds the annotation.
check_shared_topic() {
    local topic owner policy
    if ! topic=$(kube get kafkatopic "$SHARED_TOPIC" --ignore-not-found -o json); then
        fail "the KafkaTopic ${SHARED_TOPIC} can't be read"
    fi
    [ -n "$topic" ] || return 0
    owner=$(jq -r '.metadata.annotations["meta.helm.sh/release-name"] // ""' <<<"$topic")
    policy=$(jq -r '.metadata.annotations["helm.sh/resource-policy"] // ""' <<<"$topic")
    if [ "$owner" = "$RELEASE" ] && [ "$policy" != "keep" ]; then
        fail "the KafkaTopic ${SHARED_TOPIC} belongs to the release ${RELEASE} without helm.sh/resource-policy: keep, so undeploying would delete it. Deploy the validation once first with make flink-deploy (same KMS), then run the redeploy. Nothing has been undeployed."
    fi
}

# ---------------------------------------------------------------- step 1

statementset_gone() {
    local left
    left=$(kube get beamsqlstatementset "$STATEMENTSET" --ignore-not-found -o name 2>/dev/null) || { echo "the statementset can't be read"; return 1; }
    [ -z "$left" ] || { echo "the statementset ${STATEMENTSET} is still there"; return 1; }
}

kafkatopics_gone() {
    local name left="" found
    for name in $OWN_KAFKATOPICS; do
        found=$(kube get kafkatopic "$name" --ignore-not-found -o name 2>/dev/null) || { echo "the KafkaTopics can't be read"; return 1; }
        [ -z "$found" ] || left="${left} ${name}"
    done
    [ -z "$left" ] || { echo "KafkaTopic left:${left}"; return 1; }
}

# The topic operator deletes a topic in Kafka asynchronously, and with
# automatic topic creation a client asking for it could bring it back
# (empty); what counts is the broker's own list.
topics_gone() {
    local list name left=""
    list=$(broker_topics) || { echo "the topics of ${KAFKA_POD} can't be listed"; return 1; }
    for name in $OWN_TOPICS; do
        if grep -qxF "$name" <<<"$list"; then left="${left} ${name}"; fi
    done
    [ -z "$left" ] || { echo "topic left in Kafka:${left}"; return 1; }
}

step_undeploy() {
    local deadline
    deadline=$(( $(date +%s) + UNDEPLOY_TIMEOUT ))
    "$MAKE" flink-undeploy "$@" || fail "make flink-undeploy failed"
    wait_until "$deadline" "$UNDEPLOY_TIMEOUT" "the statementset gone" statementset_gone
    wait_until "$deadline" "$UNDEPLOY_TIMEOUT" "the KafkaTopics gone" kafkatopics_gone
    wait_until "$deadline" "$UNDEPLOY_TIMEOUT" "the topics gone in Kafka" topics_gone
}

# ---------------------------------------------------------------- step 2

alerta_request() {  # alerta_request <method> <path?query> [json body]: prints "<code> <body>"
    local out code
    out=$(mktemp)
    if [ $# -ge 3 ]; then
        code=$(curl -s -o "$out" -w '%{http_code}' -X "$1" -H "Authorization: Key ${ALERTA_KEY}" \
            -H 'Content-Type: application/json' --data-binary "$3" "${ALERTA}/api$2") || code=000
    else
        code=$(curl -s -o "$out" -w '%{http_code}' -X "$1" -H "Authorization: Key ${ALERTA_KEY}" \
            "${ALERTA}/api$2") || code=000
    fi
    echo "$code $(tr -d '\n' < "$out")"
    rm -f "$out"
}

alerta_total() {  # alerta_total <query>: the total of matching alerts, or fails
    local answer
    answer=$(alerta_request GET "/alerts?$1&page-size=1")
    [ "${answer%% *}" = "200" ] || return 1
    jq -er '.total' <<<"${answer#* }"
}

STEP2_START=0
settled() {
    local since total
    # whole seconds: only a difference above SETTLE is sure to span it
    if [ $(( $(date +%s) - STEP2_START )) -le "$SETTLE" ]; then
        echo "the settle time of ${SETTLE}s has not passed since the undeploy"
        return 1
    fi
    since=$(date -u -d "@$(( $(date +%s) - SETTLE ))" +%Y-%m-%dT%H:%M:%S.000Z)
    total=$(alerta_total "${SHACL_FILTER}&from-date=${since}") || { echo "Alerta didn't answer"; return 1; }
    [ "$total" -eq 0 ] || { echo "${total} SHACL alerts received within the last ${SETTLE}s"; return 1; }
}

# Alerta changes at most a page of alerts per call and answers 404 once
# nothing matches the filter.
closed_all() {
    local answer code
    answer=$(alerta_request PUT "/_bulk/alerts/status?${SHACL_FILTER}&status!=closed" \
        '{"status":"closed","text":"closed by the redeploy of the SHACL validation (make flink-redeploy)"}')
    code=${answer%% *}
    case "$code" in
        404) return 0 ;;
        200) echo "more SHACL alerts left to close"; return 1 ;;
        *) echo "the bulk close answered ${code}: ${answer#* }"; return 1 ;;
    esac
}

step_close() {
    STEP2_START=$(date +%s)
    local key port code n
    key=$(kube get secret alerta -o jsonpath='{.data.alerta-admin-key}' 2>/dev/null | base64 -d) \
        || fail "the key of Alerta can't be read from the secret alerta"
    [ -n "$key" ] || fail "the key of Alerta can't be read from the secret alerta"
    ALERTA_KEY=$key
    port=${ALERTA_LOCAL_PORT:-$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')}
    kube port-forward "$ALERTA_SERVICE" "${port}:${ALERTA_PORT}" >/dev/null 2>&1 &
    FORWARD=$!
    trap 'kill "$FORWARD" 2>/dev/null || true' EXIT
    ALERTA="http://127.0.0.1:${port}"
    n=0
    while true; do
        code=$(alerta_request GET "/alerts?page-size=1")
        [ "${code%% *}" = "200" ] && break
        kill -0 "$FORWARD" 2>/dev/null || fail "Alerta not reachable: the port-forward to ${ALERTA_SERVICE} ended"
        [ "$n" -lt "$ALERTA_TIMEOUT" ] || fail "Alerta not reachable through ${ALERTA_SERVICE} within ${ALERTA_TIMEOUT}s (HTTP ${code%% *})"
        sleep 1
        n=$(( n + 1 ))
    done
    wait_until $(( $(date +%s) + SETTLE_TIMEOUT )) "$SETTLE_TIMEOUT" "no SHACL alert for ${SETTLE}s" settled
    wait_until $(( $(date +%s) + CLOSE_TIMEOUT )) "$CLOSE_TIMEOUT" "every SHACL alert closed" closed_all
    n=$(alerta_total "${SHACL_FILTER}&status!=closed") || fail "Alerta didn't answer the count of the SHACL alerts not closed"
    [ "$n" -eq 0 ] || fail "${n} SHACL alerts are still not closed"
}

# ---------------------------------------------------------------- step 3

OLD_JOB=""
NEW_JOB=""
core_services_restarted() {
    local status overview checkpoints
    status=$(kube get flinksessionjob "$CORE_SERVICES" \
        -o jsonpath='{.status.jobStatus.jobId} {.status.jobStatus.state}' 2>/dev/null) || { echo "the FlinkSessionJob can't be read"; return 1; }
    NEW_JOB=${status%% *}
    if [ -z "$NEW_JOB" ] || [ "$NEW_JOB" = "$OLD_JOB" ] || [ "${status#* }" != "RUNNING" ]; then
        echo "the FlinkSessionJob reports ${status:-nothing}, the job before was ${OLD_JOB:-none}"
        return 1
    fi
    # Exactly one running job of that name (a job that runs twice forwards
    # every alert twice), the new one, with all its tasks running.
    overview=$(flink_get /jobs/overview) || { echo "Flink doesn't answer"; return 1; }
    if ! jq -e --arg name "$CORE_SERVICES_NAME" --arg jid "$NEW_JOB" \
        '[.jobs[] | select(.state == "RUNNING" and .name == $name)]
         | length == 1 and .[0].jid == $jid and .[0].tasks.running == .[0].tasks.total' \
        <<<"$overview" >/dev/null 2>&1; then
        echo "Flink runs: $(jq -c --arg name "$CORE_SERVICES_NAME" '[.jobs[]? | select(.name == $name) | {jid, state, tasks: "\(.tasks.running)/\(.tasks.total)"}]' <<<"$overview" 2>/dev/null)"
        return 1
    fi
    # No checkpoint restored. Flink answers that checkpointing has not been
    # enabled for a job without checkpointing, which restores nothing either.
    checkpoints=$(flink_get "/jobs/${NEW_JOB}/checkpoints") || { echo "Flink doesn't answer for the checkpoints"; return 1; }
    if jq -e '.counts.restored == 0' <<<"$checkpoints" >/dev/null 2>&1 \
        || jq -e '[.errors[]? | test("not been enabled")] | any' <<<"$checkpoints" >/dev/null 2>&1; then
        return 0
    fi
    echo "the job ${NEW_JOB} restored a checkpoint or its checkpoints can't be read: ${checkpoints}"
    return 1
}

step_restart() {
    local nonce
    OLD_JOB=$(kube get flinksessionjob "$CORE_SERVICES" -o jsonpath='{.status.jobStatus.jobId}') \
        || fail "the FlinkSessionJob ${CORE_SERVICES} can't be read"
    nonce=$(kube get flinksessionjob "$CORE_SERVICES" -o jsonpath='{.spec.restartNonce}') \
        || fail "the FlinkSessionJob ${CORE_SERVICES} can't be read"
    # With upgradeMode stateless a new nonce cancels the job and submits it
    # again, without a savepoint and with a new job ID.
    nonce=$(( ${nonce:-0} + 1 ))
    kube patch flinksessionjob "$CORE_SERVICES" --type merge -p "{\"spec\":{\"restartNonce\":${nonce}}}" >/dev/null \
        || fail "the restart nonce of ${CORE_SERVICES} can't be set"
    wait_until $(( $(date +%s) + RESTART_TIMEOUT )) "$RESTART_TIMEOUT" "one new ${CORE_SERVICES_NAME} job running" core_services_restarted
    echo "${CORE_SERVICES_NAME}: job ${OLD_JOB:-none} replaced by ${NEW_JOB}"
}

# ---------------------------------------------------------------- step 4

JOB_START=""
validation_running() {
    local status job overview
    status=$(kube get beamsqlstatementset "$STATEMENTSET" -o jsonpath='{.status.state} {.status.job_id}' 2>/dev/null) \
        || { echo "the statementset can't be read"; return 1; }
    job=${status#* }
    if [ "${status%% *}" != "RUNNING" ] || [ -z "$job" ] || [ "$job" = "$status" ]; then
        echo "the statementset reports ${status:-nothing}"
        return 1
    fi
    overview=$(flink_get /jobs/overview) || { echo "Flink doesn't answer"; return 1; }
    if ! JOB_START=$(jq -er --arg jid "$job" \
        '.jobs[] | select(.jid == $jid and .state == "RUNNING" and .tasks.running == .tasks.total) | ."start-time"' \
        <<<"$overview" 2>/dev/null); then
        echo "the job ${job} doesn't run with all its tasks yet"
        return 1
    fi
    JOB_START=$(( JOB_START / 1000 ))
}

# Per connector, a snapshot that started after the job and completed: the log
# markers the platform watchdog reads ("Snapshot step 1 - Preparing", "Snapshot
# ended with SnapshotResult [status=COMPLETED"), paired within each pod's log.
snapshots_done() {
    local pods pod log c pairs pair started fed missing=""
    pods=$(kube get pods -l app.kubernetes.io/instance=kafka-connect \
        -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].state.running.startedAt}{"\n"}{end}' 2>/dev/null) \
        || { echo "the Connect pods can't be listed"; return 1; }
    for c in $CONNECTORS; do
        pairs=""
        while read -r pod started; do
            if [ -z "$pod" ] || [ -z "$started" ]; then continue; fi
            log=$(kube logs "pod/${pod}" 2>/dev/null) || continue
            pairs="${pairs}$(grep -F "[${c}|task-" <<<"$log" | awk '
                /Snapshot step 1 - Preparing/ { s = $1 " " $2 }
                /Snapshot ended with SnapshotResult \[status=COMPLETED/ { if (s != "") print s; s = "" }')"$'\n'
        done <<<"$pods"
        fed=""
        while read -r pair; do
            [ -n "$pair" ] || continue
            started=$(date -u -d "${pair%%,*}" +%s 2>/dev/null) || continue
            if [ "$started" -ge "$JOB_START" ]; then fed=yes; break; fi
        done <<<"$pairs"
        [ -n "$fed" ] || missing="${missing} ${c}"
    done
    [ -z "$missing" ] || { echo "no completed snapshot since the job started at $(date -u -d "@${JOB_START}" +%FT%TZ) for:${missing}"; return 1; }
}

# flink-deploy hides the status of its helmfile apply; the release's own
# status is the apply's result (helm keeps it as the label of its release
# secret).
release_deployed() {
    local latest
    latest=$(kube get secret -l "owner=helm,name=${RELEASE}" \
        -o jsonpath='{range .items[*]}{.metadata.labels.version} {.metadata.labels.status}{"\n"}{end}' 2>/dev/null \
        | sort -n | tail -1) || true
    [ "${latest#* }" = "deployed" ] || fail "the helm apply of the release ${RELEASE} failed: its latest revision is ${latest:-missing}"
}

step_deploy() {
    local deadline
    deadline=$(( $(date +%s) + DEPLOY_TIMEOUT ))
    "$MAKE" flink-deploy "$@" || fail "make flink-deploy failed"
    release_deployed
    wait_until "$deadline" "$DEPLOY_TIMEOUT" "the ${STATEMENTSET} job running with all its tasks" validation_running
    wait_until "$deadline" "$DEPLOY_TIMEOUT" "a complete snapshot of every connector after the job started" snapshots_done
}

# ---------------------------------------------------------------- the order

UNDEPLOYED=""
# run_step <n> <name> <function> [arguments]: the function runs in a subshell
# with errexit, so any failing command ends the step, and a step's state
# stays its own.
run_step() {
    local n=$1 name=$2 fn=$3 rc reason
    shift 3
    if [ "$n" != "0" ]; then echo "step ${n}/4 ${name}: started"; fi
    : > "$REASON_FILE"
    set +e
    ( set -e; "$fn" "$@" )
    rc=$?
    set -e
    if [ "$rc" -ne 0 ]; then
        reason=$(cat "$REASON_FILE")
        if [ "$n" = "0" ]; then
            echo "redeploy stopped before step 1/4: ${reason:-the check failed}" >&2
        else
            echo "redeploy failed in step ${n}/4 ${name}: ${reason:-a command failed (exit ${rc})}" >&2
            if [ -n "$UNDEPLOYED" ]; then
                echo "The validation is not deployed: the platform runs without SHACL validation until the redeploy is run again. After removing the cause, run in semantic-model/shacl2flink: ${COMMAND}" >&2
            fi
        fi
        exit 1
    fi
    if [ "$n" != "0" ]; then echo "step ${n}/4 ${name}: done"; fi
}

run_step 0 "check" check_shared_topic
UNDEPLOYED=yes
run_step 1 "undeploy the validation" step_undeploy "$@"
run_step 2 "close the SHACL alerts" step_close
run_step 3 "restart Core Services" step_restart
run_step 4 "deploy the validation" step_deploy "$@"
echo "redeploy done: the validation runs and has been fed a complete snapshot; the alerts of the ${SHACL_SERVICE} are those of the constraints violated now"
