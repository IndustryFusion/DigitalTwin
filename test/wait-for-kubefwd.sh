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
# Waits until the services kubefwd forwards accept a TCP connection. kubefwd
# starts in the background and needs a while to write its /etc/hosts entries
# and open its listeners; a suite started before that sees "Connection
# refused" (or a name that does not resolve) instead of its own result.
#
#   wait-for-kubefwd.sh [timeout seconds, default 180] [host:port ...]
#
# Without endpoints it waits for the ones the suites reach through kubefwd:
# Kafka's bootstrap and the MQTT listener. A name that does not resolve yet
# counts as not ready. On timeout it fails naming every endpoint still down.
set -u

TIMEOUT=${1:-180}
shift || true
if [ "$#" -eq 0 ]; then
    set -- my-cluster-kafka-bootstrap:9092 emqx-listeners:1883
fi
INTERVAL=${KUBEFWD_WAIT_INTERVAL:-2}
START=$(date +%s)

# True when host:port accepts a TCP connection within two seconds. bash's
# /dev/tcp resolves the name itself, so an unresolved name fails here too.
answers() {
    local host=${1%:*} port=${1##*:}
    # shellcheck disable=SC2016  # expanded by the inner bash, from $0 and $1
    timeout 2 bash -c ': > "/dev/tcp/$0/$1"' "${host}" "${port}" 2>/dev/null
}

pending=("$@")
while true; do
    down=()
    for endpoint in "${pending[@]}"; do
        answers "${endpoint}" || down+=("${endpoint}")
    done
    elapsed=$(( $(date +%s) - START ))
    if [ "${#down[@]}" -eq 0 ]; then
        echo "after ${elapsed}s: forwarded and answering: $*"
        exit 0
    fi
    echo "after ${elapsed}s: not answering yet: ${down[*]}"
    if [ "${elapsed}" -ge "${TIMEOUT}" ]; then
        echo "kubefwd did not forward ${down[*]} within ${TIMEOUT}s" >&2
        exit 1
    fi
    pending=("${down[@]}")
    sleep "${INTERVAL}"
done
