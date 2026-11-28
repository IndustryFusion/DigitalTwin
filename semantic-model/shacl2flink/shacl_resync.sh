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
# Brings the SHACL alerts in Alerta in line with what the deployed validation
# finds now (`make shacl-resync`). The leaf checks write only violations, so
# nothing overwrites an alert whose constraint is satisfied now; this closes
# them all and lets a complete re-snapshot raise what is violated now. The
# validation runs with a state TTL, so it passes unchanged results on again.
#
# Steps, in this order, each after the previous one completed:
#
#   mark the validation degraded     the watchdog's ValidationConsistency warns
#   stop the job, empty its topics   REPLACE=fresh or package: nothing is replayed
#   close the SHACL alerts           service "SHACL Validator", nothing else
#   reset Core Services              its alerts filter forwards unchanged raises
#   install the new package          REPLACE=package only: its tables and chart
#   start the validation job         REPLACE=fresh: the stopped statementset;
#                                    package: the one the install created
#   trigger a complete re-snapshot   the Connect pods are deleted
#   wait until it is processed       quiet consumers, then a marker in Alerta
#   end the degraded state           the watchdog judges again
#
# A failed or timed-out step stops the resync with its name, and the watchdog
# reports it as critical until a later resync completes. Every step is safe
# to run again.
#
# Environment (time limits in seconds; exceeding one fails the step):
#   NAMESPACE                  iff
#   REPLACE                    none (default), fresh, package or checkpoint
#   RESTORE_FROM               the checkpoint or savepoint for REPLACE=checkpoint
#   RESYNC_INSTALL             REPLACE=package: the command that installs the new
#                              package (writes its tables, creates its statementset);
#                              `make flink-deploy` passes it (#1165)
#   RESYNC_INSTALL_TIMEOUT     900  the install command
#   RESYNC_STOP_TIMEOUT        300  the statementset and its job gone
#   RESYNC_SETTLE              30   no SHACL alert received after a stop
#   RESYNC_SETTLE_TIMEOUT      600  limit of the wait for the settle time
#   RESYNC_CLOSE_TIMEOUT       300  closing the SHACL alerts
#   RESYNC_RESET_TIMEOUT       600  the new Core Services job running
#   RESYNC_START_TIMEOUT       600  the new validation job running
#   RESYNC_SNAPSHOT_TIMEOUT    900  a completed snapshot of every connector
#   RESYNC_QUIET               30   the consumers quiet for this long
#   RESYNC_PROCESSED_TIMEOUT   1200 quiet consumers and the marker in Alerta
#   RESYNC_CONNECT_TIMEOUT     30   a port-forward answering
#   RESYNC_POLL                5    pause between two checks
#   RESYNC_KUBECTL_TIMEOUT     120  one kubectl call, a Kafka tool included
#   RESYNC_STATE_DIR           where a stopped statementset is kept until it
#                              runs again (~/.local/state/shacl-resync)
#   RESYNC_FORCE               true: start although another resync is marked
#                              as running

set -euo pipefail
# The work directory holds Alerta's key, the state directory the stopped
# statementset: for this user only.
umask 077

NAMESPACE=${NAMESPACE:-iff}
REPLACE=${REPLACE:-none}
RESTORE_FROM=${RESTORE_FROM:-}
STOP_TIMEOUT=${RESYNC_STOP_TIMEOUT:-300}
SETTLE=${RESYNC_SETTLE:-30}
SETTLE_TIMEOUT=${RESYNC_SETTLE_TIMEOUT:-600}
CLOSE_TIMEOUT=${RESYNC_CLOSE_TIMEOUT:-300}
RESET_TIMEOUT=${RESYNC_RESET_TIMEOUT:-600}
START_TIMEOUT=${RESYNC_START_TIMEOUT:-600}
SNAPSHOT_TIMEOUT=${RESYNC_SNAPSHOT_TIMEOUT:-900}
QUIET=${RESYNC_QUIET:-30}
PROCESSED_TIMEOUT=${RESYNC_PROCESSED_TIMEOUT:-1200}
CONNECT_TIMEOUT=${RESYNC_CONNECT_TIMEOUT:-30}
# shellcheck disable=SC2034  # read in validation_job.sh
POLL=${RESYNC_POLL:-5}
KUBECTL_TIMEOUT=${RESYNC_KUBECTL_TIMEOUT:-120}
FORCE=${RESYNC_FORCE:-false}
INSTALL=${RESYNC_INSTALL:-}
INSTALL_TIMEOUT=${RESYNC_INSTALL_TIMEOUT:-900}

STATEMENTSET=${STATEMENTSET:-shacl-validation}
STATE_CONFIGMAP=${STATE_CONFIGMAP:-platform-watchdog-state}
WATCHDOG=${WATCHDOG:-platform-watchdog}
CORE_SERVICES=${CORE_SERVICES:-core-services-job}
CORE_SERVICES_NAME=${CORE_SERVICES_NAME:-Core Services}
CONNECTORS=${CONNECTORS:-entity-table-connector rdf-table-connector}
KAFKA_POD=${KAFKA_POD:-my-cluster-nodes-0}
# The topics the validation job writes and reads back (helm/values.yaml.gotmpl,
# kafkaBridge.flink.*Topic).
JOB_TOPICS=${JOB_TOPICS:-iff.ngsild.flink.constraint_table iff.ngsild.flink.constraint_combination_table iff.ngsild.flink.constraint_trigger_table}
ALERTS_TOPIC=${ALERTS_TOPIC:-iff.alerts}
# What Core Services consumes: iff.alerts.bulk (CoreServices.java) and the
# tables of its SQL (table_definition.sql). Known before its new job has read
# anything, when its sources report no topic yet.
CORE_SERVICES_TOPICS=${CORE_SERVICES_TOPICS:-iff.alerts.bulk iff.ngsild.attributes iff.ngsild.attributes_insert}
# Core Services reads iff.alerts.bulk from the latest offset
# (CoreServices.java), as the validation reads its entities and attributes
# (LATEST_SOURCES, validation_job.sh): its reader must hold its partition
# before the re-snapshot, or the raises written before that are never
# forwarded.
CORE_LATEST_SOURCES=${RESYNC_CORE_LATEST_SOURCES:-iff.alerts.bulk}
DEBEZIUM_BRIDGE_GROUP=${DEBEZIUM_BRIDGE_GROUP:-debeziumBridgeGroup}
# The knowledge: Debezium copies the Postgres table rdf to RDF_TOPIC, which the
# validation reads as an upsert table keyed by subject, predicate and index.
RDF_TOPIC=${RDF_TOPIC:-iff.rdf}
RDF_DB_SERVICE=${RDF_DB_SERVICE:-acid-cluster}
RDF_DB_USER=${RDF_DB_USER:-flink_writer_user}
RDF_DB_NAME=${RDF_DB_NAME:-flink}
SHACL_FILTER="service=SHACL%20Validator"
# Every status but closed, as alternatives of one filter: Alerta takes a key
# given several times as any of its values.
NOT_CLOSED="status=open&status=assign&status=ack&status=shelved&status=blackout&status=expired&status=unknown"
STATE_DIR=${RESYNC_STATE_DIR:-${XDG_STATE_HOME:-${HOME}/.local/state}/shacl-resync}
SAVED="${STATE_DIR}/${NAMESPACE}.${STATEMENTSET}.json"
COMMAND="make shacl-resync REPLACE=${REPLACE}"
# A replacement by a new package is run by the deploy of that package, and
# only that deploy can run it again: a fresh restart would start the old
# statements on the new tables.
if [ "$REPLACE" = package ]; then
    COMMAND="make flink-deploy"
fi

# ---------------------------------------------------------------- the options

case "$REPLACE" in
    none|fresh) ;;
    package)
        if [ -z "$INSTALL" ]; then
            echo "resync refused before step 1: REPLACE=package needs RESYNC_INSTALL, the command that installs the new package; make flink-deploy passes it. Nothing has been changed." >&2
            exit 2
        fi ;;
    checkpoint)
        # Refused before anything is read or changed (#1042).
        cat >&2 <<EOF
