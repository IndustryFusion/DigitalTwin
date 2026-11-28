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
# Which K8s e2e shards a pull request runs, from the paths it changes.

bats_require_minimum_version 1.5.0

SCRIPT="${BATS_TEST_DIRNAME}/../../.github/scripts/e2e-shards.sh"
SUITES_DIR="${BATS_TEST_DIRNAME}/../bats"

select_for() {
    printf '%s\n' "$@" | bash "${SCRIPT}" select
}

@test "every suite directory belongs to exactly one shard" {
    assigned=""
    for shard in $(bash "${SCRIPT}" list); do
        assigned="${assigned} $(bash "${SCRIPT}" suites "${shard}")"
    done
    for dir in "${SUITES_DIR}"/test-*/; do
        name=$(basename "${dir}")
        count=$(echo "${assigned}" | tr ' ' '\n' | grep -cx "${name}" || true)
        [ "${count}" -eq 1 ] || { echo "${name} is in ${count} shards"; false; }
    done
}

@test "every suite a shard names exists" {
    for shard in $(bash "${SCRIPT}" list); do
        for suite in $(bash "${SCRIPT}" suites "${shard}"); do
            [ -d "${SUITES_DIR}/${suite}" ] || { echo "${shard}: ${suite} missing"; false; }
        done
    done
}

@test "an agent change runs only the device shard" {
    run select_for NgsildAgent/lib/utils.js NgsildAgent/test/foo.js
    [ "${output}" = '["device"]' ]
}

@test "a shacl2flink change runs the flink and flink-deploy shards" {
    run select_for semantic-model/shacl2flink/create_sql_checks_from_shacl.py
    [ "${output}" = '["flink","flink-deploy"]' ]
    run select_for semantic-model/shacl2flink/tests/bats/test-shacl-flink-deploy/test-shacl-flink-deploy.bats
    [ "${output}" = '["flink","flink-deploy"]' ]
}

@test "every path that selects flink selects flink-deploy, except the suites only flink runs" {
    for path in KafkaBridge/lib/mqttBridge.js DebeziumPostgresConnector/Dockerfile \
                .github/actions/debezium-archive/action.yml Fuseki/Dockerfile helm/charts/fuseki/values.yaml \
                helm/charts/scorpio/values.yaml helm/charts/alerta/values.yaml \
                semantic-model/shacl2flink/docs/files/shacl.ttl semantic-model/shacl2flink/Makefile \
                FlinkSqlGateway/Dockerfile FlinkOperatorWithCoreServices/pom.xml \
                FlinkSqlServicesOperator/beamsqlstatementsetoperator.py helm/charts/flink/values.yaml \
                helm/charts/sql-core/values.yaml helm/helmfile-shacl.yaml .env test/install-platform.sh; do
        run select_for "${path}"
        [[ "${output}" == *'"flink","flink-deploy"'* ]] || { echo "${path}: ${output}"; false; }
    done
    for path in test/bats/test-core-sql-services/test-alerta-bulk-filter.bats test/bats/test-jobs/platform-watchdog.bats; do
        run select_for "${path}"
        [[ "${output}" == *'"flink"'* && "${output}" != *flink-deploy* ]] || { echo "${path}: ${output}"; false; }
    done
}

@test "the flink-deploy shard has no suites below test/bats" {
    run bash "${SCRIPT}" suites flink-deploy
    [ "${status}" -eq 0 ]
    [ -z "${output}" ]
}

@test "the workflows run the deploy suite alone in flink-deploy, and both e2e targets in the nightly" {
    e2e="${BATS_TEST_DIRNAME}/../../.github/workflows/k8s-e2e.yaml"
    nightly="${BATS_TEST_DIRNAME}/../../.github/workflows/k8s-tests.yaml"
    makefile="${BATS_TEST_DIRNAME}/../../semantic-model/shacl2flink/Makefile"
    grep -q "if: matrix.shard != 'flink-deploy'" "${e2e}"
    grep -q "matrix.shard == 'flink-deploy' && 'test-flink-deploy-e2e' || 'test-flink-e2e'" "${e2e}"
    grep -q "make test-flink-deploy-e2e" "${nightly}"
    grep -q "make test-flink-e2e" "${nightly}"
    # the deploy suite runs in test-flink-deploy-e2e only
    run awk '/^test-flink-e2e:/{t=1; next} /^[a-z0-9-]+:/{t=0} t && /test-shacl-flink-deploy/' "${makefile}"
    [ -z "${output}" ]
    run awk '/^test-flink-deploy-e2e:/{t=1; next} /^[a-z0-9-]+:/{t=0} t && /bats test-shacl-flink-deploy/' "${makefile}"
    [ -n "${output}" ]
}

@test "a bridge change runs every shard the bridges are part of" {
    run select_for KafkaBridge/lib/mqttBridge.js
    [ "${output}" = '["device","broker","flink","flink-deploy"]' ]
}

