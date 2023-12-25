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

keycloakurl="http://keycloak.local/auth/realms"
realmid="iff"
usage="Usage: $(basename "$0") <deviceId> <gatewayId> [-k keycloakurl] [-r realmId]\nDefaults: \nkeycloakurl=${keycloakurl}\nrealmid=${realmid}\n"
while getopts 'k:r:h' opt; do
  # shellcheck disable=SC2221,SC2222
  case "$opt" in
    k)
      arg="$OPTARG"
      echo "Keycloak url is set to '${arg}'"
      keycloakurl="${arg}"
      ;;
    r)
      arg="$OPTARG"
      echo "Realm url is set to '${arg}'"
      realmid="${OPTARG}"
      ;;
    ?|h)
      echo "$usage"
      exit 1
      ;;
  esac
done
shift "$((OPTIND -1))"

if [ $# -eq 2 ]; then
  deviceid="$1"
  gatewayid="$2"
else
  echo "Error: Expected deviceid and gatewayid."
  echo "${usage}"
  exit 1
fi

 # shellcheck disable=2016
urnPattern='^urn:[a-zA-Z0-9][a-zA-Z0-9-]{0,31}:[a-zA-Z0-9()+,\-\.:=@;$_!*%/?#]+$'
if echo "$deviceid" | grep -E -q "$urnPattern"; then
    echo "$deviceid is URN compliant."
else
    echo "$deviceid must be an URN. Please fix the deviceId. Exiting."
    exit 1
fi

echo Processing with deviceid="${deviceid}" gatewayid="${gatewayid}" keycloakurl="${keycloakurl}" realmid="${realmid}"

if [ ! -d ../data ]; then
  mkdir ../data
fi

#Check if Jq is installed or not 
if ! dpkg -l | grep -q "jq"; then
    echo "jq is not installed. Install it..."
    exit 1
fi

# Define the JSON file path

json_data=$(jq -n \
        --arg deviceId "$deviceid" \
        --arg gatewayId "$gatewayid" \
        --arg realmId "$realmid" \
        --arg keycloakUrl "$keycloakurl" \
        '{ 
            "device_id": $deviceId, 
            "gateway_id": $gatewayId,
            "realm_id": $realmId,
            "keycloak_url": $keycloakUrl
        }')

# Create a new file and write the JSON data to it
echo "$json_data" > "$DEVICE_FILE"

echo "Data has been saved to $DEVICE_FILE"