resync refused before step 1: REPLACE=checkpoint${RESTORE_FROM:+ RESTORE_FROM=${RESTORE_FROM}} is not supported yet, see #1042.
The statementset can't be started from a given checkpoint yet. Missing:
  1. the BeamSqlStatementSet has no field naming a checkpoint or savepoint to start from;
  2. the validation takes no retained checkpoints: checkpointing is off unless the
     chart is built with CHECKPOINT=true, and externalized checkpoints are not configured;
  3. the operator's only savepoint path (updateStrategy savepoint) passes the location
     as an SQL string, while the submit job reads every setting as a map.
The topics would also have to hold the records since the checkpoint (their retention
is one hour). A job that Flink restored by itself is resynced with REPLACE=none.
Nothing has been changed.
EOF
        exit 2 ;;
    *)
        echo "resync refused before step 1: REPLACE must be none, fresh, package or checkpoint, not '${REPLACE}'. Nothing has been changed." >&2
        exit 2 ;;
esac

WORK=$(mktemp -d)
RESYNC_BASE="${WORK}/base.core"
# The same for a new validation job's latest-offset readers (step_start).
VALIDATION_BASE="${WORK}/base.validation"
ALERTA_HEADER="${WORK}/alerta.header"
# The validation's latest-offset sources (LATEST_SOURCES, entities and
# attributes unless RESYNC_LATEST_SOURCES names others) and the helpers come
# from validation_job.sh, which restart_connect.sh sources as well.
LATEST_SOURCES=${RESYNC_LATEST_SOURCES:-}
# shellcheck disable=SC1091
. "$(dirname "${BASH_SOURCE[0]}")/validation_job.sh"
trap cleanup_work EXIT

T0=$(date +%s)
if [ "$REPLACE" = fresh ]; then
    STEPS=("mark the validation degraded" "stop the validation job and empty its topics"
        "close the SHACL alerts" "reset Core Services" "start the validation job"
        "trigger a complete re-snapshot" "wait until the re-snapshot is processed"
        "end the degraded state")
elif [ "$REPLACE" = package ]; then
    STEPS=("mark the validation degraded" "stop the validation job and empty its topics"
        "close the SHACL alerts" "reset Core Services" "install the new package"
        "start the new package's validation job"
        "trigger a complete re-snapshot" "wait until the re-snapshot is processed"
        "end the degraded state")
else
    STEPS=("mark the validation degraded" "close the SHACL alerts" "reset Core Services"
        "trigger a complete re-snapshot" "wait until the re-snapshot is processed"
        "end the degraded state")
fi
TOTAL=${#STEPS[@]}
# The watchdog takes a resync still marked as running after this as failed:
# the sum of what each step can take, waits and single calls, plus a margin.
# Every step starts with a mark and a post (kubectl, Alerta's 30 s); the
# reset waits for the job and its reader and reads three topics; the stop
# waits for the statementset and the job and empties three topics (60 s each
# besides two Kafka calls); the start waits for the job and its readers.
CALL=$(( KUBECTL_TIMEOUT + 30 ))
DEADLINE=$(( T0 + TOTAL * CALL + 2 * CONNECT_TIMEOUT \
    + CALL + CLOSE_TIMEOUT \
    + 2 * RESET_TIMEOUT + 4 * KUBECTL_TIMEOUT \
    + SNAPSHOT_TIMEOUT + KUBECTL_TIMEOUT \
    + PROCESSED_TIMEOUT + 2 * KUBECTL_TIMEOUT \
    + KUBECTL_TIMEOUT + 300 ))
if [ "$REPLACE" = fresh ] || [ "$REPLACE" = package ]; then
    DEADLINE=$(( DEADLINE + 2 * STOP_TIMEOUT + 3 * (60 + 3 * KUBECTL_TIMEOUT) + SETTLE_TIMEOUT \
        + 2 * START_TIMEOUT + 2 * KUBECTL_TIMEOUT ))
fi
if [ "$REPLACE" = package ]; then
    # the install and the wait for the statementset it creates
    DEADLINE=$(( DEADLINE + INSTALL_TIMEOUT + START_TIMEOUT ))
fi

# ---------------------------------------------------------------- helpers

# fail <reason>: ends the step it is called in, with this reason
fail() {
    echo "$*" > "${WORK}/reason"
    exit 1
}

fmt() {
    date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ
}

# The Kafka tools run in the broker pod with a small heap, one at a time, as
# tools/ttl_test.py runs them. Standard input goes to the tool.
kafka_tool() {  # kafka_tool <tool> <arguments>: a tool that reads no input
    # No -i, and no stdin at all. With -i, kubectl got the resync's own stdin,
    # a terminal when run by hand; timeout runs it in a background process
    # group, so the kernel stopped it with SIGTTIN and the resync hung (#1195).
    kube exec "$KAFKA_POD" -- sh -c "KAFKA_HEAP_OPTS='-Xmx192M' bin/$1 --bootstrap-server localhost:9092 $2" </dev/null
}

kafka_feed() {  # <input> | kafka_feed <tool> <arguments>: a tool that reads the piped input
    kube exec -i "$KAFKA_POD" -- sh -c "KAFKA_HEAP_OPTS='-Xmx192M' bin/$1 --bootstrap-server localhost:9092 $2"
}

# offsets <topic> <time>: "<partition> <offset>" per partition, -1 the end,
# -2 the start
offsets() {
    local out
    out=$(kafka_tool kafka-get-offsets.sh "--topic $1 --time $2" 2>/dev/null) || return 1
    awk -F: -v t="$1" 'NF >= 3 && $(NF-2) == t { print $(NF-1), $NF }' <<<"$out"
}

alerta_total() {  # alerta_total <query>: the total of matching alerts, or fails
    local answer
    answer=$(http alerta GET "/api/alerts?$1&page-size=1")
    [ "${answer%% *}" = "200" ] || return 1
    jq -er '.total' <<<"${answer#* }"
}

# ---------------------------------------------------------------- the watchdog's marks

# The marks live in the watchdog's ConfigMap; the watchdog reads them and
# leaves them alone when it writes its own state. A null removes a mark.
set_marks() {  # set_marks <json object>
    kube patch configmap "$STATE_CONFIGMAP" --type merge -p "$(jq -c '{data: .}' <<<"$1")" >/dev/null
}

# A mark's text goes into the watchdog's alerts as it is: no quotes, no
# backslashes, no control characters, one line.
plain() {
    tr '\t\n\r"\134' "   '/" <<<"$*" | tr -d '\000-\037\177' | sed 's/ *$//'
}

# post_consistency <severity> <value> <text> [timeout]: ValidationConsistency
# as the watchdog posts it, so that the watchdog's next run carries it on.
post_consistency() {
    local payload answer
    payload=$(jq -nc --arg sev "$1" --arg value "$2" --arg text "$3" --arg env "$ENVIRONMENT" \
        --arg res "$STATEMENTSET" --arg timeout "${4:-}" \
        '{resource: $res, event: "ValidationConsistency", environment: $env, severity: $sev,
          service: ["System"], origin: "shacl-resync", value: $value, text: $text}
         + (if $timeout == "" then {} else {timeout: ($timeout | tonumber)} end)')
    answer=$(http alerta POST /api/alert "$payload")
    case "${answer%% *}" in
        2*) return 0 ;;
        *) echo "ValidationConsistency could not be posted to Alerta (HTTP ${answer%% *})" >&2; return 1 ;;
    esac
}

degraded_text() {  # degraded_text <step>
    echo "DEGRADED -- RESYNC IN PROGRESS since $(fmt "$T0"), step $1: the SHACL alerts are incomplete until the resync has completed."
}

# ---------------------------------------------------------------- the check before step 1

