#!/usr/bin/env bats
# The platform watchdog raises the conditions under which the streaming
# validation can go silently WRONG: a key that went longer than the deployed
# Flink state TTL without a complete Debezium refresh while the job had state
# sits twice in pinned join state -- only emptying the state repairs that, so
# the alert is critical, latched and says so. A state emptied by a failover
# or a JobManager restart is rebuilt by the next complete refresh. These
# tests run the script from the helm template against a mocked kubectl, the
# Debezium log lines the watchdog reads, and a real local HTTP server standing
# in for Alerta and the Flink REST API, so the /dev/tcp transport is
# exercised end-to-end, on a clock the tests set.

# shellcheck disable=SC2030,SC2031  # per-test env is intentionally test-local

bats_require_minimum_version 1.5.0

TEMPLATE="${BATS_TEST_DIRNAME}/../../helm/charts/alerta/templates/platform-watchdog.yaml"

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
    # SINK_LOG. Flink REST: answers a GET of /jobs/<id>[/exceptions|
    # /checkpoints] from ${WORK}/flink/{job,exceptions,checkpoints}.json, 404
    # without job.json. Binds port 0 and reports the chosen port via a file.
    mkdir -p "${WORK}/flink"
    cat > "${WORK}/sink.py" <<'EOF'
import http.server
import os
import sys

FLINK = os.path.join(os.path.dirname(sys.argv[1]), 'flink')
DEFAULTS = {'exceptions': b'{"exceptionHistory":{"entries":[]}}',
            'checkpoints': b'{"counts":{"completed":0,"restored":0},"latest":{}}'}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split('?')[0]
        kind = 'exceptions' if path.endswith('/exceptions') else 'checkpoints' if path.endswith('/checkpoints') else 'job'
        name = os.path.join(FLINK, kind + '.json')
        if os.path.exists(name):
            body = open(name, 'rb').read()
        elif kind != 'job' and os.path.exists(os.path.join(FLINK, 'job.json')):
            body = DEFAULTS[kind]
        else:
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

    # kubectl mock: TTL, statementset state and job, JobManager start,
    # connector states and per-bridge replica counts come from env vars, the
    # Connect log from ${WORK}/connect.log, the watchdog's ConfigMap from
    # ${WORK}/state.json (written back on patch); every call is recorded.
    cat > "${WORK}/bin/kubectl" <<'EOF'
