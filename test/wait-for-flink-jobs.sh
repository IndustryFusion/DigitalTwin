#!/bin/bash
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
# Waits until every running Flink job has all its tasks running, and fails at
# once if a job runs twice (its every output would arrive twice). The core
# services report as deployed while their job's tasks still deploy; on a
# GitHub-hosted runner that took minutes, and suites started in between saw
# no output from them.
#
#   wait-for-flink-jobs.sh [timeout seconds, default 600]
set -u

NAMESPACE=${NAMESPACE:-iff}
TIMEOUT=${1:-600}
START=$(date +%s)

state() {
    local pod
    pod=$(kubectl -n "${NAMESPACE}" get pods -l component=jobmanager \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null) || return 1
    [ -n "${pod}" ] || return 1
    kubectl -n "${NAMESPACE}" exec "${pod}" -c flink-main-container -- \
        curl -s http://localhost:8081/jobs/overview 2>/dev/null | python3 -c "
import json, sys
jobs = [j for j in json.load(sys.stdin)['jobs'] if j['state'] == 'RUNNING']
if not jobs:
    print('NONE no running job')
    sys.exit()
names = [j['name'] for j in jobs]
twice = sorted({n for n in names if names.count(n) > 1})
if twice:
    print('DUPLICATE ' + '; '.join(f'{n} runs {names.count(n)} times' for n in twice))
    sys.exit()
partial = [f\"{j['name']} {j['tasks']['running']}/{j['tasks']['total']}\"
           for j in jobs if j['tasks']['running'] != j['tasks']['total']]
print(('PARTIAL ' + '; '.join(partial)) if partial else
      'OK ' + '; '.join(f\"{j['name']} {j['tasks']['total']}/{j['tasks']['total']}\" for j in jobs))"
}

while true; do
    now=$(state || echo "UNKNOWN jobmanager not reachable")
    elapsed=$(( $(date +%s) - START ))
    echo "after ${elapsed}s: ${now}"
    case "${now}" in
        OK*) exit 0 ;;
        DUPLICATE*)
            # Every output of a job that runs twice arrives twice, and the
            # suites' expected results fail for a reason they don't name.
            echo "A Flink job was submitted more than once; the operator's log:" >&2
            kubectl -n "${NAMESPACE}" logs deploy/flink-kubernetes-operator --all-containers \
                --tail=400 2>/dev/null | grep -iE 'submit|session ?job|error' | tail -60 >&2
            exit 1 ;;
    esac
    if [ "${elapsed}" -ge "${TIMEOUT}" ]; then
        echo "Flink jobs not fully running after ${TIMEOUT}s" >&2
        exit 1
    fi
    sleep 15
done
