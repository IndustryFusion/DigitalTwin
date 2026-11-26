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
#
# Restarts Kafka Connect after a deployment of the validation (`make
# flink-deploy`), so that Debezium publishes every existing entity again, and
# waits first until the deployed validation reads what is published. The job
# reads entities and attributes from the latest offset: what is published
# before its readers hold their partitions is never validated, until the next
# regular re-snapshot.
#
# It waits until
#   the operator has taken over the deployed statementset: right after a
#     deployment over a running validation, the statementset still reports
#     RUNNING with the job that is about to be replaced;
#   the statementset reports RUNNING, and its job runs with all its tasks;
#   the job's readers of the entities and attributes hold their partitions.
#
# When that is not reached in time it exits with a non-zero status, says what
# is missing, and does not restart Kafka Connect.
#
# Environment (time limits in seconds):
#   NAMESPACE                   iff
#   VALIDATION_START_TIMEOUT    1800  the validation running and reading
#   VALIDATION_CONNECT_TIMEOUT  30    a port-forward answering
#   VALIDATION_POLL             5     pause between two checks
#   VALIDATION_KUBECTL_TIMEOUT  120   one kubectl call

set -euo pipefail
umask 077

# shellcheck disable=SC2034  # all read in validation_job.sh
NAMESPACE=${NAMESPACE:-iff}
STATEMENTSET=${STATEMENTSET:-shacl-validation}
START_TIMEOUT=${VALIDATION_START_TIMEOUT:-1800}
# shellcheck disable=SC2034
CONNECT_TIMEOUT=${VALIDATION_CONNECT_TIMEOUT:-30}
# shellcheck disable=SC2034
POLL=${VALIDATION_POLL:-5}
# shellcheck disable=SC2034
KUBECTL_TIMEOUT=${VALIDATION_KUBECTL_TIMEOUT:-120}

WORK=$(mktemp -d)
# shellcheck disable=SC1091
. "$(dirname "${BASH_SOURCE[0]}")/validation_job.sh"
trap cleanup_work EXIT

fail() {
    echo "Kafka Connect not restarted: $*. Check the statementset ${STATEMENTSET} and its job, then run make restart-connect; until then the existing entities are not validated." >&2
    exit 1
}

# The operator (kopf) keeps the configuration it last handled in an annotation
# and writes it together with the state that follows from it.
statementset_taken_over() {
    local ss
    ss=$(kube get beamsqlstatementset "$STATEMENTSET" -o json 2>/dev/null) \
        || { echo "the statementset can't be read"; return 1; }
    jq -e '.spec == (.metadata.annotations["kopf.zalando.org/last-handled-configuration"] // "{}" | fromjson | .spec)' \
        <<<"$ss" >/dev/null 2>&1 \
        || { echo "the operator has not taken over the deployed statementset yet, it reports $(jq -r '.status.state // "no state"' <<<"$ss" 2>/dev/null)"; return 1; }
}

validation_reading() {
    statementset_taken_over || return 1
    validation_running "" || return 1
    sources_placed "$(cat "${WORK}/ss_job")"
}

deployed=$(kube get beamsqlstatementset "$STATEMENTSET" --ignore-not-found -o name) \
    || fail "the statementset ${STATEMENTSET} can't be read"
[ -n "$deployed" ] || fail "no validation statementset ${STATEMENTSET} is deployed in ${NAMESPACE}"
echo "waiting until the validation runs and reads ${LATEST_SOURCES// /, } (at most ${START_TIMEOUT}s)"
wait_until "$START_TIMEOUT" "the ${STATEMENTSET} job running and reading" validation_reading
echo "the job $(cat "${WORK}/ss_job") reads; restarting Kafka Connect"
kube delete pod -l app.kubernetes.io/instance=kafka-connect --wait=false \
    || fail "the Connect pods can't be deleted"
