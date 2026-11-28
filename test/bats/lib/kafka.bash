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
# Reads of the last records of a Kafka topic (#1200).
#
# `kafkacat -o -<n>` asks for the offset n before the end. When retention has
# moved the topic's start past that offset, librdkafka resets it by
# auto.offset.reset, which kafkacat leaves at the end: with -e the read ends
# at once, empty, with status 0. A long-lived topic hits this often (on k3d,
# iff.alerts.bulk kept 3,113 of its 1,229,035 records), and so does a CI run
# of more than an hour. kafka_tail falls back to the earliest record the topic
# still holds, so it reads what is there.

: "${KAFKA_BOOTSTRAP:=my-cluster-kafka-bootstrap:9092}"
: "${KAFKA_TAIL_TIMEOUT:=30}"   # seconds; timeout(1) can't run a shell function

# kafka_tail <topic> <n> [kafkacat options...]: the last n records of the
# topic, or every record it holds when it holds fewer; to its end (-e),
# within KAFKA_TAIL_TIMEOUT seconds.
kafka_tail() {
    local topic=$1 n=$2
    shift 2
    timeout "${KAFKA_TAIL_TIMEOUT}" kafkacat -C -t "${topic}" -b "${KAFKA_BOOTSTRAP}" -o "-${n}" -e \
        -X auto.offset.reset=earliest "$@"
}
