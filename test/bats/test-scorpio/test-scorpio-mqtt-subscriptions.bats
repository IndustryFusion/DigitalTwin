#!/usr/bin/env bats

# shellcheck disable=SC2005

DEBUG=${DEBUG:-false}
SKIP=
NAMESPACE=iff
USER_SECRET=secret/credential-iff-realm-user-iff
USER=realm_user
CLIENT_ID=scorpio
KEYCLOAK_URL=http://keycloak.local/auth/realms
MQTT_URL=emqx-listeners:1883
MQTT_TOPIC_NAME="scorpio-test"
MQTT_SUB=/tmp/MQTT_SUB
MQTT_FACTORY_SUB=/tmp/MQTT_FACTORY_SUB
MQTT_SPB_TOPIC="spBv1.0/${NAMESPACE}/DDATA/testgateway/testdevice"
MQTT_WRONG_REALM_TOPIC="spBv1.0/wrong-realm/DDATA/testgateway/testdevice"
MQTT_FACTORY_MSG='{"factory_test":true,"timestamp":1655974018778}'
DEVICE_CLIENT_ID=device
DEVICE_ID=testdevice
GATEWAY_ID=testgateway
PLASMACUTTER_ID=urn:plasmacutter-test:12345
SUB_ID=urn:subscription-test:1
CUTTER=/tmp/CUTTER
CUTTER_MERGE=/tmp/CUTTER_MERGE
SUBSCRIPTION=/tmp/SUBSCRIPTION
TMPTMP=/tmp/tmptmp

# Function definitions
get_adminPassword() {
    kubectl -n iff get cm/bridge-configmap -o jsonpath="{.data['config\.json']}" | jq .mqtt.adminPassword
}

get_adminUsername() {
    kubectl -n iff get cm/bridge-configmap -o jsonpath="{.data['config\.json']}" | jq .mqtt.adminUsername
}

get_password() {
    kubectl -n ${NAMESPACE} get ${USER_SECRET} -o jsonpath='{.data.password}' | base64 -d
}

get_token() {
    curl -d "client_id=${CLIENT_ID}" -d "username=${USER}" -d "password=$password" -d 'grant_type=password' "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" | jq ".access_token" | tr -d '"'
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

create_subscription() {
    curl -vv -X POST -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/subscriptions/ -H "Content-Type: application/ld+json"
}

delete_subscription() {
    curl -vv -X DELETE -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/subscriptions/"$2" -H "Content-Type: application/ld+json"
}

create_ngsild() {
    curl -vv -X POST -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entities/ -H "Content-Type: application/ld+json"
}

delete_ngsild() {
    curl -vv -X DELETE -H "Authorization: Bearer $1" http://ngsild.local/ngsi-ld/v1/entities/"$2" -H "Content-Type: application/ld+json"
}

update_ngsild() {
    curl -vv -X PATCH -H "Authorization: Bearer $1" -d @"$2" http://ngsild.local/ngsi-ld/v1/entities/"$3" -H "Content-Type: application/ld+json"
}

setup() {
    if [ "$DEBUG" != "true" ]; then
        echo "This test works only in debug mode. Set DEBUG=true."
        exit 1
    fi
}

# Create CUTTER file
cat << EOF > ${CUTTER}
{
 "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
 "id": "${PLASMACUTTER_ID}",
 "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test",
 "https://industry-fusion.com/types/v0.9/state": {
 "type": "Property",
 "value": "ON",
 "datasetId": "urn:cutter:test1"
 }
}
EOF

# Update the entity with a new state value
cat << EOF > ${CUTTER_MERGE}
{
  "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFF",
    "datasetId": "urn:cutter:test1"
  }
}
EOF

# Create SUBSCRIPTION file
admin_password=$(get_adminPassword | tr -d '"')
admin_username=$(get_adminUsername | tr -d '"')
cat << EOF > ${SUBSCRIPTION}
{
 "@context": "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
 "id": "${SUB_ID}",
 "type": "Subscription",
 "entities": [{
 "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test"
 }],
 "notification": {
 "endpoint": {
 "uri": "mqtt://${admin_username}:${admin_password}@${MQTT_URL}/${MQTT_TOPIC_NAME}",
 "accept": "application/json"
 }
 }
}
EOF

compare_mqtt_sub() {
    local mqtt_file="$1"
    local temp_file=$TMPTMP

    # Process the MQTT_SUB file to get the last message's data
    jq -s 'last | .body.data[0]' "$mqtt_file" > "$temp_file"

    # Compare only the fields we're interested in
    cat << EOF | jq -S | diff <(jq -S '{
        id,
        type,
        "https://industry-fusion.com/types/v0.9/state": {
            type: ."https://industry-fusion.com/types/v0.9/state".type,
            value: ."https://industry-fusion.com/types/v0.9/state".value,
            datasetId: ."https://industry-fusion.com/types/v0.9/state".datasetId
        }
    }' "$temp_file") - >&3
{
  "id": "${PLASMACUTTER_ID}",
  "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test",
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "ON",
    "datasetId": "urn:cutter:test1"
  }
}
EOF
}

