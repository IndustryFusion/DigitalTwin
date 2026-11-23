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
# An upgrade of sql-core or kafka-bridges keeps every KafkaTopic (#1038). A
# topic rendered only while missing (a `lookup` guard) is in the manifest of
# the install but not of the next upgrade; helm deletes what drops out of a
# release's manifest, and Strimzi then deletes the topic in Kafka. So every
# topic is rendered always, carries helm.sh/resource-policy: keep, and has one
# owning release. `helm template` has no cluster, so `lookup` finds nothing
# here: the guard is checked in the templates, the rendering for the rest.
# adopt-kafka-topics.sh runs against a mocked kubectl and
# check-release-keeps-topics.sh against a mocked helm. The upgrade itself is
# test/bats/test-core-sql-services/test-kafka-topics-survive-upgrade.bats.

bats_require_minimum_version 1.5.0

HELM_DIR="${BATS_TEST_DIRNAME}/../../helm"
CHARTS="${HELM_DIR}/charts"

setup() {
    WORK="$(mktemp -d)"
    export WORK
}

teardown() {
    rm -rf "${WORK}"
}

@test "no chart renders a KafkaTopic only while it is missing" {
    run grep -ln 'lookup "kafka.strimzi.io/[^"]*" "KafkaTopic"' -r "${CHARTS}"
    echo "${output}"
    [ "${status}" -eq 1 ]
}

# Renders the topic templates of the platform charts into ${WORK}/<chart>.yaml,
# with the values files given as arguments on top.
render_topics() {
    cat > "${WORK}/values.yaml" <<'EOF'
kafka:
  name: my-cluster
aaio:
  enabled: true
kafkaBridge:
  alerta:
    bulkTopic: iff.alerts.bulk
    bulkTopicRetention: "300000"
    listenTopic: iff.alerts
    listenTopicRetention: "3600000"
  ngsildUpdates:
    listenTopic: iff.ngsild-updates
    listenTopicRetention: "3600000"
  debezium:
    listenTopic: iff.ngsild.public.entity
    listenTopicRetention: "3600000"
    listenTopicCompression: uncompressed
    attributesTopic: iff.ngsild.attributes
    entitiesTopic: iff.ngsild.entities
    entityTopicRetention: "3600000"
    attributesTopicRetention: "3600000"
    attributesTopicCompression: uncompressed
kafka_topic_vars:
  ENTITY_TOPIC: scorpio.entity
  REGISTRY_TOPIC: scorpio.registry
  TEMPORAL_TOPIC: scorpio.temporal
  INTERNAL_NOTIFY_TOPIC: scorpio.inotify
  INTERNAL_REGISTRYSUB_TOPIC: scorpio.regsub
  SUB_ALIVE_TOPIC: scorpio.sub.alive
  SUB_SYNC_TOPIC: scorpio.sub.sync
  REGISTRYSUB_ALIVE_TOPIC: scorpio.regsub.alive
  REGISTRYSUB_SYNC_TOPIC: scorpio.regsub.sync
  retention: 3600000
EOF
    overrides=()
    for values in "$@"; do
        overrides+=(-f "${values}")
    done
    for chart in sql-core:core-kafka-topics.yaml kafka-bridges:bridge-topics.yaml \
                 scorpio:scorpio-aaio-topics.yaml; do
        name=${chart%%:*}
        mkdir -p "${WORK}/${name}/templates"
        printf 'apiVersion: v2\nname: %s\nversion: 0.1.0\n' "${name}" > "${WORK}/${name}/Chart.yaml"
        cp "${CHARTS}/${name}/templates/${chart#*:}" "${WORK}/${name}/templates/"
        helm template "${name}" "${WORK}/${name}" -f "${WORK}/values.yaml" "${overrides[@]}" > "${WORK}/${name}.yaml"
    done
}

@test "sql-core and kafka-bridges render every topic with resource-policy keep, each in one chart" {
    command -v helm >/dev/null || skip "helm is not installed"
    render_topics
    run python3 - "${WORK}" <<'EOF'
import sys, yaml
work = sys.argv[1]
owners = {}
for chart in ('sql-core', 'kafka-bridges', 'scorpio'):
    for doc in yaml.safe_load_all(open(f'{work}/{chart}.yaml')):
        if not doc or doc['kind'] != 'KafkaTopic':
            continue
        name = doc['spec'].get('topicName', doc['metadata']['name'])
        assert name not in owners, f'{name} is declared by {owners[name]} and {chart}'
        owners[name] = chart
        if chart != 'scorpio':
            policy = (doc['metadata'].get('annotations') or {}).get('helm.sh/resource-policy')
            assert policy == 'keep', f'{chart} {name}: helm.sh/resource-policy {policy!r}'
platform = {k: v for k, v in owners.items() if v != 'scorpio'}
assert platform == {
    'iff.alerts.bulk': 'sql-core',
    'iff.alerts': 'sql-core',
    'iff.ngsild-updates': 'sql-core',
    'iff.ngsild.attributes_insert': 'sql-core',
    'iff.ngsild.public.entity': 'kafka-bridges',
    'iff.ngsild.attributes': 'kafka-bridges',
    'iff.ngsild.entities': 'kafka-bridges',
}, platform
EOF
    echo "${output}"
    [ "${status}" -eq 0 ]
}

