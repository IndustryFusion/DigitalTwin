#!/usr/bin/env bats
# shellcheck disable=SC2005
# if [ -z "${SELF_HOSTED_RUNNER}" ]; then
#    SUDO="sudo -E"
# fi

load "../lib/utils"
load "../lib/detik"
load "../lib/config"
load "../lib/db"
load "../lib/mqtt"

DEBUG=${DEBUG:-false}
SKIP=
NAMESPACE=iff
USER_SECRET=secret/credential-iff-realm-user-iff
USER=realm_user
KEYCLOAK_URL=http://keycloak.local/auth/realms
DEVICE_CLIENT_ID="device"
GATEWAY_ID="testgateway"
GATEWAY_ID2="testgateway2"
DEVICE_ID="testdevice"
DEVICE_ID2="testdevice2"
DEVICE_TOKEN_SCOPE="device_id gateway mqtt-broker offline_access subdevice_ids"
DEVICE_TOKEN_AUDIENCE_FROM_DIRECT='mqtt-broker'
SUBDEVICE_IDS='"[\"testsubdevice1\"]"'
# shellcheck disable=SC2089
SUBDEVICE_IDS2='"[\"testsubdevice1\",\"testsubdevice2\",\"testsubdevice3\"]"'
MQTT_TOPIC_NAME="spBv1.0/${NAMESPACE}/DDATA/${GATEWAY_ID}/${DEVICE_ID}"
MQTT_SUBDEVICE_TOPIC_NAME="spBv1.0/${NAMESPACE}/DDATA/${GATEWAY_ID}/testsubdevice1"
MQTT_SUBDEVICE_TOPIC_NAME2="spBv1.0/${NAMESPACE}/DDATA/${GATEWAY_ID}/testsubdevice2"
MQTT_MESSAGE='{"timestamp":1655974018778,"metrics":[{ "name":"Property/https://industry-fusion.com/types/v0.9/state","timestamp":1655974018777,"dataType":"string","value":"https://industry-fusion.com/types/v0.9/state_OFF"}],"seq":1}'
MQTT_MESSAGE2='{"timestamp":1655974018778,"metrics":[{ "name":"Property/https://industry-fusion.com/types/v0.9/state","timestamp":1655974018777,"dataType":"string","value":"https://industry-fusion.com/types/v0.9/state_ON"}],"seq":1}'
MQTT_MESSAGE3='{"timestamp":1655974018778,"metrics":[{ "name":"Property/https://industry-fusion.com/types/v0.9/state","timestamp":1655974018777,"dataType":"string","value":"no"}],"seq":1}'
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
KAFKACAT_ATTRIBUTES=/tmp/KAFKACAT_ATTRIBUTES
KAFKACAT_ATTRIBUTES_SORTED=/tmp/KAFKACAT_ATTRIBUTES_SORTED
KAFKACAT_ATTRIBUTES_TOPIC=iff.ngsild.attributes
MQTT_SUB=/tmp/MQTT_SUB
MQTT_RESULT=/tmp/MQTT_RES
TAINTED='TAINTED'


get_password() {
    kubectl -n ${NAMESPACE} get ${USER_SECRET} -o jsonpath='{.data.password}' | base64 -d
}


get_vanilla_device_token() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${DEVICE_CLIENT_ID}" \
        -d "grant_type=password" \
        -d "username=${USER}" \
        -d "password=${password}" \
        | jq ".access_token" | tr -d '"'
}


get_vanilla_refresh_and_access_token() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${DEVICE_CLIENT_ID}" \
        -d "grant_type=password" \
        -d "username=${USER}" \
        -d "password=${password}"
        
}


get_refreshed_device_token() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${DEVICE_CLIENT_ID}" \
        -d "grant_type=refresh_token" \
        -d "refresh_token=$1" \
        -d "orig_token=$2" \
        -H "X-DeviceID: ${DEVICE_ID}" \
        -H "X-GatewayID: ${GATEWAY_ID}" \
        | jq ".access_token" | tr -d '"'
}

get_refreshed_device_token_with_subcomponents() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${DEVICE_CLIENT_ID}" \
        -d "grant_type=refresh_token" \
        -d "refresh_token=$1" \
        -d "orig_token=$2" \
        -H "X-DeviceID: ${DEVICE_ID}" \
        -H "X-GatewayID: ${GATEWAY_ID}" \
        -H "X-SubDeviceIDs: ${SUBDEVICE_IDS}" \
        | jq ".access_token" | tr -d '"'
}

get_refreshed_device_token_with_subcomponents2() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${DEVICE_CLIENT_ID}" \
        -d "grant_type=refresh_token" \
        -d "refresh_token=$1" \
        -d "orig_token=$2" \
        -H "X-DeviceID: ${DEVICE_ID}" \
        -H "X-GatewayID: ${GATEWAY_ID}" \
        -H "X-SubDeviceIDs: ${SUBDEVICE_IDS2}" \
        | jq ".access_token" | tr -d '"'
}

