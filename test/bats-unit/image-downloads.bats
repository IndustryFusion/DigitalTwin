#!/usr/bin/env bats
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
# The images download from Maven Central and other hosts while they build
# (gh-1013). A download fails on an HTTP error instead of passing the error
# page on, retries transient failures, and the Debezium plugin is accepted
# only with its pinned checksum, since Maven Central has answered 200 with a
# 1-byte body.

bats_require_minimum_version 1.5.0

REPO="${BATS_TEST_DIRNAME}/../.."
FETCH="${REPO}/DebeziumPostgresConnector/fetch-verified.sh"

setup() {
    export FETCH_ATTEMPTS=3 FETCH_CURL_RETRIES=1 FETCH_RETRY_DELAY=1
    printf 'the plugin archive\n' > "${BATS_TEST_TMPDIR}/good"
    printf 'x' > "${BATS_TEST_TMPDIR}/short"
    GOOD_SHA=$(sha256sum "${BATS_TEST_TMPDIR}/good" | cut -d' ' -f1)
}

# A curl that answers with success, the first <n> times with a 1-byte body.
short_bodies_first() {
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    cat > "${BATS_TEST_TMPDIR}/bin/curl" <<EOF
#!/bin/sh
count=\$(cat "${BATS_TEST_TMPDIR}/calls" 2>/dev/null || echo 0)
count=\$((count + 1))
echo "\$count" > "${BATS_TEST_TMPDIR}/calls"
while [ "\$#" -gt 1 ]; do
    [ "\$1" = -o ] && out=\$2
    shift
done
if [ "\$count" -le $1 ]; then src=short; else src=good; fi
cp "${BATS_TEST_TMPDIR}/\$src" "\$out"
EOF
    chmod +x "${BATS_TEST_TMPDIR}/bin/curl"
    PATH="${BATS_TEST_TMPDIR}/bin:${PATH}"
}

@test "fetch-verified accepts a download with the pinned checksum" {
    run sh "${FETCH}" "file://${BATS_TEST_TMPDIR}/good" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    [ "$status" -eq 0 ]
    cmp "${BATS_TEST_TMPDIR}/good" "${BATS_TEST_TMPDIR}/out"
}

@test "fetch-verified rejects a 1-byte body served with success and removes it" {
    run sh "${FETCH}" "file://${BATS_TEST_TMPDIR}/short" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    [ "$status" -eq 1 ]
    [[ "$output" == *"giving up"*"after 3 attempts"* ]]
    [ ! -e "${BATS_TEST_TMPDIR}/out" ]
}

@test "fetch-verified downloads again after a checksum mismatch" {
    short_bodies_first 2
    run sh "${FETCH}" "https://example.invalid/plugin.tar.gz" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    [ "$status" -eq 0 ]
    [ "$(cat "${BATS_TEST_TMPDIR}/calls")" -eq 3 ]
    cmp "${BATS_TEST_TMPDIR}/good" "${BATS_TEST_TMPDIR}/out"
}

@test "fetch-verified fails when the download itself fails" {
    run sh "${FETCH}" "file://${BATS_TEST_TMPDIR}/missing" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    [ "$status" -eq 1 ]
    [ ! -e "${BATS_TEST_TMPDIR}/out" ]
}

@test "fetch-verified wants exactly url, checksum and file" {
    run sh "${FETCH}" "file://${BATS_TEST_TMPDIR}/good"
    [ "$status" -eq 2 ]
}

@test "the Debezium image fetches its plugin with fetch-verified and a pinned SHA-256" {
    dockerfile="${REPO}/DebeziumPostgresConnector/Dockerfile"
    grep -Eq '^ARG DEBEZIUM_SHA256=[0-9a-f]{64}$' "${dockerfile}"
    grep -q 'fetch-verified.sh' "${dockerfile}"
    # shellcheck disable=SC2016 # the literal Dockerfile reference
    grep -qF '"${DEBEZIUM_SHA256}"' "${dockerfile}"
}

@test "every curl and wget in a Dockerfile fails on HTTP errors, retries and is not piped" {
    run python3 - "${REPO}" <<'EOF'
import pathlib, re, sys
bad = []
for path in sorted(pathlib.Path(sys.argv[1]).glob('*/Dockerfile*')):
    text = re.sub(r'\\\n', ' ', path.read_text())
    for line in text.splitlines():
        if line.lstrip().startswith('#'):
            continue
        for m in re.finditer(r'\b(curl|wget)\b([^&;|)]*)(\|?)', line):
            tool, args, pipe = m.groups()
            if tool == 'curl':
                ok = re.search(r'(^|\s)(-[a-zA-Z]*f[a-zA-Z]*|--fail)\b', args) and '--retry ' in args
            else:
                ok = '--tries=' in args and '--retry-on-http-error=' in args
            # "apk add curl" installs curl, it does not download with it
            if re.search(r'(apk add|apt-get install|apk del)[^&;]*$', line[:m.start()]):
                continue
            if not ok or pipe:
                bad.append(f'{path.parent.name}: {m.group(0).strip()}')
print('\n'.join(bad))
sys.exit(1 if bad else 0)
EOF
    echo "$output"
    [ "$status" -eq 0 ]
}
