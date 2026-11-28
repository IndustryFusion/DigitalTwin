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
# The deploy of a validation (semantic-model/shacl2flink/deploy_validation.sh,
# #1165): the fingerprint, and the choice between keeping the running job and
# replacing the validation through the resync. kubectl, curl (Flink),
# helmfile, make and the resync are stubs; every call is logged in order.

# shellcheck disable=SC2030,SC2031,SC2154  # per-test env is test-local; bats sets stderr

bats_require_minimum_version 1.5.0

SRC="${BATS_TEST_DIRNAME}/../../semantic-model/shacl2flink"

setup() {
    WORK="$(mktemp -d)"
    export WORK
    export STATE="${WORK}/state"
    export CALLS="${WORK}/calls.log"
    mkdir -p "${WORK}/bin" "${STATE}" "${WORK}/sf/output" "${WORK}/helm"
    : > "${CALLS}"
    cp "${SRC}/deploy_validation.sh" "${SRC}/validation_job.sh" "${WORK}/sf/"

    # the resync: replaces the statementset's job, as REPLACE=package does
    cat > "${WORK}/sf/shacl_resync.sh" <<'EOF'
#!/bin/bash
echo "resync REPLACE=${REPLACE} RESYNC_INSTALL=${RESYNC_INSTALL}" >> "${CALLS}"
[ -z "${STUB_RESYNC_FAIL:-}" ] || exit 1
echo "ss-new" > "${STATE}/ss_job"
echo RUNNING > "${STATE}/ss_state"
EOF
    cat > "${WORK}/bin/kubectl" <<'EOF'
#!/bin/bash
args="$*"
args=${args#-n iff }
case "${args}" in
    "port-forward "*) exec sleep 600 3>&- ;;
esac
echo "kubectl ${args}" >> "${CALLS}"
case "${args}" in
    "get configmap shacl-validation-fingerprint --ignore-not-found -o json")
        [ ! -e "${STATE}/fp" ] || jq -n --arg f "$(cat "${STATE}/fp")" --arg j "$(cat "${STATE}/fp_job")" \
            '{data: {fingerprint: $f, job: $j}}' ;;
    "delete configmap shacl-validation-fingerprint --ignore-not-found")
        rm -f "${STATE}/fp" "${STATE}/fp_job" ;;
    "create configmap shacl-validation-fingerprint --from-literal=fingerprint="*)
        f=${args#*fingerprint=}; f=${f%% *}
        j=${args#*job=}; j=${j%% *}
        printf 'data:\n  fingerprint: %s\n  job: %s\n' "$f" "$j" ;;
    "apply -f -")
        [ -z "${STUB_APPLY_FAIL:-}" ] || exit 1
        y=$(cat)
        awk '/fingerprint:/ { print $2 }' <<<"$y" > "${STATE}/fp"
        awk '/job:/ { print $2 }' <<<"$y" > "${STATE}/fp_job" ;;
    "get beamsqlstatementset shacl-validation --ignore-not-found -o name")
        [ ! -e "${STATE}/ss_job" ] || echo "beamsqlstatementset.industry-fusion.com/shacl-validation" ;;
    "get beamsqlstatementset shacl-validation -o jsonpath={.status.state} {.status.job_id}")
        [ -e "${STATE}/ss_job" ] || exit 1
        echo "$(cat "${STATE}/ss_state") $(cat "${STATE}/ss_job")" ;;
    "get beamsqlstatementset shacl-validation -o jsonpath={.status.job_id}")
        cat "${STATE}/ss_job" ;;
    *) exit 1 ;;
esac
EOF
    cat > "${WORK}/bin/curl" <<'EOF'
#!/bin/bash
out=/dev/null
while [ $# -gt 0 ]; do
    case "$1" in
        -o) out=$2; shift ;;
        -w|-m|-X|-H|--data-binary) shift ;;
        http*) url=$1 ;;
    esac
    shift
done
path=/${url#http://*/}
answer() { printf '%s' "$2" > "${out}"; printf '%s' "$1"; }
case "${path}" in
    /config) answer 200 '{}' ;;
    /jobs/overview)
        tasks=5
        [ -z "${STUB_TASKS_DOWN:-}" ] || tasks=4
        answer 200 "$(printf '{"jobs":[{"jid":"%s","state":"RUNNING","tasks":{"running":%s,"total":5}}]}' \
            "$(cat "${STATE}/ss_job" 2>/dev/null)" "$tasks")" ;;
    *) answer 404 '{}' ;;