get_refreshed_device_token_with_wrong_ids() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${DEVICE_CLIENT_ID}" \
        -d "grant_type=refresh_token" \
        -d "refresh_token=$1" \
        -H "X-DeviceID: ${DEVICE_ID2}" \
        -H "X-GatewayID: ${GATEWAY_ID2}" \
        | jq ".access_token" | tr -d '"'
}

get_refreshed_refresh_token() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${DEVICE_CLIENT_ID}" \
        -d "grant_type=refresh_token" \
        -d "refresh_token=$1" \
        -H "X-DeviceID: ${DEVICE_ID}" \
        -H "X-GatewayID: ${GATEWAY_ID}" \
        | jq ".refresh_token" | tr -d '"'
}

get_refreshed_vanilla_token() {
    curl -X POST "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" \
        -d "client_id=${DEVICE_CLIENT_ID}" \
        -d "grant_type=refresh_token" \
        -d "refresh_token=$1" \
        -d "orig_token=$2" \
        | jq ".access_token" | tr -d '"'
}


check_vanilla_device_token_audience() {
    field=$(echo "$1" | jq -rc '.aud')
    [ "$field" = "${DEVICE_TOKEN_AUDIENCE_FROM_DIRECT}" ] || { echo "wrong value for field audience: $field!=${DEVICE_TOKEN_AUDIENCE_FROM_DIRECT}" >&3; return 1; }
    return 0
}

check_device_token_scope() {
    field=$(echo "$1" | jq ".scope" | tr -d '"' | xargs -n1 | LC_ALL="en_US.UTF-8" sort | xargs)
    [ "$field" = "${DEVICE_TOKEN_SCOPE}" ] || { echo "wrong value for field scope: $field!=${DEVICE_TOKEN_SCOPE}" >&3; return 1; }
    return 0
}

check_json_field() {
    field=$(echo "$1" | jq ".$2" | tr -d '"')
    [ "$field" = "$3" ] || { echo "wrong value for field $2: $field!=$3" >&3; return 1; }
    return 0
}

check_json_field_not_exists() {
    field=$(echo "$1" | jq ".$2" | tr -d '"')
    [ -z "$field" ] || [ "$field" = "null" ] || { echo "field $2 found with value $field" >&3; return 1; }
    return 0
}


check_refreshed_device_token() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_json_field "${jwt}" "device_id" "${DEVICE_ID}" || return 1
    check_json_field "${jwt}" "gateway" "${GATEWAY_ID}" || return 1
    check_device_token_scope "${jwt}" || return 1
    check_vanilla_device_token_audience "${jwt}" || return 1
}

check_refreshed_device_token_with_subcomponents() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_json_field "${jwt}" "device_id" "${DEVICE_ID}" || return 1
    check_json_field "${jwt}" "gateway" "${GATEWAY_ID}" || return 1
    check_json_field "${jwt}" "subdevice_ids" "$(echo "${SUBDEVICE_IDS}"| tr -d '\"')" || return 1
    check_device_token_scope "${jwt}" || return 1
    check_vanilla_device_token_audience "${jwt}" || return 1
}

check_refreshed_device_token_with_subcomponents2() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_json_field "${jwt}" "device_id" "${DEVICE_ID}" || return 1
    check_json_field "${jwt}" "gateway" "${GATEWAY_ID}" || return 1
    check_json_field "${jwt}" "subdevice_ids" "$(echo "${SUBDEVICE_IDS2}"| tr -d '\"')" || return 1
    check_device_token_scope "${jwt}" || return 1
    check_vanilla_device_token_audience "${jwt}" || return 1
}


check_refreshed_device_token_fail() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_json_field "${jwt}" "device_id" "${TAINTED}" || return 1
    check_json_field "${jwt}" "gateway" "${TAINTED}" || return 1
    check_device_token_scope "${jwt}" || return 1
    check_vanilla_device_token_audience "${jwt}" || return 1
}

check_refreshed_device_token_with_wrong_ids() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_json_field "${jwt}" "device_id" "${TAINTED}"|| return 1
    check_json_field "${jwt}" "gateway" "${TAINTED}" || return 1
    check_device_token_scope "${jwt}" || return 1
    check_vanilla_device_token_audience "${jwt}" || return 1
}


check_refreshed_vanilla_token() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_json_field "${jwt}" "device_id" "${TAINTED}" || return 1
    check_json_field "${jwt}" "gateway" "${TAINTED}" || return 1
    check_device_token_scope "${jwt}" || return 1
    check_vanilla_device_token_audience "${jwt}" || return 1
}

