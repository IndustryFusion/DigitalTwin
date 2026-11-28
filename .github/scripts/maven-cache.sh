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
# The Maven repository of the image builds, between a directory (which
# actions/cache keeps from run to run) and the BuildKit cache mount
# `id=maven-repo` that the Dockerfiles resolve into (#1181). A cache mount
# lives in the builder, which a GitHub-hosted runner starts empty; without it
# every build downloads every dependency from Maven Central again, and
# Central answers the runners' shared addresses with HTTP 429.
#
#   maven-cache.sh inject <dir>   the directory into the cache mount
#   maven-cache.sh extract <dir>  the cache mount into the directory
#   maven-cache.sh prune <key>... the maven-* Actions caches no longer used
#
# Measured: the compose cache (Flink operator and gateway) is 311 MB
# compressed; the platform cache adds Scorpio's dependencies.
#
# Both run a throwaway build with the builder `docker buildx build` uses
# (BUILDX_BUILDER, else the current one), the same one docker compose builds
# with. The cache mount is a build-time mount only: nothing of it lands in an
# image.
set -euo pipefail

# An image the builds pull anyway (the Flink operator's build stage), so this
# adds no pull of its own.
IMAGE=${MAVEN_CACHE_IMAGE:-maven:3.9.2-eclipse-temurin-17}
MOUNT="type=cache,id=maven-repo,target=/cache,sharing=locked"

# build <dockerfile text> <docker buildx build arguments...>: the build, its
# output shown only when it fails. Not with --no-cache: under it a cache
# mount is read empty. The Dockerfiles carry a nonce instead, so that the
# layer cache never skips their RUN.
build() {
    local log rc=0
    log=$(mktemp)
    printf '%s' "$1" | docker buildx build --progress=plain -f - "${@:2}" > "$log" 2>&1 || rc=$?
    [ "$rc" -eq 0 ] || { echo "maven-cache: the build failed (rc=${rc}):"; cat "$log"; }
    rm -f "$log"
    return "$rc"
}

inject() {
    local dir=$1
    if [ ! -d "$dir" ] || [ -z "$(ls -A "$dir")" ]; then
        echo "maven-cache: nothing to inject from ${dir}"
        return 0
    fi
    echo "maven-cache: injecting ${dir} ($(du -sh "$dir" | cut -f1)) into the cache mount maven-repo"
    build "$(printf 'FROM %s\nRUN --mount=%s --mount=type=bind,source=.,target=/seed cp -a /seed/. /cache/ && echo %s\n' \
        "$IMAGE" "$MOUNT" "$(nonce)")" "$dir"
}

nonce() {
    echo "maven-cache-$(date +%s%N)-$$"
}

extract() {
    local dir=$1 empty rc=0
    empty=$(mktemp -d)
    mkdir -p "$dir"
    build "$(printf 'FROM %s AS copy\nRUN --mount=%s mkdir /export && cp -a /cache/. /export/ && echo %s\nFROM scratch\nCOPY --from=copy /export /\n' \
        "$IMAGE" "$MOUNT" "$(nonce)")" -o "type=local,dest=${dir}" "$empty" || rc=$?
    rmdir "$empty"
    [ "$rc" -eq 0 ] || return "$rc"
    echo "maven-cache: extracted the cache mount maven-repo into ${dir} ($(du -sh "$dir" | cut -f1))"
}

# prune <key>...: deletes the maven-* Actions caches that are no longer used,
# so that they do not push other caches out of the repository's 10 GB: on
# main every key but the given current ones, and every cache of a pull
# request that is closed. The cache of an open pull request stays: its
# pom.xml may differ from main's.
prune() {
    local id key ref pr state
    gh cache list --key maven- --limit 1000 --json id,key,ref --jq '.[] | "\(.id) \(.key) \(.ref)"' |
        while read -r id key ref; do
            if [ "$ref" = refs/heads/main ]; then
                if printf '%s\n' "$@" | grep -qxF "$key"; then continue; fi
            elif [[ "$ref" =~ ^refs/pull/([0-9]+)/merge$ ]]; then
                pr=${BASH_REMATCH[1]}
                state=$(gh pr view "$pr" --json state --jq .state) || continue
                [ "$state" != OPEN ] || continue
            else
                continue
            fi
            echo "maven-cache: deleting ${key} of ${ref}"
            gh cache delete "$id"
        done
}

case "${1:-}" in
    inject) inject "${2:?directory missing}" ;;
    extract) extract "${2:?directory missing}" ;;
    prune) shift; [ "$#" -gt 0 ] || { echo "prune: the current keys missing" >&2; exit 2; }; prune "$@" ;;
    *) echo "usage: $0 inject|extract <dir> | prune <current key>..." >&2; exit 2 ;;
esac
