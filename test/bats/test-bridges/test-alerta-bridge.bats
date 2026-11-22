#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
SKIP= # set =skip to skip all test (and only remove $SKIP from the test you are interested in)
NAMESPACE=iff
ALERTA_SECRET=secret/alerta
ALERTA_SECRET_KEY=alerta-admin-key
ALERTA_URL=http://alerta.local
ALERTA_PATH_ALERTS=/api/alerts
ALERTA_PATH_ALERT=/api/alert
ALERTA_MSG=/tmp/ALERTA_MSG
ALERTA_TOPIC=iff.alerts
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
KAFKA_LABEL=app.kubernetes.io/name=kafka
BRIDGE=alerta-bridge
BRIDGE_GROUP=alertakafkabridge # GROUPID in KafkaBridge/alerta/app.js
RESTART_EVENT=bridge-restart-test
RESTART_MSG=/tmp/ALERTA_RESTART_MSG
# Every status Alerta knows, so that no default filter hides a closed alert.
ALL_STATUSES="status=open&status=ack&status=closed&status=shelved&status=blackout&status=expired&status=unknown"

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

cat << EOF > ${RESTART_MSG}
{
    "resource": "${RESTART_EVENT}",
    "event": "${RESTART_EVENT}",
    "environment": "Development",
    "service": [ "Digital Twin" ],
    "severity": "major",
    "text": "raised once; must stay closed across a restart of the alerta-bridge"
}
EOF

get_alerta_api_key() {
    kubectl -n ${NAMESPACE} get ${ALERTA_SECRET} -o jsonpath='{.data.'${ALERTA_SECRET_KEY}'}'| base64 -d
}

# iterate through all test alerts and delete them
# $1 api key
# $2 event (default: test)
delete_all_test_alerts() {
    key=$1
    arraylength=1
    while [ "$arraylength" -gt 0 ]; do
        alerts=$(get_alerts "$key" "${2:-test}")
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
# $2: event (default: test)
get_alerts() {
    curl -vv -X GET -H "Authorization: Key $1" "${ALERTA_URL}${ALERTA_PATH_ALERTS}?event=${2:-test}&${ALL_STATUSES}"
}

# one alert with its history
# $1: api key
# $2: alert id
get_alert_with_history() {
    curl -s -X GET -H "Authorization: Key $1" \
        "${ALERTA_URL}${ALERTA_PATH_ALERTS}?id=$2&show-history=true&${ALL_STATUSES}" | jq -c '.alerts[0]'
}

# $1: api key
# $2: alert id
# $3: status
set_alert_status() {
    curl -s -X PUT -H "Authorization: Key $1" -H "Content-Type: application/json" \
        -d "{\"status\": \"$3\", \"text\": \"closed by the e2e test\"}" \
        ${ALERTA_URL}${ALERTA_PATH_ALERT}/"$2"/status
}

kafka_pod() {
    kubectl -n ${NAMESPACE} get pods -l ${KAFKA_LABEL} -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

# Total lag of the bridge's consumer group on the alerts topic, or "unknown".
# A partition the group never committed on counts as 0 only when it is empty.
bridge_group_lag() {
    kubectl -n ${NAMESPACE} exec "$(kafka_pod)" -- \
        bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
        --group ${BRIDGE_GROUP} --describe 2>/dev/null | \
        awk -v topic=${ALERTA_TOPIC} '
            $2 == topic { seen = 1
                if ($6 ~ /^[0-9]+$/) { lag += $6 }
                else if ($5 != "0") { unknown = 1 } }
            END { if (!seen || unknown) { print "unknown" } else { print lag + 0 } }'
}

# $1: timeout in seconds
wait_for_lag_zero() {
    lag=unknown
    for _ in $(seq 1 "$1"); do
        lag=$(bridge_group_lag)
        [ "$lag" = "0" ] && return 0
        sleep 1
    done
    echo "# lag of ${BRIDGE_GROUP} on ${ALERTA_TOPIC}: $lag"
    return 1
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
    [ $DEBUG = "true" ] || (exec ${SUDO} kubefwd -n iff -l app.kubernetes.io/name=kafka svc) &
    echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    sleep 3
}
teardown(){
    echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    [ $DEBUG = "true" ] || ${SUDO} killall kubefwd
}

@test "verify alerta receives alerts over alerta bridge" {
    $SKIP
    key=$(get_alerta_api_key)
    delete_all_test_alerts "$key"
    echo "# Alerta key: $key"
    send_to_kafka_bridge ${ALERTA_MSG} ${ALERTA_TOPIC}
    sleep 5
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

@test "a restart of the alerta bridge does not reopen a closed alert" {
    $SKIP
    key=$(get_alerta_api_key)
    delete_all_test_alerts "$key" ${RESTART_EVENT}
    send_to_kafka_bridge ${RESTART_MSG} ${ALERTA_TOPIC}

    id=""
    for _ in $(seq 1 30); do
        alerts=$(get_alerts "$key" ${RESTART_EVENT})
        if [ "$(echo "$alerts" | jq -r '.alerts[0].status')" = "open" ]; then
            id=$(echo "$alerts" | jq -r '.alerts[0].id')
            break
        fi
        sleep 1
    done
    echo "# alert ${id} is open"
    [ -n "$id" ]

    # The bridge commits each record once it is posted, so its group lag drops
    # to 0. Before, it committed every 200 records, and then the last posted one.
    run wait_for_lag_zero 60
    echo "$output"
    [ "$status" -eq 0 ]

    set_alert_status "$key" "$id" closed
    closed=$(get_alert_with_history "$key" "$id")
    check_json_field "$closed" status closed
    history_before=$(echo "$closed" | jq '.history | length')
    duplicates_before=$(echo "$closed" | jq '.duplicateCount')
    echo "# closed, history entries: ${history_before}, duplicates: ${duplicates_before}"

    kubectl -n ${NAMESPACE} rollout restart deployment/${BRIDGE}
    kubectl -n ${NAMESPACE} rollout status deployment/${BRIDGE} --timeout=300s

    # A bridge that resumes before its last posted record posts the raise again,
    # and Alerta reopens the alert within seconds of the bridge joining its group.
    alert=""
    for _ in $(seq 1 12); do
        alert=$(get_alert_with_history "$key" "$id")
        [ "$(echo "$alert" | jq -r '.status')" = "closed" ] || {
            echo "# alert reopened after the restart: $(echo "$alert" | jq -c '.history[-1]')"
            false
        }
        sleep 5
    done
    [ "$(echo "$alert" | jq '.duplicateCount')" = "$duplicates_before" ]
    [ "$(echo "$alert" | jq '.history | length')" = "$history_before" ]

    run wait_for_lag_zero 60
    echo "$output"
    [ "$status" -eq 0 ]
    run delete_alert "$key" "$id"
}
