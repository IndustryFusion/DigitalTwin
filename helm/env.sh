DIRNAME=$(dirname ${BASH_SOURCE[0]})
source $DIRNAME/../.env
export NAMESPACE=iff
export LOCAL_REGISTRY=k3d-iff.localhost:12345
export EMQX_OPERATOR_NAMESPACE=emqx-operator-system
export EMQX_OPERATOR_VERSION="2.2.29"
export EMQX_VERSION=$(yq ".emqx.imageVersion" < $DIRNAME/common.yaml)
export POSTGRES_OPERATOR_VERSION="v1.15.1"
export VELERO_HELM_VERSION=velero-11.4.0
export VELERO_PLUGIN_VERSION="v1.13.2"
export VELERO_VERSION="v1.17.1"
export MINIO_OPERATOR_VERSION="6.0.4"
export CERT_MANAGER_VERSION="1.17.2"
export STRIMZI_VERSION="0.46.1"
export OFFLINE=${OFFLINE:-false}
export OFFLINE_DIR=$(cd $DIRNAME/airgap-deployment; pwd)
export KEYCLOAK_VERSION=26.7.0
# Reloader: bare helm chart version (used as `helm --version`). The offline git
# checkout derives the tag as `chart-v${RELOADER_HELM_VERSION}` (Reloader tags
# charts as chart-vX.Y.Z since 2.x).
export RELOADER_HELM_VERSION=2.2.14
export ALERTA_VERSION="9.0.4"
COMMON_MAIN_REGISTRY=$(yq ".mainRegistry" < $DIRNAME/common.yaml)
COMMON_EXTERNAL_REGISTRY=$(yq ".externalRegistry" < $DIRNAME/common.yaml)
COMMON_EXTERNAL_REGISTRY2=$(yq ".externalRegistry2" < $DIRNAME/common.yaml)
COMMON_EXTERNAL_REGISTRY3=$(yq ".externalRegistry3" < $DIRNAME/common.yaml)
COMMON_EXTERNAL_REGISTRY4=$(yq ".externalRegistry4" < $DIRNAME/common.yaml)
export MAIN_REPO=$(yq ".mainRepo" < $DIRNAME/common.yaml)
export REGISTRY=${REGISTRY:-${COMMON_MAIN_REGISTRY}}
export EXT_REGISTRY=${EXT_REGISTRY:-${COMMON_EXTERNAL_REGISTRY}}
export EXT_REGISTRY2=${EXT_REGISTRY2:-${COMMON_EXTERNAL_REGISTRY2}}
export EXT_REGISTRY3=${EXT_REGISTRY3:-${COMMON_EXTERNAL_REGISTRY3}}
export EXT_REGISTRY4=${EXT_REGISTRY4:-${COMMON_EXTERNAL_REGISTRY4}}
export KUBECTL_VERSION=1.33-debian-12