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
# The capture of test/bats/lib/aggregation.bash, used by
# test-core-sql-services/test-ngsildUpdate-aggregation.bats, against a mocked
# kafkacat: topics are files of "timestamp TAB payload" lines, and a stand-in
# for Core Services forwards one update per entity and per millisecond window
# as soon as a later record closes the window, as the ngsild_updates statement
# does. The producer stamps all lines of one call with one millisecond unless
# MOCK_SPLIT_BATCHES says to split the next multi-line calls over two, which is
# what kafkacat does now and then on a loaded runner (#1060).

bats_require_minimum_version 1.5.0

setup() {
    WORK="$(mktemp -d)"
    export MOCK_KAFKA="${WORK}/kafka"
    mkdir -p "${MOCK_KAFKA}" "${WORK}/bin"
    echo 1000 > "${MOCK_KAFKA}/clock"
    cat > "${WORK}/bin/kafkacat" <<'EOF'
#!/usr/bin/env bash
mode='' topic='' fmt='' offset='' exit_at_end=''
while [ $# -gt 0 ]; do
    case "$1" in
        -C|-P) mode=$1 ;;
        -t) topic=$2; shift ;;
        -f) fmt=$2; shift ;;
        -o) offset=$2; shift ;;
        -e) exit_at_end=1 ;;
        -b) shift ;;
    esac
    shift
done
log="${MOCK_KAFKA}/${topic}"
touch "${log}"
if [ "${mode}" = "-C" ] && [ -n "${exit_at_end}" ] && [ "${offset}" = "-1" ]; then
    # the last record, then exit
    tail -n1 "${log}" | cut -f2-
    exit 0
fi
if [ "${mode}" = "-C" ]; then
    trap 'pkill -P $$; exit 0' TERM
    if [ -n "${fmt}" ]; then
        tail -n0 -F "${log}" 2>/dev/null &
    else
        tail -n0 -F "${log}" 2>/dev/null | cut -f2- &
    fi
    sleep 0.2
    echo "% Reached end of topic ${topic} [0] at offset 0" >&2
    wait
    exit 0
fi
# producer: one millisecond per call, later than every earlier call
clock=$(( $(cat "${MOCK_KAFKA}/clock") + 10 ))
echo "${clock}" > "${MOCK_KAFKA}/clock"
mapfile -t lines
split=0
if [ "${#lines[@]}" -gt 1 ]; then
    done_splits=$(cat "${MOCK_KAFKA}/splits" 2>/dev/null || echo 0)
    if [ "${done_splits}" -lt "${MOCK_SPLIT_BATCHES:-0}" ]; then
        split=1
        echo $((done_splits + 1)) > "${MOCK_KAFKA}/splits"
    fi
