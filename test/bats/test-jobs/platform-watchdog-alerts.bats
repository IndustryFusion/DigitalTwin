#!/usr/bin/env bats
# The platform watchdog raises the conditions under which the streaming
# validation can go silently WRONG: a Debezium resync missing for longer
# than the deployed Flink state TTL means dedup state may have expired
# unrefreshed and ghost rows may sit in pinned join state -- consistency is
# no longer guaranteed and only a statementset redeploy repairs it, so that
# alert is critical and says so. These tests run the script from the helm
# template against a mocked kubectl and a real local HTTP sink standing in
# for Alerta, so the /dev/tcp transport is exercised end-to-end.

# shellcheck disable=SC2030,SC2031  # per-test env is intentionally test-local

bats_require_minimum_version 1.5.0

TEMPLATE="${BATS_TEST_DIRNAME}/../../../helm/charts/alerta/templates/platform-watchdog.yaml"

setup() {
    WORK="$(mktemp -d)"
    export WORK
    mkdir -p "${WORK}/bin"
    export MOCK_LOG="${WORK}/kubectl.log"
    export SINK_LOG="${WORK}/alerta-posts.log"
    : > "${MOCK_LOG}"
    : > "${SINK_LOG}"

    # Extract data."watchdog.sh" from the ConfigMap (the 4-space indented
    # block); the script itself contains no helm placeholders -- everything
    # arrives via env, exactly as the CronJob passes it.
    awk '/watchdog.sh: \|/{grab=1; next} grab && /^---/{grab=0} grab {sub(/^    /, ""); print}' \
        "${TEMPLATE}" > "${WORK}/watchdog.sh"

    # Alerta sink: answers 201 to every POST and appends each body to
    # SINK_LOG; binds port 0 and reports the chosen port through a file.
    cat > "${WORK}/sink.py" <<'EOF'
import http.server
import sys


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n).decode()
        with open(sys.argv[1], 'a') as f:
            f.write(body + '\n')
        self.send_response(201)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'{}')

    def log_message(self, *args):
        pass


server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
with open(sys.argv[2], 'w') as f:
    f.write(str(server.server_address[1]))
server.serve_forever()
EOF
    python3 "${WORK}/sink.py" "${SINK_LOG}" "${WORK}/sink.port" &
    SINK_PID=$!
    export SINK_PID
    for _ in $(seq 1 50); do
        [ -s "${WORK}/sink.port" ] && break
        sleep 0.1
    done

    # kubectl mock: TTL, statementset state, connect-pod age and per-bridge
    # replica counts all come from env vars; every call is recorded.
    cat > "${WORK}/bin/kubectl" <<'EOF'
#!/bin/bash
echo "$*" >> "${MOCK_LOG}"
case "$*" in
    *"get beamsqlstatementsets"*"jsonpath={.spec.sqlsettings}"*)
        if [ -n "${MOCK_TTL}" ]; then
            printf '[{"table.exec.state.ttl":"%s"}]' "${MOCK_TTL}"
            exit 0
        fi
        exit 1
        ;;
    *"get beamsqlstatementsets"*"jsonpath={.status.state}"*)
        printf '%s' "${MOCK_SS_STATE}"
        ;;
    *"get pods"*"kafka-connect"*)
        if [ -n "${MOCK_CONNECT_AGE_S}" ]; then
            date -u -d "-${MOCK_CONNECT_AGE_S} seconds" +%Y-%m-%dT%H:%M:%SZ
        fi
        ;;
    *"get deployment"*)
        [[ "$*" =~ get\ deployment\ ([a-z-]+) ]] || exit 1
        var="MOCK_DEPLOY_${BASH_REMATCH[1]//-/_}"
        val="${!var:-1 1}"
        [ "${val}" = "MISSING" ] && exit 1
        printf '%s' "${val}"
        ;;
esac
exit 0
EOF
    chmod +x "${WORK}/bin/kubectl"
    export PATH="${WORK}/bin:${PATH}"

    export NAMESPACE=iff
    export ALERTA_HOST=127.0.0.1
    ALERTA_PORT="$(cat "${WORK}/sink.port")"
    export ALERTA_PORT
    export ALERTA_API_KEY=test-key
    export FALLBACK_TTL="3600 s"
    # keep the default healthy: statementset running, resync fresh, one bridge
    export MOCK_TTL="600 s"
    export MOCK_SS_STATE="RUNNING"
    export MOCK_CONNECT_AGE_S=100
    export BRIDGES="mqtt-bridge"
}

