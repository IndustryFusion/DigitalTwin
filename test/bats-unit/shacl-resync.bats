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
# The resync of the SHACL alerts (semantic-model/shacl2flink/shacl_resync.sh):
# its steps in their order, the waits within them, the watchdog's marks and
# how a failed step stops it. kubectl and curl are stubs that keep the
# platform's state in files: kubectl answers for the Kubernetes resources,
# the Connect log and the Kafka tools in the broker pod, curl for Alerta and
# the Flink REST API. Every call is logged in order.

# shellcheck disable=SC2030,SC2031  # per-test env is intentionally test-local

bats_require_minimum_version 1.5.0

SCRIPT="${BATS_TEST_DIRNAME}/../../semantic-model/shacl2flink/shacl_resync.sh"

setup() {
    WORK="$(mktemp -d)"
    export WORK
    export STATE="${WORK}/state"
    export CALLS="${WORK}/calls.log"
    mkdir -p "${WORK}/bin" "${STATE}/topics"
    : > "${CALLS}"

    cat > "${WORK}/bin/kubectl" <<'EOF'
#!/bin/bash
args="$*"
args=${args#-n iff }
echo "kubectl ${args}" >> "${CALLS}"
echo "$(date +%s.%N) kubectl ${args}" >> "${STATE}/times.log"
count() { local n; n=$(( $(cat "${STATE}/count.$1" 2>/dev/null || echo 0) + 1 )); echo "$n" > "${STATE}/count.$1"; echo "$n"; }
stamp() { date -u -d "@$1" '+%Y-%m-%d %H:%M:%S'; }
# snapshot <start> [incomplete]: a snapshot of both connectors in the Connect log
snapshot() {
    local c
    for c in entity-table-connector rdf-table-connector; do
        printf '%s,217 INFO [%s|task-0] Snapshot step 1 - Preparing (x)\n' "$(stamp "$1")" "$c" >> "${STATE}/connect.log"
        [ -n "${2:-}" ] || printf '%s,374 INFO [%s|task-0] Snapshot ended with SnapshotResult [status=COMPLETED, offset=x] (x)\n' \
            "$(stamp "$(date +%s)")" "$c" >> "${STATE}/connect.log"
    done
}
grow() {  # grow <topic> <records>
    echo "0 $(( $(awk '{ print $2 }' "${STATE}/topics/$1.end") + $2 ))" > "${STATE}/topics/$1.end"
}
ss_field() { jq -r "$1 // empty" "${STATE}/ss.json"; }
case "${args}" in
    "get beamsqlstatementset shacl-validation --ignore-not-found -o json")
        cat "${STATE}/ss.json" 2>/dev/null || true ;;
    "get beamsqlstatementset shacl-validation -o json")
        cat "${STATE}/ss.json" ;;
    "get beamsqlstatementset shacl-validation --ignore-not-found -o name")
        if [ -e "${STATE}/ss.json" ]; then
            echo "beamsqlstatementset.industry-fusion.com/shacl-validation"
        elif [ -e "${STATE}/ss.deleting" ]; then
            if [ -n "${STUB_SS_STUCK:-}" ] || [ "$(count ss_linger)" -le "${STUB_SS_LINGER:-0}" ]; then
                echo "beamsqlstatementset.industry-fusion.com/shacl-validation"
            else
                rm -f "${STATE}/ss.deleting"
                echo "stub: the statementset is gone" >> "${CALLS}"
            fi
        fi ;;
    "get beamsqlstatementset shacl-validation -o jsonpath={.status.state} {.status.job_id}")
        [ -e "${STATE}/ss.json" ] || exit 1
        echo "$(ss_field .status.state) $(ss_field .status.job_id)" ;;
    "get beamsqlstatementset shacl-validation -o jsonpath={.status.job_id}")
        [ -e "${STATE}/ss.json" ] || exit 1
        ss_field .status.job_id ;;
    "delete beamsqlstatementset shacl-validation --wait=false")
        jq -r '.status.job_id' "${STATE}/ss.json" > "${STATE}/cancelled"
        rm -f "${STATE}/ss.json"
        touch "${STATE}/ss.deleting" ;;
    "create -f -")
        [ -z "${STUB_CREATE_FAIL:-}" ] || exit 1
        cat > "${STATE}/created.json"
        jq --arg job "ss-$(count ss_jobs)" '. + {status: {state: "RUNNING", job_id: $job}}' "${STATE}/created.json" > "${STATE}/ss.json" ;;
    "get configmap platform-watchdog-state -o json")
        printf '{"data":%s}' "$(cat "${STATE}/marks.json")" ;;
    "patch configmap platform-watchdog-state --type merge -p "*)
        patch=${args#*-p }
        echo "${patch}" >> "${STATE}/marks.log"
        [ -z "${STUB_MARKS_FAIL:-}" ] || exit 1
        if [ -n "${STUB_MARKS_FAIL_ON:-}" ] && [[ "${patch}" == *"${STUB_MARKS_FAIL_ON}"* ]]; then exit 1; fi
        jq -c --argjson p "${patch}" '. + $p.data | with_entries(select(.value != null))' "${STATE}/marks.json" > "${STATE}/marks.new"
        mv "${STATE}/marks.new" "${STATE}/marks.json"
        if [ -n "${STUB_ALERTA_DOWN_AT:-}" ] && [[ "${patch}" == *"\"resync_step\":\"${STUB_ALERTA_DOWN_AT}"* ]]; then
            touch "${STATE}/alerta_down"
        fi ;;
    "get cronjob platform-watchdog -o jsonpath="*)
        echo Development ;;
    "get secret alerta -o jsonpath={.data.alerta-admin-key}")
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
        [ -n "${STUB_CS_STUCK:-}" ] || echo "cs-$(count cs_jobs)" > "${STATE}/cs_job"
        # the periodic restart of the Connect pods comes now
        [ -z "${STUB_CRON_SNAPSHOT:-}" ] || snapshot "$(date +%s)" ;;
    "get pods -l app.kubernetes.io/instance=kafka-connect -o jsonpath="*)
        echo "kafka-connect-connect-0 2026-11-21T10:00:00Z" ;;
    "logs pod/kafka-connect-connect-0")
        cat "${STATE}/connect.log" 2>/dev/null || true ;;
    "delete pod -l app.kubernetes.io/instance=kafka-connect --wait=false")
        snapshot $(( $(date +%s) - ${STUB_SNAPSHOT_AGE:-0} )) ${STUB_SNAPSHOT_INCOMPLETE:+incomplete}
        grow iff.ngsild.public.entity 10
        grow iff.ngsild.entities 10
        # no attribute in the re-snapshot: the entities have none
        [ -n "${STUB_ATTR_NO_SNAPSHOT:-}" ] || grow iff.ngsild.attributes 20
        grow iff.ngsild.flink.constraint_trigger_table 5
        if [ -n "${STUB_BULK_GROWS:-}" ]; then
            grow iff.alerts.bulk "${STUB_BULK_GROWS}"
            [ -n "${STUB_CORE_BEHIND:-}" ] || awk '{ print $2 - 1 }' "${STATE}/topics/iff.alerts.bulk.end" > "${STATE}/core_bulk_read"
        fi ;;
    "create job --from=cronjob/platform-watchdog "*)
        echo "${args##* }" > "${STATE}/watchdog_job" ;;
    # The rdf table's keys, read from Postgres after the install (#1165 D6).
    "get secrets -o name")
        echo "secret/flink-writer-user.acid-cluster.credentials" ;;
    "get secret/flink-writer-user.acid-cluster.credentials -o go-template="*)
        echo "pw" ;;
    "get ep acid-cluster -o jsonpath="*)
        echo "acid-cluster-0" ;;
    "exec acid-cluster-0 -c postgres -- bash -c "*)
        [ -z "${STUB_RDF_DB_DOWN:-}" ] || exit 1
        cat "${STATE}/rdf.table" 2>/dev/null || true ;;
    # The Kafka tools: kafka_tool without -i (#1195), kafka_feed with it.
    "exec my-cluster-nodes-0 -- sh -c "*|"exec -i my-cluster-nodes-0 -- sh -c "*)
        cmd=${*: -1}
        topic=$(sed -n 's/.*--topic \([^ ]*\).*/\1/p' <<<"${cmd}")
        case "${cmd}" in
            *kafka-get-offsets.sh*)
                [ -z "${STUB_KAFKA_DOWN:-}" ] || exit 1
                if [ "${topic}" = iff.alerts ]; then
                    for p in $(seq 0 $(( ${STUB_ALERTS_PARTITIONS:-1} - 1 ))); do echo "iff.alerts:${p}:40"; done
                    exit 0
                fi
                if [ ! -e "${STATE}/topics/${topic}.end" ]; then
                    echo "Error occurred: Could not match any topic-partitions with the specified filters" >&2
                    exit 1
                fi
                if [[ "${cmd}" == *"--time -2"* ]]; then f=start; else f=end; fi
                [ -e "${STATE}/topics/${topic}.${f}" ] || echo "0 0" > "${STATE}/topics/${topic}.${f}"
                awk -v t="${topic}" '{ print t ":" $1 ":" $2 }' "${STATE}/topics/${topic}.${f}" ;;
            *kafka-topics.sh*--list*)
                echo iff.alerts
                for f in "${STATE}"/topics/*.end; do f=${f##*/}; echo "${f%.end}"; done ;;
            *kafka-delete-records.sh*)
                [ -z "${STUB_DELETE_FAIL:-}" ] || exit 1
                json=$(cat)
                echo "${json}" >> "${STATE}/deleted.log"
                for t in $(jq -r '.partitions[].topic' <<<"${json}" | sort -u); do
                    jq -r --arg t "$t" '.partitions[] | select(.topic == $t) | "\(.partition) \(.offset)"' <<<"${json}" > "${STATE}/topics/${t}.start"
                done ;;
            *kafka-consumer-groups.sh*)
                n=$(count lag_polls)
                lag=0
                [ "$n" -gt "${STUB_BRIDGE_LAG_POLLS:-0}" ] || lag=7
                end=$(awk '{ print $2 }' "${STATE}/topics/iff.ngsild.public.entity.end")
                echo "GROUP TOPIC PARTITION CURRENT-OFFSET LOG-END-OFFSET LAG CONSUMER-ID HOST CLIENT-ID"
                if [ -n "${STUB_BRIDGE_UNCOMMITTED:-}" ]; then
                    # a partition the group has no offset for, ending at the
                    # given offset; it starts where the .start file says
                    echo "debeziumBridgeGroup iff.ngsild.public.entity 0 - ${STUB_BRIDGE_UNCOMMITTED} - c1 /10.0.0.1 c1"
                else
                    echo "debeziumBridgeGroup iff.ngsild.public.entity 0 $(( end - lag )) ${end} ${lag} c1 /10.0.0.1 c1"
                fi ;;
            *kafka-console-producer.sh*"--topic iff.rdf "*)
                # the tombstones of removed knowledge (#1165 D6), as written
                cat >> "${STATE}/rdf.tombstones"
                echo "stub: tombstones written to iff.rdf" >> "${CALLS}" ;;
            *kafka-console-producer.sh*)
                cut -f2 > "${STATE}/marker.json"
                date +%s > "${STATE}/marker_written" ;;
            *kafka-console-consumer.sh*"--topic iff.rdf "*)
                cat "${STATE}/rdf.topic" 2>/dev/null || true ;;
            *) echo "unexpected tool ${cmd}" >&2; exit 1 ;;
        esac ;;
    *)
        echo "unexpected kubectl ${args}" >&2
        exit 1 ;;
