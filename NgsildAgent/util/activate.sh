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

usage="Usage: $(basename "$0") [-s] [-f]\n"
while getopts 'sfh' opt; do
  # shellcheck disable=SC2221,SC2222
  case "$opt" in
    f)
      file=true
      ;;
    s)
      secret=true
      ;;
    ?|h)
      echo "$usage"
      exit 1
      ;;
  esac
done
shift "$((OPTIND -1))"

if [ -n "$file" ] && [ -n "$secret" ]; then
  echo "Error: Both -f and -s cannot be set"
  echo "${usage}"
  exit 1
fi
if [ -z "$file" ] && [ -z "$secret" ]; then
  echo "Error: Either -f and -s must be set"
  echo "${usage}"
  exit 1
fi

# Check if the file exists
if [ ! -f "$DEVICE_FILE" ]; then
    echo "JSON file not found: $DEVICE_FILE. Initialization of device is needed."
    exit 1
fi



function get_token() {
  secrets=$(kubectl -n "${DEVICES_NAMESPACE}" get secret -l iff-device-onboarding=true -oname)
  for secret in $secrets; do
    echo "Processing Secret $secret" >&2
    token=$(kubectl -n "${DEVICES_NAMESPACE}" get "$secret" -o jsonpath='{.data.onboarding_token}')
    if kubectl -n "${DEVICES_NAMESPACE}" delete "$secret"  >/dev/null 2>&1; then 
      echo "$token"
      break
    fi
  done
}

if [ -z "$file" ]; then
  success=false
  while [ "$success" = "false" ]; do
    echo "Waiting for secrets ..."
    raw_token=$(get_token)
    token=$(echo "$raw_token" | base64 -d ) || token=""
    if [ -n "$token" ]; then
      success=true
    fi
    sleep 2
  done
else
if [ ! -f "$ONBOARDING_TOKEN_FILE" ]; then
    echo "JSON file not found: $ONBOARDING_TOKEN_FILE. But this is needed for onboarding from token file."
    exit 1
fi
  token=$(cat "$ONBOARDING_TOKEN_FILE") 
fi


refresh_token=$(echo "$token" | jq -r '.refresh_token')
orig_token=$(echo "$token" | jq -r '.access_token')
if [ -z "$refresh_token" ]; then
    echo "refresh_token not found, please check again"
    exit 1
fi

keycloakurl=$(jq -r '.keycloak_url' "$DEVICE_FILE")
realmid=$(jq -r '.realm_id' "$DEVICE_FILE")
gatewayid=$(jq -r '.gateway_id' "$DEVICE_FILE")
deviceid=$(jq -r '.device_id' "$DEVICE_FILE")

# Check if the file exists
if [ -z "$keycloakurl" ] || [ -z "$gatewayid" ] || [ -z "$deviceid" ] || [ -z "$realmid" ]; then
    echo "device json file doesnot contain required item, please do initialize device."
    exit 1
fi

# Define the API endpoint
DEVICE_TOKEN_ENDPOINT="$keycloakurl/${realmid}/protocol/openid-connect/token"
echo "API endpoint is : $DEVICE_TOKEN_ENDPOINT"
# Make the curl request with access token as a header and store the response in the temporary file
device_token=$(curl -X POST "$DEVICE_TOKEN_ENDPOINT"  -d "client_id=device" \
-d "grant_type=refresh_token" -d "refresh_token=${refresh_token}" -d "orig_token=${orig_token}" -d "audience=device" \
-H "X-GatewayID: $gatewayid" -H "X-DeviceID: $deviceid" 2>/dev/null | jq '.')

if [ "$(echo "$device_token" | jq 'has("error")')" = "true" ]; then
    echo "Error: Onboarding token coule not be retrieved."
    exit 1
fi
# shellcheck disable=SC2143
if [ -n "$(echo "$device_token" | jq '.access_token' | tr -d '"' | jq -R 'split(".") | .[1] | @base64d | fromjson' | grep TAINTED)" ]; then
    echo "Error: Tainted onbarding token found."
    exit 1
fi

# Replace access_key by device_key
device_token=$(echo "$device_token" | jq 'with_entries(if .key == "access_token" then .key = "device_token" else . end)')
updated_json_data=$(jq --argjson response "$device_token" '. += $response' "$DEVICE_FILE")
echo "$updated_json_data" > "$DEVICE_FILE"

echo "Device token stored in $DEVICE_FILE" 

