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

# Prints the image of the broker the platform pins: Scorpio built from the commit SCORPIO_COMMIT in
# test/build-local-platform.sh, with that script's profiles, tagged with the first 8 characters of the commit.
# Builds it when the image isn't there yet, which needs git, JDK 17, Maven and Docker and takes several minutes.
# Runs from the repository root. Progress goes to stderr; stdout carries only the image name.
set -euo pipefail
COMMIT=$(sed -n 's/^SCORPIO_COMMIT=//p' test/build-local-platform.sh)
[ -n "$COMMIT" ] || { echo "no SCORPIO_COMMIT in test/build-local-platform.sh" >&2; exit 1; }
TAG=${COMMIT:0:8}
IMAGE=ibn40/scorpio-all-in-one-runner:$TAG
if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  SRC=$(mktemp -d)
  trap 'rm -rf "$SRC"' EXIT
  echo "building $IMAGE from IndustryFusion/ScorpioBroker at $COMMIT" >&2
  git clone -q https://github.com/IndustryFusion/ScorpioBroker.git "$SRC"
  git -C "$SRC" checkout -q "$COMMIT"
  ( cd "$SRC" && mvn -q -B clean package -DskipTests -Ddocker -Ddocker-tag="$TAG" -Dkafka -Pkafka -Dquarkus.profile=kafka ) >&2
  docker image inspect "$IMAGE" > /dev/null || { echo "the build produced no $IMAGE" >&2; exit 1; }
fi
echo "$IMAGE"