esac
EOF

    cat > "${WORK}/bin/curl" <<'EOF'
#!/bin/bash
if [ "$1" = --version ]; then
    echo "curl ${STUB_CURL_VERSION:-8.5.0} (x86_64-pc-linux-gnu)"
    exit 0
fi
printf '%s\n' "$*" >> "${STATE}/curl.argv"
out=/dev/stdout method=GET url="" body="" auth=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o) out=$2; shift ;;
        -X) method=$2; shift ;;
        --data-binary) body=$2; shift ;;
        -H)
            if [[ "$2" == @* ]]; then
                # a header file: only its owner may read it
                f=${2#@}
                if [ "$(stat -c %a "$f")" = 600 ] && grep -qx 'Authorization: Key testkey' "$f"; then auth=ok; fi
            fi
            shift ;;
        -w|-m) shift ;;
        http*) url=$1 ;;
    esac
    shift
done
path=/${url#http://*/}
echo "curl ${method} ${path}" >> "${CALLS}"
echo "$(date +%s.%N) curl ${method} ${path}" >> "${STATE}/times.log"
case "${path}" in
    /api/) ;;  # the port-forward's probe asks without the key
    /api/*) [ "${auth}" = ok ] || echo "curl ${method} ${path} without the key's header file" >> "${STATE}/unauthorized" ;;
esac
count() { local n; n=$(( $(cat "${STATE}/count.$1" 2>/dev/null || echo 0) + 1 )); echo "$n" > "${STATE}/count.$1"; echo "$n"; }
answer() { printf '%s' "$2" > "${out}"; printf '%s' "$1"; }
end_of() { awk '{ print $2 }' "${STATE}/topics/$1.end"; }
case "${path}" in
    /api*)
        if [ -n "${STUB_ALERTA_DOWN:-}" ] || [ -e "${STATE}/alerta_down" ]; then printf 000; exit 7; fi ;;
esac
case "${method} ${path}" in
    "GET /api/"|"GET /config")
        answer 200 '{}' ;;
    "POST /api/alert")
        echo "${body}" >> "${STATE}/posts.log"
        answer 201 '{"status":"ok"}' ;;
    "PUT /api/_bulk/alerts/status?"*)
        echo "${body}" > "${STATE}/close_body"
        if [ -n "${STUB_BULK_ERROR:-}" ]; then
            answer 500 "$(printf '{"status":"error",\t"message":"bad\001 \\ \"x\""}')"
            exit 0
        fi
        if [ "$(count puts)" -le "${STUB_PUT_PAGES:-1}" ]; then
            answer 200 '{"status":"ok","count":1000}'
        else
            answer 404 '{"status":"error","message":"not found"}'
        fi ;;
    "GET /api/alerts?"*"from-date="*)
        if [ "$(count settle_queries)" -le "${STUB_SETTLE_BUSY:-0}" ]; then
            answer 200 '{"status":"ok","total":2,"alerts":[]}'
        else
            answer 200 '{"status":"ok","total":0,"alerts":[]}'
        fi ;;
    "GET /api/alerts?service=SHACL%20Validator&status=open&status=assign&status=ack&status=shelved&status=blackout&status=expired&status=unknown&page-size=1")
        if [ "$(count open_counts)" -eq 1 ]; then
            answer 200 "{\"status\":\"ok\",\"total\":${STUB_OPEN_BEFORE:-3},\"alerts\":[]}"
        else
            answer 200 "{\"status\":\"ok\",\"total\":${STUB_LEFT_OPEN:-0},\"alerts\":[]}"
        fi ;;
    "GET /api/alerts?page-size=1")
        answer 200 '{"status":"ok","total":0,"alerts":[]}' ;;
    "GET /api/alerts?resource=shacl-validation&event=ResyncMarker&"*)
        if [ -e "${STATE}/marker.json" ] && [ -z "${STUB_MARKER_LOST:-}" ] \
            && [ "$(count marker_polls)" -gt "${STUB_MARKER_DELAY:-0}" ]; then
            answer 200 "$(jq -c '{status: "ok", total: 1, alerts: [. + {id: "m-1", status: "closed"}]}' "${STATE}/marker.json")"
        else
            answer 200 '{"status":"ok","total":0,"alerts":[]}'
        fi ;;
    "GET /jobs/overview")
        jobs=$(printf '{"jid":"%s","name":"Core Services","state":"RUNNING","tasks":{"running":3,"total":3}}' "$(cat "${STATE}/cs_job")")
        if [ -e "${STATE}/ss.json" ]; then
            jobs="${jobs},$(printf '{"jid":"%s","name":"insert-into_default_catalog","state":"RUNNING","tasks":{"running":5,"total":5}}' "$(jq -r .status.job_id "${STATE}/ss.json")")"
        fi
        answer 200 "{\"jobs\":[${jobs}]}" ;;
    "GET /jobs/"*"/checkpoints")
        answer 200 '{"counts":{"restored":0,"completed":0}}' ;;
    "GET /jobs/"*"/vertices/v-src/metrics?get="*)
        job=${path#/jobs/}; job=${job%%/*}
        n=$(count "values.${job%%-*}")
        ids=${path#*get=}
        vals=""
        for id in ${ids//,/ }; do
            case "${id}" in
                *pendingRecords)
                    v=0
                    [ "${job%%-*}" != ss ] || [ "$n" -gt "${STUB_PENDING_POLLS:-0}" ] || v=12 ;;
                *topic.iff_alerts_bulk.partition.0.currentOffset)
                    v=$(cat "${STATE}/core_bulk_read" 2>/dev/null || echo -1) ;;
                *topic.iff_ngsild_attributes.partition.0.currentOffset)
                    # a new validation job's latest-offset attribute reader:
                    # nothing read since it was placed, or behind the records
                    # written after that
                    if [ "${job%%-*}" = ss ] && [ "${job}" != ss-0 ] && [ -n "${STUB_SS_ATTR_NOTHING:-}" ]; then
                        v=-1
                    else
                        v=$(( $(end_of iff.ngsild.attributes) - 1 ))
                        if [ "${job%%-*}" = ss ] && [ "$n" -le "${STUB_BEHIND_POLLS:-0}" ]; then v=$(( v - 5 )); fi
                    fi ;;
                *currentOffset)
                    m=${id#*KafkaSourceReader.topic.}; m=${m%.partition.*}
                    t=""
                    for f in "${STATE}"/topics/*.end; do f=${f##*/}; f=${f%.end}; [ "${f//./_}" != "$m" ] || t=$f; done
                    v=$(( $(end_of "$t") - 1 ))
                    if [ "${job%%-*}" = ss ] && [ "$n" -le "${STUB_BEHIND_POLLS:-0}" ]; then v=$(( v - 5 )); fi ;;
            esac
            vals="${vals}${vals:+,}{\"id\":\"${id}\",\"value\":\"${v}\"}"
        done
        answer 200 "[${vals}]" ;;
    "GET /jobs/"*"/vertices/v-src/metrics")
        job=${path#/jobs/}; job=${job%%/*}
        if [ "${job%%-*}" = ss ]; then
            topics="iff.ngsild.entities iff.ngsild.attributes iff.ngsild.flink.constraint_trigger_table"
            # a new job's attribute reader gets its split late
            if [ "${job}" != ss-0 ] && [ "$(count "listings.${job}")" -le "${STUB_ATTR_SPLIT_LATE:-0}" ]; then
                topics="iff.ngsild.entities iff.ngsild.flink.constraint_trigger_table"
            fi
        else
            topics="iff.alerts.bulk iff.ngsild.attributes ${STUB_CORE_EXTRA_TOPIC:-}"
            if [ "${job}" != cs-0 ] && [ "$(count "listings.${job}")" -le "${STUB_CS_SPLIT_LATE:-0}" ]; then
                topics="iff.ngsild.attributes ${STUB_CORE_EXTRA_TOPIC:-}"
            fi
        fi
        ids='{"id":"0.Source__x[1].pendingRecords"},{"id":"0.Source__x[1].numRecordsIn"}'
        for t in ${topics}; do
            t=${t//./_}
            ids="${ids},{\"id\":\"0.Source__x[1].KafkaSourceReader.topic.${t}.partition.0.currentOffset\"}"
            ids="${ids},{\"id\":\"0.Source__x[1].KafkaSourceReader.topic.${t}.partition.0.committedOffset\"}"
        done
        answer 200 "[${ids}]" ;;
    "GET /jobs/"*)
        job=${path#/jobs/}
        if [ "${job}" = "$(cat "${STATE}/cancelled" 2>/dev/null)" ]; then
            if [ -n "${STUB_JOB_STUCK:-}" ]; then
                answer 200 '{"state":"CANCELLING"}'
            else
                echo "stub: the job ${job} is cancelled" >> "${CALLS}"
                answer 200 '{"state":"CANCELED"}'
            fi
        else
            answer 200 '{"state":"RUNNING","vertices":[{"id":"v-src","name":"Source: x"}]}'
        fi ;;
    *) answer 400 '{}' ;;
esac
EOF
    chmod +x "${WORK}/bin/"*
    export PATH="${WORK}/bin:${PATH}"

    # A deployed validation running job ss-0, Core Services running cs-0, the
    # watchdog's ConfigMap without marks, and the topics with records.
    jq -n '{apiVersion: "industry-fusion.com/v1alpha4", kind: "BeamSqlStatementSet",
        metadata: {name: "shacl-validation", namespace: "iff", uid: "u-1", resourceVersion: "42",
            labels: {"app.kubernetes.io/managed-by": "Helm"},
            annotations: {"meta.helm.sh/release-name": "shacl", "meta.helm.sh/release-namespace": "iff"}},
        spec: {tables: ["t"], updateStrategy: "none"},
        status: {state: "RUNNING", job_id: "ss-0"}}' > "${STATE}/ss.json"
    echo cs-0 > "${STATE}/cs_job"
    echo '{"observing_since":"1795100000"}' > "${STATE}/marks.json"
    : > "${STATE}/marks.log"
    : > "${STATE}/posts.log"
    local t
    for t in iff.ngsild.public.entity:100 iff.ngsild.entities:100 iff.ngsild.attributes:200 \
        iff.ngsild.attributes_insert:20 iff.alerts.bulk:30 iff.ngsild.flink.constraint_table:50 \
        iff.ngsild.flink.constraint_combination_table:0 iff.ngsild.flink.constraint_trigger_table:50; do
        echo "0 ${t#*:}" > "${STATE}/topics/${t%%:*}.end"
        echo "0 0" > "${STATE}/topics/${t%%:*}.start"
    done

    export RESYNC_STATE_DIR="${WORK}/saved"
    export RESYNC_POLL=0.1
    export RESYNC_SETTLE=1
    export RESYNC_QUIET=1
    export RESYNC_CONNECT_TIMEOUT=1
    export RESYNC_STOP_TIMEOUT=2
    export RESYNC_SETTLE_TIMEOUT=5
    export RESYNC_CLOSE_TIMEOUT=5
    export RESYNC_RESET_TIMEOUT=2
    export RESYNC_START_TIMEOUT=2
    export RESYNC_SNAPSHOT_TIMEOUT=2
    export RESYNC_PROCESSED_TIMEOUT=6
    unset REPLACE RESTORE_FROM
}

