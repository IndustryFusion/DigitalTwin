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

. env.sh

printf "\n"
printf "\033[1mCreate Namspaces ${NAMESPACE}, ${EMQX_OPERATOR_NAMESPACE}\n"
printf -- "------------------------\033[0m\n"
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace ${EMQX_OPERATOR_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

printf "\n"
printf "\033[1mInstalling Keycloak Operator\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  kubectl -n ${NAMESPACE} apply -f ${OFFLINE_DIR}/keycloaks.k8s.keycloak.org-v1.yml
  kubectl -n ${NAMESPACE} apply -f ${OFFLINE_DIR}/keycloakrealmimports.k8s.keycloak.org-v1.yml
  kubectl -n ${NAMESPACE} apply -f ${OFFLINE_DIR}/kubernetes.yml
else
  kubectl -n ${NAMESPACE} apply -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/${KEYCLOAK_VERSION}/kubernetes/keycloaks.k8s.keycloak.org-v1.yml
  kubectl -n ${NAMESPACE} apply -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/${KEYCLOAK_VERSION}/kubernetes/keycloakrealmimports.k8s.keycloak.org-v1.yml
  kubectl -n ${NAMESPACE} apply -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/${KEYCLOAK_VERSION}/kubernetes/kubernetes.yml
fi

printf "\n"
printf "\033[1mInstalling Strimzi Operator\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  kubectl -n ${NAMESPACE}  apply -f ${OFFLINE_DIR}/strimzi-cluster-operator-${STRIMZI_VERSION}.yaml
else
wget -O- https://github.com/strimzi/strimzi-kafka-operator/releases/download/${STRIMZI_VERSION}/strimzi-cluster-operator-${STRIMZI_VERSION}.yaml 2>/dev/null \
  | sed "s/namespace: myproject/namespace: ${NAMESPACE}/g" \
  | kubectl -n ${NAMESPACE}  apply -f -
fi

printf "\n"
printf "\033[1mInstalling Cert-Manager CRD\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  kubectl apply -f ${OFFLINE_DIR}/cert-manager.yaml
else
  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v${CERT_MANAGER_VERSION}/cert-manager.yaml
fi


printf "\n"
printf "\033[1mInititating MinIO Operator v${MINIO_OPERATOR_VERSION}\n"
echo ------------------
if [ "$OFFLINE" = "true" ]; then
  cp ${OFFLINE_DIR}/kubectl-minio_${MINIO_OPERATOR_VERSION}_linux_amd64 .
  mv kubectl-minio_${MINIO_OPERATOR_VERSION}_linux_amd64 kubectl-minio
  chmod +x kubectl-minio
  export PATH="$(pwd):$PATH"
  kubectl minio version
  kubectl minio init --image=${REGISTRY}/minio/operator:v${MINIO_OPERATOR_VERSION} --console-image=${REGISTRY}/minio/operator:v${MINIO_OPERATOR_VERSION}
else
  wget https://github.com/minio/operator/releases/download/v${MINIO_OPERATOR_VERSION}/kubectl-minio_${MINIO_OPERATOR_VERSION}_linux_amd64
  mv kubectl-minio_${MINIO_OPERATOR_VERSION}_linux_amd64 kubectl-minio
  chmod +x kubectl-minio
  export PATH="$(pwd):$PATH"
  kubectl minio version
  kubectl minio init 
fi
printf -- "------------------------\033[0m\n"


printf "\n"
printf "\033[1mInstalling Flink SQL Operator CRD\n"
printf -- "------------------------\033[0m\n"
kubectl -n ${NAMESPACE} apply -f ../FlinkSqlServicesOperator/kubernetes/crd.yml

printf "\n"
printf "\033[1mInstalling Postgres-operator ${POSTGRES_OPERATOR_VERSION}\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  ( cd ${OFFLINE_DIR}/postgres-operator && helm -n iff upgrade --install postgres-operator ./charts/postgres-operator --set image.registry=${EXT_REGISTRY3} --set configGeneral.docker_image=${EXT_REGISTRY4}/zalando/spilo-15:2.1-p9)
else
  git clone https://github.com/zalando/postgres-operator.git
  ( cd postgres-operator && git fetch && git checkout ${POSTGRES_OPERATOR_VERSION} && helm -n iff upgrade --install postgres-operator ./charts/postgres-operator )
fi


printf "\n"
printf "\033[1mInstalling EMQX Operator\n"
printf -- "------------------------\033[0m\n"
printf "\033[1mWait 30 seconds to give cert-manager time to settle\n"
kubectl -n cert-manager wait --for=condition=ready pod -l app=cert-manager
kubectl -n cert-manager wait --for=condition=ready pod -l app=cainjector
kubectl -n cert-manager wait --for=condition=ready pod -l app=webhook
loop=0
while [ $loop -lt 10 ]; do
  printf "\033[1mNow installing\n"
  if [ "$OFFLINE" = "true" ]; then
    ( cd ${OFFLINE_DIR}/emqx-operator && helm -n ${EMQX_OPERATOR_NAMESPACE} upgrade --install --atomic emqx-operator ./deploy/charts/emqx-operator \
      --set image.repository=${REGISTRY}/emqx/emqx-operator-controller )
  else
    helm repo add emqx https://repos.emqx.io/charts
    helm repo update
    helm upgrade --install emqx-operator emqx/emqx-operator --namespace ${EMQX_OPERATOR_NAMESPACE} --create-namespace --version ${EMQX_OPERATOR_VERSION}
  fi
  if [ $? -eq 0 ];then
    break;
  loop=$((loop+1))
fi
sleep 10
done


printf "\n"
printf "\033[1mInstalling Reloader Operator\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  ( cd ${OFFLINE_DIR}/Reloader && helm upgrade --install --atomic reloader ./deployments/kubernetes/chart/reloader \
      --set reloader.image.name=${REGISTRY}/stakater/reloader --set reloader.reloadOnCreate=true)
else
  helm repo add stakater https://stakater.github.io/stakater-charts
  helm repo update
  helm upgrade --install reloader stakater/reloader --version ${RELOADER_HELM_VERSION} --set reloader.reloadOnCreate=true
fi

printf "\n"
printf "\033[1mPrepare Velero Helm Chart Repo\n"
printf -- "------------------------\033[0m\n"

if [ ! "$OFFLINE" = "true" ]; then
  ( cd ${OFFLINE_DIR} && rm -rf helm-charts && git clone https://github.com/vmware-tanzu/helm-charts.git && cd helm-charts && git checkout ${VELERO_HELM_VERSION} )
fi

printf -- "\033[1mOperators installed successfully.\033[0m\n"