check_vanilla_device_token() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_device_token_scope "${jwt}" || return 1
    check_vanilla_device_token_audience "${jwt}" || return 1
}

check_vanilla_refresh_token() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_device_token_scope "${jwt}" || return 1
}

check_dedicated_device_token() {
    jwt=$(echo "$1" | jq -R 'split(".") | .[1] | @base64d | fromjson')
    check_json_field "${jwt}" "azp" "device" || return 1
    check_json_field "${jwt}" "device_id" "${DEVICE_ID}" || return 1
    check_json_field "${jwt}" "gateway" "${GATEWAY_ID}" || return 1
    check_device_token_scope "${jwt}" || return 1
    check_vanilla_device_token_audience "${jwt}" || return 1
}


compare_create_attributes() {
    cat << EOF | diff "$1" - >&3
{"attributeValue":"https://industry-fusion.com/types/v0.9/state_OFF","datasetId":"@none","entityId":"testdevice","id":"testdevice\\\\6e27e969d7144bb8bcc17e7a","name":"https://industry-fusion.com/types/v0.9/state","nodeType":"@value","type":"https://uri.etsi.org/ngsi-ld/Property"}
EOF
}

compare_create_attributes2() {
    cat << EOF | diff "$1" - >&3
{"attributeValue":"https://industry-fusion.com/types/v0.9/state_ON","datasetId":"@none","entityId":"testsubdevice1","id":"testsubdevice1\\\\6e27e969d7144bb8bcc17e7a","name":"https://industry-fusion.com/types/v0.9/state","nodeType":"@value","type":"https://uri.etsi.org/ngsi-ld/Property"}
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

teardown() {
    killall kafkacat mosquitto_sub || true
}

@test "verify user can request onboarding token" {
    $SKIP
    password=$(get_password)
    token=$(get_vanilla_device_token)
    echo "# token=$token"
    run check_vanilla_device_token "${token}"
    [ "${status}" -eq "0" ]
}

@test "verify device token can be refreshed" {
    $SKIP
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    echo "# refresh_token=$refresh_token"
    echo "# access_token=$access_token"
    run check_vanilla_refresh_token "${refresh_token}"
    [ "${status}" -eq "0" ]
    device_token=$(get_refreshed_device_token "${refresh_token}" "${access_token}")
    echo "# device_token=$device_token"
    run check_refreshed_device_token "${device_token}"
    [ "${status}" -eq "0" ]
}

@test "verify device token can be refreshed with a subcomponent" {
    $SKIP
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    echo "# refresh_token=$refresh_token"
    echo "# access_token=$access_token"
    device_token=$(get_refreshed_device_token_with_subcomponents "${refresh_token}" "${access_token}")
    echo "# device_token=$device_token"
    run check_refreshed_device_token_with_subcomponents "${device_token}"
    [ "${status}" -eq "0" ]
}


@test "verify device token can be refreshed with several subcomponents" {
    $SKIP
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    echo "# refresh_token=$refresh_token"
    echo "# access_token=$access_token"
    device_token=$(get_refreshed_device_token_with_subcomponents2 "${refresh_token}" "${access_token}")
    echo "# device_token=$device_token"
    run check_refreshed_device_token_with_subcomponents2 "${device_token}"
    [ "${status}" -eq "0" ]
}

@test "verify device token becomes tainted if refreshed without headers" {
    $SKIP
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    run check_vanilla_refresh_token "${refresh_token}"
    [ "${status}" -eq "0" ]
    device_token=$(get_refreshed_vanilla_token "${refresh_token}" "${access_token}")
    run check_refreshed_vanilla_token "${device_token}"
    [ "${status}" -eq "0" ]
}

@test "verify device token becomes tainted if orig_token is missing" {
    $SKIP
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    echo "# refresh_token=$refresh_token"
    echo "# access_token=$access_token"
    run check_vanilla_refresh_token "${refresh_token}"
    [ "${status}" -eq "0" ]
    device_token=$(get_refreshed_device_token "${refresh_token}")
    echo "# device_token=$device_token"
    run check_refreshed_device_token_fail "${device_token}"
    [ "${status}" -eq "0" ]
}


@test "verify device token is tainted when wrong headers are used" {
    $SKIP
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    run check_vanilla_refresh_token "${refresh_token}"
    [ "${status}" -eq "0" ]
    refresh_token=$(get_refreshed_refresh_token "${refresh_token}")
    device_token=$(get_refreshed_device_token_with_wrong_ids "${refresh_token}" "${access_token}")
    echo "# refresh_token $refresh_token"
    echo "# device_token $device_token"
    echo "# access_token $access_token"
    run check_refreshed_device_token_with_wrong_ids "${device_token}"
    [ "${status}" -eq "0" ]
}

@test "verify device token can send data and is forwarded to Kafka" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    echo "# refresh_token=$refresh_token"
    echo "# access_token=$access_token"
    device_token=$(get_refreshed_device_token "${refresh_token}" "${access_token}")
    echo "# device_token: $device_token"
    mqtt_setup_service
    sleep 2
    mosquitto_pub -L "mqtt://${DEVICE_ID}:${device_token}@localhost/${MQTT_TOPIC_NAME}" -m "${MQTT_MESSAGE}"
    mqtt_delete_service
    echo "# Sent mqtt sparkplugB message, sleep 2s to let bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -c 'to_entries | sort_by(.key) | from_entries' ${KAFKACAT_ATTRIBUTES} > ${KAFKACAT_ATTRIBUTES_SORTED}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes ${KAFKACAT_ATTRIBUTES_SORTED}
    [ "$status" -eq 0 ]
}