teardown() {
    rm -rf "${WORK}"
}

# line <pattern>: the number of the first line of the calls log matching it, 0 if none
line() {
    local n
    n=$(grep -n -m1 -F -- "$1" "${CALLS}" | cut -d: -f1)
    echo "${n:-0}"
}

last_line() {
    local n
    n=$(grep -n -F -- "$1" "${CALLS}" | tail -1 | cut -d: -f1)
    echo "${n:-0}"
}

calls() {
    grep -c -F -- "$1" "${CALLS}" || true
}

# consistency_posts: severity and text of every ValidationConsistency posted
consistency_posts() {
    jq -r 'select(.event == "ValidationConsistency") | "\(.severity) \(.text)"' "${STATE}/posts.log"
}

STEPS_NONE='step 1/6 mark the validation degraded: started
step 1/6 mark the validation degraded: done
step 2/6 close the SHACL alerts: started
step 2/6 close the SHACL alerts: done
step 3/6 reset Core Services: started
step 3/6 reset Core Services: done
step 4/6 trigger a complete re-snapshot: started
step 4/6 trigger a complete re-snapshot: done
step 5/6 wait until the re-snapshot is processed: started
step 5/6 wait until the re-snapshot is processed: done
step 6/6 end the degraded state: started
step 6/6 end the degraded state: done'

STEPS_FRESH='step 1/8 mark the validation degraded: started
step 1/8 mark the validation degraded: done
step 2/8 stop the validation job and empty its topics: started
step 2/8 stop the validation job and empty its topics: done
step 3/8 close the SHACL alerts: started
step 3/8 close the SHACL alerts: done
step 4/8 reset Core Services: started
step 4/8 reset Core Services: done
step 5/8 start the validation job: started
step 5/8 start the validation job: done
step 6/8 trigger a complete re-snapshot: started
step 6/8 trigger a complete re-snapshot: done
step 7/8 wait until the re-snapshot is processed: started
step 7/8 wait until the re-snapshot is processed: done
step 8/8 end the degraded state: started
step 8/8 end the degraded state: done'

# ---------------------------------------------------------------- the order

@test "without a replacement: the steps in their order, each after the previous ended, the job kept" {
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(grep '^step ' <<<"${output}")" = "${STEPS_NONE}" ]
    mark=$(line "kubectl patch configmap platform-watchdog-state")
    close=$(line "curl PUT /api/_bulk/alerts/status")
    reset=$(line "kubectl patch flinksessionjob")
    snapshot=$(line "kubectl delete pod -l app.kubernetes.io/instance=kafka-connect")
    lag=$(last_line "kafka-consumer-groups.sh")
    marker=$(line "kafka-console-producer.sh")
    lookup=$(last_line "event=ResyncMarker")
    watchdog=$(line "kubectl create job --from=cronjob/platform-watchdog")
    [ "${mark}" -gt 0 ]
    [ "${mark}" -lt "${close}" ]
    [ "${close}" -lt "${reset}" ]
    [ "${reset}" -lt "${snapshot}" ]
    [ "${snapshot}" -lt "${lag}" ]
    [ "${lag}" -lt "${marker}" ]
    [ "${marker}" -lt "${lookup}" ]
    [ "${lookup}" -lt "${watchdog}" ]
    # nothing of a replacement
    [ "$(calls "beamsqlstatementset shacl-validation --wait=false")" -eq 0 ]
    [ "$(calls "create -f -")" -eq 0 ]
    [ "$(calls "kafka-delete-records.sh")" -eq 0 ]
    [ "$(jq -r .status.job_id "${STATE}/ss.json")" = "ss-0" ]
    # Core Services runs a new job
    [ "$(cat "${STATE}/cs_job")" = "cs-1" ]
    [ "$(cat "${STATE}/cs_patch")" = '{"spec":{"restartNonce":1}}' ]
    [[ "${output}" == "resync done in "* ]] || [[ "${output}" == *$'\n'"resync done in "* ]]
}

