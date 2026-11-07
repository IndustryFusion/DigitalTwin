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

# Stage 3, the bridge mapping: the agent's schema and the MQTT bridge's mapper, fed with the messages of stage 2.
# Runs from the repository root after stage 2. OUT is the directory for logs and results.
set -euo pipefail
( cd NgsildAgent && npm ci --silent --ignore-scripts )
( cd KafkaBridge && npm ci --silent --ignore-scripts )
node test/opcua-chain/stage3.js
