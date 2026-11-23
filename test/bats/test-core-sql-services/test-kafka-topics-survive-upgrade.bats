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
# Upgrading sql-core and kafka-bridges on the installed platform keeps every
# KafkaTopic they own (the same uid: not deleted and recreated), and a changed
# topic config reaches the existing topic (#1038). A topic the charts rendered
# only while missing dropped out of the manifest of the first upgrade after
# the install, and helm and Strimzi deleted it. The releases are upgraded with
# their own values (--reuse-values) from the charts in this checkout, twice,
# because a topic rendered only while missing came back on every second
# upgrade. Only bash, awk, jq, kubectl and helm: the runner's python has no
# YAML module.

DEBUG=${DEBUG:-false}
SKIP=
NAMESPACE=iff
CHARTS=../../helm/charts
SQL_CORE_TOPICS="iff.alerts iff.alerts.bulk iff.ngsild-updates iff.ngsild.attributes-insert"
BRIDGES_TOPICS="iff.ngsild.public.entity iff.ngsild.attributes iff.ngsild.entities"
CHANGED_TOPIC=iff.ngsild-updates
CHANGED_VALUE=kafkaBridge.ngsildUpdates.listenTopicRetention
RETENTION_FILE=/tmp/kafka-topics-survive-upgrade-retention

