#!/bin/bash
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
# Refuses to go on when uninstalling a release would delete one of the topics.
#
#   check-release-keeps-topics.sh <namespace> <release> <topic>...
#
# helm uninstall deletes every resource of the release's stored manifest
# unless that manifest gives it helm.sh/resource-policy: keep; the annotation
# on the live object doesn't count. A shacl release deployed before #1038
# declares iff.ngsild.entities without keep, so destroying it deletes the
# platform's entity topic even after adopt-kafka-topics.sh handed it to
# kafka-bridges, and Strimzi deletes the topic in Kafka. Exits 1 naming the
# topics and what to do; exits 0 when the release is not installed or keeps
# or doesn't declare every topic.
set -euo pipefail

NAMESPACE=${1:?usage: $0 <namespace> <release> <topic>...}
RELEASE=${2:?usage: $0 <namespace> <release> <topic>...}
shift 2

if ! manifest=$(helm -n "${NAMESPACE}" get manifest "${RELEASE}" 2>&1); then
    if [[ "${manifest}" == *"not found"* ]]; then
        echo "Release ${RELEASE} is not installed"
        exit 0
    fi
    echo "Cannot read the manifest of release ${RELEASE}: ${manifest}" >&2
    exit 1
fi

# The KafkaTopics of the manifest that helm uninstall would delete.
deleted=$(awk '
    function flush() {
        if (kafkatopic && name != "" && !keep) print name
        kafkatopic = 0; name = ""; keep = 0
    }
    /^---/ { flush(); next }
    /^kind: KafkaTopic[[:space:]]*$/ { kafkatopic = 1 }
    /^  name: / { if (name == "") { name = $2; gsub(/["\047]/, "", name) } }
    /^    helm\.sh\/resource-policy: ["\047]?keep["\047]?[[:space:]]*$/ { keep = 1 }
    END { flush() }
' <<<"${manifest}")

refused=()
for topic in "$@"; do
    if grep -qx "${topic}" <<<"${deleted}"; then
        refused+=("${topic}")
    fi
done
if [ "${#refused[@]}" -gt 0 ]; then
    echo "Uninstalling ${RELEASE} would delete KafkaTopic ${refused[*]}: its stored manifest" >&2
    echo "declares it without helm.sh/resource-policy: keep. Upgrade ${RELEASE} to the" >&2
    echo "current chart first (for the validation: make flink-deploy), then uninstall it." >&2
    exit 1
fi
echo "Uninstalling ${RELEASE} deletes none of: $*"
