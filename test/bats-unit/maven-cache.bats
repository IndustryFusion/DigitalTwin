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
# The Maven repository of the image builds is kept from run to run (#1181):
# the Dockerfiles resolve into the BuildKit cache mount maven-repo, and CI
# restores it before and saves it after every job that builds images, so
# Maven Central is asked only for what is new.

bats_require_minimum_version 1.5.0

REPO="${BATS_TEST_DIRNAME}/../.."
JAR="${REPO}/FlinkSqlGateway/maven-jar.sh"
CACHE_SCRIPT="${REPO}/.github/scripts/maven-cache.sh"

setup() {
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    # a wget that writes what it was asked for and counts its calls
    cat > "${BATS_TEST_TMPDIR}/bin/wget" <<EOF
#!/bin/sh
echo call >> "${BATS_TEST_TMPDIR}/wget.calls"
while [ "\$#" -gt 1 ]; do
    [ "\$1" = -O ] && out=\$2
    shift
done
echo "jar from \$1" > "\$out"
EOF
    chmod +x "${BATS_TEST_TMPDIR}/bin/wget"
    PATH="${BATS_TEST_TMPDIR}/bin:${PATH}"
    export MAVEN_REPO="${BATS_TEST_TMPDIR}/repository"
}

wget_calls() {
    wc -l < "${BATS_TEST_TMPDIR}/wget.calls" 2>/dev/null || echo 0
}

@test "maven-jar downloads a jar into the local repository at its Maven path, then copies it" {
    run sh "${JAR}" org/apache/flink flink-sql-connector-kafka 3.3.0-1.20 "${BATS_TEST_TMPDIR}/jars"
    [ "$status" -eq 0 ]
    [ "$(wget_calls)" -eq 1 ]
    stored="${MAVEN_REPO}/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.20/flink-sql-connector-kafka-3.3.0-1.20.jar"
    [ "$(cat "${stored}")" = "jar from https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.20/flink-sql-connector-kafka-3.3.0-1.20.jar" ]
    cmp "${stored}" "${BATS_TEST_TMPDIR}/jars/flink-sql-connector-kafka-3.3.0-1.20.jar"
}

@test "maven-jar takes a jar already in the local repository without asking Central" {
    sh "${JAR}" org/apache/flink flink-sql-connector-postgres-cdc 3.4.0 "${BATS_TEST_TMPDIR}/one"
    run sh "${JAR}" org/apache/flink flink-sql-connector-postgres-cdc 3.4.0 "${BATS_TEST_TMPDIR}/two"
    [ "$status" -eq 0 ]
    [ "$(wget_calls)" -eq 1 ]
    [[ "$output" == *"from the local repository"* ]]
    cmp "${BATS_TEST_TMPDIR}/one/flink-sql-connector-postgres-cdc-3.4.0.jar" \
        "${BATS_TEST_TMPDIR}/two/flink-sql-connector-postgres-cdc-3.4.0.jar"
}

@test "maven-jar keeps no partial jar when the download fails" {
    printf '#!/bin/sh\nexit 8\n' > "${BATS_TEST_TMPDIR}/bin/wget"
    run sh "${JAR}" org/apache/flink flink-sql-connector-kafka 3.3.0-1.20 "${BATS_TEST_TMPDIR}/jars"
    [ "$status" -ne 0 ]
    [ ! -e "${MAVEN_REPO}/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.20/flink-sql-connector-kafka-3.3.0-1.20.jar" ]
}

@test "maven-jar retries transient failures and a rate limit" {
    grep -q -- '--tries=5' "${JAR}"
    grep -q -- '--retry-on-http-error=429' "${JAR}"
}

