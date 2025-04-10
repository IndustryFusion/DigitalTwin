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
K3S_IMAGE=rancher/k3s:v1.28.5-k3s1-amd64


echo Installing K3d cluster
echo ----------------------
## k3d cluster with 2 nodes
k3d registry create iff.localhost -p 12345
k3d cluster list | grep iff-cluster > /dev/null && k3d cluster delete iff-cluster
k3d cluster create --image ${K3S_IMAGE} -a 2 --registry-use k3d-iff.localhost:12345 iff-cluster

echo Install Helm diff plugin
echo ------------------------ 
helm plugin install https://github.com/databus23/helm-diff

echo Install Helmfile 0.149.0
echo ----------------
cd ../helm || exit 1
# helmfile v0.149.0
wget https://github.com/helmfile/helmfile/releases/download/v0.149.0/helmfile_0.149.0_linux_amd64.tar.gz
tar -zxvf helmfile_0.149.0_linux_amd64.tar.gz
chmod u+x helmfile

echo Install miniconda with python 3.10 env py310
echo ---------------------------------
mkdir ../miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ../miniconda3/miniconda.sh
bash ../miniconda3/miniconda.sh -b -u -p ../miniconda3
source ../miniconda3/bin/conda init
source ../miniconda3/bin/activate
conda create -n py310 python=3.10 -y
conda create -n e2etest python=3.10 -y
conda install -n e2etest -c conda-forge rdflib -y
rm ../miniconda3/miniconda.sh
