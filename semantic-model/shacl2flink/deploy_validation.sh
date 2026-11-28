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
# Deploys the built validation (`make flink-deploy`, after `make helm`), fresh
# or over a running one (#1165, specification shacl2flink/validation-deployment).
#
# The fingerprint of what would be deployed -- the shacl release as helmfile
# renders it, with the deploy's values, and the three .postgres files -- is
# compared with the one kept in the ConfigMap shacl-validation-fingerprint,
# together with the job it was written for:
#
#   unchanged   the same fingerprint, kept for the job that runs with all its
#               tasks: no table is written and the job is kept. The chart is
#               applied (no diff), the Fuseki graphs deployed, and Kafka
#               Connect restarted once the job reads (restart_connect.sh).
#   replace     anything else: the fingerprint is deleted, and the resync
#               replaces the validation by the new package (REPLACE=package,
#               whose install is `make deploy-install`: the tables and
#               `helmfile sync`). Then the Fuseki graphs, then the fingerprint
#               with the new job.
#
# The fingerprint is not an annotation of the statementset: the operator
# takes every change of it as an update and resubmits the job.
#
# Environment:
#   NAMESPACE                    iff
#   FINGERPRINT_CONFIGMAP        shacl-validation-fingerprint
#   OUTPUTDIR                    output (the build's output)
#   HELM_TOP                     ../../helm (where helmfile and helmfile-shacl.yaml are)
#   HELMFILE                     ./helmfile, relative to HELM_TOP
#   MAKE                         make
#   VALIDATION_CONNECT_TIMEOUT   30   a port-forward answering
#   VALIDATION_POLL              5
#   VALIDATION_KUBECTL_TIMEOUT   120  one kubectl call

set -euo pipefail
umask 077

# shellcheck disable=SC2034  # read in validation_job.sh
NAMESPACE=${NAMESPACE:-iff}
STATEMENTSET=${STATEMENTSET:-shacl-validation}
FINGERPRINT_CONFIGMAP=${FINGERPRINT_CONFIGMAP:-shacl-validation-fingerprint}
OUTPUTDIR=${OUTPUTDIR:-output}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HELM_TOP=${HELM_TOP:-${HERE}/../../helm}
HELMFILE=${HELMFILE:-./helmfile}
MAKE=${MAKE:-make}
# shellcheck disable=SC2034
CONNECT_TIMEOUT=${VALIDATION_CONNECT_TIMEOUT:-30}
# shellcheck disable=SC2034
POLL=${VALIDATION_POLL:-5}
# shellcheck disable=SC2034
KUBECTL_TIMEOUT=${VALIDATION_KUBECTL_TIMEOUT:-120}
POSTGRES_FILES="rdf.postgres ngsild.postgres shacl-constraints.postgres"

WORK=$(mktemp -d)
# shellcheck disable=SC1091
. "${HERE}/validation_job.sh"
trap cleanup_work EXIT

fail() {
    echo "deploy failed: $*" >&2
    exit 1
}

# fingerprint: the SHA-256 of the rendered release and the tables, in a
# fixed order
fingerprint() {
    local f
    (cd "$HELM_TOP" && "$HELMFILE" -f helmfile-shacl.yaml template) > "${WORK}/render" 2> "${WORK}/render.err" \
        || fail "the shacl release can't be rendered: $(tail -3 "${WORK}/render.err" | tr '\n' ' ')"
    for f in $POSTGRES_FILES; do
        [ -f "${OUTPUTDIR}/${f}" ] || fail "${OUTPUTDIR}/${f} is missing: run make helm first"
        { echo "== ${f}"; cat "${OUTPUTDIR}/${f}"; } >> "${WORK}/render"
    done
    sha256sum "${WORK}/render" | cut -d' ' -f1
}

NEW=$(fingerprint)
kept=$(kube get configmap "$FINGERPRINT_CONFIGMAP" --ignore-not-found -o json) \
    || fail "the ConfigMap ${FINGERPRINT_CONFIGMAP} can't be read"
[ -n "$kept" ] || kept='{}'
KEPT=$(jq -r '.data.fingerprint // empty' <<<"$kept")
KEPT_JOB=$(jq -r '.data.job // empty' <<<"$kept")

running=""
if [ -n "$(kube get beamsqlstatementset "$STATEMENTSET" --ignore-not-found -o name)" ] \
        && validation_running "" > "${WORK}/running"; then
    running=$(cat "${WORK}/ss_job")
fi

echo "fingerprint of the validation to deploy: ${NEW}"
echo "kept: ${KEPT:-none}${KEPT_JOB:+ for the job ${KEPT_JOB}}; running: ${running:-no job with all its tasks}"

if [ -n "$KEPT" ] && [ "$KEPT" = "$NEW" ] && [ -n "$running" ] && [ "$KEPT_JOB" = "$running" ]; then
    echo "unchanged: the job ${running} keeps running, no table is written"
    (cd "$HELM_TOP" && "$HELMFILE" -f helmfile-shacl.yaml apply) || fail "the shacl release can't be applied"
    "$MAKE" fuseki-deploy-kms || fail "the Fuseki graphs can't be deployed"
    "$MAKE" restart-connect || fail "Kafka Connect not restarted"
    exit 0
fi

if [ -z "$KEPT" ]; then
    echo "replace: no fingerprint is kept"
elif [ "$KEPT" != "$NEW" ]; then
    echo "replace: the validation to deploy differs from the deployed one"
elif [ -z "$running" ]; then
    echo "replace: no validation job runs with all its tasks"
else
    echo "replace: the kept fingerprint belongs to the job ${KEPT_JOB}, not to the running ${running}"
fi
# None is left that a failed or interrupted replacement could be taken for.
kube delete configmap "$FINGERPRINT_CONFIGMAP" --ignore-not-found >/dev/null \
    || fail "the ConfigMap ${FINGERPRINT_CONFIGMAP} can't be deleted"
NAMESPACE=$NAMESPACE REPLACE=package RESYNC_INSTALL="${MAKE} deploy-install" "${HERE}/shacl_resync.sh" \
    || fail "the resync with the new package failed; after removing its cause, run make flink-deploy again"
"$MAKE" fuseki-deploy-kms || fail "the Fuseki graphs can't be deployed"
job=$(kube get beamsqlstatementset "$STATEMENTSET" -o jsonpath='{.status.job_id}') \
    || fail "the statementset ${STATEMENTSET} can't be read"
[ -n "$job" ] || fail "the statementset ${STATEMENTSET} reports no job"
kube create configmap "$FINGERPRINT_CONFIGMAP" --from-literal=fingerprint="$NEW" --from-literal=job="$job" \
    --dry-run=client -o yaml | kube apply -f - >/dev/null \
    || fail "the fingerprint can't be written to the ConfigMap ${FINGERPRINT_CONFIGMAP}"
echo "the validation is replaced: the job ${job} runs the new package; its fingerprint is kept"