# The KafkaTopic names of a helm manifest on stdin, one per line.
manifest_kafkatopics() {
    awk '
        function flush() { if (kafkatopic && name != "") print name; kafkatopic = 0; name = "" }
        /^---/ { flush(); next }
        /^kind: KafkaTopic[[:space:]]*$/ { kafkatopic = 1 }
        /^  name: / { if (name == "") { name = $2; gsub(/["\047]/, "", name) } }
        END { flush() }'
}

# The names of the KafkaTopics in `kubectl get kafkatopic -o json` on stdin
# whose helm release annotation is $1, one per line.
owned_kafkatopics() {
    jq -r --arg release "$1" \
        '.items[] | select(.metadata.annotations["meta.helm.sh/release-name"] == $release) | .metadata.name'
}

# A release's KafkaTopics, sorted on one line: those of its stored manifest,
# and those the cluster says it owns.
manifest_topics() {
    helm -n "${NAMESPACE}" get manifest "$1" | manifest_kafkatopics | sort | xargs
}

owned_topics() {
    kubectl -n "${NAMESPACE}" get kafkatopic -o json | owned_kafkatopics "$1" | sort | xargs
}

sorted() {
    tr ' ' '\n' <<<"$1" | sort | xargs
}

# What changes when the KafkaTopic is recreated: its uid and creation time,
# and the Kafka topic ID where this Strimzi reports one.
identity() {
    kubectl -n "${NAMESPACE}" get kafkatopic "$1" -o \
        jsonpath='{.metadata.uid} {.metadata.creationTimestamp} {.status.topicId}'
}

# Whether two identities are the same KafkaTopic: the same uid and creation
# time, both set, and the same topic ID when both report one.
same_topic() {
    read -r uid1 created1 id1 <<<"$1"
    read -r uid2 created2 id2 <<<"$2"
    [ -n "${uid1}" ] && [ -n "${created1}" ] || return 1
    [ "${uid1}" = "${uid2}" ] && [ "${created1}" = "${created2}" ] || return 1
    [ -z "${id1}" ] || [ -z "${id2}" ] || [ "${id1}" = "${id2}" ]
}

# Waits until Strimzi has reconciled the topic's current spec.
wait_reconciled() {
    for _ in $(seq 1 60); do
        state=$(kubectl -n "${NAMESPACE}" get kafkatopic "$1" -o \
            jsonpath='{.metadata.generation} {.status.observedGeneration} {.status.conditions[?(@.type=="Ready")].status}')
        read -r generation observed ready <<<"${state}"
        if [ "${generation}" = "${observed}" ] && [ "${ready}" = "True" ]; then
            return 0
        fi
        sleep 2
    done
    echo "KafkaTopic $1 not reconciled: ${state}"
    return 1
}

upgrade() {
    helm -n "${NAMESPACE}" upgrade "$1" "${CHARTS}/$1" --reuse-values "${@:2}"
}

teardown_file() {
    # puts the changed retention back, if a test changed it
    if [ -s "${RETENTION_FILE}" ]; then
        upgrade sql-core --set-string "${CHANGED_VALUE}=$(cat "${RETENTION_FILE}")" || true
        rm -f "${RETENTION_FILE}"
    fi
}

@test "every topic of sql-core and kafka-bridges is declared by exactly its owning release" {
    $SKIP
    for release in sql-core kafka-bridges; do
        if [ "${release}" = sql-core ]; then
            expected=$(sorted "${SQL_CORE_TOPICS}")
        else
            expected=$(sorted "${BRIDGES_TOPICS}")
        fi
        declared=$(manifest_topics "${release}")
        owned=$(owned_topics "${release}")
        echo "${release}: declares '${declared}', owns '${owned}', expected '${expected}'"
        [ "${declared}" = "${expected}" ] || return 1
        [ "${owned}" = "${expected}" ] || return 1
    done
    for topic in ${SQL_CORE_TOPICS} ${BRIDGES_TOPICS}; do
        policy=$(kubectl -n "${NAMESPACE}" get kafkatopic "${topic}" -o jsonpath='{.metadata.annotations.helm\.sh/resource-policy}')
        echo "${topic}: resource-policy '${policy}'"
        [ "${policy}" = "keep" ] || return 1
    done
}

@test "upgrading sql-core and kafka-bridges twice keeps every KafkaTopic, not a new one" {
    $SKIP
    declare -A before
    for topic in ${SQL_CORE_TOPICS} ${BRIDGES_TOPICS}; do
        wait_reconciled "${topic}" || return 1
        before[${topic}]=$(identity "${topic}")
        echo "${topic}: ${before[${topic}]}"
        # has a uid and a creation time: same_topic refuses empty ones
        same_topic "${before[${topic}]}" "${before[${topic}]}" || return 1
    done
    for round in 1 2; do
        upgrade kafka-bridges
        upgrade sql-core
        for topic in ${SQL_CORE_TOPICS} ${BRIDGES_TOPICS}; do
            deleting=$(kubectl -n "${NAMESPACE}" get kafkatopic "${topic}" -o jsonpath='{.metadata.deletionTimestamp}')
            if [ -n "${deleting}" ]; then
                echo "round ${round}: ${topic} is being deleted"
                return 1
            fi
            wait_reconciled "${topic}" || return 1
            after=$(identity "${topic}")
            echo "round ${round}: ${topic}: ${after}"
            # the same uid and creation time, and topic ID where one is reported
            same_topic "${before[${topic}]}" "${after}" || return 1
        done
    done
    [ "$(manifest_topics sql-core)" = "$(sorted "${SQL_CORE_TOPICS}")" ]
    [ "$(manifest_topics kafka-bridges)" = "$(sorted "${BRIDGES_TOPICS}")" ]
}

@test "a topic config changed in the chart values reaches the existing topic on upgrade" {
    $SKIP
    id=$(identity "${CHANGED_TOPIC}")
    same_topic "${id}" "${id}"
    retention=$(kubectl -n "${NAMESPACE}" get kafkatopic "${CHANGED_TOPIC}" -o jsonpath='{.spec.config.retention\.ms}')
    [ -n "${retention}" ]
    echo "${retention}" > "${RETENTION_FILE}"
    changed=$((retention + 1))
    upgrade sql-core --set-string "${CHANGED_VALUE}=${changed}"
    wait_reconciled "${CHANGED_TOPIC}"
    run kubectl -n "${NAMESPACE}" get kafkatopic "${CHANGED_TOPIC}" -o \
        jsonpath='{.spec.config.retention\.ms} {.spec.config.segment\.ms}'
    echo "${output}"
    [ "${output}" = "${changed} $((changed > 3600000 ? changed : 3600000))" ]
    same_topic "${id}" "$(identity "${CHANGED_TOPIC}")"

    upgrade sql-core --set-string "${CHANGED_VALUE}=${retention}"
    rm -f "${RETENTION_FILE}"
    wait_reconciled "${CHANGED_TOPIC}"
    [ "$(kubectl -n "${NAMESPACE}" get kafkatopic "${CHANGED_TOPIC}" -o jsonpath='{.spec.config.retention\.ms}')" = "${retention}" ]
    same_topic "${id}" "$(identity "${CHANGED_TOPIC}")"
}