#!/bin/bash
echo "$*" >> "${MOCK_LOG}"
case "$*" in
    *"patch configmap platform-watchdog-state"*)
        [ "${MOCK_PATCH}" = "FAIL" ] && { echo 'Error from server (Forbidden)' >&2; exit 1; }
        # a JSON merge patch: null deletes a key, a key left out is kept
        while [ $# -gt 0 ] && [ "$1" != "-p" ]; do shift; done
        jq -c --argjson p "$2" '. + $p.data | with_entries(select(.value != null))' "${WORK}/state.json" > "${WORK}/state.new"
        mv "${WORK}/state.new" "${WORK}/state.json"
        ;;
    *"get configmap platform-watchdog-state"*)
        [ -f "${WORK}/state.json" ] || exit 1
        printf '{"data":%s}' "$(cat "${WORK}/state.json")"
        ;;
    *"get beamsqlstatementsets"*"jsonpath={.status.job_id}"*)
        printf '%s' "${MOCK_JOB_ID}"
        ;;
    *"get pods"*"component=jobmanager"*)
        [ "${MOCK_JM}" = "ERROR" ] && exit 1
        [ -n "${MOCK_JM_STARTED}" ] && date -u -d "@${MOCK_JM_STARTED}" +%Y-%m-%dT%H:%M:%SZ
        ;;
    *"get pods"*"kafka-connect"*)
        [ "${MOCK_CONNECT_PODS}" = "ERROR" ] && exit 1
        # by name, or name and container start; a pod still starting has none
        if [[ "$*" == *"-o name"* ]]; then
            echo "pod/kafka-connect-connect-0"
        elif [ "${MOCK_CONNECT_STARTING}" = "yes" ]; then
            echo "kafka-connect-connect-0 "
        else
            echo "kafka-connect-connect-0 2026-11-19T14:50:00Z"
        fi
        ;;
    *"logs pod/kafka-connect-connect-0"*)
        [ "${MOCK_LOGS}" = "ERROR" ] && exit 1
        cat "${WORK}/connect.log"
        ;;
    *"get kafkaconnectors"*)
        [[ "$*" =~ get\ kafkaconnectors\ ([a-z-]+) ]] || exit 1
        var="MOCK_CONNECTOR_${BASH_REMATCH[1]//-/_}"
        if [ "${!var}" = "MISSING" ]; then
            echo "Error from server (NotFound): kafkaconnectors.kafka.strimzi.io \"${BASH_REMATCH[1]}\" not found" >&2
            exit 1
        fi
        if [ "${!var}" = "ERROR" ]; then
            echo "Unable to connect to the server: net/http: TLS handshake timeout" >&2
            exit 1
        fi
        [ -n "${MOCK_KUBECTL_WARNING}" ] && echo "${MOCK_KUBECTL_WARNING}" >&2
        read -r connector task <<<"${!var:-RUNNING RUNNING}"
        printf '{"status":{"connectorStatus":{"connector":{"state":"%s"},"tasks":[{"id":0,"state":"%s"}]}}}' "${connector}" "${task}"
        ;;
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
    export FLINK_HOST=127.0.0.1
    export FLINK_PORT="${ALERTA_PORT}"
    # keep the default healthy: statementset running, its job started at B
    # and refreshed at B+100, the watchdog observing since before, one bridge
    export MOCK_TTL="600 s"
    export MOCK_SS_STATE="RUNNING"
    export MOCK_JOB_ID=5ca51a5f717ed2d9a0c16efc2c820b3a
    export MOCK_JM_STARTED=$(( B - 60 ))
    export BRIDGES="mqtt-bridge"
    # the tests jump the clock between runs; the gap in the watchdog's own
    # runs has a test of its own
    export RUN_GAP=1000000
    printf '{"state":"RUNNING","start-time":%d000}' "${B}" > "${WORK}/flink/job.json"
    printf '{"observing_since":"%d"}' $(( B - 10 )) > "${WORK}/state.json"
    : > "${WORK}/connect.log"
    refresh $(( B + 100 )) $(( B + 105 ))
    export WATCHDOG_NOW=$(( B + 200 ))
}

# The job starts at B; TTL 600 s, late after 540 s.
B=1795100000

# refresh <start> <end>: a complete Debezium snapshot of both connectors
refresh() {
    local c
    for c in entity-table-connector rdf-table-connector; do
        printf '%s INFO [%s|task-0] Snapshot step 1 - Preparing (io.debezium.relational.RelationalSnapshotChangeEventSource)\n' \
            "$(date -u -d "@$1" '+%Y-%m-%d %H:%M:%S'),217" "${c}" >> "${WORK}/connect.log"
        printf '%s INFO [%s|task-0] Snapshot ended with SnapshotResult [status=COMPLETED, offset=x] (io.debezium.pipeline.source.AbstractSnapshotChangeEventSource)\n' \
            "$(date -u -d "@$2" '+%Y-%m-%d %H:%M:%S'),374" "${c}" >> "${WORK}/connect.log"
    done
}

# failover <time>: the job failed over then (restored from no checkpoint)
failover() {
    printf '{"exceptionHistory":{"entries":[{"timestamp":%d000}]}}' "$1" > "${WORK}/flink/exceptions.json"
}

# consistency: the last ValidationConsistency alert posted
consistency() {
    grep '"event":"ValidationConsistency"' "${SINK_LOG}" | tail -1
}

teardown() {
    kill "${SINK_PID}" 2>/dev/null || true
    rm -rf "${WORK}"
}

