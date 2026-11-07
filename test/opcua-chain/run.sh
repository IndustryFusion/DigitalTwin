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

# Runs all stages locally, from the repository root, and removes the containers afterwards.
# Needs Python, Node.js, Docker, curl, jq and openssl; ports 4840, 7070 and 19090 must be free.
set -euo pipefail
cd "$(dirname "$0")/../.."
export OUT=${OUT:-$PWD/.opcua-chain}
mkdir -p "$OUT"
trap 'bash test/opcua-chain/cleanup.sh' EXIT
for stage in stage1 stage2 stage3 stage4a stage4b; do
  echo "=== $stage"
  bash "test/opcua-chain/$stage.sh"
done
echo "=== the chain test passed"
