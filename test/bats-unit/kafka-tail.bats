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
# kafka_tail (test/bats/lib/kafka.bash, #1200): a read of the last records of
# a topic falls back to its earliest record after retention. Against a real
# Kafka (3.9, a topic starting at 95 of 100): `-o -20 -e` read nothing,
# `-o -20 -e -X auto.offset.reset=earliest` read the five records it holds.
# Here kafkacat is a stub; these tests keep the call as it was proven and keep
# every tail read of the suites going through it.

bats_require_minimum_version 1.5.0

REPO="${BATS_TEST_DIRNAME}/../.."

setup() {
    WORK="$(mktemp -d)"
    mkdir -p "${WORK}/bin"
    cat > "${WORK}/bin/kafkacat" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "${WORK}/args"
echo record
EOF
    chmod +x "${WORK}/bin/kafkacat"
    export WORK
    PATH="${WORK}/bin:${PATH}"
    # shellcheck source=/dev/null  # checked on its own
    . "${REPO}/test/bats/lib/kafka.bash"
}

teardown() {
    rm -rf "${WORK}"
}

@test "kafka_tail reads the last records to the end, falling back to the earliest record" {
    run kafka_tail iff.ngsild.entities 2000 -f '%s\n'
    [ "${status}" -eq 0 ]
    [ "${output}" = "record" ]
    [ "$(tr '\n' ' ' < "${WORK}/args")" = "-C -t iff.ngsild.entities -b my-cluster-kafka-bootstrap:9092 -o -2000 -e -X auto.offset.reset=earliest -f %s\n " ]
}

@test "kafka_tail ends a read that hangs within its time limit" {
    printf '#!/usr/bin/env bash\nsleep 30\n' > "${WORK}/bin/kafkacat"
    start=${SECONDS}
    KAFKA_TAIL_TIMEOUT=1 run kafka_tail t 5
    [ "${status}" -eq 124 ]
    [ $(( SECONDS - start )) -lt 10 ]
}

@test "no suite reads the last records of a topic without kafka_tail" {
    # An offset before the end (-o -<n>) outside the helper reads nothing once
    # retention moved the topic's start past it.
    found=$(find "${REPO}/test/bats" "${REPO}/semantic-model" -path '*/node_modules' -prune -o \
        \( -name '*.bats' -o -name '*.bash' -o -name '*.sh' \) -type f -print0 \
        | xargs -0 grep -nE -- '(^|[[:space:]])-o +-[0-9]+' || true)
    [ -z "${found}" ] || { echo "tail reads without kafka_tail: ${found}"; false; }
}
