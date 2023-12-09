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
json_file="../data/device.json"
temp_token_json_file="../data/onboard-token.json"

usage="Usage: $(basename $0) [-p userpassword] [-t]\n"
while getopts 'p:ht' opt; do
  case "$opt" in
    p)
      arg="$OPTARG"
      password="${arg}"
      ;;
    t)
      testmode=true
      ;;
    ?|h)
      printf "$usage"
      exit 1
      ;;
  esac
done
shift "$(($OPTIND -1))"

if [ -z "$password" ] && [ -z "$testmode" ]; then
    echo "Error: Either password or testflag must be set."
    exit 1
fi
if [ -n "$password" ] && [ -n "$testmode" ]; then
    echo "Error: password and testflag cannot be set both."
    exit 1
fi

# Check if the file exists
if [ ! -f "$json_file" ]; then
    echo "JSON file not found: $json_file"
    exit 1
fi

if [ -n "$testmode" ]; then
    PASSWORD=$(kubectl get secret credential-iff-realm-user-iff -n iff -o jsonpath='{.data.password}' | base64 --decode)
else
    PASSWORD=${password}
fi

# Check if the file exists
if [ -z "$PASSWORD" ]; then
    echo "Password not found, exiting script"
    exit 1
fi

keycloakurl=$(jq -r '.keycloakUrl' "$json_file")
# Check if the file exists
if [ -z "$keycloakurl" ]; then
    echo "keycloakurl not found, may run again ./set-device.sh"
    exit 1
fi

# Define the API endpoint
ONBOARDING_TOKEN_ENDPOINT="$keycloakurl/protocol/openid-connect/token"
echo "API endpoint is :" $ONBOARDING_TOKEN_ENDPOINT
# Make the curl request with "name" as a header and store the response in the temporary file
response_token=$(curl -X POST "$ONBOARDING_TOKEN_ENDPOINT" -d "client_id=device-onboarding" -d "username=realm_user" -d "password=$PASSWORD" \
-d "grant_type=password" | jq '.')
echo "response token" $response_token

# Overwrite the JSON file with the updated JSON data
echo "$response_token" > "$temp_token_json_file"
access_token=$(jq -r '.access_token' "$temp_token_json_file")
if [ -z "$access_token" ]; then
    echo "access_token not found, please check again. For reference received response is: $response_token"
    exit 1
fi

echo "Curl requests completed and responses stored in $temp_token_json_file " 