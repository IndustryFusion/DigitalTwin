DIRNAME=$(dirname ${BASH_SOURCE[0]})
source $DIRNAME/../.env
export NAMESPACE=iff
export LOCAL_REGISTRY=k3d-iff.localhost:12345
export EMQX_OPERATOR_NAMESPACE=emqx-operator-system
export EMQX_OPERATOR_VERSION="2.2.29"
export EMQX_VERSION=$(yq ".emqx.imageVersion" < $DIRNAME/common.yaml)
export POSTGRES_OPERATOR_VERSION="v1.9.0"
export VELERO_HELM_VERSION=velero-10.1.3
export VELERO_PLUGIN_VERSION="v1.12.2"
export VELERO_VERSION="v1.16.2"
export MINIO_OPERATOR_VERSION="5.0.14"
export CERT_MANAGER_VERSION="1.9.1"
export STRIMZI_VERSION="0.45.1"
export OFFLINE=${OFFLINE:-false}
export OFFLINE_DIR=$(cd $DIRNAME/airgap-deployment; pwd)
export KEYCLOAK_VERSION=25.0.0
export RELOADER_HELM_VERSION=v1.0.67
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
export KUBECTL_VERSION=1.28-debian-11

# Optional corporate/network proxy configuration.
# Build and deploy may run on different machines/networks (e.g. a build
# host behind proxy A pushing images, and a deploy/CI runner behind proxy B
# or no proxy at all), so the proxy value itself must NOT be hardcoded in a
# shared, git-tracked file - each host's own OS-level environment (e.g.
# HTTP_PROXY/HTTPS_PROXY/NO_PROXY exported via /etc/environment on Ubuntu)
# is the single source of truth per host. This just normalizes the
# upper/lowercase variants consistently so every consumer (Docker, Maven via
# generated settings.xml in test/prepare-platform.sh, Helm's Go net/http
# client for chart repo fetches) sees the same values without duplicating
# this logic elsewhere.
export HTTP_PROXY="${HTTP_PROXY:-${http_proxy:-}}"
export HTTPS_PROXY="${HTTPS_PROXY:-${https_proxy:-}}"
export NO_PROXY="${NO_PROXY:-${no_proxy:-}}"
export http_proxy="$HTTP_PROXY"
export https_proxy="$HTTPS_PROXY"
export no_proxy="$NO_PROXY"