esac
EOF
    cat > "${WORK}/helm/helmfile" <<'EOF'
#!/bin/bash
echo "helmfile $*" >> "${CALLS}"
case "$*" in
    *" template") cat "${STATE}/render" ;;
    *" apply") ;;
    *) exit 1 ;;
esac
EOF
    cat > "${WORK}/bin/make" <<'EOF'
#!/bin/bash
echo "make $*" >> "${CALLS}"
EOF
    chmod +x "${WORK}/bin/"* "${WORK}/helm/helmfile" "${WORK}/sf/"*.sh
    export PATH="${WORK}/bin:${PATH}"

    # a deployed validation with the job ss-0 running with all its tasks
    echo "rendered release v1" > "${STATE}/render"
    local f
    for f in rdf ngsild shacl-constraints; do echo "INSERT ${f} 1" > "${WORK}/sf/output/${f}.postgres"; done
    echo ss-0 > "${STATE}/ss_job"
    echo RUNNING > "${STATE}/ss_state"
    export HELM_TOP="${WORK}/helm" OUTPUTDIR="${WORK}/sf/output" MAKE=make
    export VALIDATION_POLL=0.1 VALIDATION_CONNECT_TIMEOUT=2
}

teardown() {
    rm -rf "${WORK}"
}

calls() {
    grep -c -F -- "$1" "${CALLS}" || true
}

line() {
    local n
    n=$(grep -n -m1 -F -- "$1" "${CALLS}" | cut -d: -f1)
    echo "${n:-0}"
}

deploy() {
    run --separate-stderr bash "${WORK}/sf/deploy_validation.sh"
    echo "${output}"
    echo "${stderr}"
}

# keep_current: the kept fingerprint is the one of what would be deployed now,
# written for the job ss-0
keep_current() {
    deploy
    [ "$status" -eq 0 ]
    : > "${CALLS}"
    echo ss-0 > "${STATE}/ss_job"
    echo ss-0 > "${STATE}/fp_job"
}

fingerprint_of_run() {
    grep -o 'fingerprint of the validation to deploy: [0-9a-f]*' <<<"$1" | awk '{ print $NF }'
}

# ---------------------------------------------------------------- the fingerprint

