#!/bin/bash
# Author: Yatindra shashi
# Brief: Script to onboard a new device
# Description: Dependend on Environment variables get device onboarding token

# Define the JSON file path
json_file="./data/user_data.json"

# Check if the file exists
if [ ! -f "$json_file" ]; then
    echo "JSON file not found: $json_file"
    exit 1
fi


# Read JSON data from the file and construct and execute API requests
while read -r json_data; do
    # Extract "name" and "age" from JSON data using jq
    keycloakurl=$(echo "$json_data" | jq -r '.keycloakUrl')

    # Define the API endpoint
    ONBOARDING_TOKEN_ENDPOINT="$keycloakurl/protocol/openid-connect/token"
   echo "API endpoint is :" $API_ENDPOINT
    # Make the curl request with "name" as a header and store the response in the temporary file
    response_token=$(curl -X POST "$ONBOARDING_TOKEN_ENDPOINT" \
   -d "client_id=device-onboarding" \ 
   -d "username=realm_user" \
   -d "password=HqYOBCcZypuhtPzzJltxjdp0TqgBbIiy" \
   -d "grant_type=password")

   updated_json_data=$(jq --arg response "$response_TOKEN" '. + {responseToken: $response}' <<< "$json_data")

    # Overwrite the JSON file with the updated JSON data
    echo "$updated_json_data" > "$json_file"

done < "$json_file"

echo "Curl requests completed and responses stored in $json_file"