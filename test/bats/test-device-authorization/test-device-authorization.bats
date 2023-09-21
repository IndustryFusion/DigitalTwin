#!/usr/bin/env bats

# if [ -z "${SELF_HOST_RUNNER}" ]; then
#    SUDO="sudo -E"
# fi

DEBUG=${DEBUG:-false}
SKIP=
NAMESPACE=iff
USER_SECRET=secret/credential-iff-realm-user-iff
USER=realm_user
KEYCLOAK_URL=http://keycloak.local/auth/realms
ONBOARDING_CLIENT_ID="device-onboarding"
DEVICE_CLIENT_ID="device"
GATEWAY_ID="testgateway"
DEVICE_ID="testdevice"
DEVICE_TOKEN_SCOPE="accounts device_id gateway mqtt-broker offline_access oisp_frontend type"
DEVICE_TOKEN_AUDIENCE_FROM_EXCHANGE='["device","mqtt-broker","oisp-frontend"]'
DEVICE_TOKEN_AUDIENCE_FROM_DIRECT='["mqtt-broker","oisp-frontend"]'
MQTT_URL=emqx:1883
MQTT_TOPIC_NAME="spBv1.0/${NAMESPACE}/DDATA/${GATEWAY_ID}/${DEVICE_ID}"
MQTT_MESSAGE='{"timestamp":1655974018778,"metrics":[{ "name":"Property/https://industry-fusion.com/types/v0.9/state","alias":"testalias","timestamp":1655974018777,"dataType":"string","value":"https://industry-fusion.com/types/v0.9/state_OFF"}],"seq":1}'

get_password() {
    kubectl -n ${NAMESPACE} get ${USER_SECRET} -o jsonpath='{.data.password}' | base64 -d
}

get_onboarding_token() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${ONBOARDING_CLIENT_ID}" \
        -d "grant_type=password" \
        -d "username=${USER}" \
        -d "password=${password}" \
        | jq ".access_token" | tr -d '"'
}

exchange_onboarding_token() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${ONBOARDING_CLIENT_ID}" \
        -d "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" \
        -d "subject_token=${onboarding_token}" \
        -d "requested_token_type=urn:ietf:params:oauth:token-type:refresh_token" \
        -d "audience=${DEVICE_CLIENT_ID}" \
        -H "X-DeviceID: ${DEVICE_ID}" \
        -H "X-GatewayID: ${GATEWAY_ID}" \
        -H "X-Access-Type: device" \
        | jq ".access_token" | tr -d '"'
}

get_device_token() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${DEVICE_CLIENT_ID}" \
        -d "grant_type=password" \
        -d "username=${USER}" \
        -d "password=${password}" \
        -H "X-DeviceID: ${DEVICE_ID}" \
        -H "X-GatewayID: ${GATEWAY_ID}" \
        -H "X-Access-Type: device" \
        | jq ".access_token" | tr -d '"'
}

check_device_token_audience_from_exchange() {
    field=$(echo "$1" | jq -rc '.aud | sort')
    [ "$field" = "${DEVICE_TOKEN_AUDIENCE_FROM_EXCHANGE}" ] || { echo "wrong value for field audience: $field!=${DEVICE_TOKEN_AUDIENCE_FROM_EXCHANGE}"; return 1; }
    return 0
}

check_device_token_audience_from_direct() {
    field=$(echo "$1" | jq -rc '.aud | sort')
    [ "$field" = "${DEVICE_TOKEN_AUDIENCE_FROM_DIRECT}" ] || { echo "wrong value for field audience: $field!=${DEVICE_TOKEN_AUDIENCE_FROM_DIRECT}"; return 1; }
    return 0
}

check_device_token_scope() {
    field=$(echo "$1" | jq ".scope" | tr -d '"' | xargs -n1 | LC_ALL="en_US.UTF-8" sort | xargs)
    [ "$field" = "${DEVICE_TOKEN_SCOPE}" ] || { echo "wrong value for field scope: $field!=${DEVICE_TOKEN_SCOPE}"; return 1; }
    return 0
}

check_json_field() {
    field=$(echo "$1" | jq ".$2" | tr -d '"')
    [ "$field" = "$3" ] || { echo "wrong value for field $2: $field!=$3"; return 1; }
    return 0
}

check_onboarding_token() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device-onboarding" || return 1
    check_json_field "${jwt}" "scope" "" || return 1
    return 0
}

check_device_token_from_exchange() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device-onboarding" || return 1
    check_json_field "${jwt}" "device_id" "${DEVICE_ID}" || return 1
    check_json_field "${jwt}" "type" "device" || return 1
    check_json_field "${jwt}" "gateway" "${GATEWAY_ID}" || return 1
    check_device_token_scope "${jwt}"
    check_device_token_audience_from_exchange "${jwt}"
    return 0
}

check_device_token_from_direct() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_json_field "${jwt}" "device_id" "${DEVICE_ID}" || return 1
    check_json_field "${jwt}" "type" "device" || return 1
    check_json_field "${jwt}" "gateway" "${GATEWAY_ID}" || return 1
    check_device_token_scope "${jwt}"
    check_device_token_audience_from_direct "${jwt}"
    return 0
}

setup() {
    # shellcheck disable=SC2086
    # [ $DEBUG = "true" ] || (exec ${SUDO} kubefwd -n oisp -l app.kubernetes.io/name=emqxtest svc) &
    # echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    # sleep 3
    return 0
}

teardown() {
    # echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    # [ $DEBUG = "true" ] || ${SUDO} killall kubefwd
    return 0
}

@test "verify user can request onboarding token" {
    $SKIP
    password=$(get_password)
    onboarding_token=$(get_onboarding_token)
    run check_onboarding_token "${onboarding_token}"
    [ "${status}" -eq "0" ]
}

@test "verify onboarding token can be exchanged for a device token" {
    $SKIP
    password=$(get_password)
    onboarding_token=$(get_onboarding_token)
    run check_onboarding_token "${onboarding_token}"
    [ "${status}" -eq "0" ]
    token=$(exchange_onboarding_token)
    run check_device_token_from_exchange "${token}"
    [ "${status}" -eq "0" ]
}

@test "verify user can request device token directly" {
    $SKIP
    password=$(get_password)
    token=$(get_device_token)
    run check_device_token_from_direct "${token}"
    [ "${status}" -eq "0" ]
}

@test "verify device token can send data" {
    skip # remove once mqtt is migrated over digital twin
    password=$(get_password)
    onboarding_token=$(get_onboarding_token)
    run check_onboarding_token "${onboarding_token}"
    [ "${status}" -eq "0" ]
    token=$(exchange_onboarding_token)
    run check_device_token_from_exchange "${token}"
    [ "${status}" -eq "0" ]
    mosquitto_pub -L "mqtt://${DEVICE_ID}:${token}@${MQTT_URL}/${MQTT_TOPIC_NAME}" -m "${MQTT_MESSAGE}"
    [ "${status}" -eq "0" ]
    # TODO: Verify data is sent
}
