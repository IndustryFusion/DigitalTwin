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
# The waits of test/bats/lib/kafka.bash, used by
# test-core-sql-services/test-alerta-bulk-filter.bats, against a mocked
# kafkacat: a topic is a file, and the broker answers only once
# MOCK_KAFKA/up exists, as Kafka does once kubefwd's listener runs. A
# consumer that finds the broker down exits, as kafkacat does with "All
# broker connections are down" (#1060).

bats_require_minimum_version 1.5.0

setup() {
    WORK="$(mktemp -d)"
    export MOCK_KAFKA="${WORK}/kafka"
    mkdir -p "${MOCK_KAFKA}" "${WORK}/bin"
    cat > "${WORK}/bin/kafkacat" <<'EOF'
#!/usr/bin/env bash
mode='' topic='' eof=false
while [ $# -gt 0 ]; do
    case "$1" in
        -C|-P|-L) mode=$1 ;;
        -t) topic=$2; shift ;;
        -e) eof=true ;;
        -b|-o|-f) shift ;;
    esac
    shift
done
if [ ! -e "${MOCK_KAFKA}/up" ]; then
    echo "% ERROR: Local: All broker connections are down: 1/1 brokers are down: terminating" >&2
    exit 1
fi
log="${MOCK_KAFKA}/${topic}"
touch "${log}"
case "${mode}" in
    -L) printf '  topic "%s" with 1 partitions:\n    partition 0, leader 0, replicas: 0, isrs: 0\n' "${topic}" ;;
    -P) cat >> "${log}" ;;
    -C)
        "${eof}" && exit 0
        trap 'pkill -P $$; exit 0' TERM
        tail -n0 -F "${log}" 2>/dev/null &
        sleep 0.2
        echo "% Reached end of topic ${topic} [0] at offset 0" >&2
        wait ;;
esac
EOF
    chmod +x "${WORK}/bin/kafkacat"
    PATH="${WORK}/bin:${PATH}"
    export AGGREGATION_POLL=0.05
    CAPTURE="${WORK}/captured"
    # shellcheck source=/dev/null  # checked on its own
    source "${BATS_TEST_DIRNAME}/../bats/lib/aggregation.bash"
    # shellcheck source=/dev/null  # checked on its own
    source "${BATS_TEST_DIRNAME}/../bats/lib/kafka.bash"
}

teardown() {
    stop_capture
    pkill -f "tail -n0 -F ${MOCK_KAFKA}" 2>/dev/null || true
    rm -rf "${WORK}"
}

produce() {
    printf '%s\n' "$@" | kafkacat -P -t iff.alerts
}

@test "wait_for_kafka waits until the forward answers" {
    ( sleep 1; touch "${MOCK_KAFKA}/up" ) &
    wait_for_kafka iff.alerts iff.alerts.bulk 3>"${WORK}/messages"
    [ ! -s "${WORK}/messages" ]
}

@test "wait_for_kafka fails within its bound and shows kafkacat's error" {
    status=0
    start=${SECONDS}
    KAFKA_READY_TIMEOUT=2 wait_for_kafka iff.alerts 3>"${WORK}/messages" || status=$?
    [ "${status}" -eq 1 ]
    [ $((SECONDS - start)) -lt 10 ]
    grep -q 'did not serve iff.alerts within 2s' "${WORK}/messages"
    grep -q 'All broker connections are down' "${WORK}/messages"
}

@test "the capture is at the end before the test produces, and waits for the expected records" {
    touch "${MOCK_KAFKA}/up"
    start_capture iff.alerts "${CAPTURE}" 3>"${WORK}/messages"
    produce '{"severity":"flush"}' '{"severity":"ok"}' '' '{"severity":"warning"}'
    ( sleep 1; produce '{"severity":"ok"}' ) &
    wait_for_records "${CAPTURE}" 3 0 3>>"${WORK}/messages"
    [ "$(count_records "${CAPTURE}")" -eq 3 ]
    grep -q 'captured 3 records, 3 expected' "${WORK}/messages"
    [ "${#CAPTURE_PIDS[@]}" -eq 0 ]
    run ! pgrep -f "tail -n0 -F ${MOCK_KAFKA}/iff.alerts"
}

@test "a record too many within the settle time reaches the comparison" {
    touch "${MOCK_KAFKA}/up"
    start_capture iff.alerts "${CAPTURE}" 3>/dev/null
    produce '{"severity":"ok"}'
    ( sleep 0.5; produce '{"severity":"critical"}' ) &
    wait_for_records "${CAPTURE}" 1 2 3>/dev/null
    [ "$(count_records "${CAPTURE}")" -eq 2 ]
}

@test "too few records end the wait within its bound and say how many came" {
    touch "${MOCK_KAFKA}/up"
    start_capture iff.alerts "${CAPTURE}" 3>/dev/null
    produce '{"severity":"ok"}'
    start=${SECONDS}
    CAPTURE_TIMEOUT=2 wait_for_records "${CAPTURE}" 5 0 3>"${WORK}/messages"
    [ $((SECONDS - start)) -lt 10 ]
    grep -q 'captured 1 records, 5 expected, within 2s' "${WORK}/messages"
}

@test "a consumer that gave up fails the start and needs no killall" {
    status=0
    start=${SECONDS}
    CAPTURE_TIMEOUT=20 start_capture iff.alerts "${CAPTURE}" 3>"${WORK}/messages" || status=$?
    [ "${status}" -eq 1 ]
    # at once, not after the time limit
    [ $((SECONDS - start)) -lt 10 ]
    grep -q 'exited or did not reach the end of it within 20s' "${WORK}/messages"
    grep -q 'All broker connections are down' "${WORK}/messages"
    stop_capture
}

@test "the bulk filter suite waits for Kafka and its alerts, with no killall left" {
    suite="${BATS_TEST_DIRNAME}/../bats/test-core-sql-services/test-alerta-bulk-filter.bats"
    grep -qE '^\s*wait_for_kafka ' "${suite}"
    grep -qE '^\s*start_capture ' "${suite}"
    grep -qE '^\s*wait_for_records \S+ 5 ' "${suite}"
    run grep -nE 'killall kafkacat' "${suite}"
    [ "${status}" -eq 1 ]
}
