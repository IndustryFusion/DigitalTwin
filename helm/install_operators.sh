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
printf "\033[1mInstalling MinIO Operator v${MINIO_OPERATOR_VERSION}\n"
echo ------------------
# MinIO Operator 6.x removed the `kubectl minio` krew plugin (and the embedded
# Operator Console), so the operator is now installed via its official Helm chart.
if [ "$OFFLINE" = "true" ]; then
  ( cd ${OFFLINE_DIR}/operator && helm -n minio-operator upgrade --install --create-namespace operator ./helm/operator \
      --set operator.image.repository=${REGISTRY}/minio/operator --set operator.image.tag=v${MINIO_OPERATOR_VERSION} )
else
  helm repo add minio-operator https://operator.min.io
  helm repo update
  helm -n minio-operator upgrade --install --create-namespace operator minio-operator/operator --version ${MINIO_OPERATOR_VERSION}
fi
# Apply preferred anti-affinity patch (strategic merge; idempotent). Wait for the
# deployment to be created by Helm first.
echo "Patching MinIO Operator deployment with preferred anti-affinity..."
kubectl -n minio-operator rollout status deployment/minio-operator --timeout=120s || true
kubectl -n minio-operator patch deployment minio-operator \
  --type='merge' \
  -p='{
    "spec": {
      "template": {
        "spec": {
          "affinity": {
            "podAntiAffinity": {
              "preferredDuringSchedulingIgnoredDuringExecution": [
                {
                  "weight": 100,
                  "podAffinityTerm": {
                    "labelSelector": {
                      "matchExpressions": [
                        {
                          "key": "name",
                          "operator": "In",
                          "values": ["minio-operator"]
                        }
                      ]
                    },
                    "topologyKey": "kubernetes.io/hostname"
                  }
                }
              ]
            }
          }
        }
      }
    }
  }'
printf -- "------------------------\033[0m\n"


printf "\n"
printf "\033[1mInstalling Flink SQL Operator CRD\n"
printf -- "------------------------\033[0m\n"
kubectl -n ${NAMESPACE} apply -f ../FlinkSqlServicesOperator/kubernetes/crd.yml

printf "\n"
printf "\033[1mInstalling Postgres-operator ${POSTGRES_OPERATOR_VERSION}\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  ( cd ${OFFLINE_DIR}/postgres-operator && helm -n iff upgrade --install postgres-operator ./charts/postgres-operator --set image.registry=${EXT_REGISTRY4} --set configGeneral.docker_image=${EXT_REGISTRY4}/zalando/spilo-15:2.1-p9)
else
  rm -rf postgres-operator
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

( cd ${OFFLINE_DIR} && rm -rf helm-charts && git clone https://github.com/vmware-tanzu/helm-charts.git && cd helm-charts && git checkout ${VELERO_HELM_VERSION} && kubectl -n velero apply -f ./charts/velero/crds/ )


printf "\n"
printf "\033[1mInstalling Flink Operator\n"
printf -- "------------------------\033[0m\n"

FLINK_OPERATOR_IMAGE_REGISTRY=${COMMON_MAIN_REGISTRY}/${MAIN_REPO}
if [ "$LOCAL" = "true" ]; then
  FLINK_OPERATOR_IMAGE_REGISTRY=${LOCAL_REGISTRY}/${MAIN_REPO}
  echo selected local image for flink operator: ${FLINK_OPERATOR_IMAGE_REGISTRY}
fi
if [ "$OFFLINE" = "true" ]; then
  ( cd ${OFFLINE_DIR}/flink-kubernetes-operator && helm -n ${NAMESPACE} upgrade --install flink-kubernetes-operator flink-kubernetes-operator-1.15.0-helm.tgz \
      --set image.repository="${FLINK_OPERATOR_IMAGE_REGISTRY}/flink-operator" --set image.tag="${DOCKER_TAG}" )
else
  helm repo add flink-kubernetes-operator https://downloads.apache.org/flink/flink-kubernetes-operator-1.15.0
  helm repo update
  helm -n ${NAMESPACE} install flink-kubernetes-operator flink-kubernetes-operator/flink-kubernetes-operator --set image.repository="${FLINK_OPERATOR_IMAGE_REGISTRY}/flink-operator" --set image.tag="${DOCKER_TAG}"

fi

printf -- "\033[1mOperators installed successfully.\033[0m\n"
