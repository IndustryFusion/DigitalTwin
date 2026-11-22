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
#
# With VALIDATION_DEPLOYED=true (shacl2flink's test-flink-e2e runs it while its
# validation is deployed) the statementset must exist, and the watchdog must
# have read the reset from Flink and found a complete refresh of both
# connectors; without it the test follows what the platform has.

DEBUG=${DEBUG:-false}
VALIDATION_DEPLOYED=${VALIDATION_DEPLOYED:-false}
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

run_watchdog() {
    kubectl -n "${NAMESPACE}" delete job "${JOB}" --ignore-not-found
    kubectl -n "${NAMESPACE}" create job "${JOB}" --from=cronjob/platform-watchdog
    kubectl -n "${NAMESPACE}" wait --for=condition=complete "job/${JOB}" --timeout=300s
}

@test "the platform watchdog judges the validation state and the connectors of the installed platform" {
    $SKIP
    run_watchdog
    run kubectl -n "${NAMESPACE}" logs "job/${JOB}"
    echo "${output}"
    [[ "${output}" =~ \[(normal|warning)\]\ shacl-validation/ValidationConsistency ]]
    [[ "${output}" != *"[critical] shacl-validation/ValidationConsistency"* ]]
    [[ "${output}" == *"entity-table-connector/ConnectorState: "* ]]
    [[ "${output}" == *"rdf-table-connector/ConnectorState: "* ]]
    # the Connect pods of the installed platform run, and the replaced check's alert is closed
    [[ "${output}" == *"[normal] kafka-connect/ConnectPods: running"* || "${output}" == *"[normal] kafka-connect/ConnectPods: starting"* ]]
    [[ "${output}" == *"[normal] kafka-connect/ResyncRecency: replaced"* ]]
    observing=$(kubectl -n "${NAMESPACE}" get configmap platform-watchdog-state -o jsonpath='{.data.observing_since}')
    [ -n "${observing}" ]
    if [ "${VALIDATION_DEPLOYED}" = true ] || kubectl -n "${NAMESPACE}" get beamsqlstatementsets shacl-validation >/dev/null 2>&1; then
        kubectl -n "${NAMESPACE}" get beamsqlstatementsets shacl-validation
        # With the validation deployed, the watchdog read the reset from
        # Flink (a wrong Flink host or JobManager selector leaves it unset),
        # and the Connect log of the installed platform holds a complete
        # snapshot of both connectors, so it found one of each: this fails
        # when the Debezium log lines or their connector context change.
        state=$(kubectl -n "${NAMESPACE}" get configmap platform-watchdog-state -o json)
        jq -e '.data.reset | tonumber > 0' <<<"${state}"
        [[ "${output}" != *"[warning] shacl-validation/ValidationConsistency: unknown"* ]]
        # The refreshes must come from the log of the running Connect pod,
        # which snapshots both connectors when it starts: keys an earlier
        # pod's log left in the state don't count. A pod restarted just
        # before has its snapshot still running, so the watchdog runs again.
        connect_start=$(kubectl -n "${NAMESPACE}" get pods -l app.kubernetes.io/instance=kafka-connect \
            -o jsonpath='{.items[0].status.containerStatuses[0].state.running.startedAt}')
        since=$(date -u -d "${connect_start}" +%s)
        for _ in $(seq 1 10); do
            state=$(kubectl -n "${NAMESPACE}" get configmap platform-watchdog-state -o json)
            jq -e --argjson since "${since}" \
                '.data | ((."entity-table-connector.done" // "0") | tonumber) >= $since and ((."rdf-table-connector.done" // "0") | tonumber) >= $since' \
                <<<"${state}" >/dev/null && break
            sleep 30
            run_watchdog
        done
        echo "Connect pod started ${connect_start}; state: $(jq -c '.data' <<<"${state}")"
        jq -e --argjson since "${since}" \
            '.data | ((."entity-table-connector.done" // "0") | tonumber) >= $since and ((."rdf-table-connector.done" // "0") | tonumber) >= $since' \
            <<<"${state}"
    else
        # Without it there is no job to judge against: the watchdog says so.
        [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: unknown"* ]]
    fi
    key=$(get_alerta_api_key)
    total=$(curl -s -H "Authorization: Key ${key}" "${ALERTA_URL}/api/alerts?event=ValidationConsistency&resource=shacl-validation" | jq '.total')
    [ "${total}" -ge 1 ]
    severity=$(curl -s -H "Authorization: Key ${key}" "${ALERTA_URL}/api/alerts?event=ConnectPods&resource=kafka-connect" | jq -r '.alerts[0].severity')
    [ "${severity}" = "normal" ]
}