teardown() {
    kill "${SINK_PID}" 2>/dev/null || true
    rm -rf "${WORK}"
}

@test "a healthy platform posts only normal (clearing) alerts" {
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[normal] kafka-connect/ResyncRecency"* ]]
    [[ "${output}" == *"[normal] shacl-validation/StatementsetState"* ]]
    [[ "${output}" == *"[normal] mqtt-bridge/BridgeHealth"* ]]
    run ! grep -qE '"severity":"(critical|warning)"' "${SINK_LOG}"
    grep -q '"resource":"kafka-connect","event":"ResyncRecency".*"severity":"normal"' "${SINK_LOG}"
    grep -qF '"service":["System"]' "${SINK_LOG}"
}

@test "resync older than the deployed ttl is critical and demands a restart" {
    export MOCK_CONNECT_AGE_S=700
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[critical] kafka-connect/ResyncRecency: 700s > ttl 600s"* ]]
    grep -q '"resource":"kafka-connect".*"severity":"critical"' "${SINK_LOG}"
    grep -q 'Consistency cannot be guaranteed. RESTART REQUIRED: redeploy the shacl-validation statementset' "${SINK_LOG}"
    grep -q 'Resuming the resync alone cannot repair this' "${SINK_LOG}"
}

@test "resync not triggered by ttl/2 (plus grace) is a warning, not critical" {
    export MOCK_CONNECT_AGE_S=560
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[warning] kafka-connect/ResyncRecency: 560s > 540s"* ]]
    run ! grep -q '"resource":"kafka-connect".*"severity":"critical"' "${SINK_LOG}"
}

@test "a healthy restart cadence just past ttl/2 stays inside the grace" {
    export MOCK_CONNECT_AGE_S=400
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[normal] kafka-connect/ResyncRecency: 400s <= ttl 600s"* ]]
}

@test "no kafka-connect pods at all is critical" {
    export MOCK_CONNECT_AGE_S=""
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[critical] kafka-connect/ResyncRecency: no pods"* ]]
}

@test "an unreadable statementset falls back to the helm ttl value" {
    export MOCK_TTL=""
    export MOCK_SS_STATE=""
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"falling back to helm value 3600 s"* ]]
    [[ "${output}" == *"[critical] shacl-validation/StatementsetState: not found"* ]]
}

@test "a non-RUNNING statementset is critical with the state in the value" {
    export MOCK_SS_STATE="DEPLOYMENTFAILURE"
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[critical] shacl-validation/StatementsetState: DEPLOYMENTFAILURE"* ]]
    grep -q '"resource":"shacl-validation".*"severity":"critical".*DEPLOYMENTFAILURE' "${SINK_LOG}"
}

@test "a bridge with zero ready pods is critical, a degraded one warns" {
    export BRIDGES="mqtt-bridge alerta-bridge"
    export MOCK_DEPLOY_mqtt_bridge="1 "
    export MOCK_DEPLOY_alerta_bridge="2 1"
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[critical] mqtt-bridge/BridgeHealth: 0/1 ready"* ]]
    [[ "${output}" == *"[warning] alerta-bridge/BridgeHealth: 1/2 ready"* ]]
}

@test "a bridge deliberately scaled to zero warns instead of paging critical" {
    export MOCK_DEPLOY_mqtt_bridge="0 "
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[warning] mqtt-bridge/BridgeHealth: scaled to zero"* ]]
}

@test "an unreachable alerta is logged but never fails the job" {
    kill "${SINK_PID}" 2>/dev/null || true
    wait "${SINK_PID}" 2>/dev/null || true
    run -0 --separate-stderr bash "${WORK}/watchdog.sh"
    # shellcheck disable=SC2154  # stderr is assigned by run --separate-stderr
    [[ "${stderr}" == *"alerta unreachable"* ]]
    [[ "${output}" == *"[normal] kafka-connect/ResyncRecency"* ]]
}