step_check() {
    local ss marks since failed deadline parts
    ss=$(kube get beamsqlstatementset "$STATEMENTSET" --ignore-not-found -o json) \
        || fail "the statementset ${STATEMENTSET} can't be read"
    if [ "$REPLACE" = package ]; then
        # The new package replaces whatever is deployed or kept: a statementset
        # kept by an earlier failed resync is not started again.
        if [ -s "$SAVED" ]; then
            echo "a statementset kept by an earlier resync in ${SAVED} is discarded: the new package replaces it"
            rm -f "$SAVED"
        fi
        if [ -z "$ss" ]; then
            echo "no validation statementset ${STATEMENTSET} is deployed: nothing to stop, the new package is installed"
            touch "${WORK}/nothing_deployed"
        fi
    elif [ -z "$ss" ]; then
        if [ "$REPLACE" = fresh ] && [ -s "$SAVED" ]; then
            # A failed resync stopped the job and did not start it again.
            echo "the statementset ${STATEMENTSET} is not deployed: it was stopped by a resync and is started again from ${SAVED}"
            touch "${WORK}/stopped"
            date +%s > "${WORK}/stopped_at"
        elif [ -s "$SAVED" ]; then
            fail "no validation statementset ${STATEMENTSET} is deployed in ${NAMESPACE}: a resync stopped it and did not start it again. make shacl-resync REPLACE=fresh starts it from ${SAVED}. Nothing has been changed."
        else
            fail "no validation statementset ${STATEMENTSET} is deployed in ${NAMESPACE}: deploy the validation first (make flink-deploy), then run the resync. Nothing has been changed."
        fi
    fi
    marks=$(kube get configmap "$STATE_CONFIGMAP" -o json | jq -c '.data // {}') \
        || fail "the ConfigMap ${STATE_CONFIGMAP} of the platform watchdog can't be read: deploy the alerta chart with the platform watchdog first. Nothing has been changed."
    since=$(jq -r '.resync_since // empty' <<<"$marks")
    failed=$(jq -r '.resync_failed // empty' <<<"$marks")
    deadline=$(jq -r '.resync_deadline // empty' <<<"$marks")
    if [ -n "$since" ] && [ -z "$failed" ] && [[ "$deadline" =~ ^[0-9]+$ ]] && [ "$deadline" -gt "$(date +%s)" ] \
        && [ "$FORCE" != true ]; then
        fail "another resync is marked as running since $(fmt "$since"), in step $(jq -r '.resync_step // "?"' <<<"$marks"), until $(fmt "$deadline"). Wait for it, or run with RESYNC_FORCE=true if it no longer runs. Nothing has been changed."
    fi
    # The marker behind Core Services' records proves the alerta-bridge
    # posted them only on a topic with one partition, which it reads in order.
    parts=$(offsets "$ALERTS_TOPIC" -1) || fail "the partitions of ${ALERTS_TOPIC} can't be read from ${KAFKA_POD}"
    parts=$(grep -c . <<<"$parts" || true)
    if [ "$parts" -eq 0 ]; then
        fail "the topic ${ALERTS_TOPIC} is not found in Kafka. Nothing has been changed."
    elif [ "$parts" -ne 1 ]; then
        fail "the topic ${ALERTS_TOPIC} has ${parts} partitions; the resync can tell that the alerta-bridge has posted every alert only on a topic with one partition, so it does not run. Nothing has been changed."
    fi
    ENVIRONMENT=$(kube get cronjob "$WATCHDOG" \
        -o jsonpath='{.spec.jobTemplate.spec.template.spec.containers[0].env[?(@.name=="ENVIRONMENT")].value}' 2>/dev/null) || ENVIRONMENT=""
    echo "${ENVIRONMENT:-Development}" > "${WORK}/environment"
    # curl reads a header from a file (-H @file) from 7.55 on.
    if ! printf '%s\n' 7.55.0 "$(curl --version | awk 'NR == 1 { print $2 }')" | sort -C -V; then
        fail "curl $(curl --version | awk 'NR == 1 { print $2 }') can't read a header from a file; the resync needs curl 7.55 or later. Nothing has been changed."
    fi
    local key
    key=$(kube get secret alerta -o jsonpath='{.data.alerta-admin-key}' | base64 -d) \
        || fail "the key of Alerta can't be read from the secret alerta"
    [ -n "$key" ] || fail "the key of Alerta can't be read from the secret alerta"
    printf 'Authorization: Key %s\n' "$key" > "$ALERTA_HEADER"
    chmod 600 "$ALERTA_HEADER"
}

# ---------------------------------------------------------------- mark the validation degraded

step_mark() {
    set_marks "$(jq -nc --arg since "$T0" --arg step "$1" --arg deadline "$DEADLINE" \
        '{resync_since: $since, resync_step: $step, resync_deadline: $deadline, resync_failed: null}')" \
        || fail "the marks can't be written to the ConfigMap ${STATE_CONFIGMAP}"
    post_consistency warning "resync in progress" "$(degraded_text "$1")" \
        || fail "Alerta not reachable: ValidationConsistency can't be posted"
}

# ---------------------------------------------------------------- stop the validation job

statementset_gone() {
    local left
    left=$(kube get beamsqlstatementset "$STATEMENTSET" --ignore-not-found -o name 2>/dev/null) \
        || { echo "the statementset can't be read"; return 1; }
    [ -z "$left" ] || { echo "the statementset ${STATEMENTSET} is still there"; return 1; }
}

job_stopped() {  # job_stopped <job id>
    local answer state
    answer=$(http flink GET "/jobs/$1")
    case "${answer%% *}" in
        404) return 0 ;;
        200) state=$(jq -r '.state // empty' <<<"${answer#* }") ;;
        *) echo "Flink doesn't answer for the job $1"; return 1 ;;
    esac
    case "$state" in
        CANCELED|FAILED|FINISHED) return 0 ;;
        *) echo "the job $1 is ${state:-in no state}"; return 1 ;;
    esac
}

topic_emptied() {  # topic_emptied <topic> <file of "<partition> <end>">
    local starts p end start left=""
    starts=$(offsets "$1" -2) || { echo "the start offsets of $1 can't be read"; return 1; }
    while read -r p end; do
        [ -n "$p" ] || continue
        start=$(awk -v p="$p" '$1 == p { print $2 }' <<<"$starts")
        if [ -z "$start" ] || [ "$start" -lt "$end" ]; then left="${left} $1-${p} starts at ${start:-?}, not ${end};"; fi
    done < "$2"
    [ -z "$left" ] || { echo "records left:${left}"; return 1; }
}

topic_exists() {  # topic_exists <topic>: it is in Kafka
    local list
    list=$(kafka_tool kafka-topics.sh "--list" 2>/dev/null) || fail "the topics can't be listed from ${KAFKA_POD}"
    grep -qxF "$1" <<<"$list"
}
empty_topic() {  # empty_topic <topic>
    local ends json
    ends=$(offsets "$1" -1) || fail "the end offsets of $1 can't be read"
    [ -n "$ends" ] || fail "the topic $1 has no partitions in Kafka"
    echo "$ends" > "${WORK}/ends"
    json=$(awk -v t="$1" '$2 > 0 { printf "%s{\"topic\":\"%s\",\"partition\":%d,\"offset\":%d}", (n++ ? "," : ""), t, $1, $2 }' \
        "${WORK}/ends")
    if [ -n "$json" ]; then
        # The file goes to the pod through standard input; the tool reads it there.
        printf '{"version":1,"partitions":[%s]}' "$json" \
            | kube exec -i "$KAFKA_POD" -- sh -c "cat > /tmp/shacl-resync-offsets.json && KAFKA_HEAP_OPTS='-Xmx192M' bin/kafka-delete-records.sh --bootstrap-server localhost:9092 --offset-json-file /tmp/shacl-resync-offsets.json; rc=\$?; rm -f /tmp/shacl-resync-offsets.json; exit \$rc" >/dev/null \
            || fail "the records of $1 can't be deleted"
    fi
    wait_until 60 "$1 emptied" topic_emptied "$1" "${WORK}/ends"
    if [ -n "$json" ]; then
        echo "  $1: the records $(awk '$2 > 0 { printf "%sof partition %s up to %s", (n++ ? ", " : ""), $1, $2 }' "${WORK}/ends") deleted"
    else
        echo "  $1: no records"
    fi
}