@test "with a fresh job: every step in its order, a new job ID, the statementset with its release labels" {
    export REPLACE=fresh
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(grep '^step ' <<<"${output}")" = "${STEPS_FRESH}" ]
    mark=$(line "kubectl patch configmap platform-watchdog-state")
    delete=$(line "kubectl delete beamsqlstatementset shacl-validation --wait=false")
    emptied=$(last_line "kafka-delete-records.sh")
    close=$(line "curl PUT /api/_bulk/alerts/status")
    reset=$(line "kubectl patch flinksessionjob")
    create=$(line "kubectl create -f -")
    snapshot=$(line "kubectl delete pod -l app.kubernetes.io/instance=kafka-connect")
    marker=$(line "kafka-console-producer.sh")
    [ "${mark}" -lt "${delete}" ]
    [ "${delete}" -lt "${emptied}" ]
    [ "${emptied}" -lt "${close}" ]
    [ "${close}" -lt "${reset}" ]
    [ "${reset}" -lt "${create}" ]
    [ "${create}" -lt "${snapshot}" ]
    [ "${snapshot}" -lt "${marker}" ]
    # the topics are emptied only after the job is gone
    [ "$(line "stub: the statementset is gone")" -gt "${delete}" ]
    [ "$(line "stub: the statementset is gone")" -lt "$(line "kafka-delete-records.sh")" ]
    [ "$(line "stub: the job ss-0 is cancelled")" -lt "$(line "kafka-delete-records.sh")" ]
    # another job ID, the release's labels and annotations, no server fields
    [ "$(jq -r .status.job_id "${STATE}/ss.json")" = "ss-1" ]
    jq -e '.metadata.annotations["meta.helm.sh/release-name"] == "shacl"
        and .metadata.labels["app.kubernetes.io/managed-by"] == "Helm"
        and .metadata.name == "shacl-validation" and .metadata.namespace == "iff"
        and .spec == {tables: ["t"], updateStrategy: "none"}
        and (.status | not) and (.metadata.uid | not) and (.metadata.resourceVersion | not)
        and (.metadata.annotations | has("shacl-resync/stopped-job") | not)' "${STATE}/created.json"
    # the saved copy is gone once the job runs again
    [ -z "$(ls -A "${RESYNC_STATE_DIR}")" ]
}

@test "with a fresh job: the three topics are emptied up to their end offsets, and no other topic" {
    export REPLACE=fresh
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(jq -c '.partitions[]' "${STATE}/deleted.log")" = '{"topic":"iff.ngsild.flink.constraint_table","partition":0,"offset":50}
{"topic":"iff.ngsild.flink.constraint_trigger_table","partition":0,"offset":50}' ]
    # the empty one needs no deletion, every one is checked
    [ "$(calls "--topic iff.ngsild.flink.constraint_combination_table --time -2")" -ge 1 ]
    [ "$(grep -cE 'kafka-topics.sh.*--(delete|create|alter)' "${CALLS}" || true)" -eq 0 ]
    [ "$(calls "delete kafkatopic")" -eq 0 ]
    [ "$(cat "${STATE}/topics/iff.ngsild.entities.start")" = "0 0" ]
    [ "$(cat "${STATE}/topics/iff.ngsild.flink.constraint_table.start")" = "0 50" ]
}

@test "with a fresh job: the stop waits until the statementset and its job are gone" {
    export REPLACE=fresh STUB_SS_LINGER=3
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "kubectl get beamsqlstatementset shacl-validation --ignore-not-found -o name")" -gt 3 ]
}

@test "no validation deployed: stops before the first step and changes nothing" {
    rm "${STATE}/ss.json"
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    # shellcheck disable=SC2154  # stderr is assigned by run --separate-stderr
    [[ "${stderr}" == *"resync refused before step 1/6: no validation statementset shacl-validation is deployed in iff: deploy the validation first (make flink-deploy)"* ]]
    [[ "${output}" != *"step 1/"* ]]
    [ "$(calls "patch")" -eq 0 ]
    [ "$(calls "curl")" -eq 0 ]
    [ ! -s "${STATE}/posts.log" ]
}

@test "iff.alerts with more than one partition: refused before the first step" {
    export STUB_ALERTS_PARTITIONS=2
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync refused before step 1/6: the topic iff.alerts has 2 partitions"* ]]
    [ "$(calls "patch")" -eq 0 ]
    [ "$(calls "curl")" -eq 0 ]
}

@test "another resync marked as running: refused, unless forced" {
    jq -c --arg d "$(( $(date +%s) + 600 ))" '. + {resync_since: "1795100000", resync_step: "3/6 reset Core Services", resync_deadline: $d}' \
        "${STATE}/marks.json" > "${STATE}/m" && mv "${STATE}/m" "${STATE}/marks.json"
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"another resync is marked as running"*"3/6 reset Core Services"*"RESYNC_FORCE=true"* ]]
    [ "$(calls "patch")" -eq 0 ]
    RESYNC_FORCE=true run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------- restore from a checkpoint

@test "REPLACE=checkpoint is refused before the first step, names #1042 and what is missing, calls nothing" {
    export REPLACE=checkpoint RESTORE_FROM=s3://flink/checkpoints/chk-7
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"REPLACE=checkpoint RESTORE_FROM=s3://flink/checkpoints/chk-7 is not supported yet, see #1042"* ]]
    [[ "${stderr}" == *"The statementset can't be started from a given checkpoint yet"* ]]
    [[ "${stderr}" == *"no field naming a checkpoint or savepoint to start from"* ]]
    [[ "${stderr}" == *"checkpointing is off unless"*"externalized checkpoints are not configured"* ]]
    [[ "${stderr}" == *"passes the location"*"reads every setting as a map"* ]]
    [[ "${stderr}" == *"Nothing has been changed."* ]]
    [[ "${output}" != *"step "* ]]
    # no alert, job, topic or ConfigMap touched: nothing called at all
    [ ! -s "${CALLS}" ]
}

@test "an unknown REPLACE is refused and calls nothing" {
    export REPLACE=redeploy
    run bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${output}" == *"REPLACE must be none, fresh, package or checkpoint"* ]]
    [ ! -s "${CALLS}" ]
}

# ---------------------------------------------------------------- the close step

@test "the close step: the SHACL filter, repeated until 404, then the count" {
    export STUB_PUT_PAGES=3
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "curl PUT /api/_bulk/alerts/status?service=SHACL%20Validator&status=open&status=assign&status=ack&status=shelved&status=blackout&status=expired&status=unknown")" -eq 4 ]
    [ "$(calls "curl PUT")" -eq 4 ]
    # counted before and after
    [ "$(calls "curl GET /api/alerts?service=SHACL%20Validator&status=open&status=assign&status=ack&status=shelved&status=blackout&status=expired&status=unknown&page-size=1")" -eq 2 ]
    [ "$(calls "status!=")" -eq 0 ]
    jq -e '.status == "closed" and (.text | contains("make shacl-resync"))' "${STATE}/close_body"
    [[ "${output}" == *"  3 SHACL alerts are not closed"* ]]
    [[ "${output}" == *"  closed 3 SHACL alerts in 3 requests"* ]]
}

@test "the close filter names every status but closed, so it misses none" {
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    filter=$(grep -m1 -F "curl PUT /api/_bulk/alerts/status?" "${CALLS}" | sed 's/.*?//')
    for st in open assign ack shelved blackout expired unknown; do
        [[ "&${filter}&" == *"&status=${st}&"* ]]
    done
    [[ "${filter}" != *"status=closed"* ]]
}

@test "nothing to close: the first 404 is nothing left" {
    export STUB_PUT_PAGES=0 STUB_OPEN_BEFORE=0
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "curl PUT")" -eq 1 ]
    [[ "${output}" == *"  closed 0 SHACL alerts in 0 requests"* ]]
}

@test "the bulk close matching nothing while alerts are not closed fails the close step" {
    export STUB_PUT_PAGES=0 STUB_OPEN_BEFORE=5
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 2/6 close the SHACL alerts: the bulk close matched none of the 5 SHACL alerts that are not closed"* ]]
    [ "$(calls "patch flinksessionjob")" -eq 0 ]
}

@test "the close step fails when SHACL alerts are left that are not closed" {
    export STUB_LEFT_OPEN=2
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 2/6 close the SHACL alerts: 2 SHACL alerts are still not closed"* ]]
    [ "$(calls "patch flinksessionjob")" -eq 0 ]
}

@test "without a stop the close step waits for no settle time" {
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "from-date=")" -eq 0 ]
}

@test "after a stop the close step waits while SHACL alerts arrive, then closes" {
    export REPLACE=fresh STUB_SETTLE_BUSY=3
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "from-date=")" -eq 4 ]
    [ "$(last_line "from-date=")" -lt "$(line "curl PUT")" ]
    [ "$(line "kafka-delete-records.sh")" -lt "$(line "from-date=")" ]
}

@test "after a stop the close step does not begin before the settle time has passed" {
    export REPLACE=fresh RESYNC_SETTLE=2
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "from-date=")" -ge 1 ]
    # the first look at Alerta's recent SHACL alerts comes the settle time
    # after the delete, although no alert arrives meanwhile
    deleted=$(grep -m1 -F 'kubectl delete beamsqlstatementset' "${STATE}/times.log" | cut -d' ' -f1)
    first=$(grep -m1 -F 'from-date=' "${STATE}/times.log" | cut -d' ' -f1)
    awk -v d="${deleted}" -v f="${first}" 'BEGIN { exit !(f - d >= 2) }'
    # and the close only after it
    put=$(grep -m1 -F 'curl PUT /api/_bulk' "${STATE}/times.log" | cut -d' ' -f1)
    awk -v p="${put}" -v f="${first}" 'BEGIN { exit !(p >= f) }'
}