compare_mqtt_sub_update() {
    local mqtt_file="$1"
    local temp_file=$TMPTMP

    # Process the MQTT_SUB file to get the last message's data
    jq -s 'last | .body.data[0]' "$mqtt_file" > "$temp_file"

    # Compare only the fields we're interested in, maintaining the correct structure
    cat << EOF | jq -S | diff <(jq -S '{
        id,
        type,
        "https://industry-fusion.com/types/v0.9/state": {
            type: ."https://industry-fusion.com/types/v0.9/state".type,
            value: ."https://industry-fusion.com/types/v0.9/state".value,
            datasetId: ."https://industry-fusion.com/types/v0.9/state".datasetId
        }
    }' "$temp_file") - >&3
{
  "id": "${PLASMACUTTER_ID}",
  "type": "https://industry-fusion.com/types/v0.9/plasmacutter_test",
  "https://industry-fusion.com/types/v0.9/state": {
    "type": "Property",
    "value": "OFF",
    "datasetId": "urn:cutter:test1"
  }
}
EOF
}

check_no_delete_notification() {
    local message_count
    message_count=$(jq -s 'length' "$1")

    # We expect to see 2 messages: one for creation, one for update
    if [ "$message_count" -eq 0 ]; then
        return 0
    else
        echo "Expected 0 messages, but found $message_count" >&2
        return 1
    fi
}

@test "verify mqtt subscription after entity creation" {
    $SKIP
    admin_password=$(get_adminPassword | tr -d '"')
    admin_username=$(get_adminUsername | tr -d '"')
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${admin_username}:${admin_password}@${MQTT_URL}/${MQTT_TOPIC_NAME}" >${MQTT_SUB}) &
    sleep 2
    create_subscription "$token" "$SUBSCRIPTION"
    sleep 2
    create_ngsild "$token" "$CUTTER"
    sleep 2
    killall mosquitto_sub 2>/dev/null || true
    delete_subscription "$token" "$SUB_ID"

    run compare_mqtt_sub ${MQTT_SUB}
    [ "$status" -eq 0 ]
}

@test "verify mqtt subscription after entity creation and update" {
    $SKIP
    admin_password=$(get_adminPassword | tr -d '"')
    admin_username=$(get_adminUsername | tr -d '"')
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${admin_username}:${admin_password}@${MQTT_URL}/${MQTT_TOPIC_NAME}" >${MQTT_SUB}) &
    sleep 2
    create_ngsild "$token" "$CUTTER"
    sleep 2
    create_subscription "$token" "$SUBSCRIPTION"
    sleep 2
    update_ngsild "$token" "$CUTTER_MERGE" "$PLASMACUTTER_ID"
    sleep 2
    killall mosquitto_sub 2>/dev/null || true
    delete_subscription "$token" "$SUB_ID"

    run compare_mqtt_sub_update ${MQTT_SUB}
    [ "$status" -eq 0 ]
}

@test "verify no mqtt notification after entity creation and deletion" {
    $SKIP
    admin_password=$(get_adminPassword | tr -d '"')
    admin_username=$(get_adminUsername | tr -d '"')
    password=$(get_password)
    token=$(get_token)
    delete_ngsild "$token" "$PLASMACUTTER_ID" || echo "Could not delete $PLASMACUTTER_ID. But that is okay."
    sleep 2
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${admin_username}:${admin_password}@${MQTT_URL}/${MQTT_TOPIC_NAME}" >${MQTT_SUB}) &
    sleep 2
    create_ngsild "$token" "$CUTTER"
    sleep 2
    create_subscription "$token" "$SUBSCRIPTION"
    sleep 2
    delete_ngsild "$token" "$PLASMACUTTER_ID"
    sleep 2
    killall mosquitto_sub 2>/dev/null || true
    delete_subscription "$token" "$SUB_ID"

    run check_no_delete_notification ${MQTT_SUB}
    [ "$status" -eq 0 ]
}

@test "verify factory user can subscribe to arbitrary SparkplugB topic" {
    $SKIP
    admin_password=$(get_adminPassword | tr -d '"')
    admin_username=$(get_adminUsername | tr -d '"')
    password=$(get_password)
    token=$(get_token)
    : > "${MQTT_FACTORY_SUB}"
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${USER}:${token}@${MQTT_URL}/${MQTT_SPB_TOPIC}" >"${MQTT_FACTORY_SUB}") &
    sleep 2
    mosquitto_pub -L "mqtt://${admin_username}:${admin_password}@${MQTT_URL}/${MQTT_SPB_TOPIC}" -m "${MQTT_FACTORY_MSG}"
    sleep 2
    killall mosquitto_sub 2>/dev/null || true

    run grep -q "factory_test" "${MQTT_FACTORY_SUB}"
    [ "$status" -eq 0 ]
}