@test "iff.ngsild.entities takes its retention from entityTopicRetention in every environment" {
    command -v helm >/dev/null || skip "helm is not installed"
    # values.yaml.gotmpl hands each environment's value to the charts as is
    grep -qF 'entityTopicRetention: {{- if hasKey .StateValues.kafkaBridge.debezium "entityTopicRetention" }} {{ .StateValues.kafkaBridge.debezium.entityTopicRetention | quote}}' \
        "${HELM_DIR}/values.yaml.gotmpl"
    for environment in "${HELM_DIR}"/environment/*.yaml; do
        # the environment's debezium retentions, quoted as values.yaml.gotmpl
        # does, and its default "3600000" where the environment sets none
        python3 - "${environment}" "${WORK}/env.yaml" <<'EOF'
import sys, yaml
debezium = (yaml.safe_load(open(sys.argv[1])).get('kafkaBridge') or {}).get('debezium') or {}
values = {k: str(debezium.get(k, 3600000)) for k in ('entityTopicRetention', 'attributesTopicRetention')}
# a value of its own for the attributes, so that the wrong one shows
values['attributesTopicRetention'] = str(int(values['entityTopicRetention']) + 1)
yaml.safe_dump({'kafkaBridge': {'debezium': values}}, open(sys.argv[2], 'w'))
EOF
        render_topics "${WORK}/env.yaml"
        run python3 - "${WORK}/kafka-bridges.yaml" "${WORK}/env.yaml" <<'EOF'
import sys, yaml
expected = int(yaml.safe_load(open(sys.argv[2]))['kafkaBridge']['debezium']['entityTopicRetention'])
topics = {d['metadata']['name']: d for d in yaml.safe_load_all(open(sys.argv[1])) if d}
config = topics['iff.ngsild.entities']['spec']['config']
assert int(config['retention.ms']) == expected, (config, expected)
assert int(config['segment.ms']) == max(expected, 3600000), (config, expected)
print(config)
EOF
        echo "${environment##*/}: ${output}"
        [ "${status}" -eq 0 ]
    done
}

@test "helmfile hands every topic to its owner before syncing sql-core, kafka-bridges or shacl" {
    run python3 - "${HELM_DIR}" <<'EOF'
import re, sys, yaml
def presync(helmfile, release):
    # the helmfile is a template; its only expression here is the namespace
    text = re.sub(r'\{\{[^}]*\}\}', 'iff', open(f'{sys.argv[1]}/{helmfile}').read())
    releases = {r['name']: r for r in yaml.safe_load(text)['releases']}
    return [h['args'] for h in releases[release].get('hooks', []) if 'presync' in h['events']]
adopt = './adopt-kafka-topics.sh'
bridges = [adopt, 'iff', 'kafka-bridges', 'iff.ngsild.public.entity', 'iff.ngsild.attributes',
           'iff.ngsild.entities']
moved = [adopt, 'iff', 'kafka-bridges', 'iff.ngsild.attributes', 'iff.ngsild.entities']
core = [adopt, 'iff', 'sql-core', 'iff.alerts', 'iff.alerts.bulk', 'iff.ngsild-updates',
        'iff.ngsild.attributes-insert']
shacl = [adopt, 'iff', 'kafka-bridges', 'iff.ngsild.entities']
assert presync('helmfile.yaml', 'kafka-bridges') == [bridges], presync('helmfile.yaml', 'kafka-bridges')
assert presync('helmfile.yaml', 'sql-core') == [moved, core], presync('helmfile.yaml', 'sql-core')
assert presync('helmfile-shacl.yaml', 'shacl') == [shacl], presync('helmfile-shacl.yaml', 'shacl')
EOF
    echo "${output}"
    [ "${status}" -eq 0 ]
    [ -x "${HELM_DIR}/adopt-kafka-topics.sh" ]
}

