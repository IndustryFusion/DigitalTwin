#!/bin/bash
# Author: Yatindra shashi
# Brief: Script to set device configuration to onboard
# Description: Dependend on Environment variables use onboarding token or ask for it and get device token

if [ ! -d ../data ]; then
  mkdir ../data
fi

#Check if Jq is installed or not 
if ! dpkg -l | grep -q "jq"; then
    echo "jq is not installed. Installing it..."
    sudo apt-get update
    sudo apt-get install -y jq
    echo "jq has been installed."
else
    echo "jq is already installed."
fi

# Define the JSON file path
json_file="../data/device.json"

# Prompt the user for input
read -p "Enter device id: " deviceid
read -p "Enter gateway id: " gatewayid
read -p "Enter realm/factory id: " realmid
read -p "Enter complete keycloak url (or 'Enter' to use default http://keycloak.local/auth/realms/iff): " keycloakurl

# Check if the keycloak url is set to the default value
if [ -z "$keycloakurl" ]; then
    keycloakurl="http://keycloak.local/auth/realms/iff"
fi

json_data=$(jq -n \
        --arg deviceId "$deviceid" \
        --arg gatewayId "$gatewayid" \
        --arg realmId "$realmid" \
        --arg keycloakUrl "$keycloakurl" \
        '{ 
            "deviceId": $deviceId, 
            "gatewayId": $gatewayId,
            "realmId": $realmId,
            "keycloakUrl": $keycloakUrl
        }')
# Check if the file already exists
if [ -f "$json_file" ]; then
    # Append the JSON data to the existing file
    rm $json_file
    echo "$json_data" >> "$json_file"
else
    # Create a new file and write the JSON data to it
    echo "$json_data" > "$json_file"
fi

echo "Data has been saved to $json_file"
