#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi

NAMESPACE=iff
ALERTA_SECRET=secret/alerta
ALERTA_SECRET_KEY=alerta-admin-key
ALERTA_URL=http://alerta.local
ALERTA_PATH_ALERTS=/api/alerts
ALERTA_PATH_ALERT=/api/alert
ALERTA_MSG=/tmp/ALERTA_MSG
ALERTA_TOPIC=iff.alerts
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092

cat << EOF > ${ALERTA_MSG}
{
    "resource": "test",
    "event": "test",
    "environment": "Development",
    "service": [ "Digital Twin" ],
    "severity": "critical",
    "customer": "customerB"
}
EOF

get_alerta_api_key() {
    kubectl -n ${NAMESPACE} get ${ALERTA_SECRET} -o jsonpath='{.data.'${ALERTA_SECRET_KEY}'}'| base64 -d
}

# iterate through all test alerts and delete them
# $1 api key
delete_all_test_alerts() {
    key=$1
    arraylength=1
    while [ "$arraylength" -gt 0 ]; do
        alerts=$(get_alerts "$key")
        arraylength=$(echo "$alerts" | jq ".alerts | length ")
        if [ "$arraylength" -gt 0 ]; then
             id=$(echo "$alerts" | jq ".alerts[0].id"| tr -d '"')
             delete_alert "$key" "$id"
        fi
    done
}

# send data to kafka bridge
# $1: file to send
# $2: kafka topic
send_to_kafka_bridge() {
    tr -d '\n' <"$1" | kafkacat -P -t "$2" -b ${KAFKA_BOOTSTRAP}
}

# receive alert
# $1: api key
get_alerts() {
    curl -vv -X GET -H "Authorization: Key $1" ${ALERTA_URL}${ALERTA_PATH_ALERTS}?event=test
}

# receive alert
# $1: api key
# $2: alert id
delete_alert() {
    curl -vv -X DELETE -H "Authorization: Key $1" ${ALERTA_URL}${ALERTA_PATH_ALERT}/"$2"
}

# check field of json object
# $1: object
# $2: field
# $3: expected field
check_json_field() {
    field=$(echo "$1" | jq ".$2" | tr -d '"')
    [ "$field" = "$3" ] || { echo "wrong value for field $2: $field!=$3"; return 1; }
    return 0
}
#check specific fields of alert
# $1: alert json object
check_alert() {
    check_json_field "$1" "resource" "test" || return 1
    check_json_field "$1" "event" "test" || return 1
    check_json_field "$1" "environment" "Development" || return 1
    check_json_field "$1" "severity" "critical" || return 1
    check_json_field "$1" "customer" "customerB" || return 1
    check_json_field "$1" "service[0]" "Digital Twin" || return 1
    return 0
}

setup() {
    # shellcheck disable=SC2086
    (exec ${SUDO} kubefwd -n iff -l app.kubernetes.io/name=kafka svc) &
    echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    sleep 3
}
teardown(){
    echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    ${SUDO} killall kubefwd
}

@test "verify alerta receives alerts over alerta bridge" {
    key=$(get_alerta_api_key)
    delete_all_test_alerts "$key"
    echo "# Alerta key: $key"
    send_to_kafka_bridge ${ALERTA_MSG} ${ALERTA_TOPIC}
    sleep 2
    alerts=$(get_alerts "$key")
    length=$(echo "$alerts" | jq ".alerts | length ")
    id=$(echo "$alerts" | jq ".alerts[0].id"| tr -d '"')
    alert0=$(echo "$alerts" | jq -c ".alerts[0]")
    echo "# found number of alerts: $length, with alert[0].id=$id"
    [ "$length" -eq 1 ]
    run check_alert "$alert0"
    [ "$status" -eq "0" ]
    run delete_alert "$key" "$id"
}
