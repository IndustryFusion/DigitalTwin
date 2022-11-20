
NAMESPACE=iff

printf "\n"
printf "\033[1mUninstalling operator subscriptions\n"
kubectl -n {NAMESPACE} delete subscription/keycloak-operator subscription/strimzi-operator operatorgroup/mygroup catalogsource/olm
kubectl -n operators delete subscription/cert-manager

printf "\n\n"
printf "\033[1mUnInstalling OLM\n"
printf -- "------------------------\033[0m "
export OLM_RELEASE=v0.20.0
kubectl delete apiservices.apiregistration.k8s.io v1.packages.operators.coreos.com -n ${NAMESPACE}
kubectl delete -f https://github.com/operator-framework/operator-lifecycle-manager/releases/download/${OLM_RELEASE}/crds.yaml -n ${NAMESPACE}
kubectl delete -f https://github.com/operator-framework/operator-lifecycle-manager/releases/download/${OLM_RELEASE}/olm.yaml  -n ${NAMESPACE}

printf "\n\n"
printf "\033[1mNot Deleting Namespace ${NAMESPACE}. Please do it on your own with kubectl delete ns/${NAMESPACE}.\n"

printf "\n"
printf "\033[1mUninstalling Flink SQL Operator CRD\n"
printf -- "------------------------\033[0m\n"
kubectl -n ${NAMESPACE} delete -f ../FlinkSqlServicesOperator/kubernetes/crd.yml

printf "\n"
printf "\033[1mUninstalling Postgres-operator\n"
printf -- "------------------------\033[0m\n"
git clone https://github.com/zalando/postgres-operator.git
cd postgres-operator
git checkout v1.8.2
helm -n iff delete postgres-operator ./charts/postgres-operator


printf "\n"
printf "\033[1mUninstalling Cert-Manager CRD\n"
printf -- "------------------------\033[0m\n"
kubectl delete -f https://github.com/cert-manager/cert-manager/releases/download/v1.9.1/cert-manager.yaml

printf -- "\n\033[1mOperators uninstalled successfully.\033[0m\n"
