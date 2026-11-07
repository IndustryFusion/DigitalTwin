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

# Stage 4b, the broker: the attributes of stage 3 through the real updates bridge into the broker of stage 4a.
# Runs from the repository root after stage 4a. OUT is the directory for logs and results.
set -euo pipefail
node test/opcua-chain/stage4b.js 2>&1 | tee "$OUT/stage4b.log"
: "The bridge logs what the broker refuses and carries on, so a logged error fails the test, even if the value arrived"
if grep -E '^error:' "$OUT/stage4b.log"; then
  echo "FAIL the updates bridge logged an error"
  exit 1
fi
echo "ok   the updates bridge logged no error"
