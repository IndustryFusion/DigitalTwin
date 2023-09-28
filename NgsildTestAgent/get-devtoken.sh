#!/bin/bash
# Author: Yatindra shashi
# Brief: Script to onboard a new device
# Description: Dependend on Environment variables use onboarding token or ask for it and get device token
# Environemnt:
# - OISP_DEVICE_ID the device id for activation

# How can I check whether device is activated? There is only a test for connectivity
# For the time being, it checks whether device has a token.

function fail {
    echo $1
    exit 1
}

DATADIR=../../../data
CONFDIR=../../../config
ADMIN=../../../oisp-admin.js

echo onboarding with OISP_DEVICE_ACTIVATION_CODE=${OISP_DEVICE_ACTIVATION_CODE} OISP_DEVICE_ID=${OISP_DEVICE_ID} OISP_FORCE_REACTIVATION=${OISP_FORCE_REACTIVATION} OISP_DEVICE_NAME=${OISP_DEVICE_NAME} OISP_GATEWAY_ID=${OISP_GATEWAY_ID}
TOKEN=$(cat ${DATADIR}/device.json | jq ".device_token")
echo Token found: $TOKEN
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
