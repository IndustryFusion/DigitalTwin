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
# Usage: fetch-plugin.sh [sha256]
#
# Downloads the plugin archive the Dockerfile pins into this directory, where
# the image build picks it up instead of downloading it. CI keeps that file
# between runs (.github/actions/debezium-archive). Optional: without the file
# the image build downloads the archive itself.
# With the argument sha256, only prints the pinned checksum.
set -eu

cd "$(dirname "$0")"
version=$(sed -n 's/^ARG DEBEZIUM_VERSION=//p' Dockerfile)
sha256=$(sed -n 's/^ARG DEBEZIUM_SHA256=//p' Dockerfile)
url=$(sed -n 's/^ARG DEBEZIUM_URL=//p' Dockerfile | sed "s/\${DEBEZIUM_VERSION}/$version/g")
if [ -z "$version" ] || [ -z "$sha256" ] || [ -z "$url" ]; then
    echo "fetch-plugin: no pinned plugin archive in $(pwd)/Dockerfile" >&2
    exit 1
fi

case "${1:-}" in
    sha256) echo "$sha256" ;;
    '') exec sh ./fetch-verified.sh "$url" "$sha256" debezium-connector-postgres.tar.gz ;;
    *) echo "usage: $0 [sha256]" >&2; exit 2 ;;
esac
