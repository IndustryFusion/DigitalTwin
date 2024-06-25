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


function checkurn(){
  local deviceid="$1"
  urnPattern='^urn:[a-zA-Z0-9][a-zA-Z0-9-]{0,31}:[a-zA-Z0-9()+,\-\.:=@;$_!*%/?#]+$'
  if echo "$deviceid" | grep -E -q "$urnPattern"; then
      echo "$deviceid is URN compliant."
  else
      echo "$deviceid must be an URN. Please fix the parameter $deviceid. Exiting."
      exit 1
  fi
}
keycloakurl="http://keycloak.local/auth/realms"
realmid="iff"
usage="Usage: $(basename "$0")[-k keycloakurl] [-r realmId] [-d additionalDeviceIds] <deviceId> <gatewayId>\nDefaults: \nkeycloakurl=${keycloakurl}\nrealmid=${realmid}\n"
while getopts 'k:r:d:h' opt; do
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
    d)
      additionalDeviceIds+=("$OPTARG")
      echo "Added additional deviceId ${OPTARG}"
    ;;
    ?|h)
      printf "$usage"
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

checkurn $deviceid
if [ ! -z "${additionalDeviceIds}" ]; then
  #deviceid='["'${deviceid}'"'
  for i in "${additionalDeviceIds[@]}"; do
    checkurn $i
    #echo proecessing $i
    #deviceid=${deviceid}', "'$i'"'
  done
  #deviceid=${deviceid}']'
#else
#  deviceid='["'${deviceid}'"]'
fi
 # shellcheck disable=2016
echo Processing with deviceid="${deviceid}" gatewayid="${gatewayid}" keycloakurl="${keycloakurl}" realmid="${realmid}"

if [ ! -d ../data ]; then
  mkdir ../data
fi

#Check if Jq is installed or not 
if ! dpkg -l | grep -q "jq"; then
    echo "jq is not installed. Install it..."
    exit 1
fi


# To preserve backward compatibility, there are now two fields, device_id and device_ids
commaSeparatedIds=
for i in "${additionalDeviceIds[@]}"; do
    if [ -n "$commaSeparatedIds" ]; then
        commaSeparatedIds+=","
    fi
    commaSeparatedIds+=$i
done

# Define the JSON file path
json_data=$(jq -n \
        --arg deviceIds "$commaSeparatedIds" \
        --arg deviceid "$deviceid" \
        --arg gatewayId "$gatewayid" \
        --arg realmId "$realmid" \
        --arg keycloakUrl "$keycloakurl" \
        '
        $deviceIds | split(",") as $ids | {
            "device_id": $deviceid,
            "subdevice_ids": $ids,
            "gateway_id": $gatewayId,
            "realm_id": $realmId,
            "keycloak_url": $keycloakUrl
        }')

# Create a new file and write the JSON data to it
echo "$json_data" > "$DEVICE_FILE"

echo "Data has been saved to $DEVICE_FILE"