step_stop() {
    local ss job topic
    if [ "$REPLACE" = package ] && [ -e "${WORK}/nothing_deployed" ]; then
        echo "  no validation job to stop: no statementset ${STATEMENTSET} is deployed"
        touch "${WORK}/stopped"
    elif [ "$REPLACE" = package ] && [ ! -e "${WORK}/stopped" ]; then
        ss=$(kube get beamsqlstatementset "$STATEMENTSET" -o json) || fail "the statementset ${STATEMENTSET} can't be read"
        job=$(jq -r '.status.job_id // empty' <<<"$ss")
        echo "${job}" > "${WORK}/stopped_job"
        # The new package's statementset replaces it: no copy is kept.
        kube delete beamsqlstatementset "$STATEMENTSET" --wait=false >/dev/null \
            || fail "the statementset ${STATEMENTSET} can't be deleted"
        touch "${WORK}/stopped"
        date +%s > "${WORK}/stopped_at"
        wait_until "$STOP_TIMEOUT" "the statementset gone" statementset_gone
        if [ -n "$job" ]; then
            wait_until "$STOP_TIMEOUT" "the job ${job} stopped" job_stopped "$job"
        fi
        echo "  the job ${job:-none} of ${STATEMENTSET} is stopped; the new package replaces it"
    elif [ ! -e "${WORK}/stopped" ]; then
        ss=$(kube get beamsqlstatementset "$STATEMENTSET" -o json) || fail "the statementset ${STATEMENTSET} can't be read"
        job=$(jq -r '.status.job_id // empty' <<<"$ss")
        # 0700, an existing one included; the copy is 0600
        mkdir -p "$STATE_DIR"
        chmod 700 "$STATE_DIR"
        # The release's labels and annotations stay, so helm keeps owning it.
        jq '{apiVersion, kind, metadata: {name: .metadata.name, namespace: .metadata.namespace,
                labels: (.metadata.labels // {}), annotations: ((.metadata.annotations // {})
                    | del(.["kubectl.kubernetes.io/last-applied-configuration"]))},
             spec} | .metadata.annotations["shacl-resync/stopped-job"] = $job' --arg job "$job" <<<"$ss" > "${SAVED}.new"
        # explicitly too: a default ACL of the directory overrides the umask
        chmod 600 "${SAVED}.new"
        mv "${SAVED}.new" "$SAVED"
        # The operator's delete handler cancels the job and lets the resource
        # go only when Flink confirmed the cancellation.
        kube delete beamsqlstatementset "$STATEMENTSET" --wait=false >/dev/null \
            || fail "the statementset ${STATEMENTSET} can't be deleted"
        touch "${WORK}/stopped"
        date +%s > "${WORK}/stopped_at"
        wait_until "$STOP_TIMEOUT" "the statementset gone" statementset_gone
        if [ -n "$job" ]; then
            wait_until "$STOP_TIMEOUT" "the job ${job} stopped" job_stopped "$job"
        fi
        echo "  the job ${job:-none} of ${STATEMENTSET} is stopped; the statementset is kept in ${SAVED}"
    fi
    for topic in $JOB_TOPICS; do
        # A first deploy installs the validation's topics only in the install
        # step: one that doesn't exist yet holds nothing to replay.
        if [ "$REPLACE" = package ] && ! topic_exists "$topic"; then
            echo "  ${topic}: not created yet, nothing to empty"
            continue
        fi
        empty_topic "$topic"
    done
}

# ---------------------------------------------------------------- close the SHACL alerts

settled() {
    local since total stopped_at
    stopped_at=$(cat "${WORK}/stopped_at")
    # whole seconds: only a difference above SETTLE is sure to span it
    if [ $(( $(date +%s) - stopped_at )) -le "$SETTLE" ]; then
        echo "the settle time of ${SETTLE}s has not passed since the job was stopped"
        return 1
    fi
    since=$(date -u -d "@$(( $(date +%s) - SETTLE ))" +%Y-%m-%dT%H:%M:%S.000Z)
    total=$(alerta_total "${SHACL_FILTER}&from-date=${since}") || { echo "Alerta didn't answer"; return 1; }
    [ "$total" -eq 0 ] || { echo "${total} SHACL alerts received within the last ${SETTLE}s"; return 1; }
}

step_close() {
    local answer code deadline n before pages
    answer=$(http alerta GET "/api/alerts?page-size=1")
    [ "${answer%% *}" = "200" ] || fail "Alerta not reachable through ${ALERTA_SERVICE} (HTTP ${answer%% *})"
    # Raises the stopped job wrote just before it stopped reach Alerta before
    # the close, not after it. While the job runs, a raise is live.
    if [ -e "${WORK}/stopped" ]; then
        wait_until "$SETTLE_TIMEOUT" "no SHACL alert for ${SETTLE}s" settled
    fi
    before=$(alerta_total "${SHACL_FILTER}&${NOT_CLOSED}") || fail "Alerta didn't answer the count of the SHACL alerts not closed"
    echo "  ${before} SHACL alerts are not closed"
    # Alerta changes at most a page of alerts per call and answers 404 once
    # nothing matches the filter.
    deadline=$(( $(date +%s) + CLOSE_TIMEOUT ))
    pages=0
    while true; do
        answer=$(http alerta PUT "/api/_bulk/alerts/status?${SHACL_FILTER}&${NOT_CLOSED}" \
            '{"status":"closed","text":"closed by the resync of the SHACL alerts (make shacl-resync)"}')
        code=${answer%% *}
        case "$code" in
            404) break ;;
            200) pages=$(( pages + 1 )) ;;
            000) fail "Alerta not reachable through ${ALERTA_SERVICE}" ;;
            *) fail "the bulk close answered ${code}: ${answer#* }" ;;
        esac
        [ "$(date +%s)" -lt "$deadline" ] || fail "SHACL alerts still left to close after ${CLOSE_TIMEOUT}s"
    done
    if [ "$before" -gt 0 ] && [ "$pages" -eq 0 ]; then
        fail "the bulk close matched none of the ${before} SHACL alerts that are not closed"
    fi
    n=$(alerta_total "${SHACL_FILTER}&${NOT_CLOSED}") || fail "Alerta didn't answer the count of the SHACL alerts not closed"
    [ "$n" -eq 0 ] || fail "${n} SHACL alerts are still not closed"
    echo "  closed ${before} SHACL alerts in ${pages} requests"
}

# ---------------------------------------------------------------- reset Core Services

core_services_restarted() {  # core_services_restarted <job before>
    local status job overview checkpoints
    status=$(kube get flinksessionjob "$CORE_SERVICES" \
        -o jsonpath='{.status.jobStatus.jobId} {.status.jobStatus.state}' 2>/dev/null) \
        || { echo "the FlinkSessionJob can't be read"; return 1; }
    job=${status%% *}
    if [ -z "$job" ] || [ "$job" = "$1" ] || [ "${status#* }" != "RUNNING" ]; then
        echo "the FlinkSessionJob reports ${status:-nothing}, the job before was ${1:-none}"
        return 1
    fi
    # Exactly one running job of that name (a job that runs twice forwards
    # every alert twice), the new one, with all its tasks running.
    overview=$(flink_get /jobs/overview) || { echo "Flink doesn't answer"; return 1; }
    if ! jq -e --arg name "$CORE_SERVICES_NAME" --arg jid "$job" \
        '[.jobs[] | select(.state == "RUNNING" and .name == $name)]
         | length == 1 and .[0].jid == $jid and .[0].tasks.running == .[0].tasks.total' \
        <<<"$overview" >/dev/null 2>&1; then
        echo "Flink runs: $(jq -c --arg name "$CORE_SERVICES_NAME" '[.jobs[]? | select(.name == $name) | {jid, state, tasks: "\(.tasks.running)/\(.tasks.total)"}]' <<<"$overview" 2>/dev/null)"
        return 1
    fi
    # No checkpoint restored. A job without checkpointing restores nothing
    # either; Flink then answers that checkpointing has not been enabled.
    checkpoints=$(http flink GET "/jobs/${job}/checkpoints")
    if jq -e '.counts.restored == 0' <<<"${checkpoints#* }" >/dev/null 2>&1 \
        || jq -e '[.errors[]? | test("not been enabled")] | any' <<<"${checkpoints#* }" >/dev/null 2>&1; then
        echo "$job" > "${WORK}/cs_job"
        return 0
    fi
    echo "the job ${job} restored a checkpoint or its checkpoints can't be read: ${checkpoints}"
    return 1
}