fi
for i in "${!lines[@]}"; do
    ts=${clock}
    [ "${split}" -eq 1 ] && [ "${i}" -eq $(( ${#lines[@]} - 1 )) ] && ts=$((clock + 1))
    if [ "${topic}" = "iff.ngsild.attributes" ] && [ "${MOCK_CORE_SERVICES:-on}" = "on" ]; then
        # the watermark passes every window before ts: forward them
        pending="${MOCK_KAFKA}/pending"
        touch "${pending}"
        awk -F'\t' -v ts="${ts}" '$1 < ts' "${pending}" | sort -n | uniq -c |
        while read -r n wts entity; do
            printf '%s\t{"op":"update","entities":"[{\\"id\\":\\"%s\\",\\"n\\":%s}]"}\n' \
                "${wts}" "${entity}" "${n}" >> "${MOCK_KAFKA}/iff.ngsild-updates"
        done
        awk -F'\t' -v ts="${ts}" '$1 >= ts' "${pending}" > "${pending}.new"
        mv "${pending}.new" "${pending}"
        printf '%s\t%s\n' "${ts}" "$(jq -r .entityId <<< "${lines[$i]}")" >> "${pending}"
    fi
    printf '%s\t%s\n' "${ts}" "${lines[$i]}" >> "${log}"
done
EOF
    chmod +x "${WORK}/bin/kafkacat"
    PATH="${WORK}/bin:${PATH}"
    export AGGREGATION_WORK="${WORK}/aggregation"
    export KAFKACAT_ATTRIBUTES="${WORK}/captured"
    export AGGREGATION_POLL=0.05
    # shellcheck source=/dev/null  # checked on its own
    source "${BATS_TEST_DIRNAME}/../bats/lib/aggregation.bash"
    printf '{"entityId":"urn:test:1","name":"a","attributeValue":"1"}\n' > "${WORK}/a"
    printf '{"entityId":"urn:test:1","name":"b","attributeValue":"2"}' > "${WORK}/b"  # no newline at the end
    printf '{"entityId":"urn:test:2","name":"a","attributeValue":"3"}\n' > "${WORK}/c"
}

teardown() {
    pkill -f "tail -n0 -F ${MOCK_KAFKA}" 2>/dev/null || true
    rm -rf "${WORK}"
}

# updates: the captured updates without those of the markers
updates() {
    grep -v flush "${KAFKACAT_ATTRIBUTES}" || true
}

@test "a batch sent within one millisecond is captured as one update, complete before the marker" {
    aggregate "${WORK}/a" "${WORK}/b" 3>"${WORK}/messages"
    [ "$(updates)" = '{"op":"update","entities":"[{\"id\":\"urn:test:1\",\"n\":2}]"}' ]
    # the marker's update is the last line: nothing was cut off before it
    tail -n1 "${KAFKACAT_ATTRIBUTES}" | grep -q 'urn:flush-test:'
    [ ! -s "${WORK}/messages" ]
}

@test "a batch split over two milliseconds is sent again instead of being judged" {
    MOCK_SPLIT_BATCHES=1 aggregate "${WORK}/a" "${WORK}/b" 3>"${WORK}/messages"
    grep -q 'attempt 1: kafkacat stamped the batch with the timestamps' "${WORK}/messages"
    [ "$(updates)" = '{"op":"update","entities":"[{\"id\":\"urn:test:1\",\"n\":2}]"}' ]
}

@test "without the read-back a split batch is forwarded as two updates, the failure of #1060" {
    # the former test flow: send the batch, then a flush record, then compare
    cat "${WORK}/a" "${WORK}/b" | MOCK_SPLIT_BATCHES=1 kafkacat -P -t iff.ngsild.attributes
    marker urn:flush | kafkacat -P -t iff.ngsild.attributes
    run grep -c 'urn:test:1' "${MOCK_KAFKA}/iff.ngsild-updates"
    [ "${output}" = "2" ]
}

@test "a batch split in every attempt fails and says so" {
    status=0
    MOCK_SPLIT_BATCHES=99 AGGREGATION_ATTEMPTS=2 aggregate "${WORK}/a" "${WORK}/b" 3>"${WORK}/messages" || status=$?
    [ "${status}" -eq 1 ]
    [ "$(grep -c 'kafkacat stamped the batch' "${WORK}/messages")" -eq 2 ]
    grep -q 'did not send the batch within one millisecond in 2 attempts' "${WORK}/messages"
    grep -q 'captured from iff.ngsild-updates' "${WORK}/messages"
}

@test "no update within the time limit fails within the bound and prints what was captured" {
    status=0
    start=${SECONDS}
    MOCK_CORE_SERVICES=off AGGREGATION_TIMEOUT=2 aggregate "${WORK}/a" 3>"${WORK}/messages" || status=$?
    [ "${status}" -eq 1 ]
    [ $((SECONDS - start)) -lt 10 ]
    grep -q 'no update of a marker came back within 2s' "${WORK}/messages"
    grep -q 'captured from iff.ngsild-updates' "${WORK}/messages"
}

@test "a prelude is sent on its own before the batch and gets its own update" {
    aggregate --prelude "${WORK}/c" "${WORK}/a" "${WORK}/b" 3>"${WORK}/messages"
    [ "$(updates | grep -c 'urn:test:2')" -eq 1 ]
    [ "$(updates | grep -c 'urn:test:1')" -eq 1 ]
    # the prelude came first, in a window of its own
    updates | head -n1 | grep -q 'urn:test:2'
}

# close_after_quiet <entity>: what Core Services' watermark does after a quiet
# period (#1060): once the record of the entity is on the attributes topic, it
# forwards its pending window without a later record.
close_after_quiet() {
    (
        until grep -q "$1" "${MOCK_KAFKA}/iff.ngsild.attributes" 2>/dev/null; do sleep 0.05; done
        sleep 0.5
        printf '{"op":"update","entities":"[{\\"id\\":\\"%s\\",\\"n\\":1}]"}\n' "$1" >> "${MOCK_KAFKA}/iff.ngsild-updates"
    ) 3>&- &
}

@test "an isolated batch is captured once its window closes after the quiet period" {
    close_after_quiet urn:test:1
    aggregate_alone urn:test:1 "${WORK}/a" 3>"${WORK}/messages"
    [ "$(grep -c 'urn:test:1' "${KAFKACAT_ATTRIBUTES}")" -eq 1 ]
    # no marker was sent
    [ "$(wc -l < "${MOCK_KAFKA}/iff.ngsild.attributes")" -eq 1 ]
}

@test "an isolated batch whose window never closes fails within the bound" {
    status=0
    start=${SECONDS}
    AGGREGATION_ALONE_TIMEOUT=2 aggregate_alone urn:test:1 "${WORK}/a" 3>"${WORK}/messages" || status=$?
    [ "${status}" -eq 1 ]
    [ $((SECONDS - start)) -lt 10 ]
    grep -q 'no update of urn:test:1 came back within 2s without a later record' "${WORK}/messages"
}

@test "a later record on the topic makes an isolated run fail: it may have closed the window" {
    (
        until grep -q urn:test:1 "${MOCK_KAFKA}/iff.ngsild.attributes" 2>/dev/null; do sleep 0.05; done
        kafkacat -P -t iff.ngsild.attributes < "${WORK}/c"
    ) 3>&- &
    status=0
    aggregate_alone urn:test:1 "${WORK}/a" 3>"${WORK}/messages" || status=$?
    [ "${status}" -eq 1 ]
    grep -q 'another record reached iff.ngsild.attributes before the update came back' "${WORK}/messages"
}

@test "the e2e suite sends every batch through aggregate, with no fixed waits left" {
    suite="${BATS_TEST_DIRNAME}/../bats/test-core-sql-services/test-ngsildUpdate-aggregation.bats"
    run grep -cE '^\s*aggregate(_alone)? ' "${suite}"
    [ "${output}" -eq "$(grep -c '^@test' "${suite}")" ]
    run grep -nE '^\s*(sleep|killall kafkacat)' "${suite}"
    [ "${status}" -eq 1 ]
}
