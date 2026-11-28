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
# `make flink-deploy` validates the entities that exist before it: it restarts
# Kafka Connect, so that Debezium publishes them again, only once the deployed
# validation job reads them. The job reads entities and attributes from the
# latest offset; what is published before its readers hold their partitions is
# never validated, until the next regular re-snapshot (#1114).
#
# 1. An entity created while no validation is deployed raises its alert after
#    the first deployment, which runs the job without RocksDB. That is what
#    the issue asks to cover; on a first deployment the statementset reports
#    RUNNING only for the new job, so this passed before the fix as well.
# 2. The reproduction of #1114: a deployment over that running validation,
#    with RocksDB again, so the package changes and the deploy replaces the
#    validation through the resync (#1165). The resync's stop deletes the
#    statementset, which needs the operator; so the operator is held back
#    once the old statementset is gone, and comes back HOLD seconds after the
#    install created the new one, as a busy operator would. Kafka Connect
#    must be restarted after the new job started, and the new job must have
#    read the entities published by that restart, with no further restart.
#    Each constraint row is read once, and no KafkaTopic is replaced.
#    (The stale RUNNING of the old job that #1114 was about can't occur any
#    more: the old statementset is gone before the new one exists.)
# 3. A changed package over the running validation: of two relationship-count
#    alerts, the one the new package satisfies closes, the other stays open
#    with the real number (#977, #1165).
# 4. The same package twice over the running validation: the job is kept,
#    each row read once, the counts not doubled, and writing the fingerprint
#    doesn't restart the job.
# 5. No kept fingerprint: replaced.
# 6. An interrupted replacement is replaced again by the next deploy.
# 7. A deploy with no validation running closes what a previous one left open.
#
# Driven by `make test-flink-e2e` before the other suites, which then run
# against the deployment of tests/e2e-kms that this suite leaves behind. The
# tests run in order; each needs the one before it.

NAMESPACE=${NAMESPACE:-iff}
SHACL2FLINK="${BATS_TEST_DIRNAME}/../../.."
E2E_KMS="${SHACL2FLINK}/tests/e2e-kms"