step_reset() {
    local old nonce t
    old=$(kube get flinksessionjob "$CORE_SERVICES" -o jsonpath='{.status.jobStatus.jobId}') \
        || fail "the FlinkSessionJob ${CORE_SERVICES} can't be read"
    nonce=$(kube get flinksessionjob "$CORE_SERVICES" -o jsonpath='{.spec.restartNonce}') \
        || fail "the FlinkSessionJob ${CORE_SERVICES} can't be read"
    # With upgradeMode stateless a new nonce cancels the job and submits it
    # again, without state and with a new job ID.
    nonce=$(( ${nonce:-0} + 1 ))
    kube patch flinksessionjob "$CORE_SERVICES" --type merge -p "{\"spec\":{\"restartNonce\":${nonce}}}" >/dev/null \
        || fail "the restart nonce of ${CORE_SERVICES} can't be set"
    wait_until "$RESET_TIMEOUT" "one new ${CORE_SERVICES_NAME} job running" core_services_restarted "$old"
    echo "  ${CORE_SERVICES_NAME}: job ${old:-none} replaced by $(cat "${WORK}/cs_job")"
    # RUNNING is not yet reading: its reader of iff.alerts.bulk starts at the
    # latest offset when it gets its split, as the validation's readers do
    # (step 5). Raises written before that would never be forwarded.
    wait_until "$RESET_TIMEOUT" "the reader of ${CORE_LATEST_SOURCES// /, } of the new ${CORE_SERVICES_NAME} job placed" \
        sources_placed "$(cat "${WORK}/cs_job")" "$CORE_LATEST_SOURCES"
    echo "  its reader of ${CORE_LATEST_SOURCES// /, } is placed"
    # What was in iff.alerts.bulk before the reader was placed is not left for
    # it to read; its sources report no offset until they read a record.
    : > "$RESYNC_BASE"
    for t in $CORE_SERVICES_TOPICS; do
        offsets "$t" -1 | awk -v t="$t" '{ print t, $1, $2 }' >> "$RESYNC_BASE" \
            || fail "the end offsets of ${t}, a source of ${CORE_SERVICES_NAME}, can't be read from ${KAFKA_POD}"
    done
}

# ---------------------------------------------------------------- start the validation job

# ---------------------------------------------------------------- install the new package

# REPLACE=package: the deploy's command writes the package's tables and
# creates its statementset, while no job reads the tables and Core Services
# has been reset. Its output is shown; a failure or an exceeded limit ends
# the step.
step_install() {
    local rc
    set +e
    timeout --kill-after=30 "$INSTALL_TIMEOUT" bash -c "$INSTALL"
    rc=$?
    set -e
    [ "$rc" -ne 124 ] || fail "the install of the new package did not end within ${INSTALL_TIMEOUT}s"
    [ "$rc" -eq 0 ] || fail "the install of the new package failed (exit ${rc})"
    echo "  the new package is installed"
    drop_removed_knowledge
}

# The keys of the rdf table as JSON, one per line, sorted: what the new
# package's knowledge is.
rdf_table_keys() {
    local secrets secret password pod
    # Read the whole list first: `kube get … | grep -m1` let kubectl die of
    # SIGPIPE when grep stopped early, and pipefail took that as a failure.
    secrets=$(kube get secrets -o name) || { echo "the secrets can't be listed"; return 1; }
    secret=$(grep -m1 -- "${RDF_DB_USER//_/-}" <<<"$secrets") \
        || { echo "no secret of ${RDF_DB_USER}"; return 1; }
    password=$(kube get "$secret" -o go-template='{{index .data "password" | base64decode}}') || return 1
    pod=$(kube get ep "$RDF_DB_SERVICE" -o jsonpath='{.subsets[0].addresses[0].targetRef.name}' 2>/dev/null) \
        || { echo "no endpoint of ${RDF_DB_SERVICE}"; return 1; }
    kube exec "$pod" -c postgres -- bash -c "PGPASSWORD='${password}' PGSSLMODE=require psql -h localhost -U ${RDF_DB_USER} -d ${RDF_DB_NAME} -Atc \"SELECT json_build_object('subject', subject, 'predicate', predicate, 'index', index) FROM rdf\"" </dev/null
}

# removed_keys <table keys> <topic records>: the keys live in the topic (the
# last record of the key not a tombstone, "null" as the consumer prints it)
# and not in the table, each as written in the topic. Both sides compared as
# parsed JSON, so the formatting of Postgres and of Debezium doesn't matter.
removed_keys() {
    python3 -c '
import json, sys
def norm(text):
    d = json.loads(text)
    return (d["subject"], d["predicate"], int(d["index"]))
table = set()
with open(sys.argv[1], encoding="utf-8") as f:
    for line in f:
        if line.strip():
            table.add(norm(line))
last = {}
with open(sys.argv[2], encoding="utf-8") as f:
    for line in f:
        key, _, value = line.rstrip("\n").partition("\t")
        if key:
            last[key] = value
live = 0
for key, value in last.items():
    if value == "null":
        continue
    try:
        k = norm(key)
    except (ValueError, KeyError, TypeError):
        continue
    live += 1
    if k not in table:
        print(key)
print(live, file=sys.stderr)
' "$1" "$2"
}

# A dropped table emits no deletes, so RDF_TOPIC keeps every key any earlier
# package had, and a new job, which reads it from the beginning, sees them all
# (#1165 D6). Each key that is live in RDF_TOPIC (its last record is not a
# tombstone) and not in the new table gets a tombstone: the upsert table drops
# it, in a running job as in a new one.
drop_removed_knowledge() {
    local tab
    tab=$(printf '\t')
    rdf_table_keys > "${WORK}/rdf.table" || fail "the keys of the rdf table can't be read"
    # An empty table would turn every key into a tombstone: refuse instead.
    [ -s "${WORK}/rdf.table" ] || fail "the rdf table is empty or can't be read: no knowledge is removed"
    # From the earliest offset to the end taken now: exactly those records, so
    # the read ends on a topic that is written to meanwhile. The timeout only
    # guards a consumer that gets stuck.
    local start end
    start=$(offsets "$RDF_TOPIC" -2 | awk 'NR == 1 { print $2 }') || fail "the start offset of ${RDF_TOPIC} can't be read"
    end=$(offsets "$RDF_TOPIC" -1 | awk 'NR == 1 { print $2 }') || fail "the end offset of ${RDF_TOPIC} can't be read"
    [ "$(offsets "$RDF_TOPIC" -1 | wc -l)" -eq 1 ] || fail "${RDF_TOPIC} has more than one partition"
    : > "${WORK}/rdf.topic"
    if [ "$(( end - start ))" -gt 0 ]; then
        kafka_tool kafka-console-consumer.sh "--topic ${RDF_TOPIC} --from-beginning --max-messages $(( end - start )) --timeout-ms 60000 --property print.key=true --property key.separator='${tab}'" \
            > "${WORK}/rdf.topic" 2>/dev/null || true
        [ "$(grep -c . "${WORK}/rdf.topic")" -ge "$(( end - start ))" ] \
            || fail "only $(grep -c . "${WORK}/rdf.topic") of the $(( end - start )) records of ${RDF_TOPIC} could be read"
    fi
    # The key is kept as written, so its tombstone has exactly its bytes.
    removed_keys "${WORK}/rdf.table" "${WORK}/rdf.topic" > "${WORK}/rdf.drop" 2> "${WORK}/rdf.live" \
        || fail "the keys of ${RDF_TOPIC} can't be compared with the rdf table"
    if [ -s "${WORK}/rdf.drop" ]; then
        sed "s/\$/${tab}__shacl_resync_tombstone__/" "${WORK}/rdf.drop" \
            | kafka_feed kafka-console-producer.sh "--topic ${RDF_TOPIC} --property parse.key=true --property key.separator='${tab}' --property null.marker=__shacl_resync_tombstone__" >/dev/null \
            || fail "the tombstones of the removed knowledge can't be written to ${RDF_TOPIC}"
    fi
    echo "  the knowledge: $(grep -c . "${WORK}/rdf.table") triples in the new package; $(cat "${WORK}/rdf.live") live keys in ${RDF_TOPIC}, $(grep -c . "${WORK}/rdf.drop" || true) of them removed by a tombstone"
}

