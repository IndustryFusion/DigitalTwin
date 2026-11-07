#!/bin/bash
#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# Stage 2, the connector: the tutorial's test server and dataservice, as written there, with a plain
# OPC UA client writing values. A TCP listener stands in for the device agent and records the messages.
# Runs from the repository root after stage 1. OUT is the directory for logs and results.
set -euo pipefail
HERE=test/opcua-chain
TUTORIAL=semantic-model/dataservice/opcua-pump-tutorial.md
PY=$PWD/.venv-dataservice/bin/python
M="$OUT/messages.jsonl"
: > "$M"
: > "$OUT/server.log"
: > "$OUT/dataservice.log"

: "The test servers' unit tests need asyncua, which Build doesn't install"
"$PY" -m pip install -q pytest==9.0.3
( cd semantic-model/dataservice && "$PY" -m pytest -q -p no:cacheprovider tests/test_relative_paths.py )

python3 "$HERE/extract.py" "$TUTORIAL" server > "$OUT/server.sh"
python3 "$HERE/extract.py" "$TUTORIAL" dataservice > "$OUT/dataservice.sh"

# Each tutorial block runs in its own process group, so that stopping it stops its python process too.
# Unbuffered, because the test waits for what the processes log.
start() { PYTHONUNBUFFERED=1 setsid bash -euo pipefail "$OUT/$1.sh" >> "$OUT/$1.log" 2>&1 & echo $! > "$OUT/$1.pid"; }
stop() { [ -f "$OUT/$1.pid" ] && kill -- "-$(cat "$OUT/$1.pid")" 2>/dev/null || true; }
running() { kill -0 "$(cat "$OUT/$1.pid")" 2>/dev/null; }
trap 'stop dataservice; stop server; kill "$(cat "$OUT/agent.pid")" 2>/dev/null || true' EXIT

wait_for_server() {
  for _ in $(seq 1 120); do
    [ "$(grep -c 'Server running' "$OUT/server.log" || true)" -ge "$1" ] && return 0
    running server || { tail -n 20 "$OUT/server.log"; return 1; }
    sleep 1
  done
  return 1
}

"$PY" "$HERE/fake_agent.py" "$M" > "$OUT/agent.log" 2>&1 & echo $! > "$OUT/agent.pid"
start server
wait_for_server 1
start dataservice
: "the connector reads each node on its own 5 s cycle; give it two cycles to connect and read everything"
sleep 12
"$PY" "$HERE/write_values.py" all
sleep 12
n=$(grep -c '^Found attributes:' "$OUT/dataservice.log" || true)
m=$(grep -c '^Found mappings:' "$OUT/dataservice.log" || true)
[ "$n" = 46 ] && [ "$m" = 46 ] && echo "ok   the dataservice finds all 46 bindings" \
  || { echo "FAIL the dataservice finds $n bindings with $m mappings"; exit 1; }
python3 "$HERE/check_messages.py" "$M"

: "outage: nothing is sent, and the dataservice keeps running"
stop server
sleep 7
n=$(wc -l < "$M")
sleep 15
[ "$(wc -l < "$M")" = "$n" ] && echo "ok   nothing is sent during the outage" || { echo "FAIL messages during the outage"; exit 1; }
running dataservice && echo "ok   the dataservice survives the outage" || { echo "FAIL the dataservice stopped"; exit 1; }

: "recovery without restarting the dataservice; a restarted server is back at its nodeset defaults"
start server
wait_for_server 2
"$PY" "$HERE/write_values.py" after
for _ in $(seq 1 30); do tail -n 60 "$M" | grep -q '"v": "42.5"' && break; sleep 1; done
tail -n 60 "$M" | grep -q '"v": "42.5"' && echo "ok   recovered after the outage" || { echo "FAIL no value after the outage"; exit 1; }
: "give every node one more cycle, so that all of them are read again before the check"
sleep 7
[ "$(grep -c '"None"' "$M" || true)" = 0 ] && echo "ok   no value is the string None" || { echo "FAIL None was sent"; exit 1; }
