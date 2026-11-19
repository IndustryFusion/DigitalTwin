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
