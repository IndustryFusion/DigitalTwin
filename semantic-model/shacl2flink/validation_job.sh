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
# What shacl_resync.sh and restart_connect.sh both need: bounded kubectl calls,
# a port-forward per service, the Flink REST API, and whether the validation
# job runs and reads. Sourced by them after they have set
#
#   NAMESPACE STATEMENTSET WORK (a directory of their own)
#   POLL KUBECTL_TIMEOUT CONNECT_TIMEOUT (seconds)
#
# and defined fail <reason>, which ends the step or the script. cleanup_work,
# their exit trap, ends the port-forwards and removes WORK.

# The validation's sources that start at the latest offset (entities in
# create_ngsild_tables.py, attributes in create_core_tables.py): what is
# published before their readers hold a partition is never read.
LATEST_SOURCES=${LATEST_SOURCES:-iff.ngsild.entities iff.ngsild.attributes}
ALERTA_SERVICE=${ALERTA_SERVICE:-svc/alerta}
ALERTA_PORT=${ALERTA_PORT:-8080}
FLINK_SERVICE=${FLINK_SERVICE:-svc/flink-jobmanager-rest}
FLINK_PORT=${FLINK_PORT:-8081}

cleanup_work() {
    local pid
    if [ -f "${WORK}/pids" ]; then
        while read -r pid; do kill "$pid" 2>/dev/null || true; done < "${WORK}/pids"
    fi
    rm -rf "$WORK"
}

# wait_until <limit> <what> <check> [arguments]: runs <check> every POLL
# seconds until it succeeds; <check> prints what is still missing. Fails the
# step after <limit> seconds.
wait_until() {
    local limit=$1 what=$2 check=$3 deadline
    shift 3
    deadline=$(( $(date +%s) + limit ))
    while true; do
        if "$check" "$@" > "${WORK}/detail"; then
            return 0
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
            fail "${what} not reached within ${limit}s: $(tr '\n' ' ' < "${WORK}/detail" | sed 's/ *$//')"
        fi
        sleep "$POLL"
    done
}

# Every kubectl call is bounded: an exec or a request that hangs fails the
# check or the step that made it instead of the whole resync.
kube() {
    timeout "$KUBECTL_TIMEOUT" kubectl -n "$NAMESPACE" "$@"
}

free_port() {
    python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

# A port-forward per service, as fuseki_kms.sh reaches Fuseki, started again
# when it ended (it follows one pod).
forward() {  # forward <name> <service> <remote port> <probe path>
    local name=$1 svc=$2 rport=$3 probe=$4 port pid n=0 code
    port=$(free_port)
    kubectl -n "$NAMESPACE" port-forward "$svc" "${port}:${rport}" >/dev/null 2>&1 &
    pid=$!
    echo "$pid" >> "${WORK}/pids"
    echo "${pid} ${port}" > "${WORK}/forward.${name}"
    while true; do
        code=$(curl -s -g -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${port}${probe}") || code=000
        [ "$code" != "000" ] && return 0
        kill -0 "$pid" 2>/dev/null || { echo "the port-forward to ${svc} ended"; return 1; }
        [ "$n" -lt "$CONNECT_TIMEOUT" ] || { echo "${svc} did not answer through a port-forward within ${CONNECT_TIMEOUT}s"; return 1; }
        sleep 1
        n=$(( n + 1 ))
    done
}

base_url() {  # base_url <name>: the local URL of a live port-forward, started when needed
    local pid="" port=""
    if [ -f "${WORK}/forward.${1}" ]; then read -r pid port < "${WORK}/forward.${1}"; fi
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        case "$1" in
            alerta) forward alerta "$ALERTA_SERVICE" "$ALERTA_PORT" /api/ >&2 || return 1 ;;
            flink) forward flink "$FLINK_SERVICE" "$FLINK_PORT" /config >&2 || return 1 ;;
        esac
        read -r pid port < "${WORK}/forward.${1}"
    fi
    echo "http://127.0.0.1:${port}"
}

