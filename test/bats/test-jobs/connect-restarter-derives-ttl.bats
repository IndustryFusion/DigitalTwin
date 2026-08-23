#!/usr/bin/env bats
# The kafka-connect restart cron re-feeds Flink state before it expires, so
# its threshold MUST follow the deployed table.exec.state.ttl -- a hardcoded
# copy is exactly how the two drifted apart and validations went silent
# between resyncs. These tests run the script from the helm template against
# a mocked kubectl, so pod ages are fabricated and nothing waits ttl/2.
# (To trigger the real cron on a cluster without waiting for its schedule:
#  kubectl create job --from=cronjob/kafka-connect-restart <name> -n iff)

bats_require_minimum_version 1.5.0

TEMPLATE="${BATS_TEST_DIRNAME}/../../../helm/charts/kafka/templates/connect-restarter.yaml"

setup() {
    WORK="$(mktemp -d)"
    export WORK
    mkdir -p "${WORK}/bin"
    export MOCK_LOG="${WORK}/kubectl.log"
    : > "${MOCK_LOG}"

    # Extract data."my-script.sh" from the ConfigMap (the 4-space indented
    # block) and render the helm placeholders like the chart would.
    awk '/my-script.sh: \|/{grab=1; next} grab && /^---/{grab=0} grab {sub(/^    /, ""); print}' \
        "${TEMPLATE}" \
      | sed -e 's/{{\.Release\.Namespace}}/iff/g' \
            -e 's/{{ \.Values\.flink\.ttl }}/3600 s/g' \
        > "${WORK}/restarter.sh"

    # kubectl mock: statementset TTL, pod list and ages come from env vars;
    # every delete is recorded instead of executed.
    cat > "${WORK}/bin/kubectl" <<'EOF'
#!/bin/bash
echo "$*" >> "${MOCK_LOG}"
case "$*" in
    *"get beamsqlstatementsets"*)
        if [ -n "${MOCK_TTL}" ]; then
            printf '[{"table.exec.state.ttl":"%s"}]' "${MOCK_TTL}"
            exit 0
        fi
        exit 1
        ;;
    *"get pods"*)
        printf '%s' "${MOCK_PODS}"
        ;;
    *"get pod "*)
        date -u -d "-${MOCK_POD_AGE_S} seconds" +%Y-%m-%dT%H:%M:%SZ
        ;;
    *"delete pod"*)
        echo "DELETE $*" >> "${MOCK_LOG}"
        ;;
esac
exit 0
EOF
    chmod +x "${WORK}/bin/kubectl"
    export PATH="${WORK}/bin:${PATH}"
    export MOCK_PODS="kafka-connect-connect-0"
    export MOCK_POD_AGE_S=100000
}

teardown() {
    rm -rf "${WORK}"
}

@test "threshold is ttl/2 minus the safety net (ttl 600 -> 240s)" {
    MOCK_TTL="600 s" run bash "${WORK}/restarter.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"deployed ttl 600s -> restart pods older than 240s (safety 60s)"* ]]
}

@test "safety net grows with the ttl (ttl 10000 -> 4900s, safety 100s)" {
    MOCK_TTL="10000 s" run bash "${WORK}/restarter.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"restart pods older than 4900s (safety 100s)"* ]]
}

@test "minute-valued ttl is parsed (10m -> 240s)" {
    MOCK_TTL="10m" run bash "${WORK}/restarter.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"deployed ttl 600s -> restart pods older than 240s"* ]]
}

@test "a tiny ttl floors the threshold at 60s instead of going negative" {
    MOCK_TTL="100 s" run bash "${WORK}/restarter.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"restart pods older than 60s"* ]]
}

@test "an unreadable statementset falls back to the helm value" {
    MOCK_TTL="" run bash "${WORK}/restarter.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"falling back to helm value 3600 s"* ]]
    [[ "${output}" == *"restart pods older than 1740s"* ]]
}

@test "a pod younger than the threshold is left alone" {
    # shellcheck disable=SC2030  # per-test env is intentionally test-local
    export MOCK_POD_AGE_S=100
    MOCK_TTL="600 s" run bash "${WORK}/restarter.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"Nothing to do"* ]]
    run ! grep -q "DELETE" "${MOCK_LOG}"
}

@test "a pod older than the threshold is restarted via the label selector" {
    # shellcheck disable=SC2031  # per-test env is intentionally test-local
    export MOCK_POD_AGE_S=1000
    MOCK_TTL="600 s" run bash "${WORK}/restarter.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"deleting pod"* ]]
    grep -q "DELETE delete pod -n iff -l app.kubernetes.io/instance=kafka-connect --wait=false" "${MOCK_LOG}"
}
