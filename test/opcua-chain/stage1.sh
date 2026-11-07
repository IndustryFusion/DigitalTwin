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

# Stage 1, the model: Steps 1 to 3 of the tutorial, as written there, and the rules of the model tools.
# Runs from the repository root. OUT is the directory for logs and results.
set -euo pipefail
HERE=test/opcua-chain
TUTORIAL=semantic-model/dataservice/opcua-pump-tutorial.md
PY=.venv-model/bin/python

python3 "$HERE/extract.py" "$TUTORIAL" install nodesets specifications model > "$OUT/stage1-tutorial.sh"
if ! bash -euo pipefail "$OUT/stage1-tutorial.sh" > "$OUT/model.log" 2>&1; then
  tail -n 40 "$OUT/model.log"
  exit 1
fi

check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; exit 1; fi; }
M=semantic-model/opcua
check '20 entities' '[ "$(jq length $M/instances.jsonld)" = 20 ]'
check '46 bindings' '[ "$(grep -c "base:boundBy" $M/bindings.ttl)" = 46 ]'
check 'no / in an entity id' '! jq -r ".[].id" $M/instances.jsonld | grep -q /'
check 'bindings conform to the binding validation' \
  '.venv-model/bin/pyshacl -s semantic-model/dataservice/validation/bindings-validation-shacl.ttl $M/bindings.ttl | grep -q "Conforms: True"'

: "The server URI identifies instances: without one there is no instance, two give different ids"
cd "$M"
"../../$PY" nodeset2owl.py ../../nodesets/instanceexample.xml -i core.owl.ttl machinery.owl.ttl di.owl.ttl pumps.owl.ttl \
    -p instanceexample -n http://yourorganisation.org/InstanceExample/ -o "$OUT/noserver.owl.ttl" > "$OUT/noserver.log" 2>&1
if "../../$PY" owl2instances.py -t http://opcfoundation.org/UA/Pumps/PumpType -n http://demo.machine/ \
    -j "$OUT/noserver.jsonld" -e "$OUT/noserver.entities.ttl" -s "$OUT/noserver.shacl.ttl" -c "$OUT/noserver.context.jsonld" -b "$OUT/noserver.bindings.ttl" \
    "$OUT/noserver.owl.ttl" >> "$OUT/noserver.log" 2>&1; then
  echo "FAIL entities without a server URI"; exit 1
fi
cd ../..
check 'without a server URI: no instance found' 'grep -q "Error: no instance of type" "$OUT/noserver.log"'
cd "$M"
"../../$PY" nodeset2owl.py ../../nodesets/instanceexample.xml -i core.owl.ttl machinery.owl.ttl di.owl.ttl pumps.owl.ttl \
    -p instanceexample -n http://yourorganisation.org/InstanceExample/ --serverUri urn:example:other-server \
    -o "$OUT/other.owl.ttl" > "$OUT/other.log" 2>&1
"../../$PY" owl2instances.py -t http://opcfoundation.org/UA/Pumps/PumpType -n http://demo.machine/ \
    -j "$OUT/other.jsonld" -e "$OUT/other.entities.ttl" -s "$OUT/other.shacl.ttl" -c "$OUT/other.context.jsonld" -b "$OUT/other.bindings.ttl" \
    "$OUT/other.owl.ttl" >> "$OUT/other.log" 2>&1
cd ../..
check 'another server URI: 20 entities' '[ "$(jq length "$OUT/other.jsonld")" = 20 ]'
check 'another server URI: no id in common' \
  '[ -z "$(comm -12 <(jq -r ".[].id" $M/instances.jsonld | sort) <(jq -r ".[].id" "$OUT/other.jsonld" | sort))" ]'
