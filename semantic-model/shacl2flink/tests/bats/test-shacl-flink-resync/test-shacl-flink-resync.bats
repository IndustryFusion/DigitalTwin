#!/usr/bin/env bats
#
# Copyright (c) 2026 IndustryFusion Foundation
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

# The resync of the SHACL alerts (`make shacl-resync`) on the platform: after
# it the alerts that are not closed are exactly those of the constraints
# violated now, with and without a fresh validation job.
#
# The leaf checks write only violations, so a raise that nothing retracts
# stays. Each round sets such stale raises up on purpose: an entity violates
# a constraint, the raise records the job wrote are kept, the constraint is
# satisfied (or the entity deleted), and the kept records are written again,
# to iff.alerts.bulk so that the alert is open again, and before the fresh
# round also to constraint_trigger_table, as a previous job leaves them for
# its successor to replay. The resync must close those alerts and keep them
# closed, bring the alert of a constraint still violated back, and leave
# another service's alert, the topics and iff.ngsild.entities alone.
#
# Round 1 runs `make shacl-resync`, round 2 `make shacl-resync REPLACE=fresh`
# with the alerta-bridge held back while the resync waits, so the resync
# must wait for its marker in Alerta.
#
# Driven by `make test-flink-e2e` after test-shacl-flink-e2e and
# test-shacl-flink-scorpio-e2e, against the deployment of tests/e2e-kms. The
# tests run in order and share their findings through files; each needs the
# ones before it.

NAMESPACE=${NAMESPACE:-iff}
SHACL2FLINK="${BATS_TEST_DIRNAME}/../../.."

