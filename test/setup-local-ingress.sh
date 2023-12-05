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

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO=sudo
fi

# Patch Coredns to add keyloak.local
# ----------------------------------
kubectl -n kube-system get cm/coredns -o jsonpath=\{".data.Corefile"\} > /tmp/Corefile || exit 1
kubectl -n kube-system get cm/coredns -o jsonpath=\{".data.NodeHosts"\} > /tmp/NodeHosts || exit 1

while [ -z "$INGRESS_IP" ]; do
    INGRESS_IP=$(kubectl -n iff get ingress/keycloak-iff-ingress -o jsonpath=\{".status.loadBalancer.ingress[0].ip"\})
    echo waiting for ingress to provide IP-Address
    sleep 1
done
echo "$INGRESS_IP" keycloak.local >> /tmp/NodeHosts || exit 1

kubectl -n kube-system create cm coredns  --from-file=/tmp/NodeHosts --from-file=/tmp/Corefile --dry-run=client -o yaml | kubectl replace -f -

# Restart coredns
# ---------------
COREDNS_POD=$(kubectl -n kube-system get pod --selector=k8s-app=kube-dns -o jsonpath=\{".items[0].metadata.name"\})
kubectl -n kube-system delete pod "${COREDNS_POD}"

# Update /etc/hosts
# -----------------
echo Update hostfile for local api
echo ------------------
${SUDO} bash -c "echo $INGRESS_IP keycloak.local alerta.local ngsild.local pgrest.local >> /etc/hosts"
