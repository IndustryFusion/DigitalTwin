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

DEVICES_NAMESPACE=devices
usage="Usage: $(basename $0) [-s] [-f]"
while getopts 'sfh' opt; do
  case "$opt" in
    f)
      file=true
      ;;
    s)
      secret=true
      ;;
    ?|h)
      printf "$usage"
      exit 1
      ;;
  esac
done
shift "$(($OPTIND -1))"

if [ -n "$file" ] && [ -n "$secret" ]; then
  echo "Error: Both -f and -s cannot be set"
  printf "${usage}"
  exit 1
fi
if [ -z "$file" ] && [ -z "$secret" ]; then
  echo "Error: Either -f and -s must be set"
  printf "${usage}"
  exit 1
fi

# Define the JSON file path
onboard_token_json_file="../data/onboard-token.json"
dev_json_file="../data/device.json"

# Check if the file exists
if [ ! -f "$dev_json_file" ]; then
    echo "JSON file not found: $dev_json_file. Initialization of device is needed."
    exit 1
fi



function get_token() {
  secrets=$(kubectl -n ${DEVICES_NAMESPACE} get secret -l iff-device-onboarding=true -oname)
  for secret in $secrets; do
    echo "Processing Secret $secret" >&2
    token=$(kubectl -n ${DEVICES_NAMESPACE} get $secret -o jsonpath='{.data.onboarding_token}')
    if kubectl -n ${DEVICES_NAMESPACE} delete $secret 2>&1 >/dev/null; then 
      echo $token
      break
    fi
  done
}

if [ -z "$file" ]; then
  success=false
  while [ "$success" = "false" ]; do
    echo "Waiting for secrets ..."
    raw_token=$(get_token)
    token=$(echo $raw_token | base64 -d ) || token=""
    if [ -n "$token" ]; then
      success=true
    fi
    sleep 2
  done
else
if [ ! -f "$onboard_token_json_file" ]; then
    echo "JSON file not found: $onboard_token_json_file. But this is needed for onboarding from token file."
    exit 1
fi
token=$(cat $onboard_token_json_file) 
fi


refresh_token=$(jq -r '.refresh_token' "$onboard_token_json_file")
if [ -z "$refresh_token" ]; then
    echo "refresh_token not found, please check again"
    exit 1
fi

keycloakurl=$(jq -r '.keycloakUrl' "$dev_json_file")
gatewayid=$(jq -r '.gateway_id' "$dev_json_file")
deviceid=$(jq -r '.device_id' "$dev_json_file")

# Check if the file exists
if [ -z "$keycloakurl" ] || [ -z "$gatewayid" ] ||[ -z "$deviceid" ]; then
    echo "device json file doesnot contain required item, please do initialize device."
    exit 1
fi

# Define the API endpoint
DEVICE_TOKEN_ENDPOINT="$keycloakurl/protocol/openid-connect/token"
echo "API endpoint is :" $DEVICE_TOKEN_ENDPOINT
# Make the curl request with access token as a header and store the response in the temporary file
device_token=$(curl -X POST "$DEVICE_TOKEN_ENDPOINT"  -d "client_id=device" \
-d "grant_type=refresh_token" -d "refresh_token=${refresh_token}" -d "audience=device" \
-H "X-GatewayID: $gatewayid" -H "X-DeviceID: $deviceid" 2>/dev/null | jq '.')

if [ "$(echo $device_token | jq 'has("error")')" = "true" ]; then
    echo "Error: Onboarding token coule not be retrieved."
    exit 1
fi
if [ -n "$(echo $device_token | jq '.access_token' | tr -d '"' | jq -R 'split(".") | .[1] | @base64d | fromjson' | grep TAINTED)" ]; then
    echo "Error: Tainted onbarding token found."
    exit 1
fi

# Replace access_key by device_key
device_token=$(echo $device_token | jq 'with_entries(if .key == "access_token" then .key = "device_token" else . end)')
updated_json_data=$(jq --argjson response "$device_token" '. += $response' "$dev_json_file")
echo "$updated_json_data" > "$dev_json_file"

echo "Device token stored in $dev_json_file " 

