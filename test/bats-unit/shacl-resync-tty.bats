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
# make shacl-resync run from a terminal hung silently in its first check
# (#1195). Its Kafka tools ran as `timeout … kubectl exec -i`, which handed
# kubectl the terminal as stdin. timeout runs its command in a background
# process group, so the kernel stopped kubectl with SIGTTIN when it read the
# terminal, and a stopped process never acts on timeout's SIGTERM. Only a
# terminal shows this: the regression test runs the tool call under a
# pseudo-terminal (script(1)), with a kubectl stub that reads its stdin.

bats_require_minimum_version 1.5.0

SHACL2FLINK="${BATS_TEST_DIRNAME}/../../semantic-model/shacl2flink"

setup() {
    WORK="$(mktemp -d)"
    mkdir -p "${WORK}/bin"
    # kubectl reads its stdin, as kubectl exec -i forwards it to the pod.
    cat > "${WORK}/bin/kubectl" <<'EOF'
#!/usr/bin/env bash
case " $* " in
    *" exec -i "*) cat > /dev/null ;;
esac
echo "pod-output"
EOF
    chmod +x "${WORK}/bin/kubectl"
    # The functions under test, as shacl_resync.sh has them: kube from
    # validation_job.sh, kafka_tool and kafka_feed from the script itself.
    {
        echo 'set -u'
        echo "NAMESPACE=iff KUBECTL_TIMEOUT=\${KUBECTL_TIMEOUT:-3} KAFKA_POD=pod"
        echo "PATH=\"${WORK}/bin:\${PATH}\""
        echo ". '${SHACL2FLINK}/validation_job.sh'"
        sed -n '/^kafka_tool() {/,/^}/p; /^kafka_feed() {/,/^}/p' "${SHACL2FLINK}/shacl_resync.sh"
        # shellcheck disable=SC2016 # expanded by the harness, not here
        echo 'out=$(kafka_tool kafka-get-offsets.sh "--topic iff.alerts --time -1"); echo "returned $? ${out}"'
    } > "${WORK}/harness.sh"
}

teardown() {
    rm -rf "${WORK}"
}

@test "a Kafka tool call from a terminal returns instead of being stopped (#1195)" {
    start=${SECONDS}
    # An outer limit well above KUBECTL_TIMEOUT: before the fix kubectl was
    # stopped for good, and only this limit ended the call.
    run timeout 20 script -qec "bash ${WORK}/harness.sh" /dev/null
    echo "after $(( SECONDS - start ))s: ${output}"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"returned 0 pod-output"* ]]
    [ $(( SECONDS - start )) -lt 10 ]
}

@test "a kubectl call that ignores SIGTERM is killed shortly after its limit" {
    cat > "${WORK}/bin/kubectl" <<'EOF'
#!/usr/bin/env bash
trap '' TERM
sleep 30
EOF
    chmod +x "${WORK}/bin/kubectl"
    start=${SECONDS}
    run bash -c "NAMESPACE=iff KUBECTL_TIMEOUT=1 KUBECTL_KILL_AFTER=1 PATH='${WORK}/bin':\${PATH}; . '${SHACL2FLINK}/validation_job.sh'; kube get pods"
    [ "${status}" -ne 0 ]
    [ $(( SECONDS - start )) -lt 10 ]
}

@test "every kubectl exec -i of the resync is fed through a pipe" {
    # -i forwards stdin to the pod. Without a pipe into it, stdin is whatever
    # the resync was started with, a terminal among them.
    run grep -n -- 'exec -i' "${SHACL2FLINK}/shacl_resync.sh" "${SHACL2FLINK}/validation_job.sh" "${SHACL2FLINK}/restart_connect.sh"
    echo "${output}"
    while IFS= read -r line; do
        [ -n "${line}" ] || continue
        # inside kafka_feed, whose every caller pipes into it, or piped here
        # shellcheck disable=SC2016 # the script's text, literally
        if [[ "${line}" == *'kube exec -i "$KAFKA_POD" -- sh -c "KAFKA_HEAP_OPTS'* ]]; then
            grep -q '^kafka_feed() {' "${SHACL2FLINK}/shacl_resync.sh"
            continue
        fi
        [[ "${line}" =~ \|[[:space:]]*kube[[:space:]]+exec[[:space:]]+-i ]] || { echo "not fed: ${line}"; false; }
    done <<< "${output}"
    # every call of kafka_feed has a pipe into it
    run grep -n 'kafka_feed ' "${SHACL2FLINK}/shacl_resync.sh"
    while IFS= read -r line; do
        [[ "${line}" == *'kafka_feed() {'* ]] && continue
        [[ "${line}" =~ \|[[:space:]]*kafka_feed ]] || { echo "kafka_feed without a pipe: ${line}"; false; }
    done <<< "${output}"
}

@test "make shacl-resync refuses a KMS: the resync works on the deployed package" {
    # A kubectl that fails, should the refusal be missing: nothing reaches a
    # cluster either way.
    printf '#!/bin/sh\nexit 1\n' > "${WORK}/bin/kubectl"
    chmod +x "${WORK}/bin/kubectl"
    run env PATH="${WORK}/bin:${PATH}" make -s -C "${SHACL2FLINK}" shacl-resync KMS=/some/package
    echo "${output}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"make flink-deploy KMS="* ]]
    [[ "${output}" != *"step "* ]]
}