# ---------------------------------------------------------------- reset Core Services

@test "the reset sets a new restart nonce and waits for a new job" {
    echo 7 > "${STATE}/cs_nonce"
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(cat "${STATE}/cs_patch")" = '{"spec":{"restartNonce":8}}' ]
    [[ "${output}" == *"Core Services: job cs-0 replaced by cs-1"* ]]
}

# ---------------------------------------------------------------- the re-snapshot

@test "the re-snapshot deletes the Connect pods and never touches the CronJob" {
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "delete pod -l app.kubernetes.io/instance=kafka-connect")" -eq 1 ]
    [ "$(calls "kafka-connect-restart")" -eq 0 ]
    [ "$(grep -c 'cronjob' "${CALLS}")" -eq "$(( $(calls "get cronjob platform-watchdog") + $(calls "create job --from=cronjob/platform-watchdog") ))" ]
    [[ "${output}" == *"entity-table-connector: snapshot completed "*"s after the Connect pods were deleted"* ]]
}

@test "a snapshot that started before the resync began does not count" {
    export STUB_SNAPSHOT_AGE=100
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 4/6 trigger a complete re-snapshot"*"no completed snapshot that started after"*"entity-table-connector rdf-table-connector"* ]]
    [ "$(calls "kafka-console-producer.sh")" -eq 0 ]
}

@test "a snapshot that dies halfway does not count" {
    export STUB_SNAPSHOT_INCOMPLETE=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 4/6 trigger a complete re-snapshot: a completed snapshot of every connector after the resync began not reached within 2s"* ]]
    [[ "${output}" != *"step 5/6"* ]]
}

@test "a snapshot the periodic restart started after the resync began counts" {
    # the CronJob restarts the pods during the reset; the resync's own
    # snapshot is then cut short
    export STUB_CRON_SNAPSHOT=1 STUB_SNAPSHOT_INCOMPLETE=1
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
}

# ---------------------------------------------------------------- processed

@test "processed: the debezium-bridge's lag keeps it waiting" {
    export STUB_BRIDGE_LAG_POLLS=4
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(calls "kafka-consumer-groups.sh")" -gt 4 ]
}

@test "processed: an empty topic the debezium-bridge has no offset for is no lag (#1204)" {
    # No entity was ever in Scorpio: iff.ngsild.public.entity is empty, and
    # the bridge, which subscribes from the end, has committed nothing.
    export STUB_BRIDGE_UNCOMMITTED=0
    echo "0 0" > "${STATE}/topics/iff.ngsild.public.entity.start"
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
}

@test "processed: a topic emptied by retention that the debezium-bridge has no offset for is no lag (#1204)" {
    # every record deleted by retention: it ends at 7 and starts at 7
    export STUB_BRIDGE_UNCOMMITTED=7
    echo "0 7" > "${STATE}/topics/iff.ngsild.public.entity.start"
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
}

@test "processed: records the debezium-bridge has no offset for keep it waiting" {
    export STUB_BRIDGE_UNCOMMITTED=7
    echo "0 2" > "${STATE}/topics/iff.ngsild.public.entity.start"
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"the debezium-bridge has 1 records left"* ]]
}

@test "processed: pendingRecords of the validation job keep it waiting" {
    export STUB_PENDING_POLLS=4
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(cat "${STATE}/count.values.ss")" -gt 4 ]
}

@test "processed: a source behind its end offset keeps it waiting" {
    export STUB_BEHIND_POLLS=4
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(cat "${STATE}/count.values.ss")" -gt 4 ]
}

@test "processed: the end offsets are those after the snapshot, of the sources the jobs report" {
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    # every source topic of both jobs, from their vertices
    for t in iff.ngsild.entities iff.ngsild.attributes iff.ngsild.flink.constraint_trigger_table iff.alerts.bulk; do
        [ "$(last_line "--topic ${t} --time -1")" -gt "$(line "delete pod -l app.kubernetes.io/instance=kafka-connect")" ]
    done
    [[ "${output}" == *"sources, as Flink names them: iff_alerts_bulk iff_ngsild_attributes iff_ngsild_entities iff_ngsild_flink_constraint_trigger_table"* ]]
}

@test "processed: a source Flink names that Kafka doesn't have fails the wait step, naming it" {
    export STUB_CORE_EXTRA_TOPIC=iff.no.such.topic
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 5/6 wait until the re-snapshot is processed"*"the source topic iff_no_such_topic reported by Flink is not in Kafka"* ]]
}

@test "reset: Core Services' end offsets come from its known topics, not from its metrics" {
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    reset_done=$(grep -n -F "patch flinksessionjob" "${CALLS}" | cut -d: -f1)
    snapshot=$(line "delete pod -l app.kubernetes.io/instance=kafka-connect")
    for t in iff.alerts.bulk iff.ngsild.attributes iff.ngsild.attributes_insert; do
        n=$(line "--topic ${t} --time -1")
        [ "${n}" -gt "${reset_done}" ]
        [ "${n}" -lt "${snapshot}" ]
    done
    # the offsets are read once its reader of iff.alerts.bulk is placed
    [ "$(line "curl GET /jobs/cs-1/vertices/v-src/metrics")" -gt "${reset_done}" ]
    [ "$(line "curl GET /jobs/cs-1/vertices/v-src/metrics")" -lt "$(line "--topic iff.alerts.bulk --time -1")" ]
}

@test "reset: a source topic of Core Services that can't be read fails the reset step, naming it" {
    mv "${STATE}/topics/iff.ngsild.attributes_insert.end" "${STATE}/gone"
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 3/6 reset Core Services: the end offsets of iff.ngsild.attributes_insert, a source of Core Services, can't be read"* ]]
    [ "$(calls "delete pod")" -eq 0 ]
}

@test "processed: what was in iff.alerts.bulk before Core Services started is not left for it" {
    # Core Services' source reports no offset (it read nothing since it
    # started at the latest offset), and nothing came after it started
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
}

@test "processed: what was in iff.ngsild.attributes before a new validation job's readers were placed is not left for them" {
    # The CI deploy suite: an earlier suite wrote attributes, the snapshot has
    # no attribute of its entities, and the new job's latest-offset reader of
    # iff.ngsild.attributes has read nothing since it was placed.
    export REPLACE=fresh STUB_SS_ATTR_NOTHING=1 STUB_ATTR_NO_SNAPSHOT=1
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
}

@test "processed: records of iff.ngsild.attributes after a new validation job's readers were placed must be read" {
    export REPLACE=fresh STUB_SS_ATTR_NOTHING=1
    run --separate-stderr bash "${SCRIPT}"
    echo "${stderr}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"wait until the re-snapshot is processed"*"the validation job ss-1 read iff.ngsild.attributes partition 0 to nothing of "* ]]
}

@test "processed: records of iff.alerts.bulk after Core Services started must be read" {
    export STUB_BULK_GROWS=3 STUB_CORE_BEHIND=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 5/6 wait until the re-snapshot is processed"*"the core job cs-1 read iff.alerts.bulk partition 0 to nothing of 33"* ]]
    [ "$(calls "kafka-console-producer.sh")" -eq 0 ]
    unset STUB_CORE_BEHIND
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
}

@test "processed: the marker is written after the quiet period, as a closed System alert, and waited for in Alerta" {
    export STUB_MARKER_DELAY=4
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(calls "event=ResyncMarker")" -gt 4 ]
    # behind the quiet period: no consumer is read after it
    [ "$(last_line "kafka-consumer-groups.sh")" -lt "$(line "kafka-console-producer.sh")" ]
    [ "$(last_line "/metrics?get=")" -lt "$(line "kafka-console-producer.sh")" ]
    grep -F "kafka-console-producer.sh" "${CALLS}" | grep -qF -- "--topic iff.alerts --property parse.key=true"
    # service System, severity normal, no status of its own, on an event the
    # watchdog does not post, so it never shows up as an open alert and leaves
    # the watchdog's alerts alone
    jq -e '.resource == "shacl-validation" and .event == "ResyncMarker" and .service == ["System"]
        and .severity == "normal" and (has("status") | not) and (has("correlate") | not)
        and .environment == "Development" and (.value | test("^[0-9]+-[0-9]+$"))' "${STATE}/marker.json"
    [[ "${output}" == *"the marker reached Alerta "*"s after it was written, closed"* ]]
}

@test "processed: a quiet period without the marker in Alerta fails in the wait step, naming the marker" {
    export STUB_MARKER_LOST=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 5/6 wait until the re-snapshot is processed: the marker in Alerta not reached within"*"has not reached Alerta"* ]]
    consistency_posts | tail -1 | grep -q '^critical RESYNC FAILED in step 5/6 wait until the re-snapshot is processed at '
    [ ! -e "${STATE}/watchdog_job" ]
}

@test "processed: records left at the time limit fail the wait step, naming the consumer" {
    export STUB_BEHIND_POLLS=100000
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 5/6 wait until the re-snapshot is processed: the debezium-bridge, the validation job and Core Services quiet for 1s not reached within"*"the validation job ss-0 read iff.ngsild"* ]]
    [ "$(calls "kafka-console-producer.sh")" -eq 0 ]
}