@test "a Debezium connector change runs broker and flink" {
    run select_for DebeziumPostgresConnector/Dockerfile
    [ "${output}" = '["broker","flink","flink-deploy"]' ]
    run select_for .github/actions/debezium-archive/action.yml
    [ "${output}" = '["broker","flink","flink-deploy"]' ]
}

@test "an EMQX chart change runs device and broker" {
    run select_for helm/charts/emqx/values.yaml
    [ "${output}" = '["device","broker"]' ]
}

@test "a Fuseki change runs broker and flink" {
    run select_for Fuseki/Dockerfile helm/charts/fuseki/values.yaml
    [ "${output}" = '["broker","flink","flink-deploy"]' ]
}

@test "a Flink component or chart change runs only the flink and flink-deploy shards" {
    for path in FlinkSqlGateway/Dockerfile FlinkOperatorWithCoreServices/pom.xml \
                FlinkSqlServicesOperator/beamsqlstatementsetoperator.py helm/charts/sql-core/values.yaml \
                helm/helmfile-shacl.yaml; do
        run select_for "${path}"
        [ "${output}" = '["flink","flink-deploy"]' ] || { echo "${path}: ${output}"; false; }
    done
}

@test "a broker-only chart change runs only the broker shard" {
    run select_for helm/charts/velero/values.yaml helm/charts/redis/values.yaml
    [ "${output}" = '["broker"]' ]
}

@test "a pgrest chart change runs only the device shard" {
    run select_for helm/charts/pgrest/values.yaml
    [ "${output}" = '["device"]' ]
}

@test "a change to the datamodel tools runs the device shard, which runs them" {
    run select_for semantic-model/datamodel/tools/jsonschema2shacl.js
    [ "${output}" = '["device"]' ]
}

@test "a change to the files the Fuseki suite uploads runs broker and flink" {
    run select_for semantic-model/shacl2flink/docs/files/shacl.ttl
    [ "${output}" = '["broker","flink","flink-deploy"]' ]
}

@test "other datamodel paths select no shard" {
    run select_for semantic-model/datamodel/README.md
    [ "${output}" = '[]' ]
}

@test "a scorpio chart change runs broker and flink" {
    run select_for helm/charts/scorpio/values.yaml
    [ "${output}" = '["broker","flink","flink-deploy"]' ]
}

@test "a change to the watchdog's end-to-end test runs broker and flink" {
    run select_for test/bats/test-jobs/platform-watchdog.bats
    [ "${output}" = '["broker","flink"]' ]
    run select_for test/bats/test-jobs/other.bats
    [ "${output}" = '["broker"]' ]
}

@test "a change to a suite runs the shard of that suite" {
    run select_for test/bats/test-scorpio/test-scorpio-mergepatch.bats
    [ "${output}" = '["broker"]' ]
    run select_for test/bats/test-core-sql-services/test-alerta-bulk-filter.bats
    [ "${output}" = '["flink"]' ]
}

@test "shared platform files run every shard" {
    for path in .env docker-compose.yml helm/helmfile.yaml helm/values.yaml.gotmpl .github/workflows/e2e-labels.yaml \
                helm/install_operators.sh helm/flink-operator-values.yaml helm/charts/keycloak/values.yaml \
                test/install-platform.sh test/bats/lib/utils.bash Keycloak/Dockerfile; do
        run select_for "${path}"
        [ "${output}" = '["device","broker","flink","flink-deploy"]' ] || { echo "${path}: ${output}"; false; }
    done
}

@test "paths the cluster never runs select no shard" {
    run select_for semantic-model/SemForge-SDK/semforge/cli.py semantic-model/opcua/nodeset2owl.py \
        README.md openspec/specs/x/spec.md test/bats-unit/e2e-shards.bats semantic-model/dataservice/startDataservice.py
    [ "${output}" = '[]' ]
}

@test "scripts of the other tests below test/ are not platform scripts" {
    run select_for test/opcua-chain/run.sh test/debezium-snapshot-memory/test.sh
    [ "${output}" = '[]' ]
}

@test "shards are merged across paths and listed once, in a fixed order" {
    run select_for semantic-model/shacl2flink/Makefile NgsildAgent/x.js FlinkSqlGateway/y NgsildAgent/z.js
    [ "${output}" = '["device","flink","flink-deploy"]' ]
}

@test "--all selects every shard regardless of the paths" {
    run bash -c "printf 'README.md\n' | bash '${SCRIPT}' select --all"
    [ "${output}" = '["device","broker","flink","flink-deploy"]' ]
}

@test "no changed paths select nothing" {
    run bash -c "printf '' | bash '${SCRIPT}' select"
    [ "${output}" = '[]' ]
}

@test "an unknown shard is an error" {
    run bash "${SCRIPT}" suites nope
    [ "${status}" -ne 0 ]
}
