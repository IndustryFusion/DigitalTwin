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
# The K8s workflows wait for kubefwd's forwards to answer before the suites
# run, instead of a fixed sleep after which the first suite could still see
# the forwarded Kafka refuse the connection (#1072). A local listener stands
# in for a forwarded service.

bats_require_minimum_version 1.5.0

ROOT="${BATS_TEST_DIRNAME}/../.."
SCRIPT="${ROOT}/test/wait-for-kubefwd.sh"
# probe every second, so that the tests stay short
export KUBEFWD_WAIT_INTERVAL=1

free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

# Listens on 127.0.0.1:$1 after $2 seconds; teardown stops it.
listen() {
    (sleep "$2"; exec python3 -m http.server --bind 127.0.0.1 "$1") >/dev/null 2>&1 &
    echo $! >> "${BATS_TEST_TMPDIR}/listeners"
}

teardown() {
    if [ -f "${BATS_TEST_TMPDIR}/listeners" ]; then
        while read -r pid; do
            pkill -P "${pid}" 2>/dev/null || true
            kill "${pid}" 2>/dev/null || true
        done < "${BATS_TEST_TMPDIR}/listeners"
    fi
}

@test "returns at once when every endpoint answers" {
    a=$(free_port); b=$(free_port)
    listen "${a}" 0; listen "${b}" 0
    # the listeners need a moment to bind; the script's own retry covers it
    run bash "${SCRIPT}" 20 "127.0.0.1:${a}" "localhost:${b}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"forwarded and answering: 127.0.0.1:${a} localhost:${b}"* ]]
}

@test "waits for an endpoint that answers only later" {
    a=$(free_port)
    listen "${a}" 4
    start=$(date +%s)
    run bash "${SCRIPT}" 30 "127.0.0.1:${a}"
    echo "${output}"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"not answering yet: 127.0.0.1:${a}"* ]]
    [ $(( $(date +%s) - start )) -ge 4 ]
}

@test "fails within the limit naming only the endpoint that never answers" {
    up=$(free_port); down=$(free_port)
    listen "${up}" 0
    start=$(date +%s)
    run --separate-stderr bash "${SCRIPT}" 3 "127.0.0.1:${up}" "127.0.0.1:${down}"
    echo "${output}"
    # shellcheck disable=SC2154  # stderr is assigned by run --separate-stderr
    echo "${stderr}"
    [ "$status" -eq 1 ]
    [ "${stderr}" = "kubefwd did not forward 127.0.0.1:${down} within 3s" ]
    [ $(( $(date +%s) - start )) -lt 15 ]
}

@test "a name that does not resolve counts as not ready" {
    run --separate-stderr bash "${SCRIPT}" 1 no-such-service.invalid:9092
    [ "$status" -eq 1 ]
    # shellcheck disable=SC2154  # stderr is assigned by run --separate-stderr
    [[ "${stderr}" == *"no-such-service.invalid:9092"* ]]
}

@test "without endpoints it waits for the forwarded Kafka and MQTT" {
    # A stub timeout refuses every probe, so a kubefwd running on this
    # machine cannot answer for the real names.
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    printf '#!/bin/bash\nexit 1\n' > "${BATS_TEST_TMPDIR}/bin/timeout"
    chmod +x "${BATS_TEST_TMPDIR}/bin/timeout"
    PATH="${BATS_TEST_TMPDIR}/bin:${PATH}" run --separate-stderr bash "${SCRIPT}" 0
    [ "$status" -eq 1 ]
    # shellcheck disable=SC2154  # stderr is assigned by run --separate-stderr
    [ "${stderr}" = "kubefwd did not forward my-cluster-kafka-bootstrap:9092 emqx-listeners:1883 within 0s" ]
}

# The step that runs the suites: kubefwd is started, then waited for.
suite_step() {
    python3 - "$1" "$2" <<'EOF'
import sys, yaml
jobs = yaml.safe_load(open(sys.argv[1]))['jobs']
runs = [s['run'] for j in jobs.values() for s in j.get('steps', [])
        if 'kubefwd' in s.get('run', '') and 'bats' in s.get('run', '')]
assert len(runs) == 1, runs
print(runs[0])
EOF
}

@test "both K8s workflows wait for kubefwd instead of sleeping a fixed time" {
    for wf in k8s-e2e.yaml k8s-tests.yaml; do
        run suite_step "${ROOT}/.github/workflows/${wf}"
        echo "${wf}: ${output}"
        [ "$status" -eq 0 ]
        step="${output}"
        run python3 - "${step}" <<'EOF'
import re, sys
lines = [l.strip() for l in sys.argv[1].splitlines()]
fwd = next(i for i, l in enumerate(lines) if 'kubefwd' in l and l.endswith('&'))
wait = next(i for i, l in enumerate(lines) if 'wait-for-kubefwd.sh' in l)
suites = next(i for i, l in enumerate(lines) if re.search(r'\bbats\b', l))
assert fwd < wait < suites, (fwd, wait, suites)
# no fixed sleep between starting kubefwd and the suites
assert not any(l.startswith('sleep') for l in lines[fwd:suites]), lines[fwd:suites]
EOF
        echo "${output}"
        [ "$status" -eq 0 ]
    done
}

@test "shacl2flink's Kafka suite waits for its kubefwd too" {
    suite="${ROOT}/semantic-model/shacl2flink/tests/bats/test-shacl-flink-e2e/test-shacl-flink-e2e.bats"
    run python3 - "${suite}" <<'EOF'
import re, sys
src = open(sys.argv[1]).read()
setup = re.search(r'^setup\(\) \{\n(.*?)^\}', src, re.S | re.M).group(1)
assert 'wait-for-kubefwd.sh' in setup, setup
assert not re.search(r'^\s*sleep\b', setup, re.M), setup
EOF
    echo "${output}"
    [ "$status" -eq 0 ]
}

@test "the script is linted with the other workflow scripts" {
    grep -q 'wait-for-kubefwd.sh' "${ROOT}/.github/workflows/build.yaml"
}
