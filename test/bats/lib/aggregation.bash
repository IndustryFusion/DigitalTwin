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
# Sends a batch of attributes to Core Services and captures the ngsild-updates
# it forwards for them, waiting for conditions instead of fixed times.
#
# Core Services aggregates attributes into one update per entity and per Kafka
# record timestamp: the ngsild_updates statement tumbles over `ts` with a
# window of one millisecond (CoreServices sql_statements.sql). kafkacat stamps
# every record when it produces it and has no option to set the timestamp, so
# the lines of one batch share a window only when kafkacat sends them within
# the same millisecond. On a loaded runner it does not always, the batch is
# split over two windows and two updates are forwarded (#1060): the test failed
# although Core Services aggregated correctly. So the batch is read back from
# the attributes topic, and when its records carry more than one timestamp the
# precondition of the test is not met: the batch is sent again instead of
# being judged.
#
# A window is closed by the watermark of a later record. Markers, attributes of
# an entity of their own, are sent until the update of a marker comes back.
# The first marker closes the window of the batch, a later one the window of
# the first marker; Core Services runs with parallelism 1 and the topic has
# one partition, so once a marker's update is captured, every update of the
# batch is captured before it. Marker entity ids contain "flush", so the tests
# drop them with `grep -v flush`.

: "${KAFKA_BOOTSTRAP:=my-cluster-kafka-bootstrap:9092}"
: "${ATTRIBUTES_TOPIC:=iff.ngsild.attributes}"
: "${KAFKACAT_NGSILD_UPDATES_TOPIC:=iff.ngsild-updates}"
: "${KAFKACAT_ATTRIBUTES:=/tmp/KAFKACAT_ATTRIBUTES}"     # the captured updates
: "${AGGREGATION_WORK:=/tmp/aggregation}"               # batch, read back, logs
: "${AGGREGATION_TIMEOUT:=60}"                          # seconds, per wait
: "${AGGREGATION_ATTEMPTS:=3}"                          # sends of a split batch
: "${AGGREGATION_POLL:=0.2}"                            # seconds between polls
: "${AGGREGATION_ALONE_TIMEOUT:=10}"                    # seconds, aggregate_alone

# kafka_tail: the last records of a topic, also after retention (#1200)
# shellcheck source=/dev/null  # checked on its own
. "$(dirname "${BASH_SOURCE[0]}")/kafka.bash"

# wait_until <seconds> <command...>: true as soon as the command is, false when
# it is still false after <seconds>.
wait_until() {
    local deadline=$((SECONDS + $1))
    shift
    until "$@"; do
        [ "${SECONDS}" -lt "${deadline}" ] || return 1
        sleep "${AGGREGATION_POLL}"
    done
}

# reached_end <stderr file of a kafkacat consumer>: it is positioned at the end
# of its topic, so it misses nothing produced from now on.
reached_end() {
    grep -q 'Reached end of topic' "$1"
}

# batch_timestamps: the record timestamps of the batch lines read back from
# the attributes topic, one per line.
batch_timestamps() {
    awk 'NR == FNR { want[$0] = 1; next }
         { tab = index($0, "\t"); if (substr($0, tab + 1) in want) print substr($0, 1, tab - 1) }' \
        "${AGGREGATION_WORK}/batch" "${AGGREGATION_WORK}/read-back"
}

batch_read_back() {
    [ "$(batch_timestamps | wc -l)" -ge "$(wc -l < "${AGGREGATION_WORK}/batch")" ]
}

# marker <entity id>: one attribute of that entity, as a line.
marker() {
    printf '{"id":"%s\\\\https://industry-fusion.com/types/v0.9/flush","entityId":"%s","name":"https://industry-fusion.com/types/v0.9/flush","type":"https://uri.etsi.org/ngsi-ld/Property","attributeValue":"flush"}\n' "$1" "$1"
}

# close_windows <marker entity id>: sends markers until the update of one is
# captured, at most AGGREGATION_TIMEOUT seconds.
close_windows() {
    local deadline=$((SECONDS + AGGREGATION_TIMEOUT))
    # the id with its closing quote, escaped as it is inside "entities"
    until grep -qF "${1}\\\"" "${KAFKACAT_ATTRIBUTES}"; do
        [ "${SECONDS}" -lt "${deadline}" ] || return 1
        marker "$1" | kafkacat -P -t "${ATTRIBUTES_TOPIC}" -b "${KAFKA_BOOTSTRAP}"
        sleep 0.5
    done
}

start_consumers() {
    : > "${KAFKACAT_ATTRIBUTES}"
    : > "${AGGREGATION_WORK}/read-back"
    (exec stdbuf -oL kafkacat -C -t "${KAFKACAT_NGSILD_UPDATES_TOPIC}" -b "${KAFKA_BOOTSTRAP}" -o end \
        >"${KAFKACAT_ATTRIBUTES}" 2>"${AGGREGATION_WORK}/updates.log" 3>&-) &
    AGGREGATION_UPDATES_PID=$!
    (exec stdbuf -oL kafkacat -C -t "${ATTRIBUTES_TOPIC}" -b "${KAFKA_BOOTSTRAP}" -o end -f '%T\t%s\n' \
        >"${AGGREGATION_WORK}/read-back" 2>"${AGGREGATION_WORK}/read-back.log" 3>&-) &
    AGGREGATION_READ_BACK_PID=$!
    wait_until "${AGGREGATION_TIMEOUT}" reached_end "${AGGREGATION_WORK}/updates.log" &&
        wait_until "${AGGREGATION_TIMEOUT}" reached_end "${AGGREGATION_WORK}/read-back.log"
}