# As in test-shacl-flink-scorpio-e2e: the services published by
# test/setup-local-ingress.sh.
KEYCLOAK_URL=${KEYCLOAK_URL:-http://keycloak.local/auth/realms}
NGSILD_URL=${NGSILD_URL:-http://ngsild.local/ngsi-ld/v1}
ALERTA_URL=${ALERTA_URL:-http://alerta.local/api}
CLIENT_ID=scorpio
REALM_USER=realm_user
USER_SECRET=secret/credential-iff-realm-user-iff

CONTEXT=https://industryfusion.github.io/contexts/staging/example/v0.2/context.jsonld
E2E=https://industryfusion.github.io/contexts/example/v0/base_entities
MACHINE_TYPE=${E2E}/E2EMachine
RANGE_TYPE=${E2E}/E2ERangeMachine
FREE_TYPE=${E2E}/E2EFreeMachine
STATE_PROP=${E2E}/hasE2EState
RANGE_PROP=${E2E}/hasE2ERange
COUNT_CONSTRAINT=CountConstraintComponent
XONE_CONSTRAINT=XoneConstraintComponent

KAFKA_POD=my-cluster-nodes-0
TRIGGER_TOPIC=iff.ngsild.flink.constraint_trigger_table
JOB_TOPICS="iff.ngsild.flink.constraint_table iff.ngsild.flink.constraint_combination_table ${TRIGGER_TOPIC}"
BULK_ALERTS_TOPIC=iff.alerts.bulk
ALERTS_TOPIC=iff.alerts
ENTITY_TOPIC=iff.ngsild.entities
OTHER_SERVICE="E2E Resync"

# Alerts appear and close within seconds on an idle cluster; as in the
# Scorpio suite the limit is far above that. The still violated alert must be
# back within one minute of the resync, and the closed ones still closed two
# minutes after it. The watchdog runs every two minutes.
TIMEOUT=${TIMEOUT:-180}
POLL=5
BACK=60
SETTLED=120
WATCHDOG_RUN=150
# Every call to the platform is bounded, and so is every test and the
# resync itself, so that a wait that never ends fails with its name instead
# of running into the shard's time limit.
KUBECTL_LIMIT=${KUBECTL_LIMIT:-60}
KAFKA_LIMIT=${KAFKA_LIMIT:-120}
RESYNC_LIMIT=${RESYNC_LIMIT:-1200}
export BATS_TEST_TIMEOUT=${BATS_TEST_TIMEOUT:-1800}
# the resync's own time limits, so that it fails within RESYNC_LIMIT
export RESYNC_STOP_TIMEOUT=${RESYNC_STOP_TIMEOUT:-180}
export RESYNC_SETTLE_TIMEOUT=${RESYNC_SETTLE_TIMEOUT:-180}
export RESYNC_CLOSE_TIMEOUT=${RESYNC_CLOSE_TIMEOUT:-120}
export RESYNC_RESET_TIMEOUT=${RESYNC_RESET_TIMEOUT:-300}
# measured in CI: 104 s from the create to the readers placed; limits are at
# least three times the measured step
export RESYNC_START_TIMEOUT=${RESYNC_START_TIMEOUT:-420}
export RESYNC_SNAPSHOT_TIMEOUT=${RESYNC_SNAPSHOT_TIMEOUT:-420}
export RESYNC_PROCESSED_TIMEOUT=${RESYNC_PROCESSED_TIMEOUT:-600}

k() {
    timeout "${KUBECTL_LIMIT}" kubectl -n "${NAMESPACE}" "$@"
}

progress() {  # a line in the CI log as it happens, findable by its tag
    echo "# [resync-e2e] $(date -u +%H:%M:%S) $*" >&3
}

# What the platform looks like after a failed test: names, states and
# numbers only.
diagnose() {
    local f jm cp
    progress "diagnostics after the failed test: ${BATS_TEST_DESCRIPTION}"
    f=$(find "${BATS_FILE_TMPDIR}" -maxdepth 1 -name 'resync.[12]' -newer "${BATS_FILE_TMPDIR}/ids" 2>/dev/null | sort | tail -1)
    if [ -n "${f}" ]; then
        progress "the last lines of the resync's output:"
        tail -30 "${f}" | cut -d' ' -f2- | cut -c1-300 | sed 's/^/#   /' >&3
    fi
    progress "pods:"
    k get pods --no-headers -o custom-columns='NAME:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount' \
        2>/dev/null | sed 's/^/#   /' >&3 || true
    progress "statementset: $(k get beamsqlstatementset shacl-validation -o jsonpath='{.status.state} {.status.job_id}' 2>/dev/null || echo missing)"
    progress "Core Services: $(k get flinksessionjob core-services-job -o jsonpath='{.status.jobStatus.state} {.status.jobStatus.jobId} nonce={.spec.restartNonce}' 2>/dev/null || echo missing)"
    progress "alerta-bridge replicas: $(k get deployment alerta-bridge -o jsonpath='{.spec.replicas}/{.status.readyReplicas}' 2>/dev/null || echo unknown)"
    jm=$(k get pods -l component=jobmanager -o jsonpath='{.items[0].metadata.name}' 2>/dev/null) || jm=""
    if [ -n "${jm}" ]; then
        progress "Flink jobs:"
        k exec "${jm}" -c flink-main-container -- curl -s -m 10 http://localhost:8081/jobs/overview 2>/dev/null \
            | jq -r '.jobs[]? | "#   \(.name) \(.jid) \(.state) \(.tasks.running)/\(.tasks.total)"' >&3 || true
    fi
    cp=$(k get pods -l app.kubernetes.io/instance=kafka-connect -o jsonpath='{.items[0].metadata.name}' 2>/dev/null) || cp=""
    if [ -n "${cp}" ]; then
        progress "the snapshots in the log of ${cp}:"
        k logs "pod/${cp}" --tail=5000 2>/dev/null | grep -E 'Snapshot step 1 - Preparing|Snapshot ended with' \
            | tail -6 | cut -c1-200 | sed 's/^/#   /' >&3 || true
    fi
    progress "the watchdog's ConfigMap:"
    k get configmap platform-watchdog-state -o json 2>/dev/null \
        | jq -r '.data // {} | to_entries[] | "#   \(.key)=\(.value | .[0:200])"' >&3 || true
}

# Back to how the suite found it: the pollers stopped, the alerta-bridge
# scaled back.
restore() {
    local f
    for f in "${BATS_FILE_TMPDIR:?}"/*.pid; do
        [ -s "${f}" ] || continue
        kill "$(cat "${f}")" 2>/dev/null || true
        : > "${f}"
    done
    if [ -s "${BATS_FILE_TMPDIR}/bridge.replicas" ]; then
        progress "scaling the alerta-bridge back to $(cat "${BATS_FILE_TMPDIR}/bridge.replicas")"
        k scale deployment alerta-bridge --replicas="$(cat "${BATS_FILE_TMPDIR}/bridge.replicas")" >/dev/null 2>&1 || true
        : > "${BATS_FILE_TMPDIR}/bridge.replicas"
    fi
}

setup_file() {
    echo "RUN_ID=$(date +%s)" > "${BATS_FILE_TMPDIR}/ids"
    # The ingress names, repaired as in test-shacl-flink-scorpio-e2e.
    if ! getent hosts ngsild.local > /dev/null; then
        echo "# ngsild.local does not resolve; repairing /etc/hosts" >&3
        local ingress_ip=""
        for _ in $(seq 1 30); do
            ingress_ip=$(k get ingress/keycloak-iff-ingress \
                -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
            [ -n "${ingress_ip}" ] && break
            sleep 1
        done
        [ -n "${ingress_ip}" ]
        local entry="${ingress_ip} keycloak.local alerta.local ngsild.local pgrest.local fuseki.local"
        if [ -w /etc/hosts ]; then
            echo "${entry}" >> /etc/hosts
        else
            sudo bash -c "echo ${entry} >> /etc/hosts"
        fi
        getent hosts ngsild.local > /dev/null
    fi
}

setup() {
    # shellcheck disable=SC1091
    . "${BATS_FILE_TMPDIR}/ids"
    STATE="${BATS_FILE_TMPDIR}"
    ALERTA_KEY=$(k get secret alerta \
        -o jsonpath='{.data.alerta-admin-key}' | base64 -d)
    # Each test needs the findings of the ones before it.
    if [ "${BATS_TEST_NUMBER}" -gt 1 ] && [ ! -e "${STATE}/passed.$(( BATS_TEST_NUMBER - 1 ))" ]; then
        skip "an earlier test of this file failed"
    fi
}

teardown() {
    restore
    if [ -n "${BATS_TEST_SKIPPED:-}" ]; then
        return
    fi
    if [ -z "${BATS_TEST_COMPLETED:-}" ]; then
        diagnose
        return
    fi
    touch "${STATE}/passed.${BATS_TEST_NUMBER}"
}

teardown_file() {
    # shellcheck disable=SC1091
    . "${BATS_FILE_TMPDIR}/ids"
    local round id key saved
    restore
    # a fresh resync that failed between stop and start leaves the
    # statementset in its saved copy: back, for the teardown of test-flink-e2e
    saved="${HOME}/.local/state/shacl-resync/${NAMESPACE}.shacl-validation.json"
    if [ -s "${saved}" ] && [ -z "$(k get beamsqlstatementset shacl-validation --ignore-not-found -o name 2>/dev/null)" ]; then
        progress "creating the statementset again from ${saved}"
        jq 'del(.metadata.annotations["shacl-resync/stopped-job"])' "${saved}" | k create -f - >/dev/null 2>&1 || true
    fi
    for round in 1 2; do
        for id in sat-count sat-range still gone; do
            delete_entity "urn:e2e-resync-${id}:${round}-${RUN_ID}" >/dev/null 2>&1 || true
        done
    done
    key=$(k get secret alerta -o jsonpath='{.data.alerta-admin-key}' | base64 -d)
    cat "${BATS_FILE_TMPDIR}"/other.*.id 2>/dev/null | while read -r id; do
        curl -s -m 30 -o /dev/null -X DELETE -H "Authorization: Key ${key}" "${ALERTA_URL}/alert/${id}" || true
    done
}

# ids <round>: the entities of a round
ids() {
    SAT_COUNT="urn:e2e-resync-sat-count:$1-${RUN_ID}"
    SAT_RANGE="urn:e2e-resync-sat-range:$1-${RUN_ID}"
    STILL="urn:e2e-resync-still:$1-${RUN_ID}"
    GONE="urn:e2e-resync-gone:$1-${RUN_ID}"
    OTHER="urn:e2e-resync-other:$1-${RUN_ID}"
    MARK="urn:e2e-resync-mark:$1-${RUN_ID}"
}

# ------------------------------------------------- NGSI-LD, as in test-shacl-flink-scorpio-e2e

get_token() {
    local password
    password=$(k get "${USER_SECRET}" -o jsonpath='{.data.password}' | base64 -d)
    curl -s -m 30 -d "client_id=${CLIENT_ID}" -d "username=${REALM_USER}" \
        -d "password=${password}" -d 'grant_type=password' \
        "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" | jq -r '.access_token'
}

create_entity() {  # create_entity <id> <type> [extra-json-members]
    local body
    if [ -n "${3:-}" ]; then
        body=$(printf '{"@context":"%s","id":"%s","type":"%s",%s}' "${CONTEXT}" "$1" "$2" "$3")
    else
        body=$(printf '{"@context":"%s","id":"%s","type":"%s"}' "${CONTEXT}" "$1" "$2")
    fi
    echo "${body}" | curl -s -m 30 -o /dev/null -w '%{http_code}' -X POST \
        -H "Authorization: Bearer $(get_token)" \
        -H 'Content-Type: application/ld+json' \
        --data-binary @- "${NGSILD_URL}/entities/"
}

set_property() {  # set_property <id> <property> <JSON value>
    printf '{"@context":"%s","%s":{"type":"Property","value":%s}}' "${CONTEXT}" "$2" "$3" \
        | curl -s -m 30 -o /dev/null -w '%{http_code}' -X POST \
            -H "Authorization: Bearer $(get_token)" \
            -H 'Content-Type: application/ld+json' \
            --data-binary @- "${NGSILD_URL}/entities/$1/attrs"
}

delete_entity() {
    curl -s -m 30 -o /dev/null -w '%{http_code}' -X DELETE \
        -H "Authorization: Bearer $(get_token)" "${NGSILD_URL}/entities/$1"
}

# ------------------------------------------------- Alerta

# Every alert of a resource whatever its status, as JSON lines; the status
# is asked for explicitly so that no default filter hides closed ones.
alerts_of() {  # alerts_of <resource> [event substring]
    curl -s -m 30 -H "Authorization: Key ${ALERTA_KEY}" \
        "${ALERTA_URL}/alerts?resource=$1&status=open&status=ack&status=shelved&status=closed&status=expired&status=blackout&status=unknown" \
        | jq -c --arg e "${2:-}" '.alerts[] | select($e == "" or (.event | contains($e)))'
}

open_count() {  # open_count <resource> [event substring]: alerts not closed
    alerts_of "$@" | jq -s '[.[] | select(.status != "closed")] | length'
}

alert_texts_for() {
    alerts_of "$1" | jq -r '"\(.status) \(.event): \(.text)"'
}

assert_open() {  # assert_open <resource> <event> [limit]
    local waited=0 limit=${3:-${TIMEOUT}}
    while [ "${waited}" -lt "${limit}" ]; do
        [ "$(open_count "$1" "$2")" -gt 0 ] && return 0
        sleep "${POLL}"
        waited=$((waited + POLL))
    done
    echo "# no open $2 alert on $1 within ${limit}s; its alerts:" >&3
    alert_texts_for "$1" | sed 's/^/#   /' >&3 || true
    return 1
}

assert_closed() {  # assert_closed <resource> [event]
    local waited=0
    while [ "${waited}" -lt "${TIMEOUT}" ]; do
        [ "$(open_count "$1" "${2:-}")" -eq 0 ] && return 0
        sleep "${POLL}"
        waited=$((waited + POLL))
    done
    echo "# alerts on $1 still not closed after ${TIMEOUT}s:" >&3
    alert_texts_for "$1" | sed 's/^/#   /' >&3
    return 1
}

closed_now() {  # closed_now <resource> [event]: no wait
    local n
    n=$(open_count "$1" "${2:-}")
    if [ "${n}" -ne 0 ]; then
        echo "# alerts on $1 not closed:" >&3
        alert_texts_for "$1" | sed 's/^/#   /' >&3
        return 1
    fi
}

# alerta_get <path?query>: the JSON body of a 200 answer, or fails naming the
# HTTP code
alerta_get() {
    local out code
    out=$(curl -s -m 30 -w '\n%{http_code}' -H "Authorization: Key ${ALERTA_KEY}" "${ALERTA_URL}$1") || true
    code=${out##*$'\n'}
    if [ "${code}" != 200 ] || ! jq -e . >/dev/null 2>&1 <<<"${out%$'\n'*}"; then
        progress "GET ${1%%\?*} answered HTTP ${code:-none}$(jq -e . >/dev/null 2>&1 <<<"${out%$'\n'*}" || echo ', not JSON')"
        return 1
    fi
    echo "${out%$'\n'*}"
}

# alert_by_id <id>: the alert with its own history, as JSON. The suites read
# Alerta only under /alerts through the ingress. The list leaves the history
# out unless asked for (show-history), and then gives the alert's history as
# /alert/<id> does, sorted by its time; /alerts/history is a search across
# alerts, not one alert's history.
alert_by_id() {
    local alert
    alert=$(alerta_get "/alerts?id=$1&show-history=true&status=open&status=assign&status=ack&status=shelved&status=closed&status=expired&status=blackout&status=unknown") || return 1
    jq -ec --arg id "$1" '[.alerts[]? | select(.id == $id)][0]' <<<"${alert}" \
        || { progress "Alerta lists no alert $1"; return 1; }
}

# show_history <what> <alert JSON>: its history in the CI log, one entry a line
show_history() {
    progress "history of $1:"
    jq -r '.history[]? | "#     \(.type) \(.status // "-") \(.severity // "-") \(.updateTime) \((.text // "")[0:100])"' <<<"$2" >&3
}

consistency() {  # the watchdog's ValidationConsistency alert
    alerts_of shacl-validation | jq -c 'select(.event == "ValidationConsistency")' | head -1
}

# ------------------------------------------------- Kafka, through the broker pod as tools/ttl_test.py

SEP=$'\t'

kafka_tool() {  # kafka_tool <tool and arguments>; stdin goes to the tool
    timeout "${KAFKA_LIMIT}" kubectl -n "${NAMESPACE}" exec -i "${KAFKA_POD}" -- sh -c "KAFKA_HEAP_OPTS='-Xmx256M' bin/$1"
}

# The whole topic up to its end offsets now, one "<key><TAB><value>" line per
# record; a tombstone reads "null". Bounded by the record count: --timeout-ms
# alone never ends on a topic written more often, as iff.alerts.bulk is by the
# alerta-bridge's heartbeat every second.
read_topic() {
    local p s e
    while read -r p e; do
        s=$(offsets "$1" -2 | awk -v p="${p}" '$1 == p { print $2 }')
        { [ -n "${s}" ] && [ "${e}" -gt "${s}" ]; } || continue
        kafka_tool "kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic $1 --partition ${p} --offset ${s} --max-messages $(( e - s )) --timeout-ms 20000 --property print.key=true --property key.separator='${SEP}'" 2>/dev/null || true
    done < <(offsets "$1" -1)
}

write_records() {  # write_records <topic> < "<key><TAB><value>" lines
    kafka_tool "kafka-console-producer.sh --bootstrap-server localhost:9092 --topic $1 --property parse.key=true --property key.separator='${SEP}'"
}

offsets() {  # offsets <topic> <-1 end | -2 start>: "<partition> <offset>" lines
    kafka_tool "kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic $1 --time $2" 2>/dev/null \
        | awk -F: '{ print $(NF-1), $NF }'
}

# The latest record per key of a resource, the state an upsert topic stands
# for; tombstones included.
latest_of() {  # latest_of <resource> < topic lines
    awk -F"${SEP}" -v r="\"$1\"" 'index($1, r) { last[$1] = $2; order[$1] = NR }
        END { for (k in last) print order[k] FS k FS last[k] }' | sort -n | cut -f2-
}

# The raises among them: in constraint_trigger_table a verdict with
# triggered true, in iff.alerts.bulk any record that is not a tombstone.
raises_of() {  # raises_of <resource> < topic lines
    latest_of "$1" | awk -F"${SEP}" '$2 != "null" && $2 != "" && ($2 !~ /"triggered"/ || $2 ~ /"triggered":true/)'
}

topic_id() {
    kafka_tool "kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic $1" 2>/dev/null \
        | grep -o 'TopicId: *[^[:space:]]*' | head -1 | awk '{ print $2 }'
}

kafkatopics() {  # every KafkaTopic with the topic ID it reports, sorted
    k get kafkatopics \
        -o jsonpath='{range .items[*]}{.metadata.name} {.status.topicId}{"\n"}{end}' | sort
}

validation_job() {
    k get beamsqlstatementset shacl-validation -o jsonpath='{.status.job_id}'
}

# ------------------------------------------------- one round

# stale_alerts <round> <with trigger records>: the alerts of the round, set up
# before its resync, and checked in place.
stale_alerts() {
    local round=$1 with_trigger=$2 id
    ids "${round}"
    progress "round ${round}: creating the entities"
    # Violating: the count of hasE2EState of an E2EMachine, or the sh:xone of
    # hasE2ERange of an E2ERangeMachine with a value between the ranges.
    for id in "${SAT_COUNT}" "${STILL}" "${GONE}"; do
        [ "$(create_entity "${id}" "${MACHINE_TYPE}")" = "201" ]
    done
    [ "$(create_entity "${SAT_RANGE}" "${RANGE_TYPE}" "\"${RANGE_PROP}\":{\"type\":\"Property\",\"value\":50}")" = "201" ]
    assert_open "${SAT_COUNT}" "${COUNT_CONSTRAINT}"
    assert_open "${STILL}" "${COUNT_CONSTRAINT}"
    assert_open "${GONE}" "${COUNT_CONSTRAINT}"
    assert_open "${SAT_RANGE}" "${XONE_CONSTRAINT}"

    progress "round ${round}: their alerts are open; reading the raises from the topics"
    # The raises the job wrote, as they stand while violated.
    read_topic "${TRIGGER_TOPIC}" > "${STATE}/trigger.${round}"
    read_topic "${BULK_ALERTS_TOPIC}" > "${STATE}/bulk.${round}"
    : > "${STATE}/stale.trigger.${round}"
    : > "${STATE}/stale.bulk.${round}"
    for id in "${SAT_COUNT}" "${SAT_RANGE}" "${GONE}"; do
        raises_of "${id}" < "${STATE}/trigger.${round}" >> "${STATE}/stale.trigger.${round}"
        raises_of "${id}" < "${STATE}/bulk.${round}" >> "${STATE}/stale.bulk.${round}"
        grep -qF "\"${id}\"" "${STATE}/stale.bulk.${round}" || { echo "# no raise of ${id} in ${BULK_ALERTS_TOPIC}" >&3; false; }
        if [ "${with_trigger}" = yes ]; then
            grep -qF "\"${id}\"" "${STATE}/stale.trigger.${round}" || { echo "# no raise of ${id} in ${TRIGGER_TOPIC}" >&3; false; }
        fi
    done

    progress "round ${round}: satisfying the constraints and deleting ${GONE}"
    # Satisfied now, or gone: the job retracts and the alerts close.
    [ "$(set_property "${SAT_COUNT}" "${STATE_PROP}" '"ON"')" = "204" ]
    [ "$(set_property "${SAT_RANGE}" "${RANGE_PROP}" 5)" = "204" ]
    [ "$(delete_entity "${GONE}")" = "204" ]
    assert_closed "${SAT_COUNT}"
    assert_closed "${SAT_RANGE}"
    assert_closed "${GONE}"

    progress "round ${round}: writing the stale raises again"
    # The raises written again, as they stand after a previous job (#977).
    if [ "${with_trigger}" = yes ]; then
        write_records "${TRIGGER_TOPIC}" < "${STATE}/stale.trigger.${round}"
        read_topic "${TRIGGER_TOPIC}" > "${STATE}/trigger.stale.${round}"
        for id in "${SAT_COUNT}" "${SAT_RANGE}" "${GONE}"; do
            [ -n "$(raises_of "${id}" < "${STATE}/trigger.stale.${round}")" ]
        done
    fi
    write_records "${BULK_ALERTS_TOPIC}" < "${STATE}/stale.bulk.${round}"
    assert_open "${SAT_COUNT}" "${COUNT_CONSTRAINT}"
    assert_open "${SAT_RANGE}" "${XONE_CONSTRAINT}"
    assert_open "${GONE}" "${COUNT_CONSTRAINT}"
    # the satisfied ones stay open: nothing in the running job retracts them
    sleep 30
    [ "$(open_count "${SAT_COUNT}" "${COUNT_CONSTRAINT}")" -gt 0 ]
    [ "$(open_count "${SAT_RANGE}" "${XONE_CONSTRAINT}")" -gt 0 ]
    # The events of the stale alerts as Alerta has them: the published
    # constraints the resync must close, not the leaves of a circuit.
    for id in "${SAT_COUNT}" "${SAT_RANGE}" "${GONE}"; do
        alerts_of "${id}" | jq -r 'select(.status != "closed") | [.resource, .event] | @tsv'
    done > "${STATE}/stale.events.${round}"
    [ -s "${STATE}/stale.events.${round}" ]

    # The alert of the constraint still violated, as it is now.
    alerts_of "${STILL}" "${COUNT_CONSTRAINT}" | jq -s -c 'map(select(.status == "open")) | .[0]' > "${STATE}/still.${round}"
    [ "$(jq -r '.id' "${STATE}/still.${round}")" != "null" ]

    progress "round ${round}: the stale alerts are open; an alert of another service and a record in ${ENTITY_TOPIC}"
    # An open alert of another service, through iff.alerts and the
    # alerta-bridge as test-bridges/test-alerta-bridge.bats sends one. Its
    # severity must be one of the platform's SEVERITY_MAP
    # (helm/charts/alerta/values.yaml, which has no "minor"): Alerta refuses
    # any other with 400 and the bridge drops the record for good.
    printf '%s%s%s\n' "$(jq -nc --arg r "${OTHER}" '{resource: $r, event: "E2EResyncOther"}')" "${SEP}" \
        "$(jq -nc --arg r "${OTHER}" --arg s "${OTHER_SERVICE}" '{resource: $r, event: "E2EResyncOther",
            environment: "Development", severity: "major", service: [$s], text: "not a SHACL alert", timeout: 7200}')" \
        | write_records "${ALERTS_TOPIC}"
    assert_open "${OTHER}" E2EResyncOther
    alerts_of "${OTHER}" E2EResyncOther | jq -r 'select(.status == "open") | .id' | head -1 > "${STATE}/other.${round}.id"
    [ -s "${STATE}/other.${round}.id" ] || { progress "round ${round}: no open alert of ${OTHER_SERVICE} on ${OTHER}"; false; }
    alert_by_id "$(cat "${STATE}/other.${round}.id")" > "${STATE}/other.${round}" \
        || { progress "round ${round}: Alerta did not answer for the alert $(cat "${STATE}/other.${round}.id")"; false; }
    [ "$(jq -r '.status' "${STATE}/other.${round}")" = "open" ]

    # A record in iff.ngsild.entities.
    printf '%s%s%s\n' "\"${MARK}\"" "${SEP}" "{\"id\":\"${MARK}\",\"type\":\"${FREE_TYPE}\",\"deleted\":false}" \
        | write_records "${ENTITY_TOPIC}"
    read_topic "${ENTITY_TOPIC}" | grep -qF "\"id\":\"${MARK}\""
    topic_id "${ENTITY_TOPIC}" > "${STATE}/entities.id.${round}"
    [ -n "$(cat "${STATE}/entities.id.${round}")" ]
}

# poll_consistency <round>: ValidationConsistency every few seconds while the
# resync runs, "<time> <severity> <text>" per line
poll_consistency() {
    ( while true; do
          echo "$(date +%s) $(consistency | jq -r '"\(.severity) \(.text)"')" >> "${STATE}/consistency.$1"
          sleep 3
      done ) 3>&- &
    echo $! > "${STATE}/consistency.$1.pid"
}

stop_poller() {  # stop_poller <pid file>
    kill "$(cat "$1")" 2>/dev/null || true
    rm -f "$1"
}

# resync <round> [make arguments]: runs the resync, its output in resync.<round>
resync() {
    local round=$1 rc
    shift
    validation_job > "${STATE}/job.before.${round}"
    date +%s > "${STATE}/start.${round}"
    progress "round ${round}: make shacl-resync $*, at most ${RESYNC_LIMIT}s"
    # every line with the time it came, and to the CI log as it comes; the
    # exit status last. fd 3 stays with this suite: nothing the resync leaves
    # behind can hold the test open. timeout signals the whole process group.
    { timeout --kill-after=30 "${RESYNC_LIMIT}" make -C "${SHACL2FLINK}" shacl-resync "$@" 2>&1 3>&-; echo "resync-exit-status $?"; } \
        | while IFS= read -r l; do
              echo "$(date +%s) ${l}"
              printf '#   resync: %s\n' "${l}" >&3
          done > "${STATE}/resync.${round}"
    rc=$(awk '$2 == "resync-exit-status" { r = $3 } END { print (r == "" ? 1 : r) }' "${STATE}/resync.${round}")
    [ "${rc}" != 124 ] || progress "round ${round}: the resync did not end within ${RESYNC_LIMIT}s"
    date +%s > "${STATE}/end.${round}"
    validation_job > "${STATE}/job.after.${round}"
    progress "round ${round}: the resync ended with status ${rc} after $(( $(cat "${STATE}/end.${round}") - $(cat "${STATE}/start.${round}") ))s"
    return "${rc}"
}

marker_of() {  # the marker a round's resync wrote
    sed -n 's/.*the marker \([0-9-]*\) is written.*/\1/p' "${STATE}/resync.$1"
}

steps_of() {  # the step lines of a round's output, without their times
    cut -d' ' -f2- "${STATE}/resync.$1" | grep '^step '
}

# after_resync <round>: the alerts after a round's resync
# alert_states: "<resource> <event> <status>" of the alerts of the
# satisfied and gone entities, one per line
alert_states() {
    local id
    for id in "${SAT_COUNT}" "${SAT_RANGE}" "${GONE}"; do
        alerts_of "${id}" | jq -r '"\(.resource) \(.event) \(.status)"'
    done | sort
}

# evidence <round>: what became of the satisfied and gone entities' alerts
# over three minutes after the resync, with what the validation was fed for
# SAT_COUNT: names, states, keys and times only.
evidence() {
    local round=$1 now last="" waited=0 token
    ids "${round}"
    progress "round ${round}: the alerts of the satisfied and gone entities for 180s after the resync:"
    while [ "${waited}" -le 180 ]; do
        now=$(alert_states)
        if [ "${now}" != "${last}" ]; then
            progress "  after $(( $(date +%s) - $(cat "${STATE}/end.${round}") ))s:"
            printf '%s\n' "${now}" | sed 's/^/#       /' >&3
            last=${now}
        fi
        sleep 10
        waited=$((waited + 10))
    done
    token=$(get_token)
    progress "round ${round}: the attributes of ${SAT_COUNT} in Scorpio: $(curl -s -m 30 -H "Authorization: Bearer ${token}" \
        "${NGSILD_URL}/entities/${SAT_COUNT}" | jq -r 'keys - ["@context", "id", "type"] | join(", ")' 2>/dev/null)"
    progress "round ${round}: the latest record per count key of ${SAT_COUNT} in ${TRIGGER_TOPIC}:"
    read_topic "${TRIGGER_TOPIC}" | latest_of "${SAT_COUNT}" | grep -F "${COUNT_CONSTRAINT}" \
        | jq -R -r 'split("\t") | "#       \(.[0][0:200]) -> \(.[1] | (fromjson? // .) | if type == "object" then {triggered} | tostring else . end)"' >&3 || true
    progress "round ${round}: the records of ${SAT_COUNT} in iff.ngsild.entities and iff.ngsild.attributes (name, deleted, observedAt):"
    read_topic "${ENTITY_TOPIC}" | grep -F "\"${SAT_COUNT}\"" \
        | jq -R -r 'split("\t")[1] | fromjson? | "#       entity deleted=\(.deleted)"' >&3 || true
    read_topic iff.ngsild.attributes | grep -F "\"${SAT_COUNT}\"" \
        | jq -R -r 'split("\t")[1] | fromjson? | "#       attribute \(.name) deleted=\(.deleted) observedAt=\(.observedAt)"' >&3 || true
}

after_resync() {
    local round=$1 id after before states
    ids "${round}"
    # Right at the end of the resync, as the spec has it. After a fresh job
    # the course of the next three minutes goes to the log first, so that a
    # failure shows whether the alert would still have closed.
    states=$(alert_states)
    if [ "${round}" = 2 ]; then
        evidence "${round}"
    fi
    if grep -v ' closed$' <<<"${states}" | grep -q .; then
        progress "round ${round}: at the end of the resync, alerts not closed:"
        grep -v ' closed$' <<<"${states}" | sed 's/^/#     /' >&3
        false
    fi
    # a count constraint, and a value constraint (sh:xone over two ranges)
    closed_now "${SAT_COUNT}"
    closed_now "${SAT_RANGE}"
    closed_now "${GONE}"
    # still violated: open again within a minute, unchanged, closed by the
    # resync in between and opened again after it
    assert_open "${STILL}" "${COUNT_CONSTRAINT}" "${BACK}"
    id=$(jq -r '.id' "${STATE}/still.${round}")
    after=$(alert_by_id "${id}")
    echo "# ${STILL}: $(jq -c '{status, severity, text}' <<<"${after}")" >&3
    [ "$(jq -r '.status' <<<"${after}")" = "open" ]
    [ "$(jq -r '.severity' <<<"${after}")" = "$(jq -r '.severity' "${STATE}/still.${round}")" ]
    [ "$(jq -r '.text' <<<"${after}")" = "$(jq -r '.text' "${STATE}/still.${round}")" ]
    # Alerta 9.0.4 records the bulk close as a "status" entry with status
    # closed and the resync's text (set_status), and the raise that comes
    # back with the same severity as a "status" entry to open (deduplicate),
    # or as a "severity" entry if the severity changed (update). The alert
    # was created in this round and stayed open until the resync, so any
    # entry to open other than its "new" one is the reopening; it is checked
    # by its place after the close, the times are only shown.
    show_history "${STILL}" "${after}"
    jq -e '(.history | map(select(.status == "closed" and ((.text // "") | contains("make shacl-resync")))) | length > 0)
        and ((.history | (map(.status == "closed" and ((.text // "") | contains("make shacl-resync"))) | index(true)) as $c
              | .[($c + 1):] | map(select(.status == "open" and .type != "new")) | length > 0))' <<<"${after}" >/dev/null \
        || { progress "${STILL}: no close by the resync followed by an entry that opened it again"; false; }
    # the other service's alert: the same status, severity and history
    before=$(cat "${STATE}/other.${round}")
    after=$(alert_by_id "$(cat "${STATE}/other.${round}.id")")
    show_history "the alert of ${OTHER_SERVICE}" "${after}"
    [ "$(jq -r '.status' <<<"${after}")" = "$(jq -r '.status' <<<"${before}")" ]
    [ "$(jq -r '.severity' <<<"${after}")" = "$(jq -r '.severity' <<<"${before}")" ]
    [ "$(jq -c '.history' <<<"${after}")" = "$(jq -c '.history' <<<"${before}")" ] \
        || { progress "the history of the alert of ${OTHER_SERVICE} changed"; false; }
    jq -e '[.history[]? | select((.text // "") | contains("make shacl-resync"))] | length == 0' <<<"${after}" >/dev/null
    # the marker: a closed alert of service System, not a SHACL alert, that
    # was never open
    id=$(alerts_of shacl-validation ResyncMarker | jq -r --arg v "$(marker_of "${round}")" 'select(.value == $v) | .id' | head -1)
    [ -n "${id}" ]
    after=$(alert_by_id "${id}")
    show_history "the marker" "${after}"
    # created closed ("new" entry closed), never an entry with status open;
    # a later marker of the same event is a duplicate with another value
    jq -e '.status == "closed" and .service == ["System"] and .severity == "normal"
        and (.history | length > 0) and ([.history[] | select(.status == "open")] | length == 0)' <<<"${after}" >/dev/null
    # iff.ngsild.entities: its topic ID and the record from before
    [ "$(topic_id "${ENTITY_TOPIC}")" = "$(cat "${STATE}/entities.id.${round}")" ]
    read_topic "${ENTITY_TOPIC}" | grep -qF "\"id\":\"${MARK}\""
}

# degraded_throughout <round>: ValidationConsistency a warning naming the
# resync from the first step until the command ended, normal within one
# watchdog run after it
degraded_throughout() {
    local round=$1 first end waited=0
    first=$(awk '$2 == "step" && $3 ~ /^1\// { print $1; exit }' "${STATE}/resync.${round}")
    [ -n "${first}" ]
    end=$(cat "${STATE}/end.${round}")
    # every reading from a few seconds after the first step until the end
    if awk -v from=$(( first + 5 )) -v to="${end}" '$1 >= from && $1 < to && !($2 == "warning" && $0 ~ /RESYNC IN PROGRESS/) { bad = 1; print }
        END { exit !bad }' "${STATE}/consistency.${round}" > "${STATE}/consistency.bad.${round}"; then
        echo "# ValidationConsistency during the resync was not the resync's warning:" >&3
        head -5 "${STATE}/consistency.bad.${round}" | sed 's/^/#   /' >&3
        return 1
    fi
    grep -q 'RESYNC IN PROGRESS' "${STATE}/consistency.${round}"
    while [ "${waited}" -lt "${WATCHDOG_RUN}" ]; do
        [ "$(consistency | jq -r '.severity')" = "normal" ] && return 0
        sleep "${POLL}"
        waited=$((waited + POLL))
    done
    echo "# ValidationConsistency not normal within ${WATCHDOG_RUN}s after the resync: $(consistency | jq -c '{severity, text}')" >&3
    return 1
}

# ------------------------------------------------- the tests

@test "round 1, before the resync: stale alerts of satisfied constraints and a gone entity, a real violation, another service's alert" {
    stale_alerts 1 no
}

@test "round 1: make shacl-resync reports its steps in order and exits 0, warning meanwhile" {
    poll_consistency 1
    rc=0
    resync 1 || rc=$?
    stop_poller "${STATE}/consistency.1.pid"
    [ "${rc}" -eq 0 ] || { tail -40 "${STATE}/resync.1" | sed 's/^/#   /' >&3; false; }
    [ "$(steps_of 1)" = "step 1/6 mark the validation degraded: started
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
step 6/6 end the degraded state: done" ]
    # without a replacement the validation job stays
    [ "$(cat "${STATE}/job.after.1")" = "$(cat "${STATE}/job.before.1")" ]
}

@test "round 1: the alerts after the resync are those of the constraints violated now" {
    after_resync 1
}

@test "round 1: ValidationConsistency warned throughout the resync and is normal after it" {
    degraded_throughout 1
}

@test "round 1: the closed alerts are still closed two minutes after the resync" {
    local wait
    ids 1
    wait=$(( $(cat "${STATE}/end.1") + SETTLED - $(date +%s) ))
    [ "${wait}" -le 0 ] || sleep "${wait}"
    closed_now "${GONE}"
    closed_now "${SAT_COUNT}"
    closed_now "${SAT_RANGE}"
}

@test "round 2, before the resync: the same, with the stale raises also in constraint_trigger_table" {
    stale_alerts 2 yes
    local t
    for t in ${JOB_TOPICS}; do
        offsets "${t}" -1 | awk -v t="${t}" '{ print t, $1, $2 }'
    done > "${STATE}/job_topics.end.2"
    [ -s "${STATE}/job_topics.end.2" ]
    kafkatopics > "${STATE}/kafkatopics.2"
    [ -s "${STATE}/kafkatopics.2" ]
}

@test "round 2: make shacl-resync REPLACE=fresh waits for its marker behind a held-back alerta-bridge" {
    # every KafkaTopic, with its topic ID, throughout the resync
    ( while true; do
          echo "$(date +%s) $(kafkatopics | tr '\n' ';')" >> "${STATE}/kafkatopics.watch"
          sleep 3
      done ) 3>&- &
    echo $! > "${STATE}/kafkatopics.pid"
    # the alerta-bridge held back from the re-snapshot until a minute after
    # the marker was written
    k get deployment alerta-bridge -o jsonpath='{.spec.replicas}' > "${STATE}/bridge.replicas"
    # Each wait ends with the resync at the latest; restore() scales the
    # bridge back whatever happens.
    ( limit=$(( $(date +%s) + RESYNC_LIMIT ))
      while ! grep -q 'step 6/8 trigger a complete re-snapshot: started' "${STATE}/resync.2" 2>/dev/null; do
          { [ "$(date +%s)" -lt "${limit}" ] && [ ! -e "${STATE}/end.2" ]; } || exit 0
          sleep 1
      done
      k scale deployment alerta-bridge --replicas=0 >/dev/null
      offsets "${ALERTS_TOPIC}" -1 | awk '{ print $2 }' > "${STATE}/alerts.held"
      date +%s > "${STATE}/bridge.down"
      while ! grep -q 'the marker .* is written' "${STATE}/resync.2" 2>/dev/null; do
          { [ "$(date +%s)" -lt "${limit}" ] && [ ! -e "${STATE}/end.2" ]; } || break
          sleep 1
      done
      [ -e "${STATE}/end.2" ] || sleep 60
      date +%s > "${STATE}/bridge.up"
      k scale deployment alerta-bridge --replicas="$(cat "${STATE}/bridge.replicas")" >/dev/null
    ) 3>&- &
    echo $! > "${STATE}/bridge.pid"
    progress "round 2: the alerta-bridge is held back from step 6 until a minute after the marker"
    poll_consistency 2
    rc=0
    resync 2 REPLACE=fresh || rc=$?
    stop_poller "${STATE}/consistency.2.pid"
    stop_poller "${STATE}/kafkatopics.pid"
    restore
    [ "${rc}" -eq 0 ] || { tail -40 "${STATE}/resync.2" | sed 's/^/#   /' >&3; false; }
    [ "$(steps_of 2)" = "step 1/8 mark the validation degraded: started
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
step 8/8 end the degraded state: done" ]
    # a fresh job: another job ID
    [ -n "$(cat "${STATE}/job.after.2")" ]
    [ "$(cat "${STATE}/job.after.2")" != "$(cat "${STATE}/job.before.2")" ]
    # the wait step did not end before the bridge was back and the marker in Alerta
    [ -s "${STATE}/bridge.up" ]
    done_at=$(awk '/ step 7\/8 wait until the re-snapshot is processed: done/ { print $1 }' "${STATE}/resync.2")
    [ "${done_at}" -ge "$(cat "${STATE}/bridge.up")" ]
}

@test "round 2: every alert written before the marker went to Alerta after the bridge was back, before the resync ended" {
    local held marker from n=0 record resource event received down end
    held=$(cat "${STATE}/alerts.held")
    down=$(cat "${STATE}/bridge.down")
    marker=$(marker_of 2)
    [ -n "${marker}" ]
    received=$(alerts_of shacl-validation ResyncMarker | jq -r --arg v "${marker}" 'select(.value == $v) | .lastReceiveTime' | head -1)
    [ -n "${received}" ]
    [ "$(date -u -d "${received}" +%s)" -le "$(cat "${STATE}/end.2")" ]
    # the records Core Services wrote to iff.alerts while the bridge was held back
    end=$(offsets "${ALERTS_TOPIC}" -1 | awk '$1 == 0 { print $2 }')
    [ "${end}" -gt "${held}" ]
    kafka_tool "kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic ${ALERTS_TOPIC} --partition 0 --offset ${held} --max-messages $(( end - held )) --timeout-ms 20000" \
        2>/dev/null > "${STATE}/alerts.backlog" || true
    from=$(grep -n -m1 -F "\"value\":\"${marker}\"" "${STATE}/alerts.backlog" | cut -d: -f1)
    [ -n "${from}" ]
    while IFS= read -r record; do
        resource=$(jq -r '.resource // empty' <<<"${record}" 2>/dev/null) || continue
        event=$(jq -r '.event // empty' <<<"${record}")
        { [ -n "${resource}" ] && [ -n "${event}" ]; } || continue
        received=$(alerts_of "${resource}" | jq -r --arg e "${event}" 'select(.event == $e) | .lastReceiveTime' | head -1)
        if [ -z "${received}" ] || [ "$(date -u -d "${received}" +%s)" -lt "${down}" ]; then
            echo "# ${resource} ${event}, written before the marker, did not reach Alerta after the bridge was held back" >&3
            false
        fi
        n=$((n + 1))
    done < <(head -n $(( from - 1 )) "${STATE}/alerts.backlog")
    echo "# ${n} alerts were written to ${ALERTS_TOPIC} behind the held-back bridge before the marker" >&3
}

@test "round 2: the job's topics hold no record from before the stop, and no stale raise" {
    local t p e s ss
    # the statementset created again keeps the release's labels and annotations
    ss=$(k get beamsqlstatementset shacl-validation -o json)
    jq -e '.metadata.labels["app.kubernetes.io/managed-by"] == "Helm"
        and .metadata.annotations["meta.helm.sh/release-name"] == "shacl"
        and (.metadata.annotations | has("shacl-resync/stopped-job") | not)' <<<"${ss}" >/dev/null \
        || { progress "the statementset lacks the release's labels or annotations: $(jq -c '{labels: .metadata.labels, annotations: (.metadata.annotations | keys)}' <<<"${ss}")"; false; }
    while read -r t p e; do
        s=$(offsets "${t}" -2 | awk -v p="${p}" '$1 == p { print $2 }')
        [ "${s}" -ge "${e}" ] || { echo "# ${t}-${p} starts at ${s}, before ${e}" >&3; false; }
    done < "${STATE}/job_topics.end.2"
    # The stale raises written before the stop whose event is that of a stale
    # alert (the published constraint), by their exact record keys: the
    # latest record of each key now is none, a tombstone or not triggered.
    # The new job may raise other keys of the same resource, such as the leaf
    # of an sh:xone branch the satisfied value doesn't meet (both jobs raise
    # it, and the circuit above it decides); that is not a replay.
    read_topic "${TRIGGER_TOPIC}" > "${STATE}/trigger.after.2"
    [ -s "${STATE}/stale.trigger.2" ]
    while IFS= read -r line; do
        jq -e --rawfile ev "${STATE}/stale.events.2" '($ev | split("\n") | map(select(. != ""))) as $e
            | ((.resource // "") + "\t" + (.event // "")) as $k | $e | index($k) != null' \
            <<<"${line%%"${SEP}"*}" >/dev/null 2>&1 && printf '%s\n' "${line}"
    done < "${STATE}/stale.trigger.2" > "${STATE}/stale.keys.2"
    if [ ! -s "${STATE}/stale.keys.2" ]; then
        progress "no stale raise in ${TRIGGER_TOPIC} carries the event of a stale alert; the alerts' events:"
        sed 's/^/#   /' "${STATE}/stale.events.2" >&3
        progress "the keys of the stale raises:"
        cut -f1 "${STATE}/stale.trigger.2" | cut -c1-300 | sed 's/^/#   /' >&3
        false
    fi
    progress "round 2: $(grep -c . "${STATE}/stale.keys.2") of $(grep -c . "${STATE}/stale.trigger.2") stale keys carry a stale alert's event and are checked in ${TRIGGER_TOPIC}"
    awk -F"${SEP}" 'NR == FNR { stale[$1] = 1; next }
        ($1 in stale) { last[$1] = $2 }
        END { for (k in stale) if ((k in last) && last[k] != "null" && last[k] != "" \
                  && (last[k] !~ /"triggered"/ || last[k] ~ /"triggered":true/)) print k FS last[k] }' \
        "${STATE}/stale.keys.2" "${STATE}/trigger.after.2" > "${STATE}/replayed.2"
    if [ -s "${STATE}/replayed.2" ]; then
        progress "${TRIGGER_TOPIC} holds a raise under the key of a stale raise from before the stop:"
        cut -c1-300 "${STATE}/replayed.2" | sed 's/^/#   /' >&3
        false
    fi
}

@test "round 2: every KafkaTopic was there throughout, with its topic ID" {
    local expected
    expected=$(tr '\n' ';' < "${STATE}/kafkatopics.2")
    [ "$(wc -l < "${STATE}/kafkatopics.watch")" -gt 0 ]
    if cut -d' ' -f2- "${STATE}/kafkatopics.watch" | grep -v -x -F "${expected}" > "${STATE}/kafkatopics.changed"; then
        echo "# the KafkaTopics changed during the resync; before: ${expected}" >&3
        head -3 "${STATE}/kafkatopics.changed" | sed 's/^/#   /' >&3
        false
    fi
}

@test "round 2: the alerts after the resync are those of the constraints violated now" {
    after_resync 2
}

@test "round 2: ValidationConsistency warned throughout the resync and is normal after it" {
    degraded_throughout 2
}

@test "round 2: the closed alerts are still closed two minutes after the resync" {
    local wait
    ids 2
    wait=$(( $(cat "${STATE}/end.2") + SETTLED - $(date +%s) ))
    [ "${wait}" -le 0 ] || sleep "${wait}"
    closed_now "${GONE}"
    closed_now "${SAT_COUNT}"
    closed_now "${SAT_RANGE}"
}
