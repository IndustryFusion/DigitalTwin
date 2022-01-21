spin() {
  local i=0
  local sp='/-\|'
  local n=${#sp}
  printf ' '
  sleep 0.1
  while true; do
    printf '\b%s' "${sp:i++%n:1}"
    sleep 0.1
  done
}


NAMESPACE=iff

printf "\n"
printf "\033[1mInstalling OLM\n"
printf -- "------------------------\033[0m\n"
curl -sL https://github.com/operator-framework/operator-lifecycle-manager/releases/download/v0.20.0/install.sh | bash -s v0.20.0

printf "\n"
printf "\033[1mInstalling Subscriptions for Keycloak operator, Strimzi, Postgres-operator \n"
printf -- "------------------------\033[0m "
spin & spinpid=$!

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
kill $spinpid
printf "\n\n"
printf "\033[1mSubscriptions installed successfully.\033[0m\n"

printf -- "\033[1mOperators installed successfully.\033[0m\n"
