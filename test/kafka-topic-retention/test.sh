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
# Does a busy topic keep records only about as long as its retention.ms?
# Kafka deletes only whole segments, and only once the newest record in a
# segment is older than retention.ms. The charts set segment.ms to
# max(retention.ms, 1 h), so the oldest record is at most
# retention.ms + segment.ms + log.retention.check.interval.ms old. Two topics,
# written to once a second, on the Kafka version the platform deploys, with
# the times scaled down from hours to seconds:
#   rolled  - retention.ms = segment.ms = RETENTION_MS (what the charts declare
#             for a topic with a retention of 1 h or more)
#   default - retention.ms = RETENTION_MS, segment.ms left at the default
# The rolled topic must lose its old records, the default one must not: that
# is the behaviour the charts rely on, and it shows the test can fail.
# Needs only Docker.
set -euo pipefail

IMAGE=${IMAGE:-apache/kafka:3.9.0}
CONTAINER=${CONTAINER:-kafka-topic-retention}
RETENTION_MS=${RETENTION_MS:-10000}
CHECK_INTERVAL_MS=${CHECK_INTERVAL_MS:-1000}
RUN_S=${RUN_S:-45}
BIN=/opt/kafka/bin
BOOTSTRAP=localhost:9092

cleanup() { docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

docker run -d --name "${CONTAINER}" \
    -e KAFKA_NODE_ID=1 \
    -e KAFKA_PROCESS_ROLES=broker,controller \
    -e KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \
    -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
    -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
    -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT \
    -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
    -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
    -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
    -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
    -e KAFKA_LOG_RETENTION_CHECK_INTERVAL_MS="${CHECK_INTERVAL_MS}" \
    -e KAFKA_HEAP_OPTS=-Xmx512M \
    "${IMAGE}" >/dev/null

kafka() { docker exec "${CONTAINER}" "$@" </dev/null; }

for _ in $(seq 60); do
    kafka "${BIN}/kafka-topics.sh" --bootstrap-server "${BOOTSTRAP}" --list >/dev/null 2>&1 && break
    sleep 1
done

kafka "${BIN}/kafka-topics.sh" --bootstrap-server "${BOOTSTRAP}" --create --topic rolled \
    --config "retention.ms=${RETENTION_MS}" --config "segment.ms=${RETENTION_MS}" >/dev/null
kafka "${BIN}/kafka-topics.sh" --bootstrap-server "${BOOTSTRAP}" --create --topic default \
    --config "retention.ms=${RETENTION_MS}" >/dev/null

# One record a second to both topics, from one producer each. They keep
# writing while the ages are read, as the platform's topics do, so the open
# segment always holds fresh records.
pids=()
for topic in rolled default; do
    (for i in $(seq $(( RUN_S + 60 ))); do echo "${i}"; sleep 1; done) \
        | docker exec -i "${CONTAINER}" "${BIN}/kafka-console-producer.sh" --bootstrap-server "${BOOTSTRAP}" --topic "${topic}" &
    pids+=("$!")
done
sleep "${RUN_S}"

offset() {
    kafka "${BIN}/kafka-get-offsets.sh" --bootstrap-server "${BOOTSTRAP}" --topic "$1" --time "$2" | cut -d: -f3
}

# Age of the oldest record still in the topic, in ms. Read
# from the broker's own segment files, the oldest one first: a segment Kafka
# has deleted is renamed to *.deleted at once, so every *.log is still in the
# topic. No consumer, so no group or fetch timing in the way.
oldest_age_ms() {
    local now ts
    for _ in 1 2 3; do
        now=$(date +%s%3N)
        ts=$(kafka sh -c "f=\$(ls /tmp/kafka-logs/$1-0/*.log | sort | head -1); ${BIN}/kafka-dump-log.sh --files \$f" \
            | sed -n '/CreateTime: /{s/.*CreateTime: \([0-9]*\).*/\1/p;q;}' || true)
        [ -n "${ts}" ] && { echo $(( now - ts )); return; }
    done
    echo "could not read the oldest record of $1" >&2
    return 1
}

for topic in rolled default; do
    echo "${topic}: offsets $(offset "${topic}" -2) to $(offset "${topic}" -1)"
done
bound_ms=$(( 2 * RETENTION_MS + CHECK_INTERVAL_MS + 5000 ))
rolled=$(oldest_age_ms rolled)
default=$(oldest_age_ms default)
kill "${pids[@]}" 2>/dev/null || true
echo "oldest record: rolled ${rolled} ms, default ${default} ms, bound ${bound_ms} ms"

if [ "${rolled}" -gt "${bound_ms}" ]; then
    echo "FAIL: the topic with segment.ms = retention.ms kept a record past retention plus one segment"
    exit 1
fi
if [ "${default}" -le "${bound_ms}" ]; then
    echo "FAIL: the topic with the default segment.ms lost its records too; the test shows nothing"
    exit 1
fi
echo "OK"