stop_consumers() {
    [ -n "${AGGREGATION_UPDATES_PID:-}" ] || return 0
    kill "${AGGREGATION_UPDATES_PID}" "${AGGREGATION_READ_BACK_PID}" 2>/dev/null
    wait "${AGGREGATION_UPDATES_PID}" "${AGGREGATION_READ_BACK_PID}" 2>/dev/null
    return 0
}

# aggregation_failed <message>: says why, with what the consumers saw.
aggregation_failed() {
    stop_consumers
    echo "# $1" >&3
    local f
    for f in updates.log read-back.log read-back; do
        echo "# ${f}:" >&3
        sed 's/^/#   /' "${AGGREGATION_WORK}/${f}" >&3
    done
    show_capture
    return 1
}

# show_capture: prints the updates captured from the ngsild-updates topic.
show_capture() {
    echo "# captured from ${KAFKACAT_NGSILD_UPDATES_TOPIC}:" >&3
    sed 's/^/#   /' "${KAFKACAT_ATTRIBUTES}" >&3
}

# aggregate [--prelude <file>] <file>...: sends the lines of the files as one
# batch to the attributes topic and leaves the updates Core Services forwards
# for it in KAFKACAT_ATTRIBUTES. The prelude, if given, is sent first and on
# its own, after the consumers are positioned.
aggregate() {
    local prelude='' attempt stamps
    if [ "$1" = "--prelude" ]; then
        prelude=$2
        shift 2
    fi
    mkdir -p "${AGGREGATION_WORK}"
    grep -h . "$@" > "${AGGREGATION_WORK}/batch"
    for attempt in $(seq "${AGGREGATION_ATTEMPTS}"); do
        start_consumers ||
            { aggregation_failed "a consumer did not reach the end of its topic within ${AGGREGATION_TIMEOUT}s"; return 1; }
        if [ -n "${prelude}" ]; then
            kafkacat -P -t "${ATTRIBUTES_TOPIC}" -b "${KAFKA_BOOTSTRAP}" < "${prelude}"
        fi
        kafkacat -P -t "${ATTRIBUTES_TOPIC}" -b "${KAFKA_BOOTSTRAP}" < "${AGGREGATION_WORK}/batch"
        # Read back before the first marker is sent: the marker then is
        # produced after the batch arrived, so it is stamped later.
        wait_until "${AGGREGATION_TIMEOUT}" batch_read_back ||
            { aggregation_failed "the batch was not read back from ${ATTRIBUTES_TOPIC} within ${AGGREGATION_TIMEOUT}s"; return 1; }
        close_windows "urn:flush-test:${BATS_TEST_NUMBER:-0}-${attempt}-$$" ||
            { aggregation_failed "no update of a marker came back within ${AGGREGATION_TIMEOUT}s"; return 1; }
        stop_consumers
        stamps=$(batch_timestamps | sort -u | tr '\n' ' ')
        if [ "$(wc -w <<< "${stamps}")" -eq 1 ]; then
            return 0
        fi
        echo "# attempt ${attempt}: kafkacat stamped the batch with the timestamps ${stamps}so it spans several aggregation windows; it is sent again" >&3
    done
    show_capture
    echo "# kafkacat did not send the batch within one millisecond in ${AGGREGATION_ATTEMPTS} attempts" >&3
    return 1
}

# aggregate_alone <entity id> <file>: sends the lines of the file as one batch
# and sends nothing after it: no marker closes its window. Core Services'
# watermark catches up with the last record after a quiet period of one second
# (IdleCatchUpWatermarks), so the update of the entity must come back within
# AGGREGATION_ALONE_TIMEOUT seconds anyway (#1060). The update is in
# KAFKACAT_ATTRIBUTES. Fails as well when another record reached the attributes
# topic before the update came back: that record, not the quiet period, may
# have closed the window, so the run proves nothing.
aggregate_alone() {
    local id=$1 file=$2
    mkdir -p "${AGGREGATION_WORK}"
    grep -h . "${file}" > "${AGGREGATION_WORK}/batch"
    start_consumers ||
        { aggregation_failed "a consumer did not reach the end of its topic within ${AGGREGATION_TIMEOUT}s"; return 1; }
    kafkacat -P -t "${ATTRIBUTES_TOPIC}" -b "${KAFKA_BOOTSTRAP}" < "${AGGREGATION_WORK}/batch"
    # the id with its closing quote, escaped as it is inside "entities"
    wait_until "${AGGREGATION_ALONE_TIMEOUT}" grep -qF "${id}\\\"" "${KAFKACAT_ATTRIBUTES}" ||
        { aggregation_failed "no update of ${id} came back within ${AGGREGATION_ALONE_TIMEOUT}s without a later record"; return 1; }
    # A record that closed the window was on the topic before the update came
    # back, so the last record of the topic decides, not the read-back
    # consumer, which may lag behind.
    kafka_tail "${ATTRIBUTES_TOPIC}" 1 -q -f '%s\n' > "${AGGREGATION_WORK}/last" 2>/dev/null
    stop_consumers
    [ "$(tail -n1 "${AGGREGATION_WORK}/batch")" = "$(cat "${AGGREGATION_WORK}/last")" ] ||
        { aggregation_failed "another record reached ${ATTRIBUTES_TOPIC} before the update came back: $(cat "${AGGREGATION_WORK}/last")"; return 1; }
}