@test "the hooks adopt every KafkaTopic the two charts render, for its owner" {
    command -v helm >/dev/null || skip "helm is not installed"
    render_topics
    run python3 - "${WORK}" "${HELM_DIR}/helmfile.yaml" <<'EOF'
import re, sys, yaml
work = sys.argv[1]
text = re.sub(r'\{\{[^}]*\}\}', 'iff', open(sys.argv[2]).read())
releases = {r['name']: r for r in yaml.safe_load(text)['releases']}
for chart in ('sql-core', 'kafka-bridges'):
    rendered = {d['metadata']['name'] for d in yaml.safe_load_all(open(f'{work}/{chart}.yaml'))
                if d and d['kind'] == 'KafkaTopic'}
    adopted = {t for h in releases[chart]['hooks'] if h['args'][2] == chart for t in h['args'][3:]}
    assert rendered == adopted, (chart, rendered, adopted)
EOF
    echo "${output}"
    [ "${status}" -eq 0 ]
}

# kubectl mock: `get` answers "name|release|policy|deletion time" from
# MOCK_TOPIC_<name with dots and dashes as underscores>, unset meaning no such
# topic; every call is logged. The tests set those variables per run, with
# `run env`.
mock_kubectl() {
    mkdir -p "${WORK}/bin"
    export MOCK_LOG="${WORK}/kubectl.log"
    : > "${MOCK_LOG}"
    cat > "${WORK}/bin/kubectl" <<'EOF'
#!/bin/bash
echo "$*" >> "${MOCK_LOG}"
if [ "$3" = "get" ]; then
    var="MOCK_TOPIC_${5//[.-]/_}"
    printf '%s' "${!var}"
fi
exit 0
EOF
    chmod +x "${WORK}/bin/kubectl"
    export PATH="${WORK}/bin:${PATH}"
}

@test "adopt-kafka-topics.sh hands a topic of another release to the new owner and keeps it" {
    mock_kubectl
    run env MOCK_TOPIC_iff_ngsild_attributes="iff.ngsild.attributes|sql-core||" \
        MOCK_TOPIC_iff_ngsild_entities="iff.ngsild.entities|shacl||" \
        bash "${HELM_DIR}/adopt-kafka-topics.sh" iff kafka-bridges iff.ngsild.attributes iff.ngsild.entities
    echo "${output}"
    cat "${MOCK_LOG}"
    [ "${status}" -eq 0 ]
    for topic in iff.ngsild.attributes iff.ngsild.entities; do
        grep -qx "\-n iff annotate --overwrite kafkatopic ${topic} meta.helm.sh/release-name=kafka-bridges meta.helm.sh/release-namespace=iff helm.sh/resource-policy=keep" "${MOCK_LOG}"
        grep -qx "\-n iff label --overwrite kafkatopic ${topic} app.kubernetes.io/managed-by=Helm" "${MOCK_LOG}"
    done
}

@test "adopt-kafka-topics.sh adopts a topic no release owns for its owner" {
    mock_kubectl
    run env MOCK_TOPIC_iff_alerts="iff.alerts|||" MOCK_TOPIC_iff_alerts_bulk="iff.alerts.bulk|sql-core|keep|" \
        bash "${HELM_DIR}/adopt-kafka-topics.sh" iff sql-core iff.alerts iff.alerts.bulk
    echo "${output}"
    cat "${MOCK_LOG}"
    [ "${status}" -eq 0 ]
    grep -qx "\-n iff annotate --overwrite kafkatopic iff.alerts meta.helm.sh/release-name=sql-core meta.helm.sh/release-namespace=iff helm.sh/resource-policy=keep" "${MOCK_LOG}"
    grep -qx "\-n iff label --overwrite kafkatopic iff.alerts app.kubernetes.io/managed-by=Helm" "${MOCK_LOG}"
    run ! grep -q "annotate --overwrite kafkatopic iff.alerts.bulk " "${MOCK_LOG}"
}

@test "adopt-kafka-topics.sh leaves a missing topic and one the release owns and keeps alone" {
    mock_kubectl
    run env MOCK_TOPIC_iff_ngsild_entities="iff.ngsild.entities|kafka-bridges|keep|" \
        bash "${HELM_DIR}/adopt-kafka-topics.sh" iff kafka-bridges iff.ngsild.attributes iff.ngsild.entities
    echo "${output}"
    cat "${MOCK_LOG}"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"KafkaTopic iff.ngsild.attributes: not there"* ]]
    [[ "${output}" == *"KafkaTopic iff.ngsild.entities: owned by kafka-bridges"* ]]
    run ! grep -q "annotate\|label" "${MOCK_LOG}"
}

@test "adopt-kafka-topics.sh leaves a KafkaTopic that is being deleted alone" {
    mock_kubectl
    run env MOCK_TOPIC_iff_alerts="iff.alerts|sql-core||2026-11-23T08:00:00Z" \
        bash "${HELM_DIR}/adopt-kafka-topics.sh" iff sql-core iff.alerts
    echo "${output}"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"KafkaTopic iff.alerts: being deleted"* ]]
    run ! grep -q "annotate\|label" "${MOCK_LOG}"
}