# As in test-shacl-flink-scorpio-e2e: the services published by
# test/setup-local-ingress.sh.
KEYCLOAK_URL=${KEYCLOAK_URL:-http://keycloak.local/auth/realms}
NGSILD_URL=${NGSILD_URL:-http://ngsild.local/ngsi-ld/v1}
ALERTA_URL=${ALERTA_URL:-http://alerta.local/api}
CLIENT_ID=scorpio
REALM_USER=realm_user
USER_SECRET=secret/credential-iff-realm-user-iff

CONTEXT=https://industryfusion.github.io/contexts/staging/example/v0.2/context.jsonld
MACHINE_TYPE=https://industryfusion.github.io/contexts/example/v0/base_entities/E2EMachine
COUNT_CONSTRAINT=CountConstraintComponent
OPERATOR=beamservices-operator
STATEMENTSET=shacl-validation

# An alert appears seconds after the job has read the entity; the limit is far
# above that and far below the regular re-snapshot (every half state TTL).
TIMEOUT=${TIMEOUT:-300}
POLL=5
# How long the operator is held back once the new statementset is applied.
HOLD=${HOLD:-90}
KUBECTL_LIMIT=${KUBECTL_LIMIT:-60}
export BATS_TEST_TIMEOUT=${BATS_TEST_TIMEOUT:-2400}
# flink-deploy's own wait, within the test's limit
export VALIDATION_START_TIMEOUT=${VALIDATION_START_TIMEOUT:-1200}

k() {
    timeout "${KUBECTL_LIMIT}" kubectl -n "${NAMESPACE}" "$@"
}

progress() {  # a line in the CI log as it happens, findable by its tag
    echo "# [deploy-e2e] $(date -u +%H:%M:%S) $*" >&3
}

# flink_get <path>: the Flink REST API, through the JobManager's pod; -g, as
# metric names hold brackets
flink_get() {
    local jm
    jm=$(k get pods -l component=jobmanager -o jsonpath='{.items[0].metadata.name}') || return 1
    k exec "${jm}" -c flink-main-container -- curl -s -g -m 10 "http://localhost:8081$1"
}

# shacl_make <log> <target> [make arguments]: make of shacl2flink. Its
# flink-deploy and flink-undeploy run bats themselves: without this suite's
# bats variables and bats' own directories in PATH, or that bats runs in this
# one's context and fails. Nor the variables of an outer make: what this suite
# gives is all it gets.
shacl_make() {
    local rc=0 log=$1 target=$2 unset=() path
    shift 2
    for v in $(compgen -v BATS_) MAKEFLAGS MFLAGS MAKELEVEL; do unset+=(-u "${v}"); done
    path=$(tr ':' '\n' <<<"${PATH}" | grep -v 'bats-core' | paste -sd:)
    env "${unset[@]}" PATH="${path}" make -C "${SHACL2FLINK}" "${target}" "$@" > "${log}" 2>&1 || rc=$?
    progress "make ${target} $* ended with ${rc}; its last lines:"
    tail -15 "${log}" | cut -c1-300 | sed 's/^/#   /' >&3
    return "${rc}"
}

deploy() {  # deploy [make variables]: make flink-deploy of tests/e2e-kms
    shacl_make "${BATS_FILE_TMPDIR}/deploy.log" flink-deploy SHACL="${E2E_KMS}/shacl.ttl" \
        KNOWLEDGE="${E2E_KMS}/knowledge.ttl" MODEL="${E2E_KMS}/model-instance.jsonld" "$@"
}

undeploy() {  # undeploy: make flink-undeploy
    shacl_make "${BATS_FILE_TMPDIR}/undeploy.log" flink-undeploy
}

diagnose() {
    progress "diagnostics after the failed test: ${BATS_TEST_DESCRIPTION}"
    progress "statementset: $(k get beamsqlstatementset "${STATEMENTSET}" -o jsonpath='{.status.state} {.status.job_id}' 2>/dev/null || echo missing)"
    progress "operator replicas: $(k get deployment "${OPERATOR}" -o jsonpath='{.spec.replicas}/{.status.readyReplicas}' 2>/dev/null || echo unknown)"
    progress "Flink jobs:"
    flink_get /jobs/overview 2>/dev/null \
        | jq -r '.jobs[]? | "#   \(.name) \(.jid) \(.state) \(.tasks.running)/\(.tasks.total) start \(."start-time")"' >&3 || true
    progress "Connect pods: $(k get pods -l app.kubernetes.io/instance=kafka-connect -o jsonpath='{range .items[*]}{.metadata.name} {.metadata.creationTimestamp} {.status.phase}{"; "}{end}' 2>/dev/null)"
}

# Back to how the suite found it: the operator running.
restore() {
    if [ -s "${BATS_FILE_TMPDIR}/hold.pid" ]; then
        kill "$(cat "${BATS_FILE_TMPDIR}/hold.pid")" 2>/dev/null || true
        : > "${BATS_FILE_TMPDIR}/hold.pid"
    fi
    if [ -s "${BATS_FILE_TMPDIR}/operator.replicas" ]; then
        k scale deployment "${OPERATOR}" --replicas="$(cat "${BATS_FILE_TMPDIR}/operator.replicas")" >/dev/null 2>&1 || true
        : > "${BATS_FILE_TMPDIR}/operator.replicas"
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
    EXISTING="urn:e2e-deploy-existing:${RUN_ID}"
    LINKED_TWO="urn:e2e-deploy-linked-two:${RUN_ID}"
    LINKED_THREE="urn:e2e-deploy-linked-three:${RUN_ID}"
    ALERTA_KEY=$(k get secret alerta -o jsonpath='{.data.alerta-admin-key}' | base64 -d)
    if [ "${BATS_TEST_NUMBER}" -gt 1 ] && [ ! -e "${BATS_FILE_TMPDIR}/passed.$(( BATS_TEST_NUMBER - 1 ))" ]; then
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
    touch "${BATS_FILE_TMPDIR}/passed.${BATS_TEST_NUMBER}"
}

teardown_file() {
    # shellcheck disable=SC1091
    . "${BATS_FILE_TMPDIR}/ids"
    restore
    delete_entity "urn:e2e-deploy-existing:${RUN_ID}" >/dev/null 2>&1 || true
    delete_entity "urn:e2e-deploy-linked-two:${RUN_ID}" >/dev/null 2>&1 || true
    delete_entity "urn:e2e-deploy-linked-three:${RUN_ID}" >/dev/null 2>&1 || true
}

get_token() {
    local password
    password=$(k get "${USER_SECRET}" -o jsonpath='{.data.password}' | base64 -d)
    curl -s -m 30 -d "client_id=${CLIENT_ID}" -d "username=${REALM_USER}" \
        -d "password=${password}" -d 'grant_type=password' \
        "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" | jq -r '.access_token'
}

create_entity() {  # create_entity <id> <type>
    printf '{"@context":"%s","id":"%s","type":"%s"}' "${CONTEXT}" "$1" "$2" \
        | curl -s -m 30 -o /dev/null -w '%{http_code}' -X POST \
            -H "Authorization: Bearer $(get_token)" \
            -H 'Content-Type: application/ld+json' \
            --data-binary @- "${NGSILD_URL}/entities/"
}

delete_entity() {
    curl -s -m 30 -o /dev/null -w '%{http_code}' -X DELETE \
        -H "Authorization: Bearer $(get_token)" "${NGSILD_URL}/entities/$1"
}

open_count() {  # open_count <resource> <event substring>: its alerts that are not closed
    curl -s -m 30 -H "Authorization: Key ${ALERTA_KEY}" \
        "${ALERTA_URL}/alerts?resource=$1&status=open&status=ack&status=shelved&status=expired&status=unknown" \
        | jq --arg e "$2" '[.alerts[]? | select(.event | contains($e))] | length'
}

assert_open() {  # assert_open <resource> <event>
    local waited=0
    while [ "${waited}" -lt "${TIMEOUT}" ]; do
        [ "$(open_count "$1" "$2")" -gt 0 ] && return 0
        sleep "${POLL}"
        waited=$(( waited + POLL ))
    done
    progress "no open $2 alert on $1 within ${TIMEOUT}s"
    return 1
}

job_of() {
    k get beamsqlstatementset "${STATEMENTSET}" -o jsonpath='{.status.job_id}'
}

# The newest Connect pod's creation, in seconds since the epoch.
connect_created() {
    k get pods -l app.kubernetes.io/instance=kafka-connect \
        -o jsonpath='{range .items[*]}{.metadata.creationTimestamp}{"\n"}{end}' \
        | sort | tail -1 | xargs -I{} date -u -d {} +%s
}

# entities_read <job>: the offset the job's reader of iff.ngsild.entities has
# reached, -1 before it read a record
entities_read() {
    local vertex metric
    for vertex in $(flink_get "/jobs/$1" | jq -r '.vertices[].id'); do
        metric=$(flink_get "/jobs/$1/vertices/${vertex}/metrics" \
            | jq -r '[.[].id | select(test("KafkaSourceReader\\.topic\\.iff_ngsild_entities\\.partition\\.[0-9]+\\.currentOffset$"))][0] // empty')
        if [ -n "${metric}" ]; then
            flink_get "/jobs/$1/vertices/${vertex}/metrics?get=${metric}" | jq -r '.[0].value'
            return 0
        fi
    done
    echo -1
}

# ---------------------------------------------------------------- #1165: deploying over a running validation

FINGERPRINT=shacl-validation-fingerprint
BASE=https://industryfusion.github.io/contexts/example/v0/base_entities
LINKED_TYPE=${BASE}/E2ELinkedMachine
CARTRIDGE=${BASE}/hasE2ECartridge
COMMON_CONFIG="${SHACL2FLINK}/../../helm/common.yaml"

kafkatopics() {  # every KafkaTopic with the topic ID it reports, sorted
    k get kafkatopics \
        -o jsonpath='{range .items[*]}{.metadata.name} {.status.topicId}{"\n"}{end}' | sort
}

fingerprint_job() {  # the job the kept fingerprint was written for
    k get configmap "${FINGERPRINT}" -o jsonpath='{.data.job}' 2>/dev/null
}

# pg_count <table>: its rows in the validation's Postgres database, found as
# make submit-postgres-tables finds it
pg_count() {
    local db svc user secret password pod
    db=$(yq '.flink.db.name' "${COMMON_CONFIG}")
    svc="$(yq '.db.teamId' "${COMMON_CONFIG}")-$(yq '.db.clusterSvcPostfix' "${COMMON_CONFIG}")"
    user=$(yq '.flink.db.writeUser' "${COMMON_CONFIG}")
    secret=$(k get secrets | grep "$(tr '_' '-' <<<"${user}")" | cut -d ' ' -f 1)
    password=$(k get secret "${secret}" -o go-template='{{index .data "password" | base64decode}}')
    pod=$(k get ep "${svc}" -o jsonpath='{.subsets[0].addresses[0].targetRef.name}')
    k exec -i "${pod}" -- bash -c "PGPASSWORD='${password}' PGSSLMODE=require psql -h localhost -U ${user} -d ${db} -tAc 'select count(*) from $1'" \
        | tr -d '[:space:]'
}

# source_records <job> <table>: the records the job's CDC source of the table
# has emitted, summed over its subtasks
source_records() {
    local vertex ids sum=0 id value
    for vertex in $(flink_get "/jobs/$1" | jq -r '.vertices[].id'); do
        ids=$(flink_get "/jobs/$1/vertices/${vertex}/metrics" \
            | jq -r --arg t "$2" '.[].id | select(test("^[0-9]+\\.Source__" + $t + "\\[[0-9]+\\]\\.numRecordsOut$"))')
        for id in ${ids}; do
            value=$(flink_get "/jobs/$1/vertices/${vertex}/metrics?get=${id}" | jq -r '.[0].value')
            sum=$(( sum + ${value%.*} ))
        done
    done
    echo "${sum}"
}

# assert_rows_read_once <job>: each constraint table's source has emitted as
# many records as the table holds -- not fewer once the snapshot is read,
# and never more
assert_rows_read_once() {
    local table rows out waited
    for table in constraint_table constraint_combination_table; do
        rows=$(pg_count "${table}")
        [ "${rows}" -gt 0 ]
        waited=0
        while true; do
            out=$(source_records "$1" "${table}")
            [ "${out}" -le "${rows}" ] || { progress "the job $1 read ${out} rows of ${table}, which holds ${rows}"; return 1; }
            [ "${out}" -lt "${rows}" ] || break
            [ "${waited}" -lt "${TIMEOUT}" ] || { progress "the job $1 read only ${out} of the ${rows} rows of ${table}"; return 1; }
            sleep "${POLL}"
            waited=$(( waited + POLL ))
        done
        progress "the job $1 read the ${rows} rows of ${table} once"
    done
}

create_linked() {  # create_linked <id> <cartridges>: a linked machine with that many cartridges
    local i rels=""
    for i in $(seq 1 "$2"); do
        rels="${rels}${rels:+,}{\"type\":\"Relationship\",\"object\":\"urn:e2e-cartridge:${i}\",\"datasetId\":\"urn:e2e-ds:${i}\"}"
    done
    printf '{"@context":"%s","id":"%s","type":"%s","%s":[%s]}' "${CONTEXT}" "$1" "${LINKED_TYPE}" "${CARTRIDGE}" "${rels}" \
        | curl -s -m 30 -o /dev/null -w '%{http_code}' -X POST \
            -H "Authorization: Bearer $(get_token)" \
            -H 'Content-Type: application/ld+json' \
            --data-binary @- "${NGSILD_URL}/entities/"
}

# changed_package <dir>: the suite's package with two cartridges allowed
# instead of one
changed_package() {
    mkdir -p "$1"
    awk '/hasE2ECartridge/ { cartridge = 1 }
         cartridge && /sh:maxCount 1 ;/ { sub(/sh:maxCount 1 ;/, "sh:maxCount 2 ;"); cartridge = 0 }
         { print }' "${E2E_KMS}/shacl.ttl" > "$1/shacl.ttl"
    ! cmp -s "${E2E_KMS}/shacl.ttl" "$1/shacl.ttl"
    # It also drops one knowledge triple no constraint reads, the ontology's
    # version: the new job must no longer see it (#1165 D6).
    sed 's/^: a owl:Ontology ;$/: a owl:Ontology ./; /^    owl:versionInfo "e2e"^^xsd:string \.$/d' "${E2E_KMS}/knowledge.ttl" > "$1/knowledge.ttl"
    ! grep -q 'owl:versionInfo' "$1/knowledge.ttl"
}

# rdf_last <subject substring> <predicate substring>: the last record of the
# iff.rdf keys matching both, "null" for a tombstone; read in the broker pod.
rdf_last() {
    k exec my-cluster-nodes-0 -- sh -c "KAFKA_HEAP_OPTS='-Xmx192M' bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic iff.rdf --from-beginning --timeout-ms 15000 --property print.key=true 2>/dev/null" </dev/null \
        | awk -F'\t' -v s="$1" -v p="$2" 'index($1, s) && index($1, p) { last = $2 } END { print last }'
}

open_text() {  # open_text <resource> <event substring>: the texts of its open alerts
    curl -s -m 30 -H "Authorization: Key ${ALERTA_KEY}" \
        "${ALERTA_URL}/alerts?resource=$1&status=open&status=ack&status=shelved&status=expired&status=unknown" \
        | jq -r --arg e "$2" '[.alerts[]? | select(.event | contains($e)) | .text] | sort | .[]'
}

# assert_open_text <resource> <event> <text>: one open alert of the event has
# that text, within TIMEOUT; prints what is open otherwise
assert_open_text() {
    local waited=0
    while [ "${waited}" -lt "${TIMEOUT}" ]; do
        open_text "$1" "$2" | grep -qF -- "$3" && return 0
        sleep "${POLL}"
        waited=$(( waited + POLL ))
    done
    progress "no open $2 alert on $1 with '$3' within ${TIMEOUT}s; open: $(open_text "$1" "$2" | tr '\n' '|')"
    return 1
}

assert_closed() {  # assert_closed <resource> <event>
    local waited=0
    while [ "${waited}" -lt "${TIMEOUT}" ]; do
        [ "$(open_count "$1" "$2")" -eq 0 ] && return 0
        sleep "${POLL}"
        waited=$(( waited + POLL ))
    done
    progress "an open $2 alert on $1 after ${TIMEOUT}s: $(open_text "$1" "$2")"
    return 1
}

@test "an entity created before the first deployment is validated after it" {
    [ -z "$(k get beamsqlstatementset "${STATEMENTSET}" --ignore-not-found -o name)" ]
    code=$(create_entity "${EXISTING}" "${MACHINE_TYPE}")
    [ "${code}" = "201" ]
    progress "created ${EXISTING} without its mandatory attribute, no validation deployed"
    deploy NOROCKSDB=true
    assert_open "${EXISTING}" "${COUNT_CONSTRAINT}"
    progress "its alert is open"
}

@test "a deployment over the running validation restarts Kafka Connect only once the new job reads" {
    local old new started created offset waited=0
    old=$(job_of)
    [ -n "${old}" ]
    kafkatopics > "${BATS_FILE_TMPDIR}/kafkatopics.before"
    k get deployment "${OPERATOR}" -o jsonpath='{.spec.replicas}' > "${BATS_FILE_TMPDIR}/operator.replicas"
    # The deploy replaces the validation through the resync (#1165): its stop
    # deletes the statementset, which needs the operator. So the operator is
    # held back once the old statementset is gone, and comes back HOLD seconds
    # after the install created the new one: until then the new statementset
    # has no job, and the deploy must wait for it.
    (
        until [ -z "$(k get beamsqlstatementset "${STATEMENTSET}" --ignore-not-found -o name 2>/dev/null)" ]; do
            sleep 1
        done
        k scale deployment "${OPERATOR}" --replicas=0 >/dev/null
        until k get beamsqlstatementset "${STATEMENTSET}" -o json 2>/dev/null \
            | jq -e '.spec.sqlsettings | any(has("state.backend"))' >/dev/null; do
            sleep 2
        done
        date +%s > "${BATS_FILE_TMPDIR}/held"
        sleep "${HOLD}"
        k scale deployment "${OPERATOR}" --replicas="$(cat "${BATS_FILE_TMPDIR}/operator.replicas")" >/dev/null
    ) 3>&- &
    echo $! > "${BATS_FILE_TMPDIR}/hold.pid"
    progress "the operator is held back once the old statementset is gone; the job ${old} runs"
    deploy
    [ -s "${BATS_FILE_TMPDIR}/held" ]
    new=$(job_of)
    progress "the job ${old} was replaced by ${new}"
    [ -n "${new}" ]
    [ "${new}" != "${old}" ]
    started=$(flink_get "/jobs/${new}" | jq -r '."start-time" / 1000 | floor')
    # The new job can only have started once the operator was back.
    [ "${started}" -ge "$(( $(cat "${BATS_FILE_TMPDIR}/held") + HOLD - 5 ))" ]
    # The pods are deleted without waiting for them to end: the new one comes
    # a little later. One created before the job started is the old one.
    until created=$(connect_created) && [ "${created}" -gt "${started}" ]; do
        [ "${waited}" -lt 120 ] || break
        sleep "${POLL}"
        waited=$(( waited + POLL ))
    done
    waited=0
    progress "the job ${new} started $(date -u -d "@${started}" +%T), the newest Connect pod was created $(date -u -d "@${created}" +%T)"
    [ "${created}" -gt "${started}" ]
    # What that restart published is read, with no other restart.
    until offset=$(entities_read "${new}") && [ "${offset}" -ge 0 ]; do
        [ "${waited}" -lt "${TIMEOUT}" ] || { progress "the job ${new} read no entity within ${TIMEOUT}s"; false; }
        sleep "${POLL}"
        waited=$(( waited + POLL ))
    done
    progress "the job ${new} has read iff.ngsild.entities up to offset ${offset}"
    [ "$(connect_created)" -eq "${created}" ]
    # Each constraint row read once, no topic replaced, and the fingerprint
    # kept for the new job.
    assert_rows_read_once "${new}"
    kafkatopics > "${BATS_FILE_TMPDIR}/kafkatopics.after"
    diff "${BATS_FILE_TMPDIR}/kafkatopics.before" "${BATS_FILE_TMPDIR}/kafkatopics.after"
    [ "$(fingerprint_job)" = "${new}" ]
    # The entity's count is still violated: its alert is open again.
    assert_open "${EXISTING}" "${COUNT_CONSTRAINT}"
}

@test "a changed package over the running validation: a satisfied relationship count closes, a violated one stays" {
    local old new
    old=$(job_of)
    # Two machines with two and three cartridges, against [1, 1].
    [ "$(create_linked "${LINKED_TWO}" 2)" = "201" ]
    [ "$(create_linked "${LINKED_THREE}" 3)" = "201" ]
    assert_open "${LINKED_TWO}" "${COUNT_CONSTRAINT}"
    assert_open "${LINKED_THREE}" "${COUNT_CONSTRAINT}"
    progress "both linked machines raise their relationship count under [1, 1]"
    # The changed package allows two.
    changed_package "${BATS_FILE_TMPDIR}/changed"
    [ "$(rdf_last base_entities/ owl#versionInfo)" != "null" ]
    deploy SHACL="${BATS_FILE_TMPDIR}/changed/shacl.ttl" KNOWLEDGE="${BATS_FILE_TMPDIR}/changed/knowledge.ttl"
    new=$(job_of)
    [ "${new}" != "${old}" ]
    assert_rows_read_once "${new}"
    # The knowledge triple the changed package dropped ends in a tombstone, so
    # the job's upsert view of iff.rdf no longer has it (#1165 D6).
    grep -qE "of them removed by a tombstone" "${BATS_FILE_TMPDIR}/deploy.log"
    [ "$(rdf_last base_entities/ owl#versionInfo)" = "null" ]
    progress "the dropped knowledge triple is a tombstone in iff.rdf: $(grep -o '[0-9]* live keys in iff.rdf, [0-9]* of them removed by a tombstone' "${BATS_FILE_TMPDIR}/deploy.log" | tail -1)"
    assert_closed "${LINKED_TWO}" "${COUNT_CONSTRAINT}"
    assert_open "${LINKED_THREE}" "${COUNT_CONSTRAINT}"
    open_text "${LINKED_THREE}" "${COUNT_CONSTRAINT}" | grep -q "Found 3 relationships instead of \[1, 2\]"
    progress "after the changed package: ${LINKED_TWO} closed, ${LINKED_THREE} open with Found 3"
    # Back to the suite's package, for the suites after this one.
    deploy
    [ "$(fingerprint_job)" = "$(job_of)" ]
}

@test "the same package over the running validation keeps the job, reads each row once, keeps the counts" {
    local job
    job=$(job_of)
    # The suite's package allows one cartridge: three are reported as three.
    assert_open_text "${LINKED_THREE}" "${COUNT_CONSTRAINT}" "Found 3 relationships instead of [1, 1]!"
    for n in 1 2; do
        deploy
        [ "$(job_of)" = "${job}" ]
        grep -q "unchanged: the job ${job} keeps running" "${BATS_FILE_TMPDIR}/deploy.log"
        grep -q "the job ${job} reads; restarting Kafka Connect" "${BATS_FILE_TMPDIR}/deploy.log"
        assert_rows_read_once "${job}"
        progress "deploy ${n} of the same package: the job ${job} kept, each row read once"
    done
    # The counts after the re-snapshots are the same, not doubled: a doubled
    # constraint row would report six.
    sleep 60
    assert_open_text "${LINKED_THREE}" "${COUNT_CONSTRAINT}" "Found 3 relationships instead of [1, 1]!"
    # Writing the fingerprint did not make the operator restart the job.
    [ "$(job_of)" = "${job}" ]
}

@test "a validation without a kept fingerprint is replaced" {
    local old
    old=$(job_of)
    k delete configmap "${FINGERPRINT}" >/dev/null
    deploy
    grep -q "replace: no fingerprint is kept" "${BATS_FILE_TMPDIR}/deploy.log"
    [ "$(job_of)" != "${old}" ]
    [ "$(fingerprint_job)" = "$(job_of)" ]
}

@test "an interrupted replacement is replaced again by the next deploy" {
    changed_package "${BATS_FILE_TMPDIR}/changed"
    # Broken off after the new statementset runs and before the resync
    # ended: the wait for the re-snapshot gets one second, so it fails there.
    # Timing a signal against the running deploy was not deterministic on
    # CI. A failed and an interrupted resync leave the deploy the same way
    # (it exits non-zero and keeps no fingerprint); the resync's handling of
    # a signal is covered by test/bats-unit/shacl-resync.bats.
    RESYNC_PROCESSED_TIMEOUT=1 deploy SHACL="${BATS_FILE_TMPDIR}/changed/shacl.ttl" KNOWLEDGE="${BATS_FILE_TMPDIR}/changed/knowledge.ttl" || true
    grep -q "resync failed in step 8/9 wait until the re-snapshot is processed" "${BATS_FILE_TMPDIR}/deploy.log" \
        || { progress "the resync did not end in its wait step"; tail -8 "${BATS_FILE_TMPDIR}/deploy.log" | sed 's/^/#   /' >&3; false; }
    grep -q "deploy failed: the resync with the new package failed" "${BATS_FILE_TMPDIR}/deploy.log"
    [ -n "$(k get beamsqlstatementset "${STATEMENTSET}" --ignore-not-found -o name)" ]
    progress "the replacement was broken off in its wait for the re-snapshot, with the new statementset deployed"
    [ -z "$(k get configmap "${FINGERPRINT}" --ignore-not-found -o name)" ]
    deploy SHACL="${BATS_FILE_TMPDIR}/changed/shacl.ttl" KNOWLEDGE="${BATS_FILE_TMPDIR}/changed/knowledge.ttl"
    grep -q "replace: no fingerprint is kept" "${BATS_FILE_TMPDIR}/deploy.log"
    [ "$(fingerprint_job)" = "$(job_of)" ]
    assert_closed "${LINKED_TWO}" "${COUNT_CONSTRAINT}"
    assert_open "${LINKED_THREE}" "${COUNT_CONSTRAINT}"
    deploy
}

@test "a deploy with no validation running closes the alerts a previous one left open" {
    # Under the changed package the two-cartridge machine satisfies its count;
    # an alert left open by an earlier validation must close.
    changed_package "${BATS_FILE_TMPDIR}/changed"
    # The previous test ends by deploying the suite's package again, whose
    # resync raises this alert anew; it may not be back yet.
    assert_open "${LINKED_TWO}" "${COUNT_CONSTRAINT}"
    undeploy
    [ "$(open_count "${LINKED_TWO}" "${COUNT_CONSTRAINT}")" -gt 0 ]
    deploy SHACL="${BATS_FILE_TMPDIR}/changed/shacl.ttl" KNOWLEDGE="${BATS_FILE_TMPDIR}/changed/knowledge.ttl"
    assert_closed "${LINKED_TWO}" "${COUNT_CONSTRAINT}"
    assert_open "${LINKED_THREE}" "${COUNT_CONSTRAINT}"
    # Leave the suite's package deployed.
    deploy
    assert_open "${LINKED_TWO}" "${COUNT_CONSTRAINT}"
}
