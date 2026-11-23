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
# Hands existing KafkaTopics to the release that owns them now, before that
# release or their former owner is upgraded.
#
#   adopt-kafka-topics.sh <namespace> <release> <topic>...
#
# The charts rendered several topics only while missing, so on an installed
# platform a topic may be owned by its former owner (iff.ngsild.attributes by
# sql-core, iff.ngsild.entities by the shacl release), or by no release at all
# when an upgrade dropped it from the manifest while the KafkaTopic stayed.
# Helm refuses to upgrade a release with a resource another release or nobody
# owns, and the former owner's upgrade deletes the topic when it leaves its
# manifest. This script writes the owner into the release annotations, which
# lets helm adopt the topic, and sets helm.sh/resource-policy: keep, which
# stops the former owner's upgrade from deleting it. It changes nothing on a
# fresh install or a second run, and leaves a KafkaTopic that is being
# deleted alone. helmfile runs it before syncing sql-core, kafka-bridges and
# shacl (presync hooks in helmfile.yaml and helmfile-shacl.yaml).
set -euo pipefail

NAMESPACE=${1:?usage: $0 <namespace> <release> <topic>...}
RELEASE=${2:?usage: $0 <namespace> <release> <topic>...}
shift 2

for topic in "$@"; do
    # name|owning release|resource policy|deletion time, empty when there is
    # no such topic
    meta=$(kubectl -n "${NAMESPACE}" get kafkatopic "${topic}" --ignore-not-found -o \
        jsonpath='{.metadata.name}|{.metadata.annotations.meta\.helm\.sh/release-name}|{.metadata.annotations.helm\.sh/resource-policy}|{.metadata.deletionTimestamp}')
    if [ -z "${meta}" ]; then
        echo "KafkaTopic ${topic}: not there, ${RELEASE} creates it"
        continue
    fi
    owner=$(cut -d'|' -f2 <<<"${meta}")
    policy=$(cut -d'|' -f3 <<<"${meta}")
    if [ -n "$(cut -d'|' -f4 <<<"${meta}")" ]; then
        echo "KafkaTopic ${topic}: being deleted, left alone"
        continue
    fi
    if [ "${owner}" = "${RELEASE}" ] && [ "${policy}" = "keep" ]; then
        echo "KafkaTopic ${topic}: owned by ${RELEASE}"
        continue
    fi
    echo "KafkaTopic ${topic}: owned by '${owner}', handing it to ${RELEASE}"
    kubectl -n "${NAMESPACE}" annotate --overwrite kafkatopic "${topic}" \
        "meta.helm.sh/release-name=${RELEASE}" \
        "meta.helm.sh/release-namespace=${NAMESPACE}" \
        "helm.sh/resource-policy=keep"
    kubectl -n "${NAMESPACE}" label --overwrite kafkatopic "${topic}" \
        "app.kubernetes.io/managed-by=Helm"
done
