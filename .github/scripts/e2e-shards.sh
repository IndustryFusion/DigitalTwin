#!/bin/bash
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
# The shards of the K8s end-to-end test that pull requests run on GitHub-hosted
# runners. Every shard installs the full platform and runs only its own suites;
# the nightly still runs every suite on one full install (k8s-tests.yaml).
#
#   e2e-shards.sh select [--all]  changed paths on stdin -> JSON array of shards
#   e2e-shards.sh suites <shard>  the test/bats suite directories of a shard
#   e2e-shards.sh list            every shard
#
# A path that matches no rule selects nothing: it is covered by Build.
#
# flink-deploy runs shacl2flink's test-shacl-flink-deploy alone (make
# test-flink-deploy-e2e): seven full deployments, about an hour, that made the
# flink shard reach its time limit (#1202). It has no suites below test/bats,
# and every path that selects flink selects it too, except the suites only
# flink runs.
set -euo pipefail

# flink-ladder: shacl2flink's test-flink-e2e with SPARQL_ENGINE=ladder (alpha),
# for changes to the ladder's own files; it has no suites of its own. The
# nightly (k8s-tests.yaml) runs it on every change.
SHARDS=(device broker flink flink-deploy flink-ladder)

suites() {
    case "$1" in
        device) echo test-device-connection test-timescaledb-bridge ;;
        broker) echo test-bridges test-fuseki test-horizontal-platform test-jobs \
                     test-keycloak test-operators test-scorpio ;;
        flink)  echo test-core-sql-services ;;  # plus shacl2flink's test-flink-e2e
        flink-deploy) ;;                         # shacl2flink's test-flink-deploy-e2e only
        flink-ladder) ;;                          # shacl2flink's test-flink-e2e only
        *) echo "unknown shard: $1" >&2; return 1 ;;
    esac
}

# Shards a single path selects, space separated ("all" for every shard).
shards_for() {
    # The platform scripts directly in test/ (install-platform.sh, ...), not
    # the scripts of other tests below it: a case pattern's * matches "/".
    if [[ "$1" == test/*.sh && "$1" != test/*/* ]]; then
        echo all
        return
    fi
    case "$1" in
        # what every install and every test depends on
        .env|docker-compose.yml|Keycloak/*|\
        helm/helmfile.yaml|helm/values.yaml.gotmpl|helm/common.*|helm/env.sh|\
        helm/install_operators.sh|helm/flink-operator-values.yaml|helm/environment/*|\
        helm/charts/postgres/*|helm/charts/kafka/*|helm/charts/keycloak/*|\
        helm/charts/seaweedfs/*|helm/charts/cert-manager/*|\
        test/bats/lib/*|test/bats/prepare-test.sh|\
        .github/workflows/k8s-e2e.yaml|.github/workflows/e2e-labels.yaml|.github/scripts/e2e-shards.sh)
            echo all ;;
        KafkaBridge/*|helm/charts/kafka-bridges/*) echo device broker flink flink-deploy ;;
        DebeziumPostgresConnector/*|.github/actions/debezium-archive/*) echo broker flink flink-deploy ;;
        NgsildAgent/*|helm/charts/pgrest/*|\
        test/bats/test-device-connection/*|test/bats/test-timescaledb-bridge/*)
            echo device ;;
        helm/charts/emqx/*) echo device broker ;;
        # the subcomponent suite runs the datamodel tools
        semantic-model/datamodel/tools/*) echo device ;;
        # the Fuseki suite uploads these files; before the shacl2flink rule
        semantic-model/shacl2flink/docs/files/*) echo broker flink flink-deploy ;;
        helm/charts/scorpio/*|helm/charts/alerta/*) echo broker flink flink-deploy ;;
        # the watchdog's end-to-end test also runs in the flink shard, where the
        # validation is deployed (shacl2flink's test-flink-e2e)
        test/bats/test-jobs/platform-watchdog.bats) echo broker flink ;;
        Fuseki/*|helm/charts/fuseki/*) echo broker flink flink-deploy ;;
        helm/charts/redis/*|helm/charts/velero/*|\
        test/bats/test-bridges/*|test/bats/test-fuseki/*|test/bats/test-horizontal-platform/*|\
        test/bats/test-jobs/*|test/bats/test-keycloak/*|test/bats/test-operators/*|\
        test/bats/test-scorpio/*)
            echo broker ;;
        # a suite only the flink shard runs
        test/bats/test-core-sql-services/*) echo flink ;;
        # SPARQL_ENGINE=ladder (alpha): its compiler, its functions and their
        # tests, before the rules of shacl2flink and the gateway
        semantic-model/shacl2flink/lib/sparql_ladder*|semantic-model/shacl2flink/tests/test_sparql_ladder*|\
        semantic-model/shacl2flink/sparql_ladder_joins.py|semantic-model/shacl2flink/tests/sparql-ladder-*.json|\
        semantic-model/shacl2flink/tests/e2e-kms/without_shapes.py|semantic-model/shacl2flink/tests/bats/test-shacl-flink-ladder/*|\
        semantic-model/shacl2flink/tests/test_e2e_without_shapes.py|FlinkSqlGateway/sparql-udf/*)
            echo flink flink-ladder ;;
        FlinkSqlGateway/*|FlinkOperatorWithCoreServices/*|FlinkSqlServicesOperator/*|\
        semantic-model/shacl2flink/*|helm/charts/flink/*|helm/charts/sql-core/*|\
        helm/helmfile-shacl.yaml)
            echo flink flink-deploy ;;
        *) ;;
    esac
}

select_shards() {
    local all=$1 path shard
    declare -A picked=()
    if [ "$all" = true ]; then
        for shard in "${SHARDS[@]}"; do picked[$shard]=1; done
    else
        while IFS= read -r path; do
            [ -n "$path" ] || continue
            for shard in $(shards_for "$path"); do
                if [ "$shard" = all ]; then
                    # every shard but the ladder's: that one runs for its own files
                    for s in "${SHARDS[@]}"; do [ "$s" = flink-ladder ] || picked[$s]=1; done
                else
                    picked[$shard]=1
                fi
            done
        done
    fi
    local out=() first=true
    for shard in "${SHARDS[@]}"; do
        [ -n "${picked[$shard]:-}" ] && out+=("\"$shard\"")
    done
    printf '['
    for shard in "${out[@]+"${out[@]}"}"; do
        $first || printf ','
        printf '%s' "$shard"
        first=false
    done
    printf ']\n'
}

case "${1:-}" in
    select) select_shards "$([ "${2:-}" = --all ] && echo true || echo false)" ;;
    suites) suites "${2:?shard missing}" ;;
    list) echo "${SHARDS[@]}" ;;
    *) echo "usage: $0 select [--all] | suites <shard> | list" >&2; exit 2 ;;
esac
