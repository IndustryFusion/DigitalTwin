#!/bin/bash
# Copyright (c) 2024 Intel Corporation
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
set -e

. ../../.env
. ../env.sh

if [ "${REGISTRY}" = "docker.io" ]; then
  IMAGES=(
      quay.io/strimzi/operator:0.32.0 
      registry.opensource.zalan.do/acid/postgres-operator:v1.9.0 
      docker.io/minio/operator:v${MINIO_OPERATOR_VERSION}
      docker.io/minio/mc:RELEASE.2023-06-28T21-54-17Z
      docker.io/emqx/emqx-operator-controller:2.2.3
      docker.io/minio/minio:RELEASE.2023-01-12T02-06-16Z
      docker.io/redis:7.2
      ghcr.io/zalando/spilo-15:2.1-p9
      docker.io/velero/velero:${VELERO_VERSION}
      docker.io/alerta/alerta-web:8.1.0
      docker.io/busybox:1.28
      docker.io/postgrest/postgrest:v12.0.0
      quay.io/strimzi/kafka:0.32.0-kafka-3.3.1
      quay.io/strimzi/operator:0.32.0
      quay.io/jetstack/cert-manager-controller:v1.9.1
      quay.io/jetstack/cert-manager-webhook:v1.9.1
      quay.io/jetstack/cert-manager-cainjector:v1.9.1
      docker.io/emqx:5.1
      quay.io/keycloak/keycloak-operator:21.1.2
      docker.io/bitnami/kubectl:${KUBECTL_VERSION}
      docker.io/velero/velero-plugin-for-aws:${VELERO_PLUGIN_VERSION}
      docker.io/rancher/mirrored-pause:3.6
      docker.io/rancher/mirrored-coredns-coredns:1.10.1
      docker.io/rancher/klipper-helm:v0.8.2-build20230815
      docker.io/rancher/local-path-provisioner:v0.0.24
      docker.io/rancher/mirrored-metrics-server:v0.6.3
      docker.io/rancher/klipper-lb:v0.4.4
      docker.io/rancher/mirrored-library-traefik:2.10.5
      docker.io/rancher/mirrored-library-busybox:1.36.1
      docker.io/ibn40/scorpio-all-in-one-runner:${DOCKER_TAG}
      docker.io/ibn40/flink-services-operator:${DOCKER_TAG}
      docker.io/ibn40/kafka-bridge:${DOCKER_TAG}
      docker.io/ibn40/keycloak:${DOCKER_TAG}
      docker.io/ibn40/flink-sql-gateway:${DOCKER_TAG}
      docker.io/ibn40/debezium-postgresql-connector:${DOCKER_TAG}
 )
else
  IMAGES=(
      quay.io/strimzi/operator:0.32.0 
      registry.opensource.zalan.do/acid/postgres-operator:v1.9.0 
      docker.io/minio/operator:v${MINIO_OPERATOR_VERSION}
      docker.io/minio/mc:RELEASE.2023-06-28T21-54-17Z
      docker.io/emqx/emqx-operator-controller:2.2.3
      docker.io/minio/minio:RELEASE.2023-01-12T02-06-16Z
      docker.io/redis:7.2
      ghcr.io/zalando/spilo-15:2.1-p9
      docker.io/velero/velero:${VELERO_VERSION}
      docker.io/alerta/alerta-web:8.1.0
      docker.io/busybox:1.28
      docker.io/postgrest/postgrest:v12.0.0
      quay.io/strimzi/kafka:0.32.0-kafka-3.3.1
      quay.io/strimzi/operator:0.32.0
      quay.io/jetstack/cert-manager-controller:v1.9.1
      quay.io/jetstack/cert-manager-webhook:v1.9.1
      quay.io/jetstack/cert-manager-cainjector:v1.9.1
      docker.io/emqx:5.1
      quay.io/keycloak/keycloak-operator:21.1.2
      docker.io/bitnami/kubectl:${KUBECTL_VERSION}
      docker.io/velero/velero-plugin-for-aws:${VELERO_PLUGIN_VERSION}
      docker.io/rancher/mirrored-pause:3.6
      docker.io/rancher/mirrored-coredns-coredns:1.10.1
      docker.io/rancher/klipper-helm:v0.8.2-build20230815
      docker.io/rancher/local-path-provisioner:v0.0.24
      docker.io/rancher/mirrored-metrics-server:v0.6.3
      docker.io/rancher/klipper-lb:v0.4.4
      docker.io/rancher/mirrored-library-traefik:2.10.5
      docker.io/rancher/mirrored-library-busybox:1.36.1
  )