@test "the fingerprint: the same rendering and tables give the same value" {
    deploy
    first=$(fingerprint_of_run "${output}")
    deploy
    [ "$(fingerprint_of_run "${output}")" = "${first}" ]
    [ ${#first} -eq 64 ]
}

@test "the fingerprint: one changed constraint row or one changed rendered value gives another" {
    deploy
    first=$(fingerprint_of_run "${output}")
    echo "INSERT shacl-constraints 2" > "${WORK}/sf/output/shacl-constraints.postgres"
    deploy
    second=$(fingerprint_of_run "${output}")
    [ "${second}" != "${first}" ]
    echo "rendered release v1, checkpoint interval changed" > "${STATE}/render"
    deploy
    [ "$(fingerprint_of_run "${output}")" != "${second}" ]
}

@test "the fingerprint is rendered by helmfile with the shacl release" {
    deploy
    [ "$(calls "helmfile -f helmfile-shacl.yaml template")" -ge 1 ]
}

# ---------------------------------------------------------------- unchanged

@test "unchanged: the same fingerprint for the running job keeps it and writes no table" {
    keep_current
    deploy
    [ "$status" -eq 0 ]
    [[ "${output}" == *"unchanged: the job ss-0 keeps running, no table is written"* ]]
    [ "$(calls "resync")" -eq 0 ]
    [ "$(calls "deploy-install")" -eq 0 ]
    [ "$(calls "submit-postgres-tables")" -eq 0 ]
    [ "$(calls "delete configmap")" -eq 0 ]
    [ "$(line "helmfile -f helmfile-shacl.yaml apply")" -gt 0 ]
    [ "$(line "make fuseki-deploy-kms")" -lt "$(line "make restart-connect")" ]
    [ "$(cat "${STATE}/ss_job")" = ss-0 ]
}

# ---------------------------------------------------------------- replace

@test "replace: a changed package deletes the fingerprint, resyncs with the install, then keeps the new one" {
    keep_current
    old=$(cat "${STATE}/fp")
    echo "INSERT shacl-constraints 2" > "${WORK}/sf/output/shacl-constraints.postgres"
    deploy
    [ "$status" -eq 0 ]
    [[ "${output}" == *"replace: the validation to deploy differs from the deployed one"* ]]
    [ "$(line "delete configmap shacl-validation-fingerprint")" -lt "$(line "resync REPLACE=package RESYNC_INSTALL=make deploy-install")" ]
    [ "$(line "resync REPLACE=package")" -lt "$(line "make fuseki-deploy-kms")" ]
    [ "$(line "make fuseki-deploy-kms")" -lt "$(line "apply -f -")" ]
    [ "$(cat "${STATE}/fp_job")" = ss-new ]
    [ "$(cat "${STATE}/fp")" != "${old}" ]
    [ "$(calls "make restart-connect")" -eq 0 ]
    [ "$(calls "helmfile -f helmfile-shacl.yaml apply")" -eq 0 ]
}

@test "replace: no fingerprint kept" {
    deploy
    [ "$status" -eq 0 ]
    [[ "${output}" == *"replace: no fingerprint is kept"* ]]
    [ "$(calls "resync REPLACE=package")" -eq 1 ]
}

@test "replace: a fingerprint kept for another job" {
    keep_current
    echo ss-other > "${STATE}/fp_job"
    deploy
    [ "$status" -eq 0 ]
    [[ "${output}" == *"replace: the kept fingerprint belongs to the job ss-other, not to the running ss-0"* ]]
    [ "$(calls "resync REPLACE=package")" -eq 1 ]
}

@test "replace: no statementset deployed" {
    keep_current
    rm -f "${STATE}/ss_job"
    deploy
    [ "$status" -eq 0 ]
    [[ "${output}" == *"replace: no validation job runs with all its tasks"* ]]
    [ "$(calls "resync REPLACE=package")" -eq 1 ]
}

@test "replace: a job that doesn't run with all its tasks" {
    keep_current
    export STUB_TASKS_DOWN=1
    deploy
    [ "$status" -eq 0 ]
    [[ "${output}" == *"replace: no validation job runs with all its tasks"* ]]
    [ "$(calls "resync REPLACE=package")" -eq 1 ]
}

@test "replace: a failed resync keeps no fingerprint and names the deploy" {
    keep_current
    echo "INSERT shacl-constraints 2" > "${WORK}/sf/output/shacl-constraints.postgres"
    export STUB_RESYNC_FAIL=1
    deploy
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"the resync with the new package failed"*"run make flink-deploy again"* ]]
    [ ! -e "${STATE}/fp" ]
    [ "$(calls "make fuseki-deploy-kms")" -eq 0 ]
}

@test "replace: after an interrupted replacement the same package replaces again" {
    keep_current
    echo "INSERT shacl-constraints 2" > "${WORK}/sf/output/shacl-constraints.postgres"
    export STUB_RESYNC_FAIL=1
    deploy
    [ "$status" -ne 0 ]
    unset STUB_RESYNC_FAIL
    : > "${CALLS}"
    deploy
    [ "$status" -eq 0 ]
    [[ "${output}" == *"replace: no fingerprint is kept"* ]]
    [ "$(calls "resync REPLACE=package")" -eq 1 ]
}

@test "a missing table file fails before anything is changed" {
    rm -f "${WORK}/sf/output/rdf.postgres"
    deploy
    [ "$status" -ne 0 ]
    [[ "${stderr}" == *"rdf.postgres is missing: run make helm first"* ]]
    [ "$(calls "resync")" -eq 0 ]
    [ "$(calls "delete configmap")" -eq 0 ]
}

# ---------------------------------------------------------------- the Makefile, read as text

rule_of() {  # rule_of <target>: its rule line and recipe
    awk -v t="$1:" '$1 == t { on = 1; print; next } on && /^\t/ { print; next } on { exit }' "${SRC}/Makefile"
}

@test "make helm writes no table" {
    run rule_of helm
    [[ "${output}" == *"helm: build"* ]]
    [[ "${output}" != *"submit-postgres-tables"* ]]
}

@test "the install writes the tables, then syncs the release, not applies it" {
    run rule_of deploy-install
    [[ "${output}" == *"make submit-postgres-tables"* ]]
    [[ "${output}" == *"helmfile-shacl.yaml sync"* ]]
    [[ "${output}" != *"helmfile-shacl.yaml apply"* ]]
}

@test "flink-deploy decides with deploy_validation.sh, and flink-undeploy deletes the fingerprint" {
    run rule_of flink-deploy
    [[ "${output}" == *"./deploy_validation.sh"* ]]
    run rule_of flink-undeploy
    [[ "${output}" == *"delete configmap shacl-validation-fingerprint"* ]]
}
