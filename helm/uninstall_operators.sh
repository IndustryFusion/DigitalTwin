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
printf "\033[1mUninstalling operator subscriptions\n"

printf "\n"
printf "\033[1mUninstalling Zalando postgres-operator\n"
printf -- "------------------------\033[0m "
spin & spinpid=$!
kubectl -n {NAMESPACE} delete subscription/postgres-operator subscription/keycloak-operator subscription/strimzi-operator operatorgroup/mygroup catalogsource/olm
kubectl -n operators delete subscription/cert-manager
kill $spinpid

printf "\n\n"
printf "\033[1mUnInstalling OLM\n"
printf -- "------------------------\033[0m "
spin & spinpid=$!
export OLM_RELEASE=v0.20.0
kubectl delete apiservices.apiregistration.k8s.io v1.packages.operators.coreos.com -n ${NAMESPACE}
kubectl delete -f https://github.com/operator-framework/operator-lifecycle-manager/releases/download/${OLM_RELEASE}/crds.yaml -n ${NAMESPACE}
kubectl delete -f https://github.com/operator-framework/operator-lifecycle-manager/releases/download/${OLM_RELEASE}/olm.yaml  -n ${NAMESPACE}
kill $spinpid

printf "\n\n"
printf "\033[1mNot Deleting Namespace ${NAMESPACE}. Please do it on your own with kubectl delete ns/${NAMESPACE}.\n"

printf "\n"
printf "\033[1mUninstalling Flink SQL Operator CRD\n"
printf -- "------------------------\033[0m\n"
kubectl -n ${NAMESPACE} delete -f ../FlinkSqlServicesOperator/kubernetes/crd.yml

printf -- "\n\033[1mOperators uninstalled successfully.\033[0m\n"