@test "adopt-kafka-topics.sh sets keep on a topic the release owns without it" {
    mock_kubectl
    run env MOCK_TOPIC_iff_ngsild_attributes="iff.ngsild.attributes|kafka-bridges||" \
        bash "${HELM_DIR}/adopt-kafka-topics.sh" iff kafka-bridges iff.ngsild.attributes
    echo "${output}"
    [ "${status}" -eq 0 ]
    grep -q "annotate --overwrite kafkatopic iff.ngsild.attributes .*helm.sh/resource-policy=keep" "${MOCK_LOG}"
}

# helm mock: `get manifest` prints ${MOCK_MANIFEST}, or fails with
# ${MOCK_HELM_ERROR} when that is set.
mock_helm() {
    mkdir -p "${WORK}/bin"
    cat > "${WORK}/bin/helm" <<'EOF'
#!/bin/bash
if [ -n "${MOCK_HELM_ERROR}" ]; then
    echo "${MOCK_HELM_ERROR}" >&2
    exit 1
fi
printf '%s\n' "${MOCK_MANIFEST}"
EOF
    chmod +x "${WORK}/bin/helm"
    export PATH="${WORK}/bin:${PATH}"
}

# A shacl manifest: a constraint topic, the entities topic with the metadata
# lines $1 (none: no keep, as a validation deployed before #1038 stored it;
# "absent": not declared, as one deployed now), and a ConfigMap of the same
# name, which is no KafkaTopic and may go.
shacl_manifest() {
    cat <<EOF
---
# Source: shacl/templates/ngsild-kafka.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: iff.ngsild.flink.constraint-table
  labels:
    strimzi.io/cluster: my-cluster
spec:
  topicName: iff.ngsild.flink.constraint_table
EOF
    if [ "$1" != absent ]; then
        cat <<EOF
---
# Source: shacl/templates/ngsild-kafka.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: iff.ngsild.entities
  labels:
    strimzi.io/cluster: my-cluster
$1
spec:
  partitions: 1
  topicName: iff.ngsild.entities
EOF
    fi
    cat <<EOF
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: iff.ngsild.entities
EOF
}

@test "check-release-keeps-topics.sh refuses to uninstall a release that would delete a topic" {
    mock_helm
    run env MOCK_MANIFEST="$(shacl_manifest)" \
        bash "${HELM_DIR}/check-release-keeps-topics.sh" iff shacl iff.ngsild.entities
    echo "${output}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Uninstalling shacl would delete KafkaTopic iff.ngsild.entities"* ]]
    [[ "${output}" == *"make flink-deploy"* ]]
}

@test "check-release-keeps-topics.sh lets a release go that keeps or doesn't declare the topic" {
    mock_helm
    keep=$'  annotations:\n    helm.sh/resource-policy: keep'
    run env MOCK_MANIFEST="$(shacl_manifest "${keep}")" \
        bash "${HELM_DIR}/check-release-keeps-topics.sh" iff shacl iff.ngsild.entities
    echo "${output}"
    [ "${status}" -eq 0 ]
    # a validation deployed now: only its own topics, which it may delete
    run env MOCK_MANIFEST="$(shacl_manifest absent)" \
        bash "${HELM_DIR}/check-release-keeps-topics.sh" iff shacl iff.ngsild.entities
    echo "${output}"
    [ "${status}" -eq 0 ]
}

@test "check-release-keeps-topics.sh passes a release that is not installed, fails on other errors" {
    mock_helm
    run env MOCK_HELM_ERROR="Error: release: not found" \
        bash "${HELM_DIR}/check-release-keeps-topics.sh" iff shacl iff.ngsild.entities
    echo "${output}"
    [ "${status}" -eq 0 ]
    run env MOCK_HELM_ERROR="Error: Kubernetes cluster unreachable" \
        bash "${HELM_DIR}/check-release-keeps-topics.sh" iff shacl iff.ngsild.entities
    echo "${output}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"Cannot read the manifest of release shacl"* ]]
}

@test "make flink-undeploy checks the shacl release before destroying it" {
    makefile="${BATS_TEST_DIRNAME}/../../semantic-model/shacl2flink/Makefile"
    recipe=$(awk '/^flink-undeploy:/ {grab = 1; next} grab && /^[^\t#]/ {exit} grab' "${makefile}")
    echo "${recipe}"
    # shellcheck disable=SC2016 # the Makefile's own $(NAMESPACE)
    check=$(grep -nF 'check-release-keeps-topics.sh $(NAMESPACE) shacl iff.ngsild.entities' <<<"${recipe}" | cut -d: -f1)
    destroy=$(grep -n 'helmfile-shacl.yaml destroy' <<<"${recipe}" | head -1 | cut -d: -f1)
    [ -n "${check}" ]
    [ -n "${destroy}" ]
    [ "${check}" -lt "${destroy}" ]
    [ -x "${HELM_DIR}/check-release-keeps-topics.sh" ]
}
