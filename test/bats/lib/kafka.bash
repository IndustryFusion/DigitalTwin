#!/usr/bin/env bash
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
# Waiting on Kafka through kubefwd and on a captured topic, instead of fixed
# sleeps. Load lib/aggregation.bash first: this uses its wait_until and
# reached_end.
#
# kubefwd logs a port-forward before its listener accepts connections; on a
# loaded runner the gap was long enough that the first consumer of a suite
# found the broker refusing, gave up ("All broker connections are down") and
# the test then failed at a killall of a kafkacat that no longer ran (#1060).

: "${KAFKA_BOOTSTRAP:=my-cluster-kafka-bootstrap:9092}"
: "${KAFKA_READY_TIMEOUT:=60}"     # seconds until Kafka answers through the forward
: "${CAPTURE_TIMEOUT:=60}"         # seconds, per wait of a capture
CAPTURE_PIDS=()

# kafka_serves <topic>: the metadata names a leader for the topic, and a
# consumer reaches its end, which needs the broker itself, not only the
# bootstrap service.
kafka_serves() {
    timeout 10 kafkacat -L -b "${KAFKA_BOOTSTRAP}" -t "$1" 2>/dev/null \
        | grep -q "partition 0, leader [0-9]" &&
        timeout 10 kafkacat -C -b "${KAFKA_BOOTSTRAP}" -t "$1" -o end -e -q >/dev/null 2>&1
}

# wait_for_kafka <topic>...: true once Kafka serves every topic, false (and
# says so) when it still does not after KAFKA_READY_TIMEOUT seconds.
wait_for_kafka() {
    local topic
    for topic in "$@"; do
        wait_until "${KAFKA_READY_TIMEOUT}" kafka_serves "${topic}" || {
            echo "# Kafka at ${KAFKA_BOOTSTRAP} did not serve ${topic} within ${KAFKA_READY_TIMEOUT}s:" >&3
            timeout 10 kafkacat -L -b "${KAFKA_BOOTSTRAP}" -t "${topic}" 2>&1 | tail -3 | sed 's/^/#   /' >&3
            return 1
        }
    done
}

# start_capture <topic> <file> [kafkacat option]...: consumes the topic from
# its end into the file, its messages into <file>.err, and returns once the
# consumer is positioned at the end, so it misses nothing produced from now on.
start_capture() {
    local topic=$1 file=$2
    shift 2
    : > "${file}"
    : > "${file}.err"
    (exec stdbuf -oL kafkacat -C -t "${topic}" -b "${KAFKA_BOOTSTRAP}" -o end "$@" \
        >"${file}" 2>"${file}.err" 3>&-) &
    CAPTURE_PIDS+=("$!")
    if wait_until "${CAPTURE_TIMEOUT}" capture_settled "$!" "${file}.err" &&
            reached_end "${file}.err"; then
        return 0
    fi
    echo "# the consumer of ${topic} exited or did not reach the end of it within ${CAPTURE_TIMEOUT}s" >&3
    print_capture "${file}"
    return 1
}

# capture_settled <pid> <stderr file>: the consumer reached the end, or it
# exited and will not.
capture_settled() {
    reached_end "$2" || ! kill -0 "$1" 2>/dev/null
}

# stop_capture: stops the consumers start_capture launched that still run; one
# that already exited is no error, unlike for a killall.
stop_capture() {
    local pid
    for pid in "${CAPTURE_PIDS[@]}"; do
        kill "${pid}" 2>/dev/null && wait "${pid}" 2>/dev/null
    done
    CAPTURE_PIDS=()
    return 0
}

# count_records <file>: the captured records the suites compare, those that are
# neither empty nor a flush.
count_records() {
    grep -v flush "$1" | grep -cv '^$' || true
}

has_records() {
    [ "$(count_records "$1")" -ge "$2" ]
}

# wait_for_records <file> <count> <settle>: waits until the file holds at least
# <count> records, at most CAPTURE_TIMEOUT seconds, then <settle> seconds more
# so that a record too many still reaches the comparison, and stops the
# consumers. The comparison decides; this only says when the capture is done.
wait_for_records() {
    local start=${SECONDS}
    if wait_until "${CAPTURE_TIMEOUT}" has_records "$1" "$2"; then
        sleep "$3"
        echo "# captured $(count_records "$1") records, $2 expected, after $((SECONDS - start))s" >&3
    else
        echo "# captured $(count_records "$1") records, $2 expected, within ${CAPTURE_TIMEOUT}s" >&3
    fi
    stop_capture
}

# print_capture <file>: what was captured, and what the consumer reported.
print_capture() {
    echo "# captured in $1:" >&3
    sed 's/^/#   /' "$1" >&3 2>/dev/null
    echo "# consumer messages:" >&3
    sed 's/^/#   /' "$1.err" >&3 2>/dev/null
    return 0
}