statementset_exists() {
    [ -n "$(kube get beamsqlstatementset "$STATEMENTSET" --ignore-not-found -o name 2>/dev/null)" ] \
        || { echo "no statementset ${STATEMENTSET} yet"; return 1; }
}

step_start() {
    local old
    if [ "$REPLACE" = package ]; then
        old=$(cat "${WORK}/stopped_job" 2>/dev/null || true)
        wait_until "$START_TIMEOUT" "the new package's statementset created" statementset_exists
    else
        [ -s "$SAVED" ] || fail "the stopped statementset is not kept in ${SAVED}"
        old=$(jq -r '.metadata.annotations["shacl-resync/stopped-job"] // empty' "$SAVED")
        if [ -z "$(kube get beamsqlstatementset "$STATEMENTSET" --ignore-not-found -o name)" ]; then
            jq 'del(.metadata.annotations["shacl-resync/stopped-job"])' "$SAVED" | kube create -f - >/dev/null \
                || fail "the statementset ${STATEMENTSET} can't be created from ${SAVED}"
        fi
    fi
    touch "${WORK}/started"
    wait_until "$START_TIMEOUT" "the ${STATEMENTSET} job running with all its tasks" validation_running "$old"
    rm -f "$SAVED"
    echo "  ${STATEMENTSET}: job ${old:-none} replaced by $(cat "${WORK}/ss_job")"
    # RUNNING is not yet reading: a reader resolves the latest offset of its
    # partition only when its split is assigned. A snapshot written before
    # that is skipped for good (an entity seen without its attributes raises
    # a count that the next snapshot, ttl/2 later, would clear). A reader
    # registers the metrics of a partition once it has its split.
    wait_until "$START_TIMEOUT" "the latest-offset sources of the new job placed" sources_placed "$(cat "${WORK}/ss_job")"
    echo "  its readers of ${LATEST_SOURCES// /, } are placed"
    # What was in those topics before the readers were placed is not left for
    # them to read, as for Core Services (RESYNC_BASE): a reader reports no
    # offset until it reads a record, and without a base the processed step
    # waited for it to read records that came before it (the CI deploy suite,
    # attributes written by an earlier suite for entities the snapshot has no
    # attributes of).
    : > "$VALIDATION_BASE"
    for t in $LATEST_SOURCES; do
        offsets "$t" -1 | awk -v t="$t" '{ print t, $1, $2 }' >> "$VALIDATION_BASE" \
            || fail "the end offsets of ${t}, a latest-offset source of the validation, can't be read from ${KAFKA_POD}"
    done
}

# ---------------------------------------------------------------- the re-snapshot