@test "verify factory user publish to SparkplugB topic is silently dropped" {
    $SKIP
    password=$(get_password)
    token=$(get_token)
    : > "${MQTT_FACTORY_SUB}"
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${USER}:${token}@${MQTT_URL}/${MQTT_SPB_TOPIC}" >"${MQTT_FACTORY_SUB}") &
    sleep 2
    mosquitto_pub -L "mqtt://${USER}:${token}@${MQTT_URL}/${MQTT_SPB_TOPIC}" -m "${MQTT_FACTORY_MSG}"
    sleep 2
    killall mosquitto_sub 2>/dev/null || true

    # EMQX deny_action=ignore silently drops the publish; factory subscriber receives nothing
    [ ! -s "${MQTT_FACTORY_SUB}" ]
}

@test "verify factory user can subscribe to non-SparkplugB topic" {
    $SKIP
    admin_password=$(get_adminPassword | tr -d '"')
    admin_username=$(get_adminUsername | tr -d '"')
    password=$(get_password)
    token=$(get_token)
    : > "${MQTT_FACTORY_SUB}"
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${USER}:${token}@${MQTT_URL}/${MQTT_TOPIC_NAME}" >"${MQTT_FACTORY_SUB}") &
    sleep 2
    mosquitto_pub -L "mqtt://${admin_username}:${admin_password}@${MQTT_URL}/${MQTT_TOPIC_NAME}" -m "${MQTT_FACTORY_MSG}"
    sleep 2
    killall mosquitto_sub 2>/dev/null || true

    run grep -q "factory_test" "${MQTT_FACTORY_SUB}"
    [ "$status" -eq 0 ]
}

@test "verify factory user can publish to non-SparkplugB topic" {
    $SKIP
    admin_password=$(get_adminPassword | tr -d '"')
    admin_username=$(get_adminUsername | tr -d '"')
    password=$(get_password)
    token=$(get_token)
    : > "${MQTT_FACTORY_SUB}"
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${admin_username}:${admin_password}@${MQTT_URL}/${MQTT_TOPIC_NAME}" >"${MQTT_FACTORY_SUB}") &
    sleep 2
    mosquitto_pub -L "mqtt://${USER}:${token}@${MQTT_URL}/${MQTT_TOPIC_NAME}" -m "${MQTT_FACTORY_MSG}"
    sleep 2
    killall mosquitto_sub 2>/dev/null || true

    run grep -q "factory_test" "${MQTT_FACTORY_SUB}"
    [ "$status" -eq 0 ]
}

@test "verify factory user cannot subscribe to SparkplugB topic with wrong realm" {
    $SKIP
    admin_password=$(get_adminPassword | tr -d '"')
    admin_username=$(get_adminUsername | tr -d '"')
    password=$(get_password)
    token=$(get_token)
    : > "${MQTT_FACTORY_SUB}"
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${USER}:${token}@${MQTT_URL}/${MQTT_WRONG_REALM_TOPIC}" >"${MQTT_FACTORY_SUB}") &
    sleep 2
    mosquitto_pub -L "mqtt://${admin_username}:${admin_password}@${MQTT_URL}/${MQTT_WRONG_REALM_TOPIC}" -m "${MQTT_FACTORY_MSG}"
    sleep 2
    killall mosquitto_sub 2>/dev/null || true

    # subscription to wrong-realm SparkplugB is denied; no message received
    [ ! -s "${MQTT_FACTORY_SUB}" ]
}

@test "verify device cannot subscribe to non-SparkplugB topic" {
    $SKIP
    admin_password=$(get_adminPassword | tr -d '"')
    admin_username=$(get_adminUsername | tr -d '"')
    password=$(get_password)
    device_tokens=$(get_vanilla_refresh_and_access_token)
    refresh_token=$(echo "$device_tokens" | jq ".refresh_token" | tr -d '"')
    access_token=$(echo "$device_tokens" | jq ".access_token" | tr -d '"')
    device_token=$(get_refreshed_device_token "${refresh_token}" "${access_token}")
    : > "${MQTT_FACTORY_SUB}"
    (exec stdbuf -oL mosquitto_sub -L "mqtt://${DEVICE_ID}:${device_token}@${MQTT_URL}/${MQTT_TOPIC_NAME}" >"${MQTT_FACTORY_SUB}") &
    sleep 2
    mosquitto_pub -L "mqtt://${admin_username}:${admin_password}@${MQTT_URL}/${MQTT_TOPIC_NAME}" -m "${MQTT_FACTORY_MSG}"
    sleep 2
    killall mosquitto_sub 2>/dev/null || true

    # device subscription to non-SparkplugB topic is denied; no message received
    [ ! -s "${MQTT_FACTORY_SUB}" ]
}