# ---------------------------------------------------------------- the marks and the degraded alert

@test "the marks: written at the first step, the step at every step, removed at the end, one watchdog run" {
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    first=$(head -1 "${STATE}/marks.log")
    jq -e '.data.resync_since and .data.resync_step == "1/6 mark the validation degraded"
        and (.data.resync_deadline | tonumber) > (.data.resync_since | tonumber)
        and .data.resync_failed == null' <<<"${first}"
    [ "$(jq -r '.data.resync_step // empty' "${STATE}/marks.log")" = "1/6 mark the validation degraded
2/6 close the SHACL alerts
3/6 reset Core Services
4/6 trigger a complete re-snapshot
5/6 wait until the re-snapshot is processed
6/6 end the degraded state" ]
    [ "$(tail -1 "${STATE}/marks.log")" = '{"data":{"resync_since":null,"resync_step":null,"resync_deadline":null,"resync_failed":null}}' ]
    [ "$(cat "${STATE}/marks.json")" = '{"observing_since":"1795100000"}' ]
    [[ "$(cat "${STATE}/watchdog_job")" == platform-watchdog-resync-* ]]
    [ "$(line "patch configmap")" -lt "$(line "curl POST /api/alert")" ]
}

@test "the degraded alert: a warning naming the resync and the step, before the first alert is closed" {
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(consistency_posts | wc -l)" -eq 6 ]
    run ! grep -q '"severity":"normal"' "${STATE}/posts.log"
    consistency_posts | head -1 | grep -qE '^warning DEGRADED -- RESYNC IN PROGRESS since [0-9T:-]+Z, step 1/6 mark the validation degraded: the SHACL alerts are incomplete until the resync has completed\.$'
    consistency_posts | grep -q '^warning .*step 5/6 wait until the re-snapshot is processed:'
    [ "$(line "curl POST /api/alert")" -lt "$(line "curl PUT /api/_bulk")" ]
    jq -e 'select(.event == "ValidationConsistency") | .service == ["System"] and .resource == "shacl-validation"
        and .environment == "Development"' "${STATE}/posts.log" >/dev/null
}

# ---------------------------------------------------------------- failures

@test "Alerta unreachable in the close step: fails there, Core Services keeps its job, the failure is marked" {
    export STUB_ALERTA_DOWN_AT="2/6"
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 2/6 close the SHACL alerts: Alerta not reachable"* ]]
    [[ "${output}" != *"step 3/6"* ]]
    [ "$(calls "patch flinksessionjob")" -eq 0 ]
    [ "$(cat "${STATE}/cs_job")" = "cs-0" ]
    jq -e '.resync_step == "2/6 close the SHACL alerts" and (.resync_failed | test("^[0-9]+ Alerta not reachable"))
        and (.resync_failed | contains("run make shacl-resync REPLACE=none again"))' "${STATE}/marks.json"
}

@test "a failed mark stops in step 1 and closes nothing" {
    export STUB_MARKS_FAIL=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 1/6 mark the validation degraded: the marks can't be written"* ]]
    [ "$(calls "curl PUT")" -eq 0 ]
}

@test "Alerta unreachable in step 1: stops there and closes nothing" {
    export STUB_ALERTA_DOWN=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 1/6 mark the validation degraded: Alerta not reachable"* ]]
    [ "$(calls "curl PUT")" -eq 0 ]
    jq -e '.resync_failed' "${STATE}/marks.json"
}

@test "the statementset not gone in time: fails in the stop step, empties no topic, closes nothing" {
    export REPLACE=fresh STUB_SS_STUCK=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 2/8 stop the validation job and empty its topics: the statementset gone not reached within 2s"* ]]
    [[ "${stderr}" == *"The SHACL validation doesn't run"*"make shacl-resync REPLACE=fresh"* ]]
    [ "$(calls "kafka-delete-records.sh")" -eq 0 ]
    [ "$(calls "curl PUT")" -eq 0 ]
}

@test "the job not cancelled in time: fails in the stop step" {
    export REPLACE=fresh STUB_JOB_STUCK=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 2/8 stop the validation job and empty its topics: the job ss-0 stopped not reached within 2s: the job ss-0 is CANCELLING"* ]]
    [ "$(calls "kafka-delete-records.sh")" -eq 0 ]
}

@test "records that can't be deleted fail the stop step" {
    export REPLACE=fresh STUB_DELETE_FAIL=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 2/8 stop the validation job and empty its topics: the records of iff.ngsild.flink.constraint_table can't be deleted"* ]]
    [ "$(calls "curl PUT")" -eq 0 ]
}

@test "Core Services not reset in time: fails in the reset step and triggers no snapshot" {
    export STUB_CS_STUCK=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 3/6 reset Core Services: one new Core Services job running not reached within 2s"* ]]
    [ "$(calls "delete pod")" -eq 0 ]
}

@test "the job not started: fails in the start step and says the validation doesn't run" {
    export REPLACE=fresh STUB_CREATE_FAIL=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 5/8 start the validation job: the statementset shacl-validation can't be created"* ]]
    [[ "${stderr}" == *"The SHACL validation doesn't run: its job was stopped and not started again"*"make shacl-resync REPLACE=fresh"* ]]
    [ "$(calls "delete pod")" -eq 0 ]
    jq -e '.resync_failed | contains("The SHACL validation doesn'"'"'t run") and contains("make shacl-resync REPLACE=fresh")' "${STATE}/marks.json"
}

@test "the marks not removed: fails in the last step, starts no watchdog run" {
    export STUB_MARKS_FAIL_ON='"resync_since":null'
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 6/6 end the degraded state: the marks can't be removed"* ]]
    [ ! -e "${STATE}/watchdog_job" ]
}

@test "a failure posts the critical alert, naming the step and the command" {
    export STUB_CS_STUCK=1
    run bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    jq -e 'select(.event == "ValidationConsistency" and .severity == "critical") | .timeout == 0
        and (.text | test("^RESYNC FAILED in step 3/6 reset Core Services at [0-9T:-]+Z: one new Core Services job running not reached"))
        and (.text | contains("The SHACL alerts may be incomplete or stale; run make shacl-resync REPLACE=none again."))' \
        "${STATE}/posts.log" >/dev/null
}

@test "failed while the job is stopped, then run again with the cause removed: completes" {
    export REPLACE=fresh STUB_ALERTA_DOWN_AT="3/8"
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 3/8 close the SHACL alerts"* ]]
    [[ "${stderr}" == *"The SHACL validation doesn't run: its job was stopped and not started again. After removing the cause, run in semantic-model/shacl2flink: make shacl-resync REPLACE=fresh"* ]]
    [ ! -e "${STATE}/ss.json" ]
    [ -s "${RESYNC_STATE_DIR}/iff.shacl-validation.json" ]
    # without a replacement it is refused: the job must be started
    rm -f "${STATE}/alerta_down"
    unset STUB_ALERTA_DOWN_AT
    REPLACE=none run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"a resync stopped it and did not start it again. make shacl-resync REPLACE=fresh starts it"* ]]
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(grep '^step ' <<<"${output}")" = "${STEPS_FRESH}" ]
    [ "$(calls "delete beamsqlstatementset")" -eq 1 ]
    [ "$(jq -r .status.job_id "${STATE}/ss.json")" = "ss-1" ]
    jq -e '.metadata.annotations["meta.helm.sh/release-name"] == "shacl"' "${STATE}/created.json"
    [ "$(cat "${STATE}/marks.json")" = '{"observing_since":"1795100000"}' ]
}

@test "run again after a failed step without a replacement: completes and removes the failure" {
    export STUB_CS_STUCK=1
    run bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    jq -e '.resync_failed' "${STATE}/marks.json"
    unset STUB_CS_STUCK
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(grep '^step ' <<<"${output}")" = "${STEPS_NONE}" ]
    jq -e 'has("resync_failed") | not' "${STATE}/marks.json"
}

@test "killed by a timeout in a step: the failure is marked at once, naming the interruption" {
    export STUB_CS_STUCK=1 RESYNC_RESET_TIMEOUT=60
    run timeout 4 bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    jq -e '.resync_step == "3/6 reset Core Services" and (.resync_failed | test("^[0-9]+ interrupted by SIGTERM"))' "${STATE}/marks.json"
}

@test "start: the re-snapshot waits until the new job's latest-offset readers have their partitions" {
    export REPLACE=fresh STUB_ATTR_SPLIT_LATE=4
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(cat "${STATE}/count.listings.ss-1")" -gt 4 ]
    [[ "${output}" == *"its readers of iff.ngsild.entities, iff.ngsild.attributes are placed"* ]]
    # no snapshot before the listing that showed the attributes' partition
    placed=$(grep -n -F "curl GET /jobs/ss-1/vertices/v-src/metrics" "${CALLS}" | grep -v 'get=' | sed -n 5p | cut -d: -f1)
    [ -n "${placed}" ]
    [ "${placed}" -lt "$(line "delete pod -l app.kubernetes.io/instance=kafka-connect")" ]
}

