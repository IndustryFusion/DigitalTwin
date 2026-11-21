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
# The platform watchdog as deployed: one run of its CronJob on the installed
# platform judges the validation state from the Connect log and Flink, reads
# the KafkaConnectors, keeps its findings in its ConfigMap and posts to
# Alerta. A freshly installed platform is consistent or still rebuilding,
# never inconsistent. The scenarios themselves are in test/bats-unit.

DEBUG=${DEBUG:-false}
SKIP=
NAMESPACE=iff
ALERTA_URL=http://alerta.local
JOB=platform-watchdog-e2e

get_alerta_api_key() {
    kubectl -n "${NAMESPACE}" get secret alerta -o jsonpath='{.data.alerta-admin-key}' | base64 -d
}

# The scheduled runs are suspended while the test runs its own: two runs at
# once would patch the watchdog's ConfigMap over each other.
setup_file() {
    kubectl -n "${NAMESPACE}" patch cronjob platform-watchdog -p '{"spec":{"suspend":true}}'
    for _ in $(seq 1 90); do
        [ -z "$(kubectl -n "${NAMESPACE}" get cronjob platform-watchdog -o jsonpath='{.status.active}')" ] && break
        sleep 2
    done
}

teardown_file() {
    kubectl -n "${NAMESPACE}" delete job "${JOB}" --ignore-not-found
    kubectl -n "${NAMESPACE}" patch cronjob platform-watchdog -p '{"spec":{"suspend":false}}'
}

@test "the platform watchdog judges the validation state and the connectors of the installed platform" {
    $SKIP
    kubectl -n "${NAMESPACE}" delete job "${JOB}" --ignore-not-found
    kubectl -n "${NAMESPACE}" create job "${JOB}" --from=cronjob/platform-watchdog
    kubectl -n "${NAMESPACE}" wait --for=condition=complete "job/${JOB}" --timeout=300s
    run kubectl -n "${NAMESPACE}" logs "job/${JOB}"
    echo "${output}"
    [[ "${output}" =~ \[(normal|warning)\]\ shacl-validation/ValidationConsistency ]]
    [[ "${output}" != *"[critical] shacl-validation/ValidationConsistency"* ]]
    [[ "${output}" == *"entity-table-connector/ConnectorState: "* ]]
    [[ "${output}" == *"rdf-table-connector/ConnectorState: "* ]]
    observing=$(kubectl -n "${NAMESPACE}" get configmap platform-watchdog-state -o jsonpath='{.data.observing_since}')
    [ -n "${observing}" ]
    if kubectl -n "${NAMESPACE}" get beamsqlstatementsets shacl-validation >/dev/null 2>&1; then
        # With the validation deployed, the Connect log of the installed
        # platform holds a complete snapshot of both connectors, so the
        # watchdog must have found one of each: this fails when the Debezium
        # log lines or their connector context change.
        state=$(kubectl -n "${NAMESPACE}" get configmap platform-watchdog-state -o json)
        jq -e '.data | has("entity-table-connector.done") and has("rdf-table-connector.done")' <<<"${state}"
    else
        # Without it there is no job to judge against: the watchdog says so.
        [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: unknown"* ]]
    fi
    key=$(get_alerta_api_key)
    total=$(curl -s -H "Authorization: Key ${key}" "${ALERTA_URL}/api/alerts?event=ValidationConsistency&resource=shacl-validation" | jq '.total')
    [ "${total}" -ge 1 ]
}
