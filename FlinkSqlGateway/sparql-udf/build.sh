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
# Compiles the functions against the jars in <flink-lib>, runs the test vectors
# and writes <jar>.
set -e
cd "$(dirname "$0")"
lib=$1
jar=$2
out=$(mktemp -d)
javac --release 11 -cp "$lib/*" -d "$out/main" $(find src -name '*.java')
javac --release 11 -cp "$out/main:$lib/*" -d "$out/test" $(find test -name '*.java')
java -cp "$out/test:$out/main:$lib/*" org.industryfusion.sparql.VectorsTest test/sparql-ladder-vectors.json
jar cf "$jar" -C "$out/main" .
rm -rf "$out"
