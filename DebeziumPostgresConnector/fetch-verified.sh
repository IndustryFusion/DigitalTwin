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
# Downloads <url> to <file> and accepts it only if its SHA-256 is <sha256>.
# curl retries transport and HTTP errors itself; the checksum catches what
# curl cannot see, such as Maven Central answering 200 with a 1-byte body.
# A download with the wrong checksum is fetched again, up to
# FETCH_ATTEMPTS times; on giving up, <file> is removed and the exit code is 1.
#
# FETCH_ATTEMPTS (3), FETCH_CURL_RETRIES (5) and FETCH_RETRY_DELAY (10
# seconds) tune the retries.
set -eu

if [ "$#" -ne 3 ]; then
    echo "usage: $0 <url> <sha256> <file>" >&2
    exit 2
fi
url=$1
sha256=$2
file=$3
attempts=${FETCH_ATTEMPTS:-3}
retries=${FETCH_CURL_RETRIES:-5}
delay=${FETCH_RETRY_DELAY:-10}

attempt=1
while :; do
    if curl -fsSL --retry "$retries" --retry-delay "$delay" --retry-all-errors \
            -o "$file" "$url" &&
       echo "$sha256  $file" | sha256sum -c -; then
        exit 0
    fi
    rm -f "$file"
    if [ "$attempt" -ge "$attempts" ]; then
        echo "fetch-verified: giving up on $url after $attempt attempts" >&2
        exit 1
    fi
    echo "fetch-verified: attempt $attempt of $attempts failed, retrying in ${delay}s" >&2
    attempt=$((attempt + 1))
    sleep "$delay"
done
