#!/usr/bin/env bats
# shellcheck disable=SC2005
# if [ -z "${SELF_HOSTED_RUNNER}" ]; then
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
MQTT_URL=emqx-listeners:1883
MQTT_TOPIC_NAME="spBv1.0/${NAMESPACE}/DDATA/${GATEWAY_ID}/${DEVICE_ID}"
MQTT_MESSAGE='{"timestamp":1655974018778,"metrics":[{ "name":"Property/https://industry-fusion.com/types/v0.9/state","timestamp":1655974018777,"dataType":"string","value":"https://industry-fusion.com/types/v0.9/state_OFF"}],"seq":1}'
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
KAFKACAT_ATTRIBUTES=/tmp/KAFKACAT_ATTRIBUTES
KAFKACAT_ATTRIBUTES_TOPIC=iff.ngsild.attributes
MQTT_SUB=/tmp/MQTT_SUB


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


compare_create_attributes() {
    cat << EOF | diff "$1" - >&3
{"id":"testdevice\\\\https://industry-fusion.com/types/v0.9/state",\
"entityId":"testdevice",\
"nodeType":"@value",\
"name":"https://industry-fusion.com/types/v0.9/state",\
"type":"https://uri.etsi.org/ngsi-ld/Property",\
"https://uri.etsi.org/ngsi-ld/hasValue":"https://industry-fusion.com/types/v0.9/state_OFF",\
"index":0}
EOF
}

compare_mqtt_sub(){
    cat << EOF | diff "$1" - >&3
{"timestamp":1655974018778,"metrics":[{ "name":"Property/https://industry-fusion.com/types/v0.9/state",\
"timestamp":1655974018777,"dataType":"string",\
"value":"https://industry-fusion.com/types/v0.9/state_OFF"}],"seq":1}
EOF
}

get_adminPassword() {
    echo "$(kubectl -n iff get cm/bridge-configmap -o jsonpath="{.data['config\.json']}"| jq .mqtt.adminPassword)"
}

get_adminUsername() {
    echo "$(kubectl -n iff get cm/bridge-configmap -o jsonpath="{.data['config\.json']}"| jq .mqtt.adminUsername)"
}

setup() {
    # shellcheck disable=SC2086
    if [ "$DEBUG" != "true" ]; then
        echo "This test works only in debug mode. Set DEBUG=true."
        exit 1
    fi
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

@test "verify device token can send data and is forwarded to Kafka" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    password=$(get_password)
    onboarding_token=$(get_onboarding_token)
    run check_onboarding_token "${onboarding_token}"
    [ "${status}" -eq "0" ]
    token=$(exchange_onboarding_token)
    run check_device_token_from_exchange "${token}"
    [ "${status}" -eq "0" ]
    run mosquitto_pub -L "mqtt://${DEVICE_ID}:${token}@${MQTT_URL}/${MQTT_TOPIC_NAME}" -m "${MQTT_MESSAGE}"
    [ "${status}" -eq "0" ]
    echo "# Sent mqtt sparkplugB message, sleep 2s to let bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes ${KAFKACAT_ATTRIBUTES}
    [ "$status" -eq 0 ]
}
@test "verify mqtt admin can send and receive data" {
    $SKIP
    password=$(get_adminPassword | tr -d '"')
    username=$(get_adminUsername | tr -d '"')
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${username}:${password}@${MQTT_URL}/${MQTT_TOPIC_NAME}" >${MQTT_SUB}) &
    sleep 2
    run mosquitto_pub -L "mqtt://${username}:${password}@${MQTT_URL}/${MQTT_TOPIC_NAME}" -m "${MQTT_MESSAGE}"
    [ "${status}" -eq "0" ]
    echo "# Sent mqtt sparkplugB message, sleep 2s to let bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall mosquitto_sub
    echo "# Compare ATTRIBUTES"
    run compare_mqtt_sub ${MQTT_SUB}
    [ "$status" -eq 0 ]
}
