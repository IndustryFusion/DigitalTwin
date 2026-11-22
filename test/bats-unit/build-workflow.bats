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
# A failed Build job opens a tmate shell only when asked for, so that a
# failure shows at once instead of after the job's timeout.

bats_require_minimum_version 1.5.0

WORKFLOW="${BATS_TEST_DIRNAME}/../../.github/workflows/build.yaml"

tmate_steps() {
    python3 - "${WORKFLOW}" <<'EOF'
import json, sys, yaml
jobs = yaml.safe_load(open(sys.argv[1]))['jobs']
steps = [dict(s, job=name) for name, job in jobs.items() for s in job.get('steps', [])
         if 'action-tmate' in s.get('uses', '')]
print(json.dumps(steps))
EOF
}

@test "every job of Build has at most one tmate step, and there is at least one" {
    run tmate_steps
    [ "$status" -eq 0 ]
    count=$(echo "${output}" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')
    [ "${count}" -ge 1 ]
}

@test "every tmate step runs only on failure and only when asked for" {
    run tmate_steps
    echo "${output}" | python3 -c '
import json, sys
for s in json.load(sys.stdin):
    cond = s.get("if", "")
    assert "failure()" in cond, (s["job"], cond)
    assert "ci-debug" in cond and "inputs.debug" in cond, (s["job"], cond)
    assert "&&" in cond.split("failure()", 1)[1], (s["job"], cond)
'
}

@test "every tmate step is bounded and open to the actor only" {
    run tmate_steps
    echo "${output}" | python3 -c '
import json, sys
for s in json.load(sys.stdin):
    assert s.get("timeout-minutes", 0) and s["timeout-minutes"] <= 30, s["job"]
    assert s.get("with", {}).get("limit-access-to-actor") is True, s["job"]
'
}

@test "a manual run of Build can ask for the debug shell" {
    run python3 -c "
import sys, yaml
on = yaml.safe_load(open('${WORKFLOW}'))[True]
assert on['workflow_dispatch']['inputs']['debug']['type'] == 'boolean'
"
    [ "$status" -eq 0 ]
}

# The SemForge SDK's page tests run in headless Chromium and skip without it;
# in Build a missing browser must fail them, not skip them (#960).

semforge_job() {
    python3 - "${WORKFLOW}" <<'EOF'
import json, sys, yaml
print(json.dumps(yaml.safe_load(open(sys.argv[1]))['jobs']['semforge-sdk']))
EOF
}

browser_step() {
    semforge_job | python3 -c '
import json, sys
steps = json.load(sys.stdin)["steps"]
print(next(s["run"] for s in steps if "SEMFORGE_CHROME=" in s.get("run", "")))
'
}

@test "the SemForge SDK job requires the browser for its page tests" {
    run semforge_job
    [ "$status" -eq 0 ]
    echo "${output}" | python3 -c '
import json, sys
job = json.load(sys.stdin)
assert str(job.get("env", {}).get("SEMFORGE_REQUIRE_CHROME")) == "1", job.get("env")
'
}

@test "the SemForge SDK job sets the browser before it runs the tests" {
    run semforge_job
    [ "$status" -eq 0 ]
    echo "${output}" | python3 -c '
import json, sys
steps = json.load(sys.stdin)["steps"]
find = next(i for i, s in enumerate(steps) if "SEMFORGE_CHROME=" in s.get("run", ""))
build = next(i for i, s in enumerate(steps) if "make lint test" in s.get("run", ""))
assert "GITHUB_ENV" in steps[find]["run"] and find < build, (find, build)
'
}

@test "the browser step hands the runner's Chrome to the page tests" {
    script=$(browser_step)
    bin="${BATS_TEST_TMPDIR}/bin"
    mkdir -p "${bin}"
    printf '#!/bin/sh\necho "Google Chrome 1.0"\n' > "${bin}/google-chrome"
    chmod +x "${bin}/google-chrome"
    env_file="${BATS_TEST_TMPDIR}/env"
    GITHUB_ENV="${env_file}" PATH="${bin}:/usr/bin:/bin" run bash -e -c "${script}"
    [ "$status" -eq 0 ]
    grep -qx "SEMFORGE_CHROME=${bin}/google-chrome" "${env_file}"
}

@test "the browser step fails when the runner has no Chrome" {
    script=$(browser_step)
    empty="${BATS_TEST_TMPDIR}/empty"
    mkdir -p "${empty}"
    env_file="${BATS_TEST_TMPDIR}/env"
    GITHUB_ENV="${env_file}" PATH="${empty}" run /bin/bash -e -c "${script}"
    [ "$status" -ne 0 ]
    [[ "${output}" == *"no Chrome or Chromium"* ]]
    [ ! -s "${env_file}" ]
}

# The release record is append-only (openspec gh-942-append-only-release-record):
# on a pull request, kms-check compares each record with the base branch, which
# the shallow checkout does not have and the step fetches.
semforge_step() {
    python3 - "${WORKFLOW}" <<'EOF'
import json, sys, yaml
steps = yaml.safe_load(open(sys.argv[1]))['jobs']['semforge-sdk']['steps']
print(json.dumps([s for s in steps if 'kms-check' in s.get('run', '')]))
EOF
}

@test "kms-check takes the pull request's base branch from the environment" {
    run semforge_step
    [ "$status" -eq 0 ]
    # shellcheck disable=SC2016 # the ${{ }} are GitHub expressions, not shell
    echo "${output}" | python3 -c '
import json, sys
steps = json.load(sys.stdin)
assert len(steps) == 1, steps
step = steps[0]
assert step["env"]["BASE_REF"] == "${{ github.base_ref }}", step.get("env")
assert "${{" not in step["run"], "expressions go through env, not into the script"
'
}

@test "kms-check compares with the base branch on a pull request, and with nothing otherwise" {
    run semforge_step
    [ "$status" -eq 0 ]
    script=$(echo "${output}" | python3 -c '
import json, sys
run = json.load(sys.stdin)[0]["run"]
print("\n".join(l for l in run.splitlines()
                if not l.strip().startswith(("source ", "conda "))))
')
    stub="${BATS_TEST_TMPDIR}/bin"
    calls="${BATS_TEST_TMPDIR}/calls"
    mkdir -p "${stub}" "${BATS_TEST_TMPDIR}/semantic-model/SemForge-SDK"
    for tool in git make; do
        printf '#!/bin/sh\necho "%s $*" >> "%s"\n' "${tool}" "${calls}" > "${stub}/${tool}"
        chmod +x "${stub}/${tool}"
    done
    # the step installs the cross-check requirements with the SDK's own pip
    mkdir -p "${BATS_TEST_TMPDIR}/semantic-model/SemForge-SDK/venv/bin"
    printf '#!/bin/sh\necho "pip $*" >> "%s"\n' "${calls}" > "${BATS_TEST_TMPDIR}/semantic-model/SemForge-SDK/venv/bin/pip"
    chmod +x "${BATS_TEST_TMPDIR}/semantic-model/SemForge-SDK/venv/bin/pip"

    (cd "${BATS_TEST_TMPDIR}" && PATH="${stub}:${PATH}" BASE_REF=main bash -e -c "${script}")
    grep -qx 'git fetch --no-tags --depth=1 origin +refs/heads/main:refs/remotes/origin/main' "${calls}"
    grep -qx 'make lint test kms-check KMS_AGAINST=origin/main' "${calls}"

    rm "${calls}"
    (cd "${BATS_TEST_TMPDIR}" && PATH="${stub}:${PATH}" BASE_REF='' bash -e -c "${script}")
    run grep -c '^git ' "${calls}"
    [ "${output}" = "0" ]
    grep -qx 'make lint test kms-check KMS_AGAINST=' "${calls}"
}
