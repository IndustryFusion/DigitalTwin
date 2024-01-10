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
printf "\033[1mRemoving Keycloak Operator\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  kubectl -n ${NAMESPACE} delete -f ${OFFLINE_DIR}/keycloaks.k8s.keycloak.org-v1.yml
  kubectl -n ${NAMESPACE} delete -f ${OFFLINE_DIR}/keycloakrealmimports.k8s.keycloak.org-v1.yml
  kubectl -n ${NAMESPACE} delete -f ${OFFLINE_DIR}/kubernetes.yml
else
  kubectl -n ${NAMESPACE} delete -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/${KEYCLOAK_VERSION}/kubernetes/keycloaks.k8s.keycloak.org-v1.yml
  kubectl -n ${NAMESPACE} delete -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/${KEYCLOAK_VERSION}/kubernetes/keycloakrealmimports.k8s.keycloak.org-v1.yml
  kubectl -n ${NAMESPACE} delete -f https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/${KEYCLOAK_VERSION}/kubernetes/kubernetes.yml
fi

printf "\n"
printf "\033[1mRemoving Strimzi Operator\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  kubectl -n ${NAMESPACE}  delete -f ${OFFLINE_DIR}/strimzi-cluster-operator-${STRIMZI_VERSION}.yaml
else
wget -O- https://github.com/strimzi/strimzi-kafka-operator/releases/download/${STRIMZI_VERSION}/strimzi-cluster-operator-${STRIMZI_VERSION}.yaml 2>/dev/null \
  | sed "s/namespace: myproject/namespace: ${NAMESPACE}/g" \
  | kubectl -n ${NAMESPACE}  delete -f -
fi

printf "\n"
printf "\033[1mDelete Cert-Manager CRD\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  kubectl delete -f ${OFFLINE_DIR}/cert-manager.yaml
else
  kubectl delete -f https://github.com/cert-manager/cert-manager/releases/download/v${CERT_MANAGER_VERSION}/cert-manager.yaml
fi


printf "\n"
printf "\033[1mNOT removing MinIO Operator v${MINIO_OPERATOR_VERSION}\n"
printf "\033[1mDo it manually with 'kubectl minio delete'\n"

printf -- "------------------------\033[0m\n"


printf "\n"
printf "\033[1mDelete Flink SQL Operator CRD\n"
printf -- "------------------------\033[0m\n"
kubectl -n ${NAMESPACE} delete -f ../FlinkSqlServicesOperator/kubernetes/crd.yml

printf "\n"
printf "\033[1mDelete Postgres-operator ${POSTGRES_OPERATOR_VERSION}\n"
printf -- "------------------------\033[0m\n"
if [ "$OFFLINE" = "true" ]; then
  ( cd ${OFFLINE_DIR}/postgres-operator && helm -n iff delete postgres-operator)
else
  ( cd postgres-operator && helm -n iff delete postgres-operator )
fi


printf "\n"
printf "\033[1mRemoving EMQX Operator\n"
printf -- "------------------------\033[0m\n"
#if [ "$OFFLINE" = "true" ]; then
#  ( cd ${OFFLINE_DIR}/emqx-operator && helm -n ${EMQX_OPERATOR_NAMESPACE} delete emqx-operator )
#else
helm -n ${EMQX_OPERATOR_NAMESPACE} delete emqx-operator
#fi


# printf "\n"
# printf "\033[1mDelete Namspaces ${NAMESPACE}, ${EMQX_OPERATOR_NAMESPACE}\n"
# printf -- "------------------------\033[0m\n"
# kubectl delete namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace ${EMQX_OPERATOR_NAMESPACE} --dry-run=client -o yaml | kubectl delete -f -


printf -- "\033[1mOperators uninstalled successfully.\033[0m\n"
