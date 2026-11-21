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

# The redeploy of the validation (`make flink-redeploy`) on the platform: the
# alerts afterwards are exactly those of the constraints violated now.
#
# The leaf checks write only violations, so a raise the previous job wrote
# into constraint_trigger_table and that nothing retracts stays, and a new job
# replays it from the topic. The setup makes such stale raises on purpose:
# it lets an entity violate a constraint, keeps the raise records the job
# wrote into constraint_trigger_table and iff.alerts.bulk, satisfies the
# constraint (or deletes the entity) and writes the kept records again, the
# way they stand after the previous job, so that the alert is open while the
# constraint is satisfied. The redeploy must close those alerts and keep them
# closed, and bring the alert of a constraint still violated back.
#
# Driven by `make test-flink-e2e` after test-shacl-flink-e2e and
# test-shacl-flink-scorpio-e2e, against the deployment of tests/e2e-kms. It
# leaves that KMS deployed for the teardown of test-flink-e2e. The tests run
# in order and share their findings through files; each needs the ones
# before it.

NAMESPACE=${NAMESPACE:-iff}
SHACL2FLINK="${BATS_TEST_DIRNAME}/../../.."
E2E_KMS=${E2E_KMS:-${SHACL2FLINK}/tests/e2e-kms}

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
BULK_ALERTS_TOPIC=iff.alerts.bulk
ENTITY_TOPIC=iff.ngsild.entities
OTHER_SERVICE="E2E Redeploy"

# Alerts appear and close within seconds on an idle cluster; as in the
# Scorpio suite the limit is far above that. The still violated alert must be
# back within two minutes of the redeploy, and the closed ones still closed
# two minutes after it.
TIMEOUT=${TIMEOUT:-180}
POLL=5
SETTLED=120