fi
for image in ${IMAGES[@]}; do 
    tagged=${image/quay.io/$LOCAL_REGISTRY}
    tagged=${tagged/docker.io/$LOCAL_REGISTRY}
    tagged=${tagged/registry.opensource.zalan.do/$LOCAL_REGISTRY}
    tagged=${tagged/ghcr.io/$LOCAL_REGISTRY}
    echo pulling $image and pushing $tagged
    echo $tagged
    docker pull $image
    docker tag $image $tagged
    docker push $tagged
    if [ "$SAVE_CONTAINERS" = "true" ]; then
      savename=docker-images/$(echo $image| tr '/' '_' | tr ':' '%')
      docker save -o $savename $image
    fi
done

wget --no-clobber --directory-prefix ${OFFLINE_DIR} https://github.com/minio/operator/releases/download/v${MINIO_OPERATOR_VERSION}/kubectl-minio_${MINIO_OPERATOR_VERSION}_linux_amd64
wget --no-clobber --directory-prefix ${OFFLINE_DIR} https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/${KEYCLOAK_VERSION}/kubernetes/keycloaks.k8s.keycloak.org-v1.yml
wget --no-clobber --directory-prefix ${OFFLINE_DIR} https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/${KEYCLOAK_VERSION}/kubernetes/keycloakrealmimports.k8s.keycloak.org-v1.yml
wget -O- https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/${KEYCLOAK_VERSION}/kubernetes/kubernetes.yml 2>/dev/null | sed "s/quay\.io/$LOCAL_REGISTRY/g" > ${OFFLINE_DIR}/kubernetes.yml
wget -O- https://github.com/cert-manager/cert-manager/releases/download/v${CERT_MANAGER_VERSION}/cert-manager.yaml 2>/dev/null | sed "s/quay\.io/$LOCAL_REGISTRY/g" > ${OFFLINE_DIR}/cert-manager.yaml
wget -O- https://github.com/strimzi/strimzi-kafka-operator/releases/download/${STRIMZI_VERSION}/strimzi-cluster-operator-${STRIMZI_VERSION}.yaml 2>/dev/null \
  | sed "s/quay\.io/$LOCAL_REGISTRY/g" | sed "s/namespace: myproject/namespace: ${NAMESPACE}/g" > ${OFFLINE_DIR}/strimzi-cluster-operator-${STRIMZI_VERSION}.yaml
( cd ${OFFLINE_DIR} && rm -rf emqx-operator && git clone https://github.com/emqx/emqx-operator.git && cd emqx-operator && git checkout ${EMQX_OPERATOR_VERSION} )
( cd ${OFFLINE_DIR} && rm -rf postgres-operator && git clone https://github.com/zalando/postgres-operator.git && cd postgres-operator && git checkout ${POSTGRES_OPERATOR_VERSION} )
( cd ${OFFLINE_DIR} && rm -rf helm-charts && git clone https://github.com/vmware-tanzu/helm-charts.git && cd helm-charts && git checkout ${VELERO_HELM_VERSION})
( cd ${OFFLINE_DIR} && rm -rf Reloader && git clone https://github.com/stakater/Reloader.git && cd Reloader && git checkout ${RELOADER_HELM_VERSION})