@test "every mvn in a Dockerfile resolves into the cache mount maven-repo" {
    run python3 - "${REPO}" <<'EOF'
import pathlib, re, sys
bad = []
for path in sorted(pathlib.Path(sys.argv[1]).glob('*/Dockerfile*')):
    text = re.sub(r'\\\n', ' ', path.read_text())
    for line in text.splitlines():
        if re.match(r'\s*RUN\b.*\bmvn\b', line) and \
                'type=cache,id=maven-repo,target=/root/.m2/repository' not in line:
            bad.append(f'{path.parent.name}: {line.strip()[:100]}')
print('\n'.join(bad))
sys.exit(1 if bad else 0)
EOF
    echo "$output"
    [ "$status" -eq 0 ]
}

@test "every jar a Dockerfile takes from Maven Central goes through the cache mount" {
    # The Debezium plugin has a cache of its own (fetch-verified, gh-1099).
    run python3 - "${REPO}" <<'EOF'
import pathlib, re, sys
bad = []
for path in sorted(pathlib.Path(sys.argv[1]).glob('*/Dockerfile*')):
    if path.parent.name == 'DebeziumPostgresConnector':
        continue
    text = re.sub(r'\\\n', ' ', path.read_text())
    for line in text.splitlines():
        if line.lstrip().startswith('#'):
            continue
        if 'repo1.maven.org' in line or 'repo.maven.apache.org' in line:
            bad.append(f'{path.parent.name}: {line.strip()[:100]}')
        if 'maven-jar.sh' in line and line.lstrip().startswith('RUN') and \
                'type=cache,id=maven-repo,target=/root/.m2/repository' not in line:
            bad.append(f'{path.parent.name}: maven-jar.sh without the cache mount')
print('\n'.join(bad))
sys.exit(1 if bad else 0)
EOF
    echo "$output"
    [ "$status" -eq 0 ]
}

@test "every workflow job that builds the images restores the Maven repository before and saves it after" {
    run python3 - "${REPO}/.github/workflows" <<'EOF'
import pathlib, re, sys, yaml
# a step that builds the images with Maven: docker compose build of every
# service, or one that runs build-local-platform.sh (one service alone, such
# as the Debezium image, needs no Maven)
BUILDS = re.compile(r'(^|[;&|]\s*)(docker compose build\s*$|bash build-local-platform\.sh\b)', re.M)
bad, seen = [], 0
for path in sorted(pathlib.Path(sys.argv[1]).glob('*.y*ml')):
    doc = yaml.safe_load(path.read_text())
    for name, job in (doc.get('jobs') or {}).items():
        steps = job.get('steps') or []
        runs = [i for i, s in enumerate(steps)
                if BUILDS.search((s.get('run') or '').replace('cd test && ', ''))]
        if not runs or job.get('runs-on') == 'private':
            continue  # the self-hosted runner keeps its builder, and with it the cache mount
        seen += 1
        caches = [(i, s) for i, s in enumerate(steps) if s.get('uses') == './.github/actions/maven-cache']
        restore = [(i, s) for i, s in caches if s['with']['mode'] == 'restore']
        save = [(i, s) for i, s in caches if s['with']['mode'] == 'save']
        if len(restore) != 1 or len(save) != 1:
            bad.append(f'{path.name}/{name}: wants one restore and one save, has {len(restore)} and {len(save)}')
            continue
        (ri, r), (si, s) = restore[0], save[0]
        if not ri < min(runs) or not si > max(runs):
            bad.append(f'{path.name}/{name}: restore before and save after the build')
        # A key cannot be overwritten: a failed or cancelled build would save
        # a partial repository that later runs restore as an exact hit.
        if s.get('if') != 'success()':
            bad.append(f'{path.name}/{name}: the save runs after a successful build only (if: success())')
        if r['with']['name'] != s['with']['name'] or r['with']['hash'] != s['with']['hash']:
            bad.append(f'{path.name}/{name}: restore and save with the same name and hash')
print('\n'.join(bad))
print(f'jobs checked: {seen}')
sys.exit(1 if bad or seen < 3 else 0)
EOF
    echo "$output"
    [ "$status" -eq 0 ]
}

@test "the action saves only a repository with jars in it, and only after a miss" {
    action="${REPO}/.github/actions/maven-cache/action.yml"
    run python3 - "${action}" <<'EOF'
import sys, yaml
steps = {s['name']: s for s in yaml.safe_load(open(sys.argv[1]))['runs']['steps']}
extract, save = steps['Extract the BuildKit cache mount'], steps['Save the Maven repository']
assert "-name '*.jar'" in extract['run'] and 'save=true' in extract['run'], extract['run']
assert "steps.extract.outputs.save == 'true'" in save['if'], save['if']
assert "env.MAVEN_CACHE_HIT != 'true'" in save['if'], save['if']
EOF
    echo "$output"
    [ "$status" -eq 0 ]
}

@test "the platform cache's key covers the pinned Scorpio commit" {
    grep -q '^SCORPIO_COMMIT=' "${REPO}/test/build-local-platform.sh"
    for f in k8s-e2e.yaml maven-cache.yaml; do
        grep -q "hashFiles('FlinkOperatorWithCoreServices/CoreServices/pom.xml', 'FlinkSqlGateway/Dockerfile', 'test/build-local-platform.sh')" \
            "${REPO}/.github/workflows/${f}" || { echo "${f}"; false; }
    done
}

@test "maven-cache.sh wants inject or extract and a directory" {
    run bash "${CACHE_SCRIPT}"
    [ "$status" -eq 2 ]
    run bash "${CACHE_SCRIPT}" inject
    [ "$status" -ne 0 ]
}

@test "maven-cache.sh injects nothing from an empty or missing directory, without a build" {
    printf '#!/bin/sh\necho "docker $*" >> %s/docker.calls\n' "${BATS_TEST_TMPDIR}" > "${BATS_TEST_TMPDIR}/bin/docker"
    chmod +x "${BATS_TEST_TMPDIR}/bin/docker"
    mkdir -p "${BATS_TEST_TMPDIR}/empty"
    run bash "${CACHE_SCRIPT}" inject "${BATS_TEST_TMPDIR}/empty"
    [ "$status" -eq 0 ]
    run bash "${CACHE_SCRIPT}" inject "${BATS_TEST_TMPDIR}/missing"
    [ "$status" -eq 0 ]
    [ ! -e "${BATS_TEST_TMPDIR}/docker.calls" ]
}

# A docker that records its calls and refuses what the real CLI refuses.
recording_docker() {
    cat > "${BATS_TEST_TMPDIR}/bin/docker" <<EOF
#!/bin/sh
echo "docker \$*" >> "${BATS_TEST_TMPDIR}/docker.calls"
case " \$* " in *" -q "*|*" --quiet "*)
    case " \$* " in *" --progress=plain "*)
        echo "ERROR: progress=plain and quiet cannot be used together" >&2; exit 1 ;;
    esac ;;
esac
cat >> "${BATS_TEST_TMPDIR}/docker.stdin"
[ -z "\${DOCKER_FAILS:-}" ] || { echo "ERROR: the build failed" >&2; exit 1; }
EOF
    chmod +x "${BATS_TEST_TMPDIR}/bin/docker"
}

# A gh with four maven caches: main's current and an old one, an open and a
# closed pull request's; and a cache that is not Maven's.
caches_gh() {
    cat > "${BATS_TEST_TMPDIR}/bin/gh" <<EOF
#!/bin/sh
case "\$1 \$2" in
    "cache list")
        printf '%s\n' "1 maven-platform-new refs/heads/main" "2 maven-platform-old refs/heads/main" \
            "3 maven-compose-pr refs/pull/10/merge" "4 maven-compose-pr refs/pull/11/merge" \
            "5 maven-compose-new refs/heads/main" ;;
    "pr view")
        [ "\$3" = 10 ] && echo OPEN || echo MERGED ;;
    "cache delete")
        echo "\$3" >> "${BATS_TEST_TMPDIR}/deleted" ;;
    *) echo "unexpected gh \$*" >&2; exit 1 ;;
esac
EOF
    chmod +x "${BATS_TEST_TMPDIR}/bin/gh"
}

@test "maven-cache.sh prune keeps main's current keys and open pull requests, deletes the rest" {
    caches_gh
    run bash "${CACHE_SCRIPT}" prune maven-compose-new maven-platform-new
    echo "$output"
    [ "$status" -eq 0 ]
    [ "$(sort "${BATS_TEST_TMPDIR}/deleted" | tr '\n' ' ')" = "2 4 " ]
}

@test "maven-cache.sh prune wants the current keys" {
    caches_gh
    run bash "${CACHE_SCRIPT}" prune
    [ "$status" -eq 2 ]
    [ ! -e "${BATS_TEST_TMPDIR}/deleted" ]
}

@test "maven-cache.yaml prunes with the keys the jobs save" {
    wf="${REPO}/.github/workflows/maven-cache.yaml"
    grep -qF "COMPOSE_KEY: maven-compose-\${{ hashFiles('FlinkOperatorWithCoreServices/CoreServices/pom.xml', 'FlinkSqlGateway/Dockerfile') }}" "${wf}"
    grep -qF "hash: \${{ hashFiles('FlinkOperatorWithCoreServices/CoreServices/pom.xml', 'FlinkSqlGateway/Dockerfile') }}" "${REPO}/.github/workflows/build.yaml"
    grep -qF "PLATFORM_KEY: maven-platform-\${{ hashFiles('FlinkOperatorWithCoreServices/CoreServices/pom.xml', 'FlinkSqlGateway/Dockerfile', 'test/build-local-platform.sh') }}" "${wf}"
    # shellcheck disable=SC2016 # the workflow's literal text
    grep -qF 'maven-cache.sh prune "$COMPOSE_KEY" "$PLATFORM_KEY"' "${wf}"
    grep -qF 'actions: write' "${wf}"
}

@test "maven-cache.sh fails loudly, with the build's output, when its build fails" {
    recording_docker
    mkdir -p "${BATS_TEST_TMPDIR}/repo/org"
    DOCKER_FAILS=1 run bash "${CACHE_SCRIPT}" inject "${BATS_TEST_TMPDIR}/repo"
    [ "$status" -ne 0 ]
    [[ "$output" == *"ERROR: the build failed"* ]]
    DOCKER_FAILS=1 run bash "${CACHE_SCRIPT}" extract "${BATS_TEST_TMPDIR}/out"
    [ "$status" -ne 0 ]
    [[ "$output" == *"ERROR: the build failed"* ]]
}

@test "maven-cache.sh injects and extracts through the cache mount the Dockerfiles use" {
    recording_docker
    mkdir -p "${BATS_TEST_TMPDIR}/repo/org"
    run bash "${CACHE_SCRIPT}" inject "${BATS_TEST_TMPDIR}/repo"
    [ "$status" -eq 0 ]
    run bash "${CACHE_SCRIPT}" extract "${BATS_TEST_TMPDIR}/out"
    [ "$status" -eq 0 ]
    [ "$(grep -c 'id=maven-repo' "${BATS_TEST_TMPDIR}/docker.stdin")" -eq 2 ]
    grep -q -- "-o type=local,dest=${BATS_TEST_TMPDIR}/out" "${BATS_TEST_TMPDIR}/docker.calls"
    grep -q "build .*-f - ${BATS_TEST_TMPDIR}/repo" "${BATS_TEST_TMPDIR}/docker.calls"
    # Under --no-cache a cache mount is read empty (measured with BuildKit
    # v0.25): a nonce keeps the layer cache from skipping the RUN instead.
    run ! grep -q -- '--no-cache' "${BATS_TEST_TMPDIR}/docker.calls"
    [ "$(grep -c 'echo maven-cache-[0-9]' "${BATS_TEST_TMPDIR}/docker.stdin")" -eq 2 ]
}