@test "start: a latest-offset reader that never gets its partition fails the start step, naming the topic" {
    export REPLACE=fresh STUB_ATTR_SPLIT_LATE=100000
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 5/8 start the validation job: the latest-offset sources of the new job placed not reached within 2s: no reader of the job ss-1 has a partition of: iff.ngsild.attributes"* ]]
    [ "$(calls "delete pod")" -eq 0 ]
}

# ---------------------------------------------------------------- the review's points

@test "Alerta's key is never in a curl command line: it comes from a header file only its owner can read" {
    export REPLACE=fresh
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ -s "${STATE}/curl.argv" ]
    run ! grep -q testkey "${STATE}/curl.argv"
    grep -q -- '-H @' "${STATE}/curl.argv"
    # every call to Alerta carried the header from the file
    [ ! -e "${STATE}/unauthorized" ]
}

@test "a curl older than 7.55 is refused before the first step" {
    export STUB_CURL_VERSION=7.54.1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync refused before step 1/6: curl 7.54.1 can't read a header from a file; the resync needs curl 7.55 or later"* ]]
    [ "$(calls "patch")" -eq 0 ]
}

@test "reset: the re-snapshot waits until the new Core Services job's reader of iff.alerts.bulk has its partition" {
    export STUB_CS_SPLIT_LATE=4
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"its reader of iff.alerts.bulk is placed"* ]]
    # the base of Core Services and the snapshot come after the listing that
    # showed the partition
    placed=$(grep -n -F "curl GET /jobs/cs-1/vertices/v-src/metrics" "${CALLS}" | grep -v 'get=' | sed -n 5p | cut -d: -f1)
    [ -n "${placed}" ]
    [ "${placed}" -lt "$(line "--topic iff.alerts.bulk --time -1")" ]
    [ "${placed}" -lt "$(line "delete pod -l app.kubernetes.io/instance=kafka-connect")" ]
}

@test "reset: a reader of iff.alerts.bulk that never gets its partition fails the reset step and triggers no snapshot" {
    export STUB_CS_SPLIT_LATE=100000
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 3/6 reset Core Services: the reader of iff.alerts.bulk of the new Core Services job placed not reached within 2s: no reader of the job cs-1 has a partition of: iff.alerts.bulk"* ]]
    [ "$(calls "delete pod")" -eq 0 ]
}

@test "the deadline covers what every step can take" {
    export REPLACE=fresh
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    first=$(head -1 "${STATE}/marks.log")
    span=$(jq -r '(.data.resync_deadline | tonumber) - (.data.resync_since | tonumber)' <<<"${first}")
    # two waits each in the stop, the reset and the start, the topic emptying,
    # the settle time, the close, the snapshot and the wait step
    min=$(( 2 * RESYNC_STOP_TIMEOUT + 3 * 60 + RESYNC_SETTLE_TIMEOUT + RESYNC_CLOSE_TIMEOUT + 2 * RESYNC_RESET_TIMEOUT \
        + 2 * RESYNC_START_TIMEOUT + RESYNC_SNAPSHOT_TIMEOUT + RESYNC_PROCESSED_TIMEOUT ))
    [ "${span}" -gt "${min}" ]
}

@test "TERM during a step ends the step at once, marks and posts the failure, and exits 143" {
    export STUB_CS_STUCK=1 RESYNC_RESET_TIMEOUT=120
    bash "${SCRIPT}" > "${WORK}/out" 2> "${WORK}/err" &
    pid=$!
    for _ in $(seq 1 100); do grep -q '3/6 reset Core Services' "${STATE}/marks.log" 2>/dev/null && break; sleep 0.1; done
    sleep 0.5
    kill -TERM "${pid}"
    start=$(date +%s)
    rc=0
    wait "${pid}" || rc=$?
    [ "${rc}" -eq 143 ]
    [ $(( $(date +%s) - start )) -lt 10 ]
    grep -q 'resync failed in step 3/6 reset Core Services: interrupted by SIGTERM' "${WORK}/err"
    jq -e '.resync_failed | test("^[0-9]+ interrupted by SIGTERM")' "${STATE}/marks.json"
    jq -e 'select(.event == "ValidationConsistency" and .severity == "critical") | .text | startswith("RESYNC FAILED in step 3/6 reset Core Services")' \
        "${STATE}/posts.log" >/dev/null
}

@test "INT during a step ends it the same way and exits 130" {
    export STUB_CS_STUCK=1 RESYNC_RESET_TIMEOUT=120
    # a job started with & ignores INT; start the script as a terminal would
    python3 -c 'import os, signal, sys; signal.signal(signal.SIGINT, signal.SIG_DFL); os.execvp("bash", ["bash", sys.argv[1]])' \
        "${SCRIPT}" > "${WORK}/out" 2> "${WORK}/err" &
    pid=$!
    for _ in $(seq 1 100); do grep -q '3/6 reset Core Services' "${STATE}/marks.log" 2>/dev/null && break; sleep 0.1; done
    sleep 0.5
    kill -INT "${pid}"
    rc=0
    wait "${pid}" || rc=$?
    [ "${rc}" -eq 130 ]
    grep -q 'resync failed in step 3/6 reset Core Services: interrupted by SIGINT' "${WORK}/err"
    jq -e 'select(.event == "ValidationConsistency" and .severity == "critical")' "${STATE}/posts.log" >/dev/null
}

@test "the stopped statementset is kept where only its owner can read it" {
    export REPLACE=fresh STUB_CREATE_FAIL=1
    run bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [ "$(stat -c %a "${RESYNC_STATE_DIR}")" = 700 ]
    [ "$(stat -c %a "${RESYNC_STATE_DIR}/iff.shacl-validation.json")" = 600 ]
}

@test "control characters, quotes and backslashes of a reason don't reach the marks" {
    export STUB_BULK_ERROR=1
    run bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    failed=$(jq -r '.resync_failed' "${STATE}/marks.json")
    [[ "${failed}" == *"the bulk close answered 500"* ]]
    run ! grep -qP '[\x00-\x1f\x7f"\\]' <<<"${failed}"
}


# ---------------------------------------------------------------- a new package (#1165)

STEPS_PACKAGE='step 1/9 mark the validation degraded: started
step 1/9 mark the validation degraded: done
step 2/9 stop the validation job and empty its topics: started
step 2/9 stop the validation job and empty its topics: done
step 3/9 close the SHACL alerts: started
step 3/9 close the SHACL alerts: done
step 4/9 reset Core Services: started
step 4/9 reset Core Services: done
step 5/9 install the new package: started
step 5/9 install the new package: done
step 6/9 start the new package'"'"'s validation job: started
step 6/9 start the new package'"'"'s validation job: done
step 7/9 trigger a complete re-snapshot: started
step 7/9 trigger a complete re-snapshot: done
step 8/9 wait until the re-snapshot is processed: started
step 8/9 wait until the re-snapshot is processed: done
step 9/9 end the degraded state: started
step 9/9 end the degraded state: done'

# package_install [fail]: the install command of a new package, as the deploy
# passes it: it writes the tables and creates the package's statementset.
# iff.rdf's start and end offsets for the records in rdf.topic: the read of
# the knowledge takes exactly that many records.
rdf_offsets() {
    echo "0 ${RDF_START:-0}" > "${STATE}/topics/iff.rdf.start"
    echo "0 $(( ${RDF_START:-0} + $(grep -c . "${STATE}/rdf.topic") ))" > "${STATE}/topics/iff.rdf.end"
}

package_install() {
    # The new package's knowledge, as the install leaves the rdf table, and
    # iff.rdf holding the same keys: nothing to remove.
    printf '%s\n' '{"subject" : "s1", "predicate" : "p", "index" : 0}' '{"subject" : "s2", "predicate" : "p", "index" : 0}' > "${STATE}/rdf.table"
    printf '%s\t%s\n' '{"subject":"s1","predicate":"p","index":0}' '{"object":"o1"}' \
        '{"subject":"s2","predicate":"p","index":0}' '{"object":"o2"}' > "${STATE}/rdf.topic"
    rdf_offsets
    cat > "${WORK}/bin/install-package" <<'EOF'
#!/bin/bash
echo "install: write the tables" >> "${CALLS}"
[ -z "${STUB_INSTALL_FAIL:-}" ] || exit 3
jq -n '{apiVersion: "industry-fusion.com/v1alpha4", kind: "BeamSqlStatementSet",
    metadata: {name: "shacl-validation", namespace: "iff",
        labels: {"app.kubernetes.io/managed-by": "Helm"},
        annotations: {"meta.helm.sh/release-name": "shacl", "meta.helm.sh/release-namespace": "iff"}},
    spec: {tables: ["t2"], updateStrategy: "none"}}' | kubectl -n iff create -f -
echo "install: the statementset created" >> "${CALLS}"
EOF
    chmod +x "${WORK}/bin/install-package"
    export REPLACE=package RESYNC_INSTALL=install-package
}