@test "a healthy platform posts only normal (clearing) alerts" {
    run bash "${WORK}/watchdog.sh"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"[normal] shacl-validation/ValidationConsistency: consistent"* ]]
    [[ "${output}" == *"[normal] shacl-validation/StatementsetState"* ]]
    [[ "${output}" == *"[normal] mqtt-bridge/BridgeHealth"* ]]
    [[ "${output}" == *"[normal] entity-table-connector/ConnectorState: RUNNING RUNNING"* ]]
    run ! grep -qE '"severity":"(critical|warning)"' "${SINK_LOG}"
    grep -qF '"service":["System"]' "${SINK_LOG}"
    jq -e '."rdf-table-connector.done" == "1795100105"' "${WORK}/state.json"
}

@test "a refresh that dies halfway does not count: the refresh is late" {
    WATCHDOG_NOW=$(( B + 300 )) bash "${WORK}/watchdog.sh" >/dev/null
    printf '%s INFO [rdf-table-connector|task-0] Snapshot step 1 - Preparing (x)\n' \
        "$(date -u -d "@$(( B + 500 ))" '+%Y-%m-%d %H:%M:%S'),100" >> "${WORK}/connect.log"
    export WATCHDOG_NOW=$(( B + 700 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: refresh late"* ]]
    consistency | grep -q 'REFRESH LATE: .*rdf-table-connector (last complete refresh 2026-11-19T14:55:00Z, window closes 2026-11-19T15:05:00Z)'
}

@test "young pods without a refresh since the state was emptied: rebuilding" {
    : > "${WORK}/connect.log"
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: rebuilding"* ]]
    consistency | grep -q 'REBUILDING -- REFRESH REQUIRED.*the job 5ca51a5f717ed2d9a0c16efc2c820b3a started.*No complete refresh of entity-table-connector, rdf-table-connector since'
}

@test "a failover without a checkpoint empties the state: rebuilding until the next refresh" {
    failover $(( B + 300 ))
    export WATCHDOG_NOW=$(( B + 320 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: rebuilding since 2026-11-19T14:58:20Z"* ]]
    consistency | grep -q 'failed over and restarted without a checkpoint. No checkpoint can restore the state: checkpointing is disabled'
    consistency | grep -q 'the kafka-connect-restart cron triggers one by 2026-11-19T15:03:20Z'
    refresh $(( B + 400 )) $(( B + 405 ))
    export WATCHDOG_NOW=$(( B + 420 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[normal] shacl-validation/ValidationConsistency: consistent"* ]]
}

@test "a failover restored from a checkpoint keeps the state" {
    failover $(( B + 300 ))
    printf '{"counts":{"completed":3,"restored":1},"latest":{"restored":{"id":9,"restore_timestamp":%d000}},"history":[]}' $(( B + 301 )) > "${WORK}/flink/checkpoints.json"
    export WATCHDOG_NOW=$(( B + 320 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[normal] shacl-validation/ValidationConsistency: consistent"* ]]
}

@test "a JobManager restart without a checkpoint empties the state" {
    export MOCK_JM_STARTED=$(( B + 300 ))
    export WATCHDOG_NOW=$(( B + 320 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: rebuilding since 2026-11-19T14:58:20Z"* ]]
    consistency | grep -q 'the Flink JobManager restarted and relaunched the job'
}

@test "a missed window is inconsistent, critical without timeout, and names the repair" {
    bash "${WORK}/watchdog.sh" >/dev/null
    refresh $(( B + 750 )) $(( B + 760 ))
    export WATCHDOG_NOW=$(( B + 800 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[critical] shacl-validation/ValidationConsistency: inconsistent since 2026-11-19T15:05:00Z"* ]]
    consistency | jq -e '.timeout == 0'
    consistency | grep -q 'INCONSISTENT -- REDEPLOYMENT REQUIRED. entity-table-connector: no complete refresh from 2026-11-19T14:55:00Z until 2026-11-19T15:06:00Z, 660s, longer than the state TTL of 600s'
    consistency | grep -q 'Repair: (1) redeploy the shacl-validation statementset, (2) restart Core Services (core-services-job), (3) delete the open alerts of service SHACL Validator, (4) restart kafka-connect for a complete refresh'
    consistency | grep -q 'No checkpoint can restore the state: checkpointing is disabled'
}

@test "no complete refresh within the ttl is inconsistent before any refresh comes" {
    bash "${WORK}/watchdog.sh" >/dev/null
    export WATCHDOG_NOW=$(( B + 720 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[critical] shacl-validation/ValidationConsistency"* ]]
    consistency | grep -q 'no complete refresh since 2026-11-19T14:55:00Z, 620s'
}

@test "the inconsistency stays through the next refresh and every run, until the state is emptied" {
    bash "${WORK}/watchdog.sh" >/dev/null
    WATCHDOG_NOW=$(( B + 720 )) bash "${WORK}/watchdog.sh" >/dev/null
    refresh $(( B + 800 )) $(( B + 805 ))
    WATCHDOG_NOW=$(( B + 820 )) bash "${WORK}/watchdog.sh" >/dev/null
    consistency | jq -e '.severity == "critical"'
    # an alert closed by hand is raised again by the next run
    WATCHDOG_NOW=$(( B + 940 )) bash "${WORK}/watchdog.sh" >/dev/null
    [ "$(grep -c '"event":"ValidationConsistency".*"severity":"critical"' "${SINK_LOG}")" -eq 3 ]
    # emptied after it: rebuilding, then consistent after the next refresh
    failover $(( B + 1000 ))
    export WATCHDOG_NOW=$(( B + 1010 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"inconsistency of "*" ended: state emptied at 2026-11-19T15:10:00Z"* ]]
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: rebuilding"* ]]
    refresh $(( B + 1100 )) $(( B + 1105 ))
    export WATCHDOG_NOW=$(( B + 1120 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[normal] shacl-validation/ValidationConsistency: consistent"* ]]
}

@test "the alert names a checkpoint taken before the state went stale" {
    printf '{"counts":{"completed":2,"restored":0},"latest":{},"history":[{"id":7,"status":"COMPLETED","latest_ack_timestamp":%d000,"external_path":"s3://flink/checkpoints/chk-7"},{"id":8,"status":"COMPLETED","latest_ack_timestamp":%d000,"external_path":"s3://flink/checkpoints/chk-8"}]}' \
        $(( B + 300 )) $(( B + 900 )) > "${WORK}/flink/checkpoints.json"
    bash "${WORK}/watchdog.sh" >/dev/null
    export WATCHDOG_NOW=$(( B + 720 ))
    run bash "${WORK}/watchdog.sh"
    consistency | grep -q 'restoring checkpoint #7 completed at 2026-11-19T14:58:20Z (s3://flink/checkpoints/chk-7)'
}

@test "checkpoints taken only after the state went stale cannot restore it" {
    printf '{"counts":{"completed":1,"restored":0},"latest":{},"history":[{"id":8,"status":"COMPLETED","latest_ack_timestamp":%d000,"external_path":"s3://flink/checkpoints/chk-8"}]}' \
        $(( B + 900 )) > "${WORK}/flink/checkpoints.json"
    bash "${WORK}/watchdog.sh" >/dev/null
    export WATCHDOG_NOW=$(( B + 720 ))
    run bash "${WORK}/watchdog.sh"
    consistency | grep -q "No checkpoint in Flink's recent checkpoint history was taken before the state went stale"
}

@test "without the job from Flink the consistency is not assessed, naming why" {
    bash "${WORK}/watchdog.sh" >/dev/null
    mv "${WORK}/flink/job.json" "${WORK}/flink/job.off"
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: unknown"* ]]
    consistency | grep -q "can't be assessed: Flink does not answer for the job 5ca51a5f717ed2d9a0c16efc2c820b3a. No inconsistency is raised or ended"
    export MOCK_JOB_ID=""
    run bash "${WORK}/watchdog.sh"
    consistency | grep -q "can't be assessed: the statementset reports no job"
}

@test "a kept inconsistency stays critical while Flink is down" {
    bash "${WORK}/watchdog.sh" >/dev/null
    WATCHDOG_NOW=$(( B + 720 )) bash "${WORK}/watchdog.sh" >/dev/null
    mv "${WORK}/flink/job.json" "${WORK}/flink/job.off"
    export WATCHDOG_NOW=$(( B + 740 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[critical] shacl-validation/ValidationConsistency"* ]]
    consistency | jq -e '.timeout == 0'
    consistency | grep -q "The consistency can't be checked again now: Flink does not answer"
}

@test "a KafkaConnector that can't be read for another reason posts nothing" {
    export MOCK_CONNECTOR_rdf_table_connector=ERROR
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"KafkaConnector rdf-table-connector not readable, ConnectorState not posted"* ]]
    run ! grep -q '"resource":"rdf-table-connector"' "${SINK_LOG}"
}

@test "a failed read of the Connect pods or their log is no answer: nothing is judged" {
    bash "${WORK}/watchdog.sh" >/dev/null
    export MOCK_CONNECT_PODS=ERROR
    export WATCHDOG_NOW=$(( B + 702 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: unknown"* ]]
    consistency | grep -q "can't be assessed: the Connect pods can't be listed"
    unset MOCK_CONNECT_PODS
    export MOCK_LOGS=ERROR
    run bash "${WORK}/watchdog.sh"
    consistency | grep -q "can't be assessed: the log of kafka-connect-connect-0 can't be read"
}

@test "a Connect pod still starting has no log yet, which is not unknown" {
    export MOCK_CONNECT_STARTING=yes
    export MOCK_LOGS=ERROR
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" != *"ValidationConsistency: unknown"* ]]
    # no refresh is known from a pod without a log
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: rebuilding"* ]]
}

@test "a JobManager restart seen through an unreadable run is still rebuilding" {
    bash "${WORK}/watchdog.sh" >/dev/null
    MOCK_JM=ERROR WATCHDOG_NOW=$(( B + 320 )) bash "${WORK}/watchdog.sh" >/dev/null
    export MOCK_JM_STARTED=$(( B + 310 ))
    export WATCHDOG_NOW=$(( B + 440 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: rebuilding since 2026-11-19T14:58:30Z"* ]]
}

@test "a job started from a checkpoint keeps its state: a latch does not end" {
    bash "${WORK}/watchdog.sh" >/dev/null
    WATCHDOG_NOW=$(( B + 720 )) bash "${WORK}/watchdog.sh" >/dev/null
    printf '{"state":"RUNNING","start-time":%d000}' $(( B + 800 )) > "${WORK}/flink/job.json"
    printf '{"counts":{"completed":1,"restored":1},"latest":{"restored":{"id":3,"restore_timestamp":%d000}},"history":[]}' $(( B + 801 )) > "${WORK}/flink/checkpoints.json"
    export WATCHDOG_NOW=$(( B + 820 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" != *"ended"* ]]
    [[ "${output}" == *"[critical] shacl-validation/ValidationConsistency"* ]]
}

@test "a failed read of the JobManager pod is no answer: nothing is judged" {
    export MOCK_JM_STARTED=$(( B + 300 ))
    WATCHDOG_NOW=$(( B + 320 )) bash "${WORK}/watchdog.sh" >/dev/null
    export MOCK_JM=ERROR
    export WATCHDOG_NOW=$(( B + 720 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: unknown"* ]]
    consistency | grep -q "the start of the Flink JobManager can't be read"
    run ! grep -q '"event":"ValidationConsistency".*"severity":"critical"' "${SINK_LOG}"
}

@test "a kubectl warning on stderr does not keep a failed connector from being reported" {
    export MOCK_KUBECTL_WARNING="Warning: couldn't get resource list for metrics.k8s.io/v1beta1"
    export MOCK_CONNECTOR_rdf_table_connector="RUNNING FAILED"
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[critical] rdf-table-connector/ConnectorState: RUNNING FAILED"* ]]
}

@test "a ConfigMap that can't be written is reported" {
    export MOCK_PATCH=FAIL
    run -0 --separate-stderr bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] platform-watchdog/WatchdogState: kept state not writable"* ]]
    run ! grep -q '"event":"WatchdogState".*"severity":"normal"' "${SINK_LOG}"
    run ! grep -q '"event":"ValidationConsistency"' "${SINK_LOG}"
}

@test "a KafkaConnector that does not exist warns" {
    export CONNECTORS="entity-table-connector no-such-connector"
    export MOCK_CONNECTOR_no_such_connector=MISSING
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] no-such-connector/ConnectorState: not found"* ]]
}

@test "an ended inconsistency is removed from the ConfigMap and does not come back" {
    bash "${WORK}/watchdog.sh" >/dev/null
    WATCHDOG_NOW=$(( B + 720 )) bash "${WORK}/watchdog.sh" >/dev/null
    jq -e 'has("latch_reason")' "${WORK}/state.json"
    failover $(( B + 1000 ))
    refresh $(( B + 1100 )) $(( B + 1105 ))
    WATCHDOG_NOW=$(( B + 1120 )) bash "${WORK}/watchdog.sh" >/dev/null
    jq -e 'has("latch_reason") | not' "${WORK}/state.json"
    # Flink answers nothing about failovers for a run: the latch stays gone
    printf '' > "${WORK}/flink/exceptions.json"
    export WATCHDOG_NOW=$(( B + 1240 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" != *"[critical] shacl-validation/ValidationConsistency"* ]]
}

@test "an empty answer from Flink is no answer: the consistency is not assessed" {
    failover $(( B + 300 ))
    WATCHDOG_NOW=$(( B + 320 )) bash "${WORK}/watchdog.sh" >/dev/null
    printf '' > "${WORK}/flink/exceptions.json"
    export WATCHDOG_NOW=$(( B + 340 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: unknown"* ]]
    jq -e '.reset == "1795100300"' "${WORK}/state.json"
}

@test "once Flink answers again after longer than the gap limit the watchdog observes anew" {
    export RUN_GAP=150
    WATCHDOG_NOW=$(( B + 200 )) bash "${WORK}/watchdog.sh" >/dev/null
    mv "${WORK}/flink/job.json" "${WORK}/flink/job.off"
    for t in 320 440 560 680; do WATCHDOG_NOW=$(( B + t )) bash "${WORK}/watchdog.sh" >/dev/null; done
    refresh $(( B + 750 )) $(( B + 760 ))
    mv "${WORK}/flink/job.off" "${WORK}/flink/job.json"
    export WATCHDOG_NOW=$(( B + 800 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"could not be read since 2026-11-19T14:58:40Z: observing anew"* ]]
    [[ "${output}" == *"[normal] shacl-validation/ValidationConsistency: consistent"* ]]
}

@test "one unreadable run is like a skipped run: a window missed across it is still found" {
    export RUN_GAP=150
    for t in 200 320 440 560; do WATCHDOG_NOW=$(( B + t )) bash "${WORK}/watchdog.sh" >/dev/null; done
    MOCK_LOGS=ERROR WATCHDOG_NOW=$(( B + 680 )) bash "${WORK}/watchdog.sh" >/dev/null
    refresh $(( B + 690 )) $(( B + 760 ))
    export WATCHDOG_NOW=$(( B + 800 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" != *"observing anew"* ]]
    [[ "${output}" == *"[critical] shacl-validation/ValidationConsistency"* ]]
}

@test "a gap in the watchdog's own runs starts the history anew instead of latching" {
    unset RUN_GAP
    bash "${WORK}/watchdog.sh" >/dev/null
    : > "${WORK}/connect.log"
    refresh $(( B + 750 )) $(( B + 760 ))
    export WATCHDOG_NOW=$(( B + 800 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"no run since 2026-11-19T14:56:40Z: the refreshes in between are unknown, observing anew"* ]]
    [[ "${output}" == *"[normal] shacl-validation/ValidationConsistency: consistent"* ]]
}

@test "a refresh older than the ttl before the watchdog observed is not latched at once" {
    printf '{"observing_since":"%d"}' $(( B + 800 )) > "${WORK}/state.json"
    export WATCHDOG_NOW=$(( B + 800 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" != *"[critical] shacl-validation/ValidationConsistency"* ]]
    export WATCHDOG_NOW=$(( B + 1500 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[critical] shacl-validation/ValidationConsistency"* ]]
}

@test "a state emptied before the watchdog observed becomes inconsistent a ttl after it began" {
    printf '{"observing_since":"%d"}' $(( B + 50 )) > "${WORK}/state.json"
    : > "${WORK}/connect.log"
    WATCHDOG_NOW=$(( B + 100 )) bash "${WORK}/watchdog.sh" >/dev/null
    export WATCHDOG_NOW=$(( B + 620 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: no refresh seen yet"* ]]
    consistency | grep -q 'NOT ASSESSED YET: no complete refresh of entity-table-connector, rdf-table-connector seen since the watchdog began observing at 2026-11-19T14:54:10Z'
    export WATCHDOG_NOW=$(( B + 700 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[critical] shacl-validation/ValidationConsistency"* ]]
}

@test "an error answer from Flink is no answer either" {
    failover $(( B + 300 ))
    WATCHDOG_NOW=$(( B + 320 )) bash "${WORK}/watchdog.sh" >/dev/null
    printf '{"errors":["Service temporarily unavailable"]}' > "${WORK}/flink/exceptions.json"
    export WATCHDOG_NOW=$(( B + 340 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[warning] shacl-validation/ValidationConsistency: unknown"* ]]
    jq -e '.reset == "1795100300"' "${WORK}/state.json"
}

@test "a refresh before the watchdog observed is not the start of a gap" {
    printf '{"observing_since":"%d"}' $(( B + 800 )) > "${WORK}/state.json"
    WATCHDOG_NOW=$(( B + 800 )) bash "${WORK}/watchdog.sh" >/dev/null
    refresh $(( B + 900 )) $(( B + 905 ))
    export WATCHDOG_NOW=$(( B + 920 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[normal] shacl-validation/ValidationConsistency: consistent"* ]]
}

@test "no refresh within the ttl after the state was emptied is inconsistent" {
    : > "${WORK}/connect.log"
    export WATCHDOG_NOW=$(( B + 700 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[critical] shacl-validation/ValidationConsistency"* ]]
    consistency | grep -q 'no complete refresh since the state was emptied at 2026-11-19T14:53:20Z'
}

@test "installed on a running platform, the time before it observed is not judged" {
    printf '{"observing_since":"%d"}' $(( B + 5000 )) > "${WORK}/state.json"
    : > "${WORK}/connect.log"
    refresh $(( B + 4900 )) $(( B + 4905 ))
    export WATCHDOG_NOW=$(( B + 5000 ))
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[normal] shacl-validation/ValidationConsistency: consistent"* ]]
}

@test "without its ConfigMap the watchdog does not judge, leaves the alert as it was and warns" {
    rm "${WORK}/state.json"
    run -0 --separate-stderr bash "${WORK}/watchdog.sh"
    # shellcheck disable=SC2154  # stderr is assigned by run --separate-stderr
    [[ "${stderr}" == *"configmap platform-watchdog-state not readable: the consistency is not judged"* ]]
    [[ "${output}" == *"[warning] platform-watchdog/WatchdogState: kept state not readable"* ]]
    run ! grep -q '"event":"ValidationConsistency"' "${SINK_LOG}"
    run ! grep -q "patch configmap" "${MOCK_LOG}"
    printf '{"observing_since":"%d"}' $(( B - 10 )) > "${WORK}/state.json"
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[normal] platform-watchdog/WatchdogState"* ]]
}

@test "a failed connector task is critical, and normal again once it runs" {
    export MOCK_CONNECTOR_rdf_table_connector="RUNNING FAILED"
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[critical] rdf-table-connector/ConnectorState: RUNNING FAILED"* ]]
    grep -q '"resource":"rdf-table-connector","event":"ConnectorState".*"severity":"critical"' "${SINK_LOG}"
    export MOCK_CONNECTOR_rdf_table_connector="RUNNING RUNNING"
    run bash "${WORK}/watchdog.sh"
    [[ "${output}" == *"[normal] rdf-table-connector/ConnectorState: RUNNING RUNNING"* ]]
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
    [[ "${output}" == *"[normal] mqtt-bridge/BridgeHealth"* ]]
}