# http <alerta|flink> <method> <path> [json body]: prints "<code> <body>",
# code 000 when the service can't be reached
http() {
    local base out code auth=()
    out="${WORK}/body.$$.${RANDOM}"
    if ! base=$(base_url "$1"); then
        echo "000 "
        return 0
    fi
    # The key goes to curl from a file, never in its arguments.
    [ "$1" = alerta ] && auth=(-H "@${ALERTA_HEADER}")
    if [ $# -ge 4 ]; then
        code=$(curl -s -g -m 30 -o "$out" -w '%{http_code}' -X "$2" "${auth[@]}" \
            -H 'Content-Type: application/json' --data-binary "$4" "${base}$3") || code=000
    else
        code=$(curl -s -g -m 30 -o "$out" -w '%{http_code}' -X "$2" "${auth[@]}" "${base}$3") || code=000
    fi
    echo "${code} $(tr -d '\n' < "$out" 2>/dev/null)"
    rm -f "$out"
}

flink_get() {  # flink_get <path>: the body of a 200 answer, or fails
    local answer
    answer=$(http flink GET "$1")
    [ "${answer%% *}" = "200" ] || return 1
    echo "${answer#* }"
}

# ---------------------------------------------------------------- the validation job

validation_running() {  # validation_running <job before>
    local status job overview
    status=$(kube get beamsqlstatementset "$STATEMENTSET" -o jsonpath='{.status.state} {.status.job_id}' 2>/dev/null) \
        || { echo "the statementset can't be read"; return 1; }
    job=${status#* }
    if [ "${status%% *}" != "RUNNING" ] || [ -z "$job" ] || [ "$job" = "$status" ] || [ "$job" = "$1" ]; then
        echo "the statementset reports ${status:-nothing}"
        return 1
    fi
    overview=$(flink_get /jobs/overview) || { echo "Flink doesn't answer"; return 1; }
    if ! jq -e --arg jid "$job" '.jobs[] | select(.jid == $jid and .state == "RUNNING" and .tasks.running == .tasks.total)' \
        <<<"$overview" >/dev/null 2>&1; then
        echo "the job ${job} doesn't run with all its tasks yet"
        return 1
    fi
    echo "$job" > "${WORK}/ss_job"
}

sources_placed() {  # sources_placed <job id> [topics, LATEST_SOURCES by default]
    local t missing=""
    job_sources "$1" > "${WORK}/sources.start" || { echo "Flink doesn't answer for the job $1"; return 1; }
    for t in ${2:-$LATEST_SOURCES}; do
        grep -qF ".KafkaSourceReader.topic.$(metric_name "$t").partition." "${WORK}/sources.start" \
            || missing="${missing} ${t}"
    done
    [ -z "$missing" ] || { echo "no reader of the job $1 has a partition of:${missing}"; return 1; }
}

# The Kafka sources of a Flink job, from the metrics of its vertices:
# "<vertex> <metric>" per line, every currentOffset per topic and partition
# and every pendingRecords.
job_sources() {  # job_sources <job id>
    local job vid ids
    job=$(flink_get "/jobs/$1") || return 1
    for vid in $(jq -r '.vertices[]?.id' <<<"$job"); do
        ids=$(flink_get "/jobs/$1/vertices/${vid}/metrics") || return 1
        jq -r --arg v "$vid" '.[]?.id | select(test("\\.KafkaSourceReader\\.topic\\..+\\.partition\\.[0-9]+\\.currentOffset$") or test("\\.pendingRecords$"))
            | "\($v) \(.)"' <<<"$ids"
    done
}

# The topic as the sources' metric names carry it: Flink's metric query
# service replaces '.', ' ', ':' and ',' with '_' in every part of a name, so
# iff.alerts.bulk appears as iff_alerts_bulk.
metric_name() {
    local n=${1//[ .:,]/_}
    echo "$n"
}
