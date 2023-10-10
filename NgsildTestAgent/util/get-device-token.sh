#!/bin/bash
# Author: Yatindra shashi
# Brief: Script to get device token to connect device to mqtt server
# Description: Dependend on Environment variables get device onboarding token

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

echo "If you are running on local host, please check if you already run script ../test/setup-local-ingress.sh"
access_token=$(jq -r '.access_token' "$onboard_token_json_file")
if [ -z "$access_token" ]; then
    echo "access_token not found, please check again"
    exit 1
fi

keycloakurl=$(jq -r '.keycloakUrl' "$dev_json_file")
gatewayid=$(jq -r '.gatewayId' "$dev_json_file")
deviceid=$(jq -r '.deviceId' "$dev_json_file")

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
-d "audience=device" -H "X-GatewayID: $gatewayid" -H "X-DeviceID: $deviceid" -H "X-Access-Type: device" -H "X-DeviceUID: uid" | jq '.')
echo "response token" $response_token

updated_json_data=$(jq --argjson response "$response_token" '. += $response' "$dev_json_file")
echo "$updated_json_data" > "$dev_json_file"

echo "Device token stored in $dev_json_file " 