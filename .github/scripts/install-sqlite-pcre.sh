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
# Installs the sqlite3 CLI and builds its PCRE2 extension into
# /usr/lib/sqlite3, where shacl2flink's ~/.sqliterc (written by `make setup`)
# looks for it.
set -e

# Retries: the mirrors answer GitHub's runners with 503 at times.
sudo apt-get -o Acquire::Retries=5 update -qq
sudo apt-get -o Acquire::Retries=5 install -y sqlite3 libsqlite3-dev libpcre2-dev
sudo mkdir -p /usr/lib/sqlite3
# Pinned: the build compiles and installs whatever the clone holds, so it
# must be a reviewed commit, not the branch head of the day.
PCRE2_EXTENSION_COMMIT=e3e02a4af39d5dfdbd2cc8801696ed9ae2faf569
work=$(mktemp -d)
git clone https://github.com/christian-proust/sqlite3-pcre2.git "$work/sqlite3-pcre2"
git -C "$work/sqlite3-pcre2" checkout --quiet "$PCRE2_EXTENSION_COMMIT"
( cd "$work/sqlite3-pcre2" && make && make install )
rm -rf "$work"
