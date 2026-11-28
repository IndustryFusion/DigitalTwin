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
# maven-jar.sh <group path> <artifact> <version> <destination directory>:
# copies a jar from Maven Central into the destination, through the local
# repository at /root/.m2/repository (the cache mount maven-repo of the
# Dockerfile, #1181): Central is asked only when the jar is not in it yet.
# Run with a bind mount, so the script does not land in the image.
set -eu
group=$1 artifact=$2 version=$3 dest=$4
path="${group}/${artifact}/${version}/${artifact}-${version}.jar"
jar="${MAVEN_REPO:-/root/.m2/repository}/${path}"
if [ ! -s "${jar}" ]; then
    mkdir -p "$(dirname "${jar}")"
    wget --tries=5 --waitretry=10 --retry-connrefused --retry-on-http-error=429,500,502,503,504 \
        -O "${jar}.part" "https://repo1.maven.org/maven2/${path}"
    mv "${jar}.part" "${jar}"
else
    echo "maven-jar: ${path} from the local repository"
fi
mkdir -p "${dest}"
cp -p "${jar}" "${dest}/"
