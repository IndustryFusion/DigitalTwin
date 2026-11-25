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
# 1-byte body. A rate limit (HTTP 429) is waited out up to a total limit, and CI
# keeps the archive between runs (gh-1099).

bats_require_minimum_version 1.5.0

REPO="${BATS_TEST_DIRNAME}/../.."
FETCH="${REPO}/DebeziumPostgresConnector/fetch-verified.sh"

setup() {
    export FETCH_ATTEMPTS=3 FETCH_CURL_RETRIES=1 FETCH_RETRY_DELAY=1 FETCH_MAX_SECONDS=60
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

teardown() {
    [ -z "${SERVER_PID:-}" ] || kill "${SERVER_PID}" 2>/dev/null || true
}

# A server that answers <n> requests with 429 (and Retry-After <value>, unless
# empty; "date" is the HTTP date 5 seconds ahead), then with the archive. Writes
# the time of every request to the file requests.
rate_limited_first() {
    cat > "${BATS_TEST_TMPDIR}/server.py" <<'EOF'
import email.utils, http.server, os, sys, time
root, limited, retry_after = sys.argv[1], int(sys.argv[2]), sys.argv[3]
class Handler(http.server.BaseHTTPRequestHandler):
    count = 0
    def do_GET(self):
        Handler.count += 1
        with open(root + '/requests', 'a') as f:
            f.write('%f\n' % time.monotonic())
        body = b''
        if Handler.count > limited:
            self.send_response(200)
            body = open(root + '/good', 'rb').read()
        else:
            self.send_response(429)
            if retry_after == 'date':
                self.send_header('Retry-After', email.utils.formatdate(time.time() + 5, usegmt=True))
            elif retry_after:
                self.send_header('Retry-After', retry_after)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
with open(root + '/port.new', 'w') as f:
    f.write(str(server.server_port))
os.rename(root + '/port.new', root + '/port')
server.serve_forever()
EOF
    python3 "${BATS_TEST_TMPDIR}/server.py" "${BATS_TEST_TMPDIR}" "$1" "$2" 3>&- &
    SERVER_PID=$!
    for _ in $(seq 100); do
        [ -e "${BATS_TEST_TMPDIR}/port" ] && break
        sleep 0.1
    done
    URL="http://127.0.0.1:$(cat "${BATS_TEST_TMPDIR}/port")/plugin.tar.gz"
    export no_proxy=127.0.0.1
}

# The pauses between the requests, in whole seconds (rounded down).
pauses() {
    awk 'NR > 1 { printf "%s%d", sep, $1 - last + 0.05; sep = " " } { last = $1 }' "${BATS_TEST_TMPDIR}/requests"
}

@test "fetch-verified waits as many seconds as Retry-After asks for and says so" {
    rate_limited_first 1 3
    run sh "${FETCH}" "${URL}" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    echo "$output"
    [ "$status" -eq 0 ]
    cmp "${BATS_TEST_TMPDIR}/good" "${BATS_TEST_TMPDIR}/out"
    [ "$(pauses)" -ge 3 ]
    [[ "$output" == *"429"*"retry in 3 seconds"* ]]
}

@test "fetch-verified waits until the HTTP date Retry-After gives" {
    rate_limited_first 1 date
    run sh "${FETCH}" "${URL}" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    echo "$output"
    [ "$status" -eq 0 ]
    # the date has whole seconds
    [ "$(pauses)" -ge 3 ]
}

@test "fetch-verified backs off with growing pauses on a 429 without Retry-After" {
    rate_limited_first 3 ''
    run env FETCH_CURL_RETRIES=3 sh "${FETCH}" "${URL}" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    echo "$output"
    [ "$status" -eq 0 ]
    cmp "${BATS_TEST_TMPDIR}/good" "${BATS_TEST_TMPDIR}/out"
    read -r first second third <<< "$(pauses)"
    [ "$first" -ge 1 ]
    [ "$second" -ge 2 ]
    [ "$third" -ge 4 ]
    [[ "$output" == *"429"*"retry in 1 seconds"*"retry in 2 seconds"*"retry in 4 seconds"* ]]
}

@test "fetch-verified waits out a rate limit of some minutes by default" {
    unset FETCH_ATTEMPTS FETCH_CURL_RETRIES FETCH_RETRY_DELAY FETCH_MAX_SECONDS
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    cat > "${BATS_TEST_TMPDIR}/bin/timeout" <<EOF
#!/bin/sh
echo "\$@" > "${BATS_TEST_TMPDIR}/args"
exit 124
EOF
    chmod +x "${BATS_TEST_TMPDIR}/bin/timeout"
    PATH="${BATS_TEST_TMPDIR}/bin:${PATH}" run sh "${FETCH}" https://example.invalid/x "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    [ "$status" -eq 1 ]
    # 10 retries: pauses of 1 + 2 + ... + 256 = 511 s before the limit, and no
    # --retry-delay, which would turn the growing pauses off
    grep -Eq '^(600|59[0-9]) curl .*--retry 10 ' "${BATS_TEST_TMPDIR}/args"
    run ! grep -q -- '--retry-delay' "${BATS_TEST_TMPDIR}/args"
}

@test "fetch-verified gives up at its limit, however long Retry-After is" {
    rate_limited_first 99 3600
    run env FETCH_MAX_SECONDS=3 timeout 20 sh "${FETCH}" "${URL}" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    echo "$output"
    [ "$status" -eq 1 ]
    [[ "$output" == *"giving up"*"limit of 3s"* ]]
    [ "$(wc -l < "${BATS_TEST_TMPDIR}/requests")" -eq 1 ]
    [ ! -e "${BATS_TEST_TMPDIR}/out" ]
}

@test "fetch-verified gives up at its limit when a 429 without Retry-After goes on" {
    rate_limited_first 99 ''
    run env FETCH_MAX_SECONDS=5 FETCH_CURL_RETRIES=10 timeout 20 sh "${FETCH}" "${URL}" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    echo "$output"
    [ "$status" -eq 1 ]
    [[ "$output" == *"giving up"*"limit of 5s"* ]]
}

@test "fetch-verified does not start a pause that passes its limit" {
    run env FETCH_MAX_SECONDS=5 FETCH_RETRY_DELAY=60 timeout 20 sh "${FETCH}" "file://${BATS_TEST_TMPDIR}/short" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    [ "$status" -eq 1 ]
    [[ "$output" == *"giving up"*"limit of 5s"* ]]
}

@test "fetch-verified keeps an archive that is already there with the pinned checksum" {
    short_bodies_first 0
    cp "${BATS_TEST_TMPDIR}/good" "${BATS_TEST_TMPDIR}/out"
    run sh "${FETCH}" "https://example.invalid/plugin.tar.gz" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    [ "$status" -eq 0 ]
    [ ! -e "${BATS_TEST_TMPDIR}/calls" ]
    cmp "${BATS_TEST_TMPDIR}/good" "${BATS_TEST_TMPDIR}/out"
}

@test "fetch-verified downloads again when the archive already there is corrupted" {
    short_bodies_first 0
    cp "${BATS_TEST_TMPDIR}/short" "${BATS_TEST_TMPDIR}/out"
    run sh "${FETCH}" "https://example.invalid/plugin.tar.gz" "${GOOD_SHA}" "${BATS_TEST_TMPDIR}/out"
    [ "$status" -eq 0 ]
    [[ "$output" == *"has another checksum"* ]]
    [ "$(cat "${BATS_TEST_TMPDIR}/calls")" -eq 1 ]
    cmp "${BATS_TEST_TMPDIR}/good" "${BATS_TEST_TMPDIR}/out"
}

@test "fetch-plugin downloads what the Dockerfile pins to where the image build looks" {
    dir="${BATS_TEST_TMPDIR}/connector"
    mkdir "${dir}"
    cp "${REPO}/DebeziumPostgresConnector/Dockerfile" "${REPO}/DebeziumPostgresConnector/fetch-plugin.sh" "${dir}/"
    cat > "${dir}/fetch-verified.sh" <<'EOF'
printf '%s\n' "$@"
EOF
    run sh "${dir}/fetch-plugin.sh" sha256
    [ "$status" -eq 0 ]
    [[ "$output" =~ ^[0-9a-f]{64}$ ]]
    sha=$output
    run sh "${dir}/fetch-plugin.sh"
    [ "$status" -eq 0 ]
    echo "$output"
    echo "${lines[0]}" | grep -Eq '^https://repo1\.maven\.org/[^$]*/debezium-connector-postgres-[0-9][^/$]*-plugin\.tar\.gz$'
    [ "${lines[1]}" = "${sha}" ]
    [ "${lines[2]}" = debezium-connector-postgres.tar.gz ]
    # the pattern matches the file, and may match nothing
    grep -qF 'COPY fetch-verified.sh debezium-connector-postgres.tar.g[z] /tmp/' "${dir}/Dockerfile"
    run sh "${dir}/fetch-plugin.sh" other
    [ "$status" -eq 2 ]
    : > "${dir}/Dockerfile"
    run sh "${dir}/fetch-plugin.sh"
    [ "$status" -eq 1 ]
}

@test "the plugin archive is ignored by git" {
    grep -qx '/debezium-connector-postgres.tar.gz' "${REPO}/DebeziumPostgresConnector/.gitignore"
}

@test "every workflow job that builds the Debezium image takes the archive from the cache first" {
    run python3 - "${REPO}/.github/workflows" <<'EOF'
import pathlib, re, sys
build = re.compile(r'docker[ -]compose build|bash (\./)?(test/)?build-local-platform\.sh')
builders, bad = [], []
for path in sorted(pathlib.Path(sys.argv[1]).glob('*.y*ml')):
    job, cached = None, False
    for line in path.read_text().splitlines():
        if line.lstrip().startswith('#'):
            continue
        m = re.match(r'  ([\w-]+):\s*$', line)
        if m:
            job, cached = m.group(1), False
        if re.search(r'uses: \./\.github/actions/debezium-archive\s*$', line):
            cached = True
        if build.search(line):
            builders.append(f'{path.name}:{job}')
            if not cached:
                bad.append(f'{path.name}:{job}')
print('builders', *builders)
print('without the cache', *bad)
sys.exit(1 if bad or len(builders) < 5 else 0)
EOF
    echo "$output"
    [ "$status" -eq 0 ]
}

@test "the cached archive is keyed by the pinned checksum and verified after the restore" {
    run python3 - "${REPO}/.github/actions/debezium-archive/action.yml" <<'EOF'
import sys
text = open(sys.argv[1]).read()
order = ['fetch-plugin.sh sha256', 'actions/cache/restore@',
         'key: debezium-connector-postgres-${{ steps.pin.outputs.sha256 }}',
         'run: sh DebeziumPostgresConnector/fetch-plugin.sh\n', 'actions/cache/save@',
         "if: steps.cache.outputs.cache-hit != 'true'"]
at = [text.find(o) for o in order]
assert -1 not in at and at == sorted(at), at
assert text.count('path: DebeziumPostgresConnector/debezium-connector-postgres.tar.gz') == 2
EOF
    echo "$output"
    [ "$status" -eq 0 ]
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