# The ids are fixed per file run, kept in the file's temporary directory.
setup_file() {
    local run_id
    run_id=$(date +%s)
    cat > "${BATS_FILE_TMPDIR}/ids" <<EOF
SAT_COUNT=urn:e2e-redeploy-sat-count:${run_id}
SAT_RANGE=urn:e2e-redeploy-sat-range:${run_id}
STILL=urn:e2e-redeploy-still:${run_id}
GONE=urn:e2e-redeploy-gone:${run_id}
OTHER=urn:e2e-redeploy-other:${run_id}
MARKER=urn:e2e-redeploy-marker:${run_id}
EOF
    # The ingress names, repaired as in test-shacl-flink-scorpio-e2e.
    if ! getent hosts ngsild.local > /dev/null; then
        echo "# ngsild.local does not resolve; repairing /etc/hosts" >&3
        local ingress_ip=""
        for _ in $(seq 1 30); do
            ingress_ip=$(kubectl -n "${NAMESPACE}" get ingress/keycloak-iff-ingress \
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
    ALERTA_KEY=$(kubectl -n "${NAMESPACE}" get secret alerta \
        -o jsonpath='{.data.alerta-admin-key}' | base64 -d)
    # Each test needs the findings of the ones before it.
    if [ "${BATS_TEST_NUMBER}" -gt 1 ] && [ ! -e "${STATE}/passed.$(( BATS_TEST_NUMBER - 1 ))" ]; then
        skip "an earlier test of this file failed"
    fi
}

teardown() {
    if [ -z "${BATS_TEST_COMPLETED:-}" ] || [ -n "${BATS_TEST_SKIPPED:-}" ]; then
        return
    fi
    touch "${STATE}/passed.${BATS_TEST_NUMBER}"
}

teardown_file() {
    # shellcheck disable=SC1091
    . "${BATS_FILE_TMPDIR}/ids"
    local id key
    for id in "${SAT_COUNT}" "${SAT_RANGE}" "${STILL}" "${GONE}"; do
        delete_entity "${id}" >/dev/null 2>&1 || true
    done
    key=$(kubectl -n "${NAMESPACE}" get secret alerta -o jsonpath='{.data.alerta-admin-key}' | base64 -d)
    if [ -s "${BATS_FILE_TMPDIR}/other.id" ]; then
        curl -s -o /dev/null -X DELETE -H "Authorization: Key ${key}" \
            "${ALERTA_URL}/alert/$(cat "${BATS_FILE_TMPDIR}/other.id")" || true
    fi
    [ -z "$(cat "${BATS_FILE_TMPDIR}/poller.pid" 2>/dev/null)" ] || kill "$(cat "${BATS_FILE_TMPDIR}/poller.pid")" 2>/dev/null || true
}

# ------------------------------------------------- NGSI-LD, as in test-shacl-flink-scorpio-e2e

get_token() {
    local password
    password=$(kubectl -n "${NAMESPACE}" get "${USER_SECRET}" -o jsonpath='{.data.password}' | base64 -d)
    curl -s -d "client_id=${CLIENT_ID}" -d "username=${REALM_USER}" \
        -d "password=${password}" -d 'grant_type=password' \
        "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" | jq -r '.access_token'
}

create_entity() {  # create_entity <id> <type>
    printf '{"@context":"%s","id":"%s","type":"%s"}' "${CONTEXT}" "$1" "$2" \
        | curl -s -o /dev/null -w '%{http_code}' -X POST \
            -H "Authorization: Bearer $(get_token)" \
            -H 'Content-Type: application/ld+json' \
            --data-binary @- "${NGSILD_URL}/entities/"
}

set_property() {  # set_property <id> <property> <JSON value>
    printf '{"@context":"%s","%s":{"type":"Property","value":%s}}' "${CONTEXT}" "$2" "$3" \
        | curl -s -o /dev/null -w '%{http_code}' -X POST \
            -H "Authorization: Bearer $(get_token)" \
            -H 'Content-Type: application/ld+json' \
            --data-binary @- "${NGSILD_URL}/entities/$1/attrs"
}

delete_entity() {
    curl -s -o /dev/null -w '%{http_code}' -X DELETE \
        -H "Authorization: Bearer $(get_token)" "${NGSILD_URL}/entities/$1"
}

# ------------------------------------------------- Alerta

# Every alert of a resource whatever its status, as JSON lines; the status
# is asked for explicitly so that no default filter hides closed ones.
alerts_of() {  # alerts_of <resource> [event substring]
    curl -s -H "Authorization: Key ${ALERTA_KEY}" \
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

alert_by_id() {
    curl -s -H "Authorization: Key ${ALERTA_KEY}" "${ALERTA_URL}/alert/$1" | jq -c '.alert'
}

# ------------------------------------------------- Kafka, through the broker pod as tools/ttl_test.py

SEP=$'\t'

kafka_tool() {  # kafka_tool <tool and arguments>; stdin goes to the tool
    kubectl -n "${NAMESPACE}" exec -i "${KAFKA_POD}" -- sh -c "KAFKA_HEAP_OPTS='-Xmx256M' bin/$1"
}

# The whole topic, one "<key><TAB><value>" line per record; a tombstone
# reads "null".
read_topic() {
    kafka_tool "kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic $1 --from-beginning --timeout-ms 20000 --property print.key=true --property key.separator='${SEP}'" 2>/dev/null || true
}

write_records() {  # write_records <topic> < "<key><TAB><value>" lines
    kafka_tool "kafka-console-producer.sh --bootstrap-server localhost:9092 --topic $1 --property parse.key=true --property key.separator='${SEP}'"
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

# ------------------------------------------------- the tests

@test "before the redeploy: stale raises open for satisfied constraints and a gone entity, one real violation, another service's alert, a record in iff.ngsild.entities" {
    local id
    # Four entities violating a constraint: the count of hasE2EState of an
    # E2EMachine, or the count and the sh:xone of hasE2ERange of an
    # E2ERangeMachine.
    for id in "${SAT_COUNT}" "${STILL}" "${GONE}"; do
        [ "$(create_entity "${id}" "${MACHINE_TYPE}")" = "201" ]
    done
    [ "$(create_entity "${SAT_RANGE}" "${RANGE_TYPE}")" = "201" ]
    assert_open "${SAT_COUNT}" "${COUNT_CONSTRAINT}"
    assert_open "${STILL}" "${COUNT_CONSTRAINT}"
    assert_open "${GONE}" "${COUNT_CONSTRAINT}"
    assert_open "${SAT_RANGE}" "${XONE_CONSTRAINT}"

    # The raises the job wrote for three of them, as they stand while violated.
    read_topic "${TRIGGER_TOPIC}" > "${STATE}/trigger.before"
    read_topic "${BULK_ALERTS_TOPIC}" > "${STATE}/bulk.before"
    : > "${STATE}/stale.trigger"
    : > "${STATE}/stale.bulk"
    for id in "${SAT_COUNT}" "${SAT_RANGE}" "${GONE}"; do
        raises_of "${id}" < "${STATE}/trigger.before" >> "${STATE}/stale.trigger"
        raises_of "${id}" < "${STATE}/bulk.before" >> "${STATE}/stale.bulk"
        grep -qF "\"${id}\"" "${STATE}/stale.trigger" || { echo "# no raise of ${id} in ${TRIGGER_TOPIC}" >&3; false; }
        grep -qF "\"${id}\"" "${STATE}/stale.bulk" || { echo "# no raise of ${id} in ${BULK_ALERTS_TOPIC}" >&3; false; }
    done
    grep -F "\"${SAT_RANGE}\"" "${STATE}/stale.trigger" | grep -qF "${XONE_CONSTRAINT}"

    # Satisfied now, or gone: the job retracts and the alerts close.
    [ "$(set_property "${SAT_COUNT}" "${STATE_PROP}" '"ON"')" = "204" ]
    [ "$(set_property "${SAT_RANGE}" "${RANGE_PROP}" 5)" = "204" ]
    [ "$(delete_entity "${GONE}")" = "204" ]
    assert_closed "${SAT_COUNT}"
    assert_closed "${SAT_RANGE}"
    assert_closed "${GONE}"

    # The raises written again, as they stand after the previous job of
    # #977: in the topic it replays, and open in Alerta.
    write_records "${TRIGGER_TOPIC}" < "${STATE}/stale.trigger"
    write_records "${BULK_ALERTS_TOPIC}" < "${STATE}/stale.bulk"
    assert_open "${SAT_COUNT}" "${COUNT_CONSTRAINT}"
    assert_open "${SAT_RANGE}" "${XONE_CONSTRAINT}"
    assert_open "${GONE}" "${COUNT_CONSTRAINT}"
    read_topic "${TRIGGER_TOPIC}" > "${STATE}/trigger.stale"
    for id in "${SAT_COUNT}" "${SAT_RANGE}" "${GONE}"; do
        [ -n "$(raises_of "${id}" < "${STATE}/trigger.stale")" ]
    done
    # the satisfied ones stay open: nothing in the running job retracts them
    sleep 30
    [ "$(open_count "${SAT_COUNT}" "${COUNT_CONSTRAINT}")" -gt 0 ]
    [ "$(open_count "${SAT_RANGE}" "${XONE_CONSTRAINT}")" -gt 0 ]

    # The alert of the constraint still violated, as it is now.
    alerts_of "${STILL}" "${COUNT_CONSTRAINT}" | jq -s -c 'map(select(.status == "open")) | .[0]' > "${STATE}/still.before"
    [ "$(jq -r '.id' "${STATE}/still.before")" != "null" ]

    # An open alert of another service.
    jq -n --arg r "${OTHER}" --arg s "${OTHER_SERVICE}" '{resource: $r, event: "E2ERedeployOther",
        environment: "Development", severity: "minor", service: [$s], text: "not a SHACL alert", timeout: 7200}' \
        | curl -s -X POST -H "Authorization: Key ${ALERTA_KEY}" -H 'Content-Type: application/json' \
            --data-binary @- "${ALERTA_URL}/alert" | jq -r '.id' > "${STATE}/other.id"
    [ "$(cat "${STATE}/other.id")" != "null" ]
    alert_by_id "$(cat "${STATE}/other.id")" > "${STATE}/other.before"
    [ "$(jq -r '.status' "${STATE}/other.before")" = "open" ]

    # A record in iff.ngsild.entities, and the topic's ID.
    printf '%s%s%s\n' "\"${MARKER}\"" "${SEP}" "{\"id\":\"${MARKER}\",\"type\":\"${FREE_TYPE}\",\"deleted\":false}" \
        | write_records "${ENTITY_TOPIC}"
    topic_id "${ENTITY_TOPIC}" > "${STATE}/entities.id"
    [ -n "$(cat "${STATE}/entities.id")" ]
    read_topic "${ENTITY_TOPIC}" | grep -qF "\"id\":\"${MARKER}\""
}

@test "the redeploy reports its four steps in order and exits 0" {
    # Watch the KafkaTopic of iff.ngsild.entities all through the redeploy.
    : > "${STATE}/entities.watch"
    ( while true; do
          if kubectl -n "${NAMESPACE}" get kafkatopic "${ENTITY_TOPIC}" -o name >/dev/null 2>&1; then
              echo "present $(date +%s)" >> "${STATE}/entities.watch"
          else
              echo "MISSING $(date +%s)" >> "${STATE}/entities.watch"
          fi
          sleep 2
      done ) 3>&- &
    echo $! > "${STATE}/poller.pid"

    rc=0
    make -C "${SHACL2FLINK}" flink-redeploy SHACL="${E2E_KMS}/shacl.ttl" \
        KNOWLEDGE="${E2E_KMS}/knowledge.ttl" MODEL="${E2E_KMS}/model-instance.jsonld" \
        > "${STATE}/redeploy.log" 2>&1 || rc=$?
    date +%s > "${STATE}/redeploy.end"
    kill "$(cat "${STATE}/poller.pid")" 2>/dev/null || true
    : > "${STATE}/poller.pid"
    grep -E '^(step |redeploy )' "${STATE}/redeploy.log" | sed 's/^/# /' >&3
    [ "${rc}" -eq 0 ] || { tail -40 "${STATE}/redeploy.log" | sed 's/^/#   /' >&3; false; }
    [ "$(grep '^step ' "${STATE}/redeploy.log")" = "step 1/4 undeploy the validation: started
step 1/4 undeploy the validation: done
step 2/4 close the SHACL alerts: started
step 2/4 close the SHACL alerts: done
step 3/4 restart Core Services: started
step 3/4 restart Core Services: done
step 4/4 deploy the validation: started
step 4/4 deploy the validation: done" ]
}

@test "the alerts of the constraints satisfied now are closed and no raise of them is replayed" {
    # a count constraint, and a value constraint (sh:xone over two ranges)
    closed_now "${SAT_COUNT}"
    closed_now "${SAT_RANGE}"
    # constraint_trigger_table is a new topic: the stale raises are not in it.
    read_topic "${TRIGGER_TOPIC}" > "${STATE}/trigger.after"
    local id
    for id in "${SAT_COUNT}" "${SAT_RANGE}" "${GONE}"; do
        if [ -n "$(raises_of "${id}" < "${STATE}/trigger.after")" ]; then
            echo "# ${TRIGGER_TOPIC} holds a raise of ${id}:" >&3
            raises_of "${id}" < "${STATE}/trigger.after" | sed 's/^/#   /' >&3
            false
        fi
    done
}

@test "the alert of the constraint still violated is open again within two minutes, unchanged, closed by the redeploy in between" {
    assert_open "${STILL}" "${COUNT_CONSTRAINT}" "${SETTLED}"
    local id after
    id=$(jq -r '.id' "${STATE}/still.before")
    after=$(alert_by_id "${id}")
    echo "# ${STILL}: $(jq -c '{status, severity, text}' <<<"${after}")" >&3
    [ "$(jq -r '.status' <<<"${after}")" = "open" ]
    [ "$(jq -r '.severity' <<<"${after}")" = "$(jq -r '.severity' "${STATE}/still.before")" ]
    [ "$(jq -r '.text' <<<"${after}")" = "$(jq -r '.text' "${STATE}/still.before")" ]
    # closed by the redeploy, then opened again
    jq -e '[.history[] | select(.status == "closed" and ((.text // "") | contains("redeploy")))] | length > 0' <<<"${after}" >/dev/null
    jq -e '([.history[] | select(.status == "closed" and ((.text // "") | contains("redeploy"))) | .updateTime] | max) as $closed
        | [.history[] | select(.status == "open" and .updateTime > $closed)] | length > 0' <<<"${after}" >/dev/null
}

@test "the alerts of the gone entity and the satisfied constraints are still closed two minutes after the redeploy" {
    local wait
    wait=$(( $(cat "${STATE}/redeploy.end") + SETTLED - $(date +%s) ))
    [ "${wait}" -le 0 ] || sleep "${wait}"
    closed_now "${GONE}"
    closed_now "${SAT_COUNT}"
    closed_now "${SAT_RANGE}"
}

@test "the alert of another service is untouched" {
    local after
    after=$(alert_by_id "$(cat "${STATE}/other.id")")
    [ "$(jq -r '.status' <<<"${after}")" = "$(jq -r '.status' "${STATE}/other.before")" ]
    [ "$(jq -r '.severity' <<<"${after}")" = "$(jq -r '.severity' "${STATE}/other.before")" ]
    [ "$(jq '.history | length' <<<"${after}")" = "$(jq '.history | length' "${STATE}/other.before")" ]
    jq -e '[.history[] | select((.text // "") | contains("redeploy"))] | length == 0' <<<"${after}" >/dev/null
}

@test "iff.ngsild.entities is kept: its KafkaTopic throughout, its topic ID and its records" {
    if grep -q MISSING "${STATE}/entities.watch"; then
        echo "# the KafkaTopic ${ENTITY_TOPIC} was missing at times during the redeploy:" >&3
        grep MISSING "${STATE}/entities.watch" | head -5 | sed 's/^/#   /' >&3
        false
    fi
    [ "$(grep -c present "${STATE}/entities.watch")" -gt 0 ]
    [ "$(topic_id "${ENTITY_TOPIC}")" = "$(cat "${STATE}/entities.id")" ]
    read_topic "${ENTITY_TOPIC}" | grep -qF "\"id\":\"${MARKER}\""
}
