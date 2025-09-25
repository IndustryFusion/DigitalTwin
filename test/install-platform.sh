#!/bin/bash
# Copyright (c) 2022, 2024 Intel Corporation
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

. ../helm/env.sh

usage="Usage: $(basename "$0") [-t label] [-c command] [-olsv] <command>\n-t:\
    Define label to apply\n-o:\
    offline installation\n-l:\
    local installation (for test & debug)\n-c:\
    command: apply|sync|all|show|destroy|opinst|opuninst\n-v:\
    verbose output\n"
while getopts 't:c:olsv' opt; do
  # shellcheck disable=SC2221,SC2222
  case "$opt" in
    t)
      arg="$OPTARG"
      labels="${arg}"
      ;;
    o)
      export OFFLINE=true
      ;;
    l)
      export LOCAL=true
      ;;
    c)
      arg="$OPTARG"
      command="${arg}"
      ;;
    ?|h)
      printf "$usage"
      exit 1
      ;;
  esac
done

case $command in
  apply)
    apply=true
  ;;
  sync)
    sync=true
  ;;
  all)
    all=true
  ;;
  destroy)
    destroy=true
  ;;
  opinst)
    install_operators=true
  ;;
  opuninst)
    uninstall_operators=true
  ;;
  show)
    showonly=true
  ;;
  *)
    echo "Unknown command given."
    printf "$usage"
    exit 1
  ;;
esac


if [ "$LOCAL" = "true" ]; then
    export REGISTRY=${LOCAL_REGISTRY}
fi
if [ "$OFFLINE" = "true" ]; then
    export REGISTRY=${LOCAL_REGISTRY}
    export EXT_REGISTRY=${LOCAL_REGISTRY}
    export EXT_REGISTRY2=${LOCAL_REGISTRY}
    export EXT_REGISTRY3=${LOCAL_REGISTRY}
    export EXT_REGISTRY4=${LOCAL_REGISTRY}
fi


set_helm_params(){
    echo --set mainRegistry=$REGISTRY \
    --set externalRegistry=$EXT_REGISTRY \
    --set externalRegistry2=$EXT_REGISTRY2 \
    --set externalRegistry3=$EXT_REGISTRY3 \
    --set externalRegistry4=$EXT_REGISTRY4 \
    --set mainVersion=$DOCKER_TAG
}

install_operators(){
    echo Install operators
    ( cd ../helm && bash ./install_operators.sh )

    echo Test whether operators are coming up
    ( cd ./bats && bats test-operators/*.bats )
}

uninstall_operators(){
    echo "Uninstall operators (except minio)"
    ( cd ../helm && bash ./uninstall_operators.sh )

}

apply_labels(){
    labels=$1
    command=$2
    if [ -z "$command" ] || [ -z "$labels" ]; then
      echo "No labels or command defined. Nothing applied"
      return
    fi
    if [ -n "$verbose" ]; then
      echo Executing helmfile command: ./helmfile  $(set_helm_params) -l $labels $command
    fi
    if [ ! "$command" = "destroy" ]; then
      ( cd ../helm && \
          ./helmfile  $(set_helm_params) -l $labels $command)
    else 
      if [ "$command" = "destroy" ]; then
      echo "( cd ../helm && ./helmfile -l $labels $command )"
        ( cd ../helm &&
            ./helmfile -l $labels $command )
      fi
    fi

}

install_velero(){
   command=$1
   if [ "$OFFLINE" = "true" ]; then
        echo Install velero in offline mode
        ( cd ../helm && ./helmfile $(set_helm_params) \
        --set "velero.image.repository=$LOCAL_REGISTRY/velero/velero" \
        --set "velero.kubectl.image.repository=$LOCAL_REGISTRY/bitnamilegacy/kubectl" \
        --set "velero.kubectl.image.tag=${KUBECTL_VERSION}" \
        --set "velero.initContainers[0].image=$LOCAL_REGISTRY/velero/velero-plugin-for-aws:${VELERO_PLUGIN_VERSION}" -l app=velero $command
        )
    else
        echo Install velero from remote registry
        ( cd ../helm && ./helmfile $(set_helm_params) \
        --set "velero.kubectl.image.tag=${KUBECTL_VERSION}" \
        -l app=velero $command
        )
    fi
}


echo Additional HELM parameters: $(set_helm_params)

if [ -n "$showonly" ]; then
    exit 0
fi

echo "$apply$destroy$sync" and $labels
if [ "$apply$destroy$sync" = "true" ] && [ -z "$labels" ]; then
    echo "Error: Label must be defined for this command."
    printf "$usage"
    exit 1
fi

if [ -n "$sync" ] && [ -z "$labels" ]; then
    echo "Error: -y needs -t defined as well"
    exit 1
fi

if [ -n "$destroy" ] && [ -z "$labels" ]; then
    echo "Error: -d needs -l defined as well"
    exit 1
fi

# Protect minio :-)
if [ -n "$label" ] && [ -n "$destroy" ]; then
  label=$label",app!=minio"
fi


if [ -n "$all" ]; then
    echo Full installation
    install_operators
    echo Install first part
    apply_labels "order=first" apply
    #( cd ../helm && ./helmfile -l order=first apply $(set_helm_params) )
    ( cd ./bats && bats test-jobs/keycloak-realm-import-job-is-up.bats )
    # Increase backoff limit for realm import job, unfortunately, right now,
    # keycloak operator does not reset the job if backoff limit is exceeded,
    # this behavior will probably be fixed in the future
    kubectl -n ${NAMESPACE} patch job iff-keycloak-realm-import -p '{"spec":{"backoffLimit":60}}'
    ( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-first.bats )
            
    echo Install second part
    apply_labels "order=second" apply
    #( cd ../helm && ./helmfile -l order=second apply $(set_helm_params) )
    ( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-second.bats )

    echo Setup Ingress for localhost
    bash ./setup-local-ingress.sh

    echo Install third part
    apply_labels "order=third" apply
    #( cd ../helm && ./helmfile -l order=third apply $(set_helm_params) )
    ( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-third.bats )

    install_velero apply

    echo Install the rest
    apply_labels "app!=velero,order!=first,order!=second,order!=third" apply || echo "No remaining chart found." 
    ( cd ./bats && bats test-horizontal-platform/horizontal-platform-up-and-running-velero.bats )
fi
if [ -n "$apply" ]; then
    if [ "$labels" = "app=velero" ];then
      install_velero apply
    else
      echo Only apply labels $labels
      apply_labels "$labels" apply
    fi
fi
if [ -n "$sync" ]; then
    if [ "$labels" = "app=velero" ];then
      install_velero sync
    else
      echo Only sync labels $labels
      apply_labels "$labels" sync
    fi
fi
if [ -n "$destroy" ]; then
    echo Only destroy labels $labels
    apply_labels "$labels" destroy
fi
if [ -n "$install_operators" ]; then
    echo Installing Operators only
    install_operators
fi
if [ -n "$uninstall_operators" ]; then
    echo Installing Operators only
    uninstall_operators
fi