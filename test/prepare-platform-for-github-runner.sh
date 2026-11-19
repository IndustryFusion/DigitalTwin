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
# Prepares a GitHub-hosted ubuntu-24.04 runner for the K8s e2e test. Python
# 3.10 and Java 17 come from the workflow's setup actions. prepare-platform.sh
# is for an interactive machine (it reinstalls Docker and asks before
# installing); this one never prompts.
#
#   prepare-platform-for-github-runner.sh images   to build the platform images:
#                                                  docker-compose, maven and the
#                                                  local registry they go to
#   prepare-platform-for-github-runner.sh cluster  to install and test: helm,
#                                                  helmfile, the suites' tools,
#                                                  the registry, the k3d cluster
#   (no argument: both)
set -euo pipefail

K3S_IMAGE=rancher/k3s:v1.33.13-k3s2
K3D_VERSION=v5.9.0
HELM_VERSION=v3.20.2
HELM_DIFF_VERSION=v3.15.9
HELMFILE_VERSION=0.149.0
KUBEFWD_VERSION=1.22.0
MAVEN_VERSION=3.8.7

cd "$(dirname "$0")"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

cleanup_disk() {
    echo "== disk before cleanup"; df -h /
    # The images of the whole platform are stored twice (registry and node
    # containerd); the preinstalled toolchains this test never uses make room.
    sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /usr/local/.ghcup \
        /opt/hostedtoolcache/CodeQL /usr/local/share/boost /usr/share/swift
    docker system prune -af >/dev/null
    echo "== disk after cleanup"; df -h /
}

registry() {
    curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | TAG="${K3D_VERSION}" bash
    echo "127.0.0.1 k3d-iff.localhost" | sudo tee -a /etc/hosts >/dev/null
    k3d registry create iff.localhost -p 12345
}

build_tools() {
    # build-local-platform.sh calls the standalone docker-compose
    if ! command -v docker-compose >/dev/null; then
        printf '#!/bin/sh\nexec docker compose "$@"\n' | sudo tee /usr/local/bin/docker-compose >/dev/null
        sudo chmod +x /usr/local/bin/docker-compose
    fi
    # build-local-platform.sh sources maven.sh for the Scorpio build; the $ in
    # it expand when it is sourced, not here
    wget -q -P "$work" "https://archive.apache.org/dist/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz"
    sudo tar xzf "$work/apache-maven-${MAVEN_VERSION}-bin.tar.gz" -C /opt
    # shellcheck disable=SC2016
    printf 'export M2_HOME=/opt/apache-maven-%s\nexport PATH="$M2_HOME/bin:$PATH"\n' "${MAVEN_VERSION}" \
        | sudo tee /etc/profile.d/maven.sh >/dev/null
}

test_tools() {
    # Retries: the mirrors answer GitHub's runners with 503 at times.
    sudo apt-get -o Acquire::Retries=5 update -qq
    sudo apt-get -o Acquire::Retries=5 install -y -qq jq kcat bats mosquitto-clients postgresql-client \
        sqlite3 libsqlite3-dev libpcre2-dev psmisc
    command -v kafkacat >/dev/null || sudo ln -s "$(command -v kcat)" /usr/local/bin/kafkacat
    yq --version  # helm/env.sh needs mikefarah's yq, preinstalled on the runner

    wget -q -P "$work" "https://github.com/txn2/kubefwd/releases/download/${KUBEFWD_VERSION}/kubefwd_Linux_x86_64.tar.gz"
    tar xzf "$work/kubefwd_Linux_x86_64.tar.gz" -C "$work" kubefwd
    sudo mv "$work/kubefwd" /usr/local/bin/

    wget -q -P "$work" "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz"
    tar xzf "$work/helm-${HELM_VERSION}-linux-amd64.tar.gz" -C "$work" linux-amd64/helm
    sudo mv "$work/linux-amd64/helm" /usr/local/bin/helm
    helm plugin install https://github.com/databus23/helm-diff --version "${HELM_DIFF_VERSION}"

    wget -q -P "$work" "https://github.com/helmfile/helmfile/releases/download/v${HELMFILE_VERSION}/helmfile_${HELMFILE_VERSION}_linux_amd64.tar.gz"
    tar xzf "$work/helmfile_${HELMFILE_VERSION}_linux_amd64.tar.gz" -C ../helm helmfile

    pip install -q rdflib  # the e2etest environment of the self-hosted runner
}

cluster() {
    # Two agents like the self-hosted runner: every k3d node advertises the
    # host's CPUs, and on a single node the summed CPU requests left velero
    # Pending.
    k3d cluster create --image "${K3S_IMAGE}" -a 2 --registry-use k3d-iff.localhost:12345 iff-cluster \
        --k3s-arg "--kubelet-arg=eviction-hard=imagefs.available<2%,nodefs.available<2%,nodefs.inodesFree<2%@all"
    kubectl get nodes
}

case "${1:-all}" in
    images)  cleanup_disk; build_tools; registry ;;
    cluster) cleanup_disk; test_tools; registry; cluster ;;
    all)     cleanup_disk; build_tools; test_tools; registry; cluster ;;
    *) echo "usage: $0 [images|cluster]" >&2; exit 2 ;;
esac