# Per connector, a snapshot that started after the resync began and completed:
# the log markers the platform watchdog reads ("Snapshot step 1 - Preparing",
# then "Snapshot ended with SnapshotResult [status=COMPLETED"), paired within
# each pod's log. The time of the first such completion goes to snap.<c>.
snapshots_done() {
    local pods pod started c log pairs pair start end missing=""
    pods=$(kube get pods -l app.kubernetes.io/instance=kafka-connect \
        -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].state.running.startedAt}{"\n"}{end}' 2>/dev/null) \
        || { echo "the Connect pods can't be listed"; return 1; }
    for c in $CONNECTORS; do
        pairs=""
        while read -r pod started; do
            # a pod still starting has no log yet
            if [ -z "$pod" ] || [ -z "$started" ]; then continue; fi
            log=$(kube logs "pod/${pod}" 2>/dev/null) || continue
            pairs="${pairs}$(grep -F "[${c}|task-" <<<"$log" | awk '
                /Snapshot step 1 - Preparing/ { s = $1 " " $2 }
                /Snapshot ended with SnapshotResult \[status=COMPLETED/ { if (s != "") print s "|" $1 " " $2; s = "" }')"$'\n'
        done <<<"$pods"
        end=""
        while read -r pair; do
            [ -n "$pair" ] || continue
            start=$(date -u -d "$(cut -d, -f1 <<<"${pair%%|*}")" +%s 2>/dev/null) || continue
            if [ "$start" -ge "$T0" ]; then
                end=$(date -u -d "$(cut -d, -f1 <<<"${pair#*|}")" +%s 2>/dev/null) || end=$start
                break
            fi
        done <<<"$pairs"
        if [ -n "$end" ]; then
            [ -s "${WORK}/snap.${c}" ] || echo "$end" > "${WORK}/snap.${c}"
        else
            missing="${missing} ${c}"
        fi
    done
    [ -z "$missing" ] || { echo "no completed snapshot that started after $(fmt "$T0") for:${missing}"; return 1; }
}

step_snapshot() {
    local deleted c
    # As restart_connect.sh does. The kafka-connect-restart CronJob stays as it is:
    # a snapshot it starts after the resync began counts as well.
    kube delete pod -l app.kubernetes.io/instance=kafka-connect --wait=false >/dev/null \
        || fail "the Connect pods can't be deleted"
    deleted=$(date +%s)
    wait_until "$SNAPSHOT_TIMEOUT" "a completed snapshot of every connector after the resync began" snapshots_done
    for c in $CONNECTORS; do
        echo "  ${c}: snapshot completed $(( $(cat "${WORK}/snap.${c}") - deleted ))s after the Connect pods were deleted"
    done
}

# ---------------------------------------------------------------- processed

# The metric values of a job's sources: "<metric> <value>" per line.
source_values() {  # source_values <job id> <sources file>
    local vid metrics answer
    while read -r vid; do
        metrics=$(awk -v v="$vid" '$1 == v { printf "%s%s", (n++ ? "," : ""), $2 }' "$2")
        answer=$(flink_get "/jobs/$1/vertices/${vid}/metrics?get=${metrics}") || return 1
        jq -r '.[]? | "\(.id) \(.value)"' <<<"$answer"
    done < <(awk '{ print $1 }' "$2" | sort -u)
}

bridge_lag() {  # the summed lag of the debezium-bridge's group, or fails
    local out rows lag=0 first topic partition end start
    out=$(kafka_tool kafka-consumer-groups.sh "--describe --group ${DEBEZIUM_BRIDGE_GROUP}" 2>/dev/null) || return 1
    # GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG ...: "<lag>" per
    # partition the group has an offset for, "- <topic> <partition> <end>"
    # per partition it has none for ("-").
    rows=$(awk -v g="$DEBEZIUM_BRIDGE_GROUP" '$1 == g && $3 ~ /^[0-9]+$/ {
            print ($6 ~ /^[0-9]+$/ ? $6 : "- " $2 " " $3 " " $5) }' <<<"$out")
    [ -n "$rows" ] || return 1
    # A partition without an offset counts as one record not read, unless it
    # holds none (start == end, empty or emptied by retention): the bridge
    # subscribes from the end and commits nothing before its first record, so
    # on a platform where Scorpio never held an entity its topic stays
    # uncommitted (#1204).
    while read -r first topic partition end; do
        if [ "$first" != "-" ]; then
            lag=$(( lag + first ))
            continue
        fi
        [[ "$end" =~ ^[0-9]+$ ]] || { lag=$(( lag + 1 )); continue; }
        start=$(offsets "$topic" -2 | awk -v p="$partition" '$1 == p { print $2 }') || return 1
        [[ "$start" =~ ^[0-9]+$ ]] || return 1
        [ "$end" -le "$start" ] || lag=$(( lag + 1 ))
    done <<<"$rows"
    echo "$lag"
}

source_topics() {  # source_topics <sources file>...: the topics as named in the metrics
    cat "$@" | awk '{ print $2 }' \
        | sed -n 's/.*\.KafkaSourceReader\.topic\.\(.*\)\.partition\.[0-9]*\.currentOffset$/\1/p' | sort -u
}

# The real topics of the sources: "<topic> <name in the metrics>" per line,
# from the broker's list of topics.
resolve_topics() {
    local list m t found
    list=$(kafka_tool kafka-topics.sh "--list" 2>/dev/null) || { echo "the topics can't be listed from ${KAFKA_POD}"; return 1; }
    while read -r m; do
        [ -n "$m" ] || continue
        found=""
        while read -r t; do
            [ -n "$t" ] || continue
            if [ "$(metric_name "$t")" = "$(metric_name "$m")" ]; then found=$t; break; fi
        done <<<"$list"
        [ -n "$found" ] || { echo "the source topic ${m} reported by Flink is not in Kafka"; return 1; }
        echo "${found} ${m}"
    done < <(source_topics "$@")
}

# Once per resync: the end offsets of every partition the two jobs read,
# taken when the debezium-bridge has turned the snapshot into its topics:
# "<topic> <name in the metrics> <partition> <offset>".
take_ends() {
    local t m
    if ! resolve_topics "${WORK}"/sources.validation "${WORK}"/sources.core > "${WORK}/topics.map"; then
        tail -1 "${WORK}/topics.map"  # what is missing
        return 1
    fi
    : > "${WORK}/ends.new"
    : > "${WORK}/starts.new"
    while read -r t m; do
        offsets "$t" -1 | awk -v t="$t" -v m="$m" '{ print t, m, $1, $2 }' >> "${WORK}/ends.new" \
            || { echo "the end offsets of ${t} can't be read"; return 1; }
        offsets "$t" -2 | awk -v t="$t" '{ print t, $1, $2 }' >> "${WORK}/starts.new" \
            || { echo "the start offsets of ${t} can't be read"; return 1; }
    done < "${WORK}/topics.map"
    mv "${WORK}/ends.new" "${WORK}/ends.all"
    mv "${WORK}/starts.new" "${WORK}/starts.all"
}

# One poll: prints what is not quiet and fails, or succeeds.
quiet_now() {
    local lag name job values left="" t m p e s b cur pending
    lag=$(bridge_lag) || { echo "the lag of the debezium-bridge (${DEBEZIUM_BRIDGE_GROUP}) can't be read"; return 1; }
    [ "$lag" -eq 0 ] || { echo "the debezium-bridge has ${lag} records left"; return 1; }
    [ -s "${WORK}/ends.all" ] || take_ends || return 1
    for name in validation core; do
        job=$(cat "${WORK}/job.${name}")
        values=$(source_values "$job" "${WORK}/sources.${name}") || { echo "Flink doesn't answer the metrics of ${job}"; return 1; }
        # a value that is not a number (NaN before a fetch) is not quiet either
        pending=$(awk '$1 ~ /\.pendingRecords$/ && $2 != "0" && $2 != "0.0" { printf "%s%s", (n++ ? "," : ""), $2 }' <<<"$values")
        [ -z "$pending" ] || left="${left} the ${name} job ${job} reports pendingRecords ${pending};"
        while read -r t m p e; do
            [ -n "$t" ] || continue
            grep -qF "KafkaSourceReader.topic.${m}.partition." "${WORK}/sources.${name}" || continue
            s=$(awk -v t="$t" -v p="$p" '$1 == t && $2 == p { print $3 }' "${WORK}/starts.all")
            if [ "$name" = core ] && [ -s "$RESYNC_BASE" ]; then
                b=$(awk -v t="$t" -v p="$p" '$1 == t && $2 == p { print $3 }' "$RESYNC_BASE")
                if [ -n "$b" ] && [ "$b" -gt "${s:-0}" ]; then s=$b; fi
            fi
            if [ "$name" = validation ] && [ -s "$VALIDATION_BASE" ]; then
                b=$(awk -v t="$t" -v p="$p" '$1 == t && $2 == p { print $3 }' "$VALIDATION_BASE")
                if [ -n "$b" ] && [ "$b" -gt "${s:-0}" ]; then s=$b; fi
            fi
            # a partition without records needs nothing
            [ "$e" -gt "${s:-0}" ] || continue
            # currentOffset is the offset of the last record read
            cur=$(awk -v m=".KafkaSourceReader.topic.${m}.partition.${p}.currentOffset" '
                { i = index($1, m) } i > 0 && i + length(m) - 1 == length($1) && $2 ~ /^-?[0-9.]+$/ { if (!f || $2 + 0 > c) c = $2 + 0; f = 1 }
                END { if (f) printf "%d", c }' <<<"$values")
            if [ -z "$cur" ] || [ "$cur" -lt $(( e - 1 )) ]; then
                [ -n "$cur" ] && [ "$cur" -ge 0 ] || cur=nothing
                left="${left} the ${name} job ${job} read ${t} partition ${p} to ${cur} of ${e};"
            fi
        done < "${WORK}/ends.all"
    done
    [ -z "$left" ] || { echo "records left:${left}"; return 1; }
}

QUIET_SINCE=""
quiet_period() {
    if quiet_now > "${WORK}/poll"; then
        [ -n "$QUIET_SINCE" ] || QUIET_SINCE=$(date +%s)
        if [ $(( $(date +%s) - QUIET_SINCE )) -ge "$QUIET" ]; then return 0; fi
        echo "quiet for $(( $(date +%s) - QUIET_SINCE ))s of ${QUIET}s"
        return 1
    fi
    QUIET_SINCE=""
    cat "${WORK}/poll"
    return 1
}

sources_known() {
    local name job
    for name in validation core; do
        job=$(cat "${WORK}/job.${name}")
        job_sources "$job" > "${WORK}/sources.${name}" || { echo "Flink doesn't answer for the job ${job}"; return 1; }
        grep -q 'currentOffset$' "${WORK}/sources.${name}" || { echo "the job ${job} reports no Kafka source yet"; return 1; }
    done
}

marker_in_alerta() {
    local answer
    answer=$(http alerta GET "/api/alerts?resource=${STATEMENTSET}&event=ResyncMarker&status=open&status=closed&status=ack&status=shelved&status=expired&status=unknown")
    [ "${answer%% *}" = "200" ] || { echo "Alerta didn't answer"; return 1; }
    if ! jq -e --arg v "$MARKER" '[.alerts[]? | select(.value == $v)] | length > 0' <<<"${answer#* }" >/dev/null 2>&1; then
        echo "the marker ${MARKER} written to ${ALERTS_TOPIC} has not reached Alerta"
        return 1
    fi
    jq -c --arg v "$MARKER" '[.alerts[] | select(.value == $v)][0] | {id, status}' <<<"${answer#* }" > "${WORK}/marker"
}

step_processed() {
    local deadline job record written tab=$'\t'
    deadline=$(( $(date +%s) + PROCESSED_TIMEOUT ))
    remaining() { echo $(( deadline - $(date +%s) > 0 ? deadline - $(date +%s) : 0 )); }
    wait_until "$(remaining)" "a completed snapshot of every connector after the resync began" snapshots_done
    job=$(kube get beamsqlstatementset "$STATEMENTSET" -o jsonpath='{.status.job_id}') || job=""
    [ -n "$job" ] || fail "the statementset ${STATEMENTSET} reports no job"
    echo "$job" > "${WORK}/job.validation"
    job=$(kube get flinksessionjob "$CORE_SERVICES" -o jsonpath='{.status.jobStatus.jobId}') || job=""
    [ -n "$job" ] || fail "the FlinkSessionJob ${CORE_SERVICES} reports no job"
    echo "$job" > "${WORK}/job.core"
    wait_until "$(remaining)" "the Kafka sources of both jobs known" sources_known
    echo "  sources, as Flink names them: $(source_topics "${WORK}"/sources.validation "${WORK}"/sources.core | tr '\n' ' ')"
    wait_until "$(remaining)" "the debezium-bridge, the validation job and Core Services quiet for ${QUIET}s" quiet_period
    echo "  the consumers were quiet for ${QUIET}s $(( $(date +%s) - T0 ))s after the resync began"
    # The marker goes behind Core Services' records. The alerta-bridge posts
    # the one partition in order and gets a record again after a failed post,
    # so once Alerta has the marker it has every alert written before it. It
    # posts the value as it is: an alert of service System with severity
    # normal and no status, which Alerta keeps closed, on its own event.
    MARKER="${T0}-$$"
    record=$(jq -nc --arg res "$STATEMENTSET" --arg env "$(cat "${WORK}/environment")" --arg v "$MARKER" \
        --arg text "Marker of the resync of the SHACL alerts that began at $(fmt "$T0"): every alert before it has been posted." \
        '{resource: $res, event: "ResyncMarker", environment: $env, severity: "normal", service: ["System"],
          origin: "shacl-resync", value: $v, text: $text}')
    printf '%s\t%s\n' "$(jq -nc --arg res "$STATEMENTSET" '{resource: $res, event: "ResyncMarker"}')" "$record" \
        | kafka_feed kafka-console-producer.sh "--topic ${ALERTS_TOPIC} --property parse.key=true --property key.separator='${tab}'" >/dev/null \
        || fail "the marker can't be written to ${ALERTS_TOPIC}"
    written=$(date +%s)
    echo "  the marker ${MARKER} is written to ${ALERTS_TOPIC}"
    wait_until "$(remaining)" "the marker in Alerta" marker_in_alerta
    echo "  the marker reached Alerta $(( $(date +%s) - written ))s after it was written, $(jq -r '.status' "${WORK}/marker")"
}

# ---------------------------------------------------------------- end the degraded state

step_end() {
    set_marks '{"resync_since":null,"resync_step":null,"resync_deadline":null,"resync_failed":null}' \
        || fail "the marks can't be removed from the ConfigMap ${STATE_CONFIGMAP}"
    # The watchdog's own judgement, which knows a kept inconsistency, ends
    # the warning; one run now instead of at the next schedule.
    if kube create job --from="cronjob/${WATCHDOG}" "${WATCHDOG}-resync-${T0}" >/dev/null 2>&1; then
        echo "  started the watchdog run ${WATCHDOG}-resync-${T0}"
    else
        echo "  the watchdog run could not be started; its next scheduled run, within two minutes, judges the consistency"
    fi
}

# ---------------------------------------------------------------- the order

# run_step <n> <function>: the function runs in a subshell with errexit, so
# any failing command ends the step, and a step's variables stay its own.
CUR_STEP=""
STEP_PID=""
SIGNAL=""
# A signal while a step runs goes on to the step, which runs in the
# background so that the signal is taken at once; the failure path then
# marks and posts it like any other failure. Between steps it is handled at
# once. INT exits 130, TERM 143.
on_signal() {
    SIGNAL=$1
    if [ -n "$STEP_PID" ] && kill -0 "$STEP_PID" 2>/dev/null; then
        # a background subshell ignores INT: TERM ends it either way
        kill -TERM "$STEP_PID" 2>/dev/null || true
    elif [ -n "$CUR_STEP" ]; then
        step_failed "$CUR_STEP" "interrupted by SIG${SIGNAL}"
    else
        exit_signal
    fi
}
exit_signal() {
    if [ "$SIGNAL" = INT ]; then exit 130; fi
    exit 143
}
trap 'on_signal INT' INT
trap 'on_signal TERM' TERM

# step_failed <step> <reason>: says why, marks the failure and posts it, and
# exits non-zero
step_failed() {
    local step=$1 reason=$2 detail note="" command="$COMMAND" now
    trap '' INT TERM
    echo "resync failed in step ${step}: ${reason}" >&2
    if [ -e "${WORK}/stopped" ] && [ ! -e "${WORK}/started" ] && [ "$REPLACE" = package ]; then
        # A fresh restart would run the old statements on the new tables.
        note=" The SHACL validation doesn't run: its job was stopped for a new package, and ${command} of that package installs and starts it."
        echo "The SHACL validation doesn't run: its job was stopped for a new package. After removing the cause, run in semantic-model/shacl2flink: ${command}, with the same package" >&2
    elif [ -e "${WORK}/stopped" ] && [ ! -e "${WORK}/started" ]; then
        command="make shacl-resync REPLACE=fresh"
        note=" The SHACL validation doesn't run: its job was stopped and not started again, and ${command} starts it."
        echo "The SHACL validation doesn't run: its job was stopped and not started again. After removing the cause, run in semantic-model/shacl2flink: ${command} (the statementset is kept in ${SAVED})" >&2
    else
        echo "After removing the cause, run in semantic-model/shacl2flink: ${command}" >&2
    fi
    now=$(date +%s)
    detail="$(plain "$reason"). The SHACL alerts may be incomplete or stale; run ${command} again.${note}"
    # The watchdog reports the failure from the marks until a later resync
    # completes; the alert is there at once.
    set_marks "$(jq -nc --arg failed "${now} ${detail}" '{resync_failed: $failed}')" \
        || echo "the failure could not be marked in the ConfigMap ${STATE_CONFIGMAP}" >&2
    post_consistency critical "resync failed" "RESYNC FAILED in step ${step} at $(fmt "$now"): ${detail}" 0 || true
    if [ -n "$SIGNAL" ]; then exit_signal; fi
    exit 1
}

run_step() {
    local n=$1 fn=$2 rc reason step started
    : > "${WORK}/reason"
    if [ "$n" = 0 ]; then
        # Said before the first cluster call, so a slow check is visible (#1195).
        echo "checking the preconditions: the statementset, its job, Core Services, the alerts topic and the watchdog's marks"
        set +e
        ( set -e; "$fn" )
        rc=$?
        set -e
        if [ "$rc" -ne 0 ]; then
            echo "resync refused before step 1/${TOTAL}: $(cat "${WORK}/reason")" >&2
            exit 1
        fi
        return 0
    fi
    step="${n}/${TOTAL} ${STEPS[$(( n - 1 ))]}"
    CUR_STEP=$step
    echo "step ${step}: started"
    started=$(date +%s)
    set +e
    (
        set -e
        trap - INT TERM
        if [ "$n" -gt 1 ]; then
            set_marks "$(jq -nc --arg step "$step" '{resync_step: $step}')" \
                || fail "the marks can't be written to the ConfigMap ${STATE_CONFIGMAP}"
            post_consistency warning "resync in progress" "$(degraded_text "$step")" || true
        fi
        "$fn" "$step"
    ) &
    STEP_PID=$!
    # A trapped signal ends the wait early; the step then ends on the TERM
    # passed on to it, and is waited for again.
    while true; do
        wait "$STEP_PID"
        rc=$?
        kill -0 "$STEP_PID" 2>/dev/null || break
    done
    STEP_PID=""
    set -e
    if [ -n "$SIGNAL" ]; then
        step_failed "$step" "interrupted by SIG${SIGNAL}"
    fi
    if [ "$rc" -eq 0 ]; then
        echo "step ${step}: done"
        echo "  took $(( $(date +%s) - started ))s"
        return 0
    fi
    reason=$(cat "${WORK}/reason")
    step_failed "$step" "${reason:-a command failed (exit ${rc})}"
}

run_step 0 step_check
ENVIRONMENT=$(cat "${WORK}/environment")
STEP_FNS=(step_mark)
[ "$REPLACE" = fresh ] || [ "$REPLACE" = package ] && STEP_FNS+=(step_stop)
STEP_FNS+=(step_close step_reset)
[ "$REPLACE" = package ] && STEP_FNS+=(step_install)
[ "$REPLACE" = fresh ] || [ "$REPLACE" = package ] && STEP_FNS+=(step_start)
STEP_FNS+=(step_snapshot step_processed step_end)
# a stop by an earlier run counts, so the settle time and the note apply
for i in "${!STEP_FNS[@]}"; do
    run_step $(( i + 1 )) "${STEP_FNS[$i]}"
done
echo "resync done in $(( $(date +%s) - T0 ))s: the SHACL alerts are those of the constraints violated now"
