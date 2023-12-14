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



# Define the JSON file path
onboard_token_json_file="../data/onboard-token.json"
dev_json_file="../data/device.json"

# Check if the file exists
if [ ! -f "$dev_json_file" ]; then
    echo "JSON file not found: $dev_json_file"
    exit 1
fi

if [ ! -f "$onboard_token_json_file" ]; then
    echo "JSON file not found: $onboard_token_json_file"
    exit 1
fi

access_token=$(jq -r '.access_token' "$onboard_token_json_file")
if [ -z "$access_token" ]; then
    echo "access_token not found, please check again"
    exit 1
fi

keycloakurl=$(jq -r '.keycloakUrl' "$dev_json_file")
gatewayid=$(jq -r '.gateway_id' "$dev_json_file")
deviceid=$(jq -r '.device_id' "$dev_json_file")

# Check if the file exists
if [ -z "$keycloakurl" ] || [ -z "$gatewayid" ] ||[ -z "$deviceid" ]; then
    echo "device json file doesnot contain required item, may run again ./set-device.sh"
    exit 1
fi

# Define the API endpoint
ONBOARDING_TOKEN_ENDPOINT="$keycloakurl/protocol/openid-connect/token"
echo "API endpoint is :" $ONBOARDING_TOKEN_ENDPOINT
# Make the curl request with access token as a header and store the response in the temporary file
response_token=$(curl -X POST "$ONBOARDING_TOKEN_ENDPOINT" -d "client_id=device-onboarding" -d "subject_token=$access_token" \
-d "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" -d "requested_token_type=urn:ietf:params:oauth:token-type:refresh_token" \
-d "audience=device" -H "X-GatewayID: $gatewayid" -H "X-DeviceID: $deviceid" -H "X-Access-Type: device" -H "X-DeviceUID: uid" 2>/dev/null | jq '.')

if [ "$(echo $response_token | jq 'has("error")')" = "true" ]; then
    echo "Error: Invalid onbarding token found."
    exit 1
fi

# Replace access_key by device_key
response_token=$(echo $response_token | jq 'with_entries(if .key == "access_token" then .key = "device_token" else . end)')
echo $response_token
updated_json_data=$(jq --argjson response "$response_token" '. += $response' "$dev_json_file")
echo "$updated_json_data" > "$dev_json_file"

echo "Device token stored in $dev_json_file " 