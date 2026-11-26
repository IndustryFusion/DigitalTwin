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
#    with RocksDB again, so the statementset changes and its job is replaced.
#    The operator is held back for a while, as a busy operator would be:
#    until it acts, the statementset still reports RUNNING with the old job.
#    Kafka Connect must be restarted after the new job started, and the new
#    job must have read the entities published by that restart, with no
#    further restart. (The alert of test 1 can't tell: it stays open, and Core
#    Services forwards no unchanged raise again.)
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

deploy() {  # deploy [make variables]: make flink-deploy of tests/e2e-kms
    local rc=0 log="${BATS_FILE_TMPDIR}/deploy.log" unset=() path
    # flink-deploy runs bats itself: without this suite's bats variables and
    # bats' own directories in PATH, or that bats runs in this one's context.
    # Nor the variables of an outer make: what this suite gives is all it gets.
    for v in $(compgen -v BATS_) MAKEFLAGS MFLAGS MAKELEVEL; do unset+=(-u "${v}"); done
    path=$(tr ':' '\n' <<<"${PATH}" | grep -v 'bats-core' | paste -sd:)
    env "${unset[@]}" PATH="${path}" make -C "${SHACL2FLINK}" flink-deploy SHACL="${E2E_KMS}/shacl.ttl" \
        KNOWLEDGE="${E2E_KMS}/knowledge.ttl" MODEL="${E2E_KMS}/model-instance.jsonld" "$@" \
        > "${log}" 2>&1 || rc=$?
    progress "make flink-deploy $* ended with ${rc}; its last lines:"
    tail -15 "${log}" | cut -c1-300 | sed 's/^/#   /' >&3
    return "${rc}"
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
    k get deployment "${OPERATOR}" -o jsonpath='{.spec.replicas}' > "${BATS_FILE_TMPDIR}/operator.replicas"
    k scale deployment "${OPERATOR}" --replicas=0 >/dev/null
    k wait --for=delete pod -l "app=${OPERATOR}" --timeout=50s >/dev/null 2>&1 || true
    progress "the operator is held back; the job ${old} runs"
    # Back HOLD seconds after the new statementset is applied.
    (
        until k get beamsqlstatementset "${STATEMENTSET}" -o json 2>/dev/null \
            | jq -e '.spec.sqlsettings | any(has("state.backend"))' >/dev/null; do
            sleep 2
        done
        sleep "${HOLD}"
        k scale deployment "${OPERATOR}" --replicas="$(cat "${BATS_FILE_TMPDIR}/operator.replicas")" >/dev/null
    ) 3>&- &
    echo $! > "${BATS_FILE_TMPDIR}/hold.pid"
    deploy
    new=$(job_of)
    progress "the job ${old} was replaced by ${new}"
    [ -n "${new}" ]
    [ "${new}" != "${old}" ]
    started=$(flink_get "/jobs/${new}" | jq -r '."start-time" / 1000 | floor')
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
}
