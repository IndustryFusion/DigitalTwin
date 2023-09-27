#!/bin/bash
# Author: Yatindra shashi
# Brief: Script to onboard a new device
# Description: Dependend on Environment variables get device token based on onboarding token env.
# Environemnt:
# - ONBOARDING_TOKEN if defined and device doesnot have device token, it will get using the code 
# - DEVICE_ID the device id for onboarding
# - KEYCLOAK_REALM_ID device realm Id
# - KEYCLOAK_URL 

# How can I check whether device is activated? There is only a test for connectivity
# For the time being, it checks whether device has a token.

function fail {
    echo $1
    exit 1
}

KEYCLOAK_DEFAULT_URL="http://keycloak.local/auth/realms"

if [ ! -d ./data ]; then
  mkdir ./data
fi

echo onboarding with OISP_DEVICE_ACTIVATION_CODE=${OISP_DEVICE_ACTIVATION_CODE} OISP_DEVICE_ID=${OISP_DEVICE_ID} OISP_FORCE_REACTIVATION=${OISP_FORCE_REACTIVATION} OISP_DEVICE_NAME=${OISP_DEVICE_NAME} OISP_GATEWAY_ID=${OISP_GATEWAY_ID}
TOKEN=$(cat ${DATADIR}/device.json | jq ".device_token")
echo Token found: $TOKEN


add_a_user()
{
  USER=$1
  PASSWORD=$2
  shift; shift;
  # Having shifted twice, the rest is now comments ...
  COMMENTS=$@
  echo "Adding user $USER ..."
  echo useradd -c "$COMMENTS" $USER
  echo passwd $USER $PASSWORD
  echo "Added user $USER ($COMMENTS) with pass $PASSWORD"
}

###
# Main body of script starts here
###
echo "Start of script..."
add_a_user bob letmein Bob Holness the presenter
add_a_user fred badpassword Fred Durst the singer
add_a_user bilko worsepassword Sgt. Bilko the role model
echo "End of script..."




if [ -z "$TOKEN" ] || [ "$TOKEN" = "\"\"" ] || [ "$TOKEN" = "false" ] || [ ! -z "$OISP_FORCE_REACTIVATION" ]; then
    if [ -z "$OISP_DEVICE_ACTIVATION_CODE" ]; then
        fail "No Device Activation Code given but no token found or reactivation is forced"
    fi
    ${ADMIN} test
    ${ADMIN} initialize
    if [ ! -z "$OISP_DEVICE_ID" ]; then
        ${ADMIN} set-device-id $OISP_DEVICE_ID
    else
        fail "No device id given"
    fi
    if [ ! -z "$OISP_DEVICE_NAME" ]; then
        ${ADMIN} set-device-name $OISP_DEVICE_NAME
    fi
    if [ ! -z "$OISP_GATEWAY_ID" ]; then
	${ADMIN} set-gateway-id $OISP_GATEWAY_ID
    fi
    echo ${ADMIN} activate $OISP_DEVICE_ACTIVATION_CODE
    ${ADMIN} activate $OISP_DEVICE_ACTIVATION_CODE || fail "Could not activate device"
fi
