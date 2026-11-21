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

# Stage 4a: the context broker the platform pins (test/build-local-platform.sh), with Postgres and Kafka. Keycloak
# is replaced by a key pair: Scorpio accepts tokens signed with it, and stage 4b signs its own.
# Runs from the repository root. OUT is the directory for logs and results. SCORPIO_IMAGE overrides the broker.
set -euo pipefail
SCORPIO=${SCORPIO_IMAGE:-$(bash test/opcua-chain/scorpio-image.sh)}
N=opcua-chain
s=$SECONDS
for image in postgis/postgis:14-3.4 apache/kafka-native:3.9.0 "$SCORPIO"; do
  docker image inspect "$image" > /dev/null 2>&1 || docker pull -q "$image" > /dev/null
done
echo "image pulls: $((SECONDS-s))s"
s=$SECONDS
code=$(bash test/opcua-chain/broker.sh up $N 19090 "$SCORPIO" "$OUT")
[ "$code" = 401 ] && echo "ok   $SCORPIO up in $((SECONDS-s))s, refusing requests without a token" || { echo "FAIL Scorpio answers $code"; exit 1; }