@test "verify device token can send data to subcomponent and is forwarded to Kafka" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    echo "# refresh_token=$refresh_token"
    echo "# access_token=$access_token"
    device_token=$(get_refreshed_device_token_with_subcomponents  "${refresh_token}" "${access_token}")
    echo "# device_token: $device_token"
    mqtt_setup_service
    sleep 2
    mosquitto_pub -L "mqtt://${DEVICE_ID}:${device_token}@localhost/${MQTT_SUBDEVICE_TOPIC_NAME}" -m "${MQTT_MESSAGE2}"
    mqtt_delete_service
    echo "# Sent mqtt sparkplugB message, sleep 2s to let bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -c 'to_entries | sort_by(.key) | from_entries' ${KAFKACAT_ATTRIBUTES} > ${KAFKACAT_ATTRIBUTES_SORTED}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes2 ${KAFKACAT_ATTRIBUTES_SORTED}
    [ "$status" -eq 0 ]
}

@test "verify device token can not send data to unknown subcomponent" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    echo "# refresh_token=$refresh_token"
    echo "# access_token=$access_token"
    device_token=$(get_refreshed_device_token_with_subcomponents  "${refresh_token}" "${access_token}")
    echo "# device_token: $device_token"
    mqtt_setup_service
    sleep 2
    mosquitto_pub -L "mqtt://${DEVICE_ID}:${device_token}@localhost/${MQTT_SUBDEVICE_TOPIC_NAME}" -m "${MQTT_MESSAGE2}"
    mosquitto_pub -L "mqtt://${DEVICE_ID}:${device_token}@localhost/${MQTT_SUBDEVICE_TOPIC_NAME2}" -m "${MQTT_MESSAGE3}"
    mqtt_delete_service
    echo "# Sent mqtt sparkplugB message, sleep 2s to let bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall kafkacat
    LC_ALL="en_US.UTF-8" sort -o ${KAFKACAT_ATTRIBUTES} ${KAFKACAT_ATTRIBUTES}
    jq -c 'to_entries | sort_by(.key) | from_entries' ${KAFKACAT_ATTRIBUTES} > ${KAFKACAT_ATTRIBUTES_SORTED}
    echo "# Compare ATTRIBUTES"
    run compare_create_attributes2 ${KAFKACAT_ATTRIBUTES_SORTED}
    [ "$status" -eq 0 ]
}

@test "verify tainted device is rejected" {
    $SKIP
    password=$(get_password)
    token=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$token" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$token" | jq ".access_token" | tr -d '"')
    device_token=$(get_refreshed_vanilla_token "${refresh_token}" "${access_token}")
    mqtt_setup_service
    sleep 2
    mosquitto_pub -L "mqtt://${DEVICE_ID}:${device_token}@localhost/${MQTT_TOPIC_NAME}" -m "${MQTT_MESSAGE}" 2>${MQTT_RESULT} || true
    mqtt_delete_service
    cat ${MQTT_RESULT} | grep "not authorised"
}

@test "verify mqtt admin can send and receive data" {
    $SKIP
    password=$(get_adminPassword | tr -d '"')
    username=$(get_adminUsername | tr -d '"')
    mqtt_setup_service
    sleep 2
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${username}:${password}@localhost/${MQTT_TOPIC_NAME}" >${MQTT_SUB}) &
    sleep 2
    mosquitto_pub -L "mqtt://${username}:${password}@localhost/${MQTT_TOPIC_NAME}" -m "${MQTT_MESSAGE}"
    echo "# Sent mqtt sparkplugB message, sleep 2s to let bridge react"
    sleep 2
    echo "# now killing kafkacat and evaluate result"
    killall mosquitto_sub
    mqtt_delete_service
    echo "# Compare ATTRIBUTES"
    run compare_mqtt_sub ${MQTT_SUB}
    [ "$status" -eq 0 ]
}
