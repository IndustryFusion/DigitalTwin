#!/bin/bash
# Copyright (c) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# use specific k3s image to avoid surprises with k8s api changes
K3S_IMAGE=rancher/k3s:v1.22.6-k3s1-amd64
CURR_DIR=$(pwd)
SCRIPT_PATH=$(realpath $0)

printf "\033[1mInstalling docker\n"
printf -- "-----------------\033[0m\n"
sudo apt -qq update
sudo apt-get -qq install apt-transport-https ca-certificates curl gnupg-agent software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo apt -qq update
sudo apt-get install -y docker-ce=5:19.03.15~3-0~ubuntu-$(lsb_release -cs) docker-ce-cli=5:19.03.15~3-0~ubuntu-$(lsb_release -cs) containerd.io
printf "\033[1mSuccessfully installed %s\033[0m\n" "$(docker --version)"
printf "\n"

if [[ -z $(groups | grep docker) ]];
then
    sudo usermod -a -G docker $USER;
    echo "$USER has been added to the docker group.";
    echo "Script is being restarted for changes to take effect.";
    sudo -u $USER /bin/bash $SCRIPT_PATH;
    exit;
fi;

printf "\033[1mInstalling docker-compose\n"
printf -- "-----------------\033[0m\n"
sudo curl -L "https://github.com/docker/compose/releases/download/1.26.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/bin/docker-compose
sudo chmod +x /usr/bin/docker-compose
printf "\033[1mSuccessfully installed docker-compose %s\033[0m\n"
printf "\n"

echo Installing kubectl
echo ----------------------
sudo apt -qq install snapd
sudo snap install kubectl --classic

echo Installing K3d cluster
echo ----------------------
## k3d cluster with 2 nodes
curl -s https://raw.githubusercontent.com/rancher/k3d/main/install.sh | TAG=v4.4.8 bash
k3d registry create iff.localhost -p 12345
k3d cluster create --image ${K3S_IMAGE} -a 2 --registry-use iff.localhost:12345 iff-cluster

echo Install Helm v3.7.2
echo ---------------
 # helm v3.7.2
wget https://get.helm.sh/helm-v3.7.2-linux-amd64.tar.gz
tar -zxvf helm-v3.7.2-linux-amd64.tar.gz
sudo mv linux-amd64/helm /usr/bin/helm

echo Install Helm diff plugin
echo ------------------------ 
helm plugin install https://github.com/databus23/helm-diff

echo Install Helmfile
echo ----------------
cd ../helm || exit 1
# helmfile v0.143.0
wget https://github.com/roboll/helmfile/releases/download/v0.143.0/helmfile_linux_amd64
chmod u+x helmfile_linux_amd64

echo Install Java 17
echo ---------------
sudo apt update
sudo apt install openjdk-17-jdk openjdk-17-jre

echo Installing maven
echo ----------------------
wget https://dlcdn.apache.org/maven/maven-3/3.8.7/binaries/apache-maven-3.8.7-bin.tar.gz
tar -xzf apache-maven-3.8.7-bin.tar.gz
sudo mv apache-maven-3.8.7 /opt/
rm apache-maven-3.8.7-bin.tar.gz
touch maven.sh
sudo chmod 775 /etc/profile.d/maven.sh
echo 'M2_HOME='/opt/apache-maven-3.8.7'
PATH="$M2_HOME/bin:$PATH"
export PATH' >> maven.sh
sudo mv maven.sh /etc/profile.d/
source /etc/profile.d/maven.sh
mvn --version


echo Install shellcheck
echo ------------------
sudo apt install -yq shellcheck

echo Install jq
echo ------------------
sudo apt install -yq jq

echo Install kafkacat
echo ------------------
sudo apt install -yq kafkacat

echo Install bats
echo ------------------
sudo apt install -yq bats

echo Install kubefwd
echo ------------------
wget https://github.com/txn2/kubefwd/releases/download/1.22.0/kubefwd_Linux_x86_64.tar.gz
tar xvzf kubefwd_Linux_x86_64.tar.gz
sudo mv kubefwd /usr/local/bin

sudo apt install -yq bats

if [ -n "${SELF_HOSTED_RUNNER}" ]; then
    echo Change group of /etc/hosts
    echo --------------------------
    sudo groupadd runner
    sudo chgrp runner /etc/hosts
    sudo usermod -a -G runner "${USER}"
    sudo chmod 664 /etc/hosts

    echo "set suid flag for kubefwd"
    echo --------------------------
    sudo chown root /usr/local/bin/kubefwd
    sudo chmod +s /usr/local/bin/kubefwd

    echo "set suid flag for kubefwd"
    echo --------------------------
    sudo chgrp runner /tmp
    sudo chmod 775 /tmp
    sudo apt install acl
    sudo setfacl -Rdm g:runner:rwx /tmp
    sudo chmod g+s /tmp
fi