@test "a new package: every step in its order, the tables only after the stop, the new statementset's job" {
    package_install
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ "$(grep '^step ' <<<"${output}")" = "${STEPS_PACKAGE}" ]
    delete=$(line "kubectl delete beamsqlstatementset shacl-validation --wait=false")
    gone=$(line "stub: the statementset is gone")
    cancelled=$(line "stub: the job ss-0 is cancelled")
    emptied=$(last_line "kafka-delete-records.sh")
    reset=$(line "kubectl patch flinksessionjob")
    tables=$(line "install: write the tables")
    snapshot=$(line "kubectl delete pod -l app.kubernetes.io/instance=kafka-connect")
    [ "${delete}" -lt "${gone}" ]
    [ "${gone}" -lt "${tables}" ]
    [ "${cancelled}" -lt "${tables}" ]
    [ "${emptied}" -lt "${tables}" ]
    [ "${reset}" -lt "${tables}" ]
    [ "${tables}" -lt "${snapshot}" ]
    # the package's statementset runs with another job, the stopped one is not created again
    [ "$(jq -r .status.job_id "${STATE}/ss.json")" = "ss-1" ]
    [ "$(jq -c .spec.tables "${STATE}/ss.json")" = '["t2"]' ]
    [ "$(calls "kubectl create -f -")" -eq 1 ]
    [ -z "$(ls -A "${RESYNC_STATE_DIR}" 2>/dev/null)" ]
    [[ "${output}" == *"job ss-0 replaced by ss-1"* ]]
}

@test "a new package: the three topics are emptied, no topic is deleted" {
    package_install
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    [ "$(jq -c '.partitions[]' "${STATE}/deleted.log")" = '{"topic":"iff.ngsild.flink.constraint_table","partition":0,"offset":50}
{"topic":"iff.ngsild.flink.constraint_trigger_table","partition":0,"offset":50}' ]
    [ "$(grep -cE 'kafka-topics.sh.*--(delete|create|alter)' "${CALLS}" || true)" -eq 0 ]
    [ "$(calls "delete kafkatopic")" -eq 0 ]
}

@test "a new package with no validation deployed: nothing to stop, installed and started" {
    package_install
    rm -f "${STATE}/ss.json"
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"no validation statementset shacl-validation is deployed: nothing to stop"* ]]
    [ "$(calls "kubectl delete beamsqlstatementset")" -eq 0 ]
    [ "$(line "install: write the tables")" -gt 0 ]
    [ "$(jq -r .status.job_id "${STATE}/ss.json")" = "ss-1" ]
}

@test "a first package: the job's topics don't exist yet, nothing to empty, installed and started" {
    package_install
    rm -f "${STATE}/ss.json" "${STATE}"/topics/iff.ngsild.flink.*
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"iff.ngsild.flink.constraint_table: not created yet, nothing to empty"* ]]
    [[ "${output}" == *"iff.ngsild.flink.constraint_trigger_table: not created yet, nothing to empty"* ]]
    [ "$(calls "kafka-delete-records.sh")" -eq 0 ]
    [ "$(jq -r .status.job_id "${STATE}/ss.json")" = "ss-1" ]
}

@test "a fresh job still needs its topics: a missing one fails the stop step" {
    export REPLACE=fresh
    rm -f "${STATE}"/topics/iff.ngsild.flink.constraint_table.*
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"the end offsets of iff.ngsild.flink.constraint_table can't be read"* ]]
}

@test "a new package after a failed resync with a fresh job: the kept statementset is discarded, not refused" {
    package_install
    mkdir -p "${RESYNC_STATE_DIR}"
    jq '. + {metadata: (.metadata + {annotations: {"shacl-resync/stopped-job": "ss-0"}})}' "${STATE}/ss.json" \
        > "${RESYNC_STATE_DIR}/iff.shacl-validation.json"
    rm -f "${STATE}/ss.json"
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"is discarded: the new package replaces it"* ]]
    [ ! -e "${RESYNC_STATE_DIR}/iff.shacl-validation.json" ]
    [ "$(jq -c .spec.tables "${STATE}/ss.json")" = '["t2"]' ]
}

@test "a new package: each live key of iff.rdf its knowledge lacks gets a tombstone, after the install (#1165 D6)" {
    package_install
    # s3 is in iff.rdf but not in the new table: removed by the package.
    # s4 is a tombstone already; s5 was one and is live again, and in the table.
    printf '%s\n' '{"subject" : "s1", "predicate" : "p", "index" : 0}' '{"subject" : "s5", "predicate" : "p", "index" : 0}' > "${STATE}/rdf.table"
    printf '%s\t%s\n' '{"subject":"s1","predicate":"p","index":0}' '{"object":"o1"}' \
        '{"subject":"s3","predicate":"p","index":0}' '{"object":"o3"}' \
        '{"subject":"s4","predicate":"p","index":0}' '{"object":"o4"}' \
        '{"subject":"s4","predicate":"p","index":0}' 'null' \
        '{"subject":"s5","predicate":"p","index":0}' 'null' \
        '{"subject":"s5","predicate":"p","index":0}' '{"object":"o5"}' > "${STATE}/rdf.topic"
    # The topic's earliest offset is no longer 0 (retention): it is read from
    # there, all of it.
    RDF_START=1200 rdf_offsets
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    # exactly s3, with its key's own bytes and the null marker
    [ "$(cat "${STATE}/rdf.tombstones")" = "$(printf '%s\t%s' '{"subject":"s3","predicate":"p","index":0}' '__shacl_resync_tombstone__')" ]
    [[ "${output}" == *"2 triples in the new package; 3 live keys in iff.rdf, 1 of them removed by a tombstone"* ]]
    # after the tables are written, before the new job is started
    [ "$(line "install: write the tables")" -lt "$(line "stub: tombstones written to iff.rdf")" ]
}

@test "a read of iff.rdf that ends before its end offset writes no tombstone: the install step fails" {
    package_install
    # The end offset promises more records than the consumer returns.
    echo "0 9" > "${STATE}/topics/iff.rdf.end"
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -ne 0 ]
    [ ! -e "${STATE}/rdf.tombstones" ]
    [[ "${output}" == *"only 2 of the 9 records of iff.rdf could be read"* ]]
}

@test "the same knowledge again: no tombstone is written" {
    package_install
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [ ! -e "${STATE}/rdf.tombstones" ]
    [[ "${output}" == *"2 live keys in iff.rdf, 0 of them removed by a tombstone"* ]]
}

@test "an empty or unreadable rdf table removes no knowledge: the install step fails" {
    package_install
    : > "${STATE}/rdf.table"
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -ne 0 ]
    [ ! -e "${STATE}/rdf.tombstones" ]
    [[ "${output}" == *"the rdf table is empty or can't be read: no knowledge is removed"* ]]
    package_install
    export STUB_RDF_DB_DOWN=1
    run bash "${SCRIPT}"
    echo "${output}"
    [ "$status" -ne 0 ]
    [ ! -e "${STATE}/rdf.tombstones" ]
    [[ "${output}" == *"the keys of the rdf table can't be read"* ]]
}

@test "a new package whose install fails: the install step named, the deploy named, the failure marked" {
    package_install
    export STUB_INSTALL_FAIL=1
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"resync failed in step 5/9 install the new package: the install of the new package failed (exit 3)"* ]]
    [[ "${stderr}" == *"its job was stopped for a new package"*"make flink-deploy"* ]]
    [[ "${stderr}" != *"REPLACE=fresh"* ]]
    jq -e '.resync_failed | contains("make flink-deploy") and (contains("REPLACE=fresh") | not)' "${STATE}/marks.json"
    [ "$(calls "delete pod")" -eq 0 ]
    jq -e 'select(.event == "ValidationConsistency" and .severity == "critical")' "${STATE}/posts.log" >/dev/null
}

@test "a new package without an install command is refused and calls nothing" {
    export REPLACE=package
    unset RESYNC_INSTALL
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -eq 2 ]
    [[ "${stderr}" == *"REPLACE=package needs RESYNC_INSTALL"* ]]
    [ ! -s "${CALLS}" ]
}

@test "a new package while another resync runs: refused before the first step, nothing installed" {
    package_install
    echo "{\"observing_since\":\"1795100000\",\"resync_since\":\"$(date +%s)\",\"resync_step\":\"3/8 close\",\"resync_deadline\":\"$(( $(date +%s) + 600 ))\"}" \
        > "${STATE}/marks.json"
    run --separate-stderr bash "${SCRIPT}"
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"another resync is marked as running"* ]]
    [ "$(calls "install: write the tables")" -eq 0 ]
    [ "$(calls "kubectl delete beamsqlstatementset")" -eq 0 ]
}

@test "a new package: the deadline includes the install" {
    package_install
    export RESYNC_INSTALL_TIMEOUT=5000
    run bash "${SCRIPT}"
    [ "$status" -eq 0 ]
    deadline=$(grep -o '"resync_deadline":"[0-9]*"' "${STATE}/marks.log" | head -1 | grep -o '[0-9]*')
    export RESYNC_INSTALL_TIMEOUT=0
    rm -f "${STATE}/marks.log"; : > "${STATE}/marks.log"
    echo '{"observing_since":"1795100000"}' > "${STATE}/marks.json"
    run bash "${SCRIPT}"
    short=$(grep -o '"resync_deadline":"[0-9]*"' "${STATE}/marks.log" | head -1 | grep -o '[0-9]*')
    [ $(( deadline - short )) -ge 4990 ]
}
