NAMESPACE=iff

printf "\n"
printf "\033[1mInstalling OLM\n"
printf -- "------------------------\033[0m\n"
curl -sL https://github.com/operator-framework/operator-lifecycle-manager/releases/download/v0.20.0/install.sh | bash -s v0.20.0

printf "\n"
printf "\033[1mInstalling Subscriptions for Keycloak operator, Strimzi \n"
printf -- "------------------------\033[0m "

kubectl create ns ${NAMESPACE}

cat << EOF  | kubectl apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: CatalogSource
metadata:
  name: operatorhubio-catalog
  namespace: olm
spec:
  sourceType: grpc
  image: quay.io/operatorhubio/catalog:latest
  displayName: Community Operators
  publisher: OperatorHub.io
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: mygroup
  namespace: ${NAMESPACE}
spec:
  targetNamespaces:
  - ${NAMESPACE}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: keycloak-operator
  namespace: ${NAMESPACE}
spec:
  name: keycloak-operator
  channel: fast
  source: operatorhubio-catalog
  sourceNamespace: olm
  installPlanApproval: Manual
  startingCSV: keycloak-operator.v21.1.2
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: strimzi-operator
  namespace: ${NAMESPACE}
spec:
  name: strimzi-kafka-operator
  channel: strimzi-0.32.x
  source: operatorhubio-catalog
  installPlanApproval: Manual
  startingCSV: strimzi-cluster-operator.v0.32.0
  sourceNamespace: olm
EOF

printf "\n"
printf "\033[1mInstalling Cert-Manager CRD\n"
printf -- "------------------------\033[0m\n"
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.9.1/cert-manager.yaml


printf "\n\n"
printf "\033[1mSubscriptions installed successfully.\033[0m\n"


printf "\n"
printf "\033[1mInititating MinIO Operator v4.5.8\n"
echo ------------------
wget https://github.com/minio/operator/releases/download/v4.5.8/kubectl-minio_4.5.8_linux_amd64
mv kubectl-minio_4.5.8_linux_amd64 kubectl-minio
chmod +x kubectl-minio
export PATH="$(pwd):$PATH"
kubectl minio version
kubectl minio init
printf -- "------------------------\033[0m\n"

printf "\n"
printf "\033[1mInstalling Flink SQL Operator CRD\n"
printf -- "------------------------\033[0m\n"
kubectl -n ${NAMESPACE} apply -f ../FlinkSqlServicesOperator/kubernetes/crd.yml

printf "\n"
printf "\033[1mInstalling Postgres-operator v1.9.0\n"
printf -- "------------------------\033[0m\n"
git clone https://github.com/zalando/postgres-operator.git
cd postgres-operator
git fetch
git checkout v1.9.0
helm -n iff install postgres-operator ./charts/postgres-operator


printf "\n"
printf "\033[1mInstalling EMQX Operator\n"
printf -- "------------------------\033[0m\n"
printf "\033[1mWait 30 seconds to give cert-manager time to settle\n"
sleep 30 # Wait 30 seconds to give cert-manager time to settle (otherwise it is failing due to missing api)
printf "\033[1mNow install\n"
helm repo add emqx https://repos.emqx.io/charts
helm repo update
helm upgrade --install emqx-operator emqx/emqx-operator --namespace emqx-operator-system --create-namespace --version 2.2.3


printf -- "\033[1mOperators installed successfully.\033[0m\n"

