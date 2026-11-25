#!/bin/sh
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
# Usage: fetch-verified.sh <url> <sha256> <file>
#
# Downloads <url> to <file> and accepts it only if its SHA-256 is <sha256>. A
# <file> that is already there with that checksum is kept and not downloaded.
#
# curl retries HTTP 408, 429 and 5xx and timeouts: it waits as long as the
# server asks for with Retry-After, else 1, 2, 4, ... seconds, and prints the
# error and the wait. Everything else that fails (a reset connection, a 404, a
# body with the wrong checksum, such as Maven Central answering 200 with a
# 1-byte body) is fetched again up to FETCH_ATTEMPTS times, with pauses that
# double. All of it ends after FETCH_MAX_SECONDS. curl's own --retry-max-time
# is no such limit: the curl 7.76.1 of the image honours a Retry-After that is
# longer, and it does not end a transfer that hangs.
# On giving up, <file> is removed and the exit code is 1.
#
# FETCH_ATTEMPTS (5), FETCH_CURL_RETRIES (10), FETCH_RETRY_DELAY (10 seconds,
# the first pause) and FETCH_MAX_SECONDS (600) tune the retries.
set -eu

if [ "$#" -ne 3 ]; then
    echo "usage: $0 <url> <sha256> <file>" >&2
    exit 2
fi
url=$1
sha256=$2
file=$3
attempts=${FETCH_ATTEMPTS:-5}
retries=${FETCH_CURL_RETRIES:-10}
delay=${FETCH_RETRY_DELAY:-10}
limit=${FETCH_MAX_SECONDS:-600}

log() { echo "fetch-verified: $*" >&2; }
verified() { echo "$sha256  $file" | sha256sum -c -; }
give_up() {
    rm -f "$file"
    log "giving up on $url $*"
    exit 1
}

if [ -f "$file" ]; then
    if verified; then
        log "$file is already there with the pinned checksum, not downloading"
        exit 0
    fi
    log "$file is there but has another checksum, downloading it again"
    rm -f "$file"
fi

log "downloading $url, waiting up to ${limit}s in total"
end=$(($(date +%s) + limit))
attempt=1
while :; do
    left=$((end - $(date +%s)))
    [ "$left" -gt 0 ] || give_up "after the limit of ${limit}s"
    status=0
    timeout "$left" curl -fL --no-progress-meter --retry "$retries" --retry-connrefused \
        -o "$file" "$url" || status=$?
    if [ "$status" -eq 0 ] && verified; then
        exit 0
    fi
    rm -f "$file"
    [ "$status" -ne 124 ] || give_up "after the limit of ${limit}s"
    [ "$attempt" -lt "$attempts" ] || give_up "after $attempt attempts"
    left=$((end - $(date +%s)))
    [ "$delay" -lt "$left" ] || give_up "after $attempt attempts: the next pause of ${delay}s would pass the limit of ${limit}s"
    log "attempt $attempt of $attempts failed, retrying in ${delay}s"
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
done
