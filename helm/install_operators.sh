NAMESPACE=iff

printf "\n"
printf "\033[1mInstalling OLM\n"
printf -- "------------------------\033[0m\n"
curl -sL https://github.com/operator-framework/operator-lifecycle-manager/releases/download/v0.20.0/install.sh | bash -s v0.20.0

printf "\n"
printf "\033[1mInstalling Subscriptions for Keycloak operator, Strimzi, Postgres-operator \n"
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
  channel: alpha
  source: operatorhubio-catalog
  sourceNamespace: olm
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: postgres-operator
  namespace: ${NAMESPACE}
spec:
  name: postgres-operator
  channel: stable
  source: operatorhubio-catalog
  sourceNamespace: olm
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: strimzi-operator
  namespace: ${NAMESPACE}
spec:
  name: strimzi-kafka-operator
  channel: stable
  source: operatorhubio-catalog
  sourceNamespace: olm
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: cert-manager
  namespace: operators
spec:
  name: cert-manager
  channel: stable
  source: operatorhubio-catalog
  sourceNamespace: olm
EOF
#kubectl create -f https://operatorhub.io/install/alpha/keycloak-operator.yaml   
printf "\n\n"
printf "\033[1mSubscriptions installed successfully.\033[0m\n"

printf "\n"
printf "\033[1mInstalling KREW\n"
printf -- "------------------------\033[0m\n"
(
  set -x; cd "$(mktemp -d)" &&
  OS="$(uname | tr '[:upper:]' '[:lower:]')" &&
  ARCH="$(uname -m | sed -e 's/x86_64/amd64/' -e 's/\(arm\)\(64\)\?.*/\1\2/' -e 's/aarch64$/arm64/')" &&
  KREW="krew-${OS}_${ARCH}" &&
  curl -fsSLO "https://github.com/kubernetes-sigs/krew/releases/latest/download/${KREW}.tar.gz" &&
  tar zxvf "${KREW}.tar.gz" &&
  ./"${KREW}" install krew
)
printf "\n"
printf "\033[1mInstalling MINIO operator via krew\n"
printf -- "------------------------\033[0m\n"
export PATH="${KREW_ROOT:-$HOME/.krew}/bin:$PATH"
kubectl krew update
kubectl krew install minio
kubectl minio init


printf -- "\033[1mOperators installed successfully.\033[0m\n"
