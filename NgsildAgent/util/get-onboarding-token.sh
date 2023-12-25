#!/bin/bash
# Copyright (c) 2023 Intel Corporation
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

# shellcheck disable=SC1091
. common.sh


secret_enabled=false;
usage="Usage: $(basename "$0") [-p password] [-s secret-file-name] <username>\n"
while getopts 's:p:h' opt; do
  # shellcheck disable=SC2221,SC2222
  case "$opt" in
    p)
      arg="$OPTARG"
      password="${arg}"
      ;;
    s)
      arg="$OPTARG"
      secret_file=$arg
      secret_enabled=true
      ;;
    ?|h)
      echo "$usage"
      exit 1
      ;;
  esac
done
shift "$((OPTIND -1))"

if [ $# -eq 1 ]; then
  username="$1"
else
  echo "Error: Expected <username>."
  echo "${usage}"
  exit 1
fi

if [ -z "${password}" ]; then
    echo -n Password: 
    read -rs password
fi;

function create_secret() {
    token=$(echo -n "$1"| base64 -w 0)
    randompf=$(tr -dc a-z0-9 </dev/urandom | head -c 12;)
cat >"$secret_file" << EOF
apiVersion: v1
kind: Secret
metadata:
  name: iff-device-onboarding-${randompf}
  namespace: ${DEVICES_NAMESPACE}
  labels:
    iff-device-onboarding: "true"
data:
  onboarding_token: ${token}
EOF
}


if [ ! -f "$DEVICE_FILE" ]; then
    echo "Device file not found: $DEVICE_FILE"
    exit 1
fi



keycloakurl=$(jq -r '.keycloak_url' "$DEVICE_FILE")
realmid=$(jq -r '.realm_id' "$DEVICE_FILE")


ONBOARDING_TOKEN_ENDPOINT="$keycloakurl/${realmid}/protocol/openid-connect/token"

response_token=$(curl -X POST "$ONBOARDING_TOKEN_ENDPOINT"  -d "client_id=device" \
-d "grant_type=password" -d "password=${password}" -d "username=${username}" 2>/dev/null | jq '.')

if [ -z "$response_token" ] || [ "$(echo "$response_token" | jq 'has("error")')" = "true" ]; then
    echo "Error: Invalid or no onbarding token received."
    exit 1
fi

# Replace access_key by device_key
if [ "$secret_enabled" = "true" ]; then
    create_secret "$response_token"
    echo "Device token secret stored in $secret_file"
else
    echo "$response_token" > "$ONBOARDING_TOKEN_FILE"
    echo "Device token stored in $ONBOARDING_TOKEN_FILE"
fi
