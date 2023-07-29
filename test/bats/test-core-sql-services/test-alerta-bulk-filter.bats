#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
ALERT1=/tmp/ALERT1
ALERT2=/tmp/ALERT2
ALERT3=/tmp/ALERT3
ALERT4=/tmp/ALERT4
ALERT5=/tmp/ALERT5
ALERT6=/tmp/ALERT6
ALERTS_TOPIC=iff.alerts
BULK_ALERTS_TOPIC=iff.alerts.bulk
KAFKACAT_ATTRIBUTES=/tmp/KAFKACAT_ATTRIBUTES
KAFKACAT_ATTRIBUTES_FILTERED=/tmp/KAFKACAT_ATTRIBUTES_FILTERED
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092


cat << EOF | tr -d '\n' > ${ALERT1}
{"resource":"urn:plasmacutter-test:12345","event":"Test event"};{
  "resource": "urn:plasmacutter-test:12345",
  "event": "Test event",
  "environment": "Development",
  "service": ["E2E test"],
  "severity": "ok",
  "customer": "test",
  "text": "OK"
}
EOF

cat << EOF | tr -d '\n' > ${ALERT2}
{"resource":"urn:plasmacutter-test:12345","event":"Test event"};{
  "resource": "urn:plasmacutter-test:12345",
  "event": "Test event",
  "environment": "Development",
  "service": ["E2E test"],
  "severity": "warning",
  "customer": "test",
  "text": "Warning"
}
EOF

cat << EOF | tr -d '\n' > ${ALERT3}
{"resource":"urn:plasmacutter-test:12345","event":"Test event"};{
  "resource": "urn:plasmacutter-test:12345",
  "event": "Test event",
  "environment": "Development",
  "service": [
    "E2E test"
  ],
  "severity": "critical",
  "customer": "test",
  "text": "critical"
}
EOF

cat << EOF | tr -d '\n' > ${ALERT4}
{"resource":"urn:plasmacutter-test:12345","event":"Test event"};{
  "resource": "urn:plasmacutter-test:12345",
  "event": "Test event",
  "environment": "Development",
  "service": [
    "E2E test"
  ],
  "severity": "flush",
  "customer": "test",
  "text": "critical"
}
EOF

cat << EOF | tr -d '\n' > ${ALERT5}
{"resource":"urn:plasmacutter-test:xxxx","event":"Test event"};{
  "resource": "urn:plasmacutter-test:xxxx",
  "event": "Test event",
  "environment": "Development",
  "service": [
    "E2E test"
  ],
  "severity": "flush",
  "customer": "test",
  "text": "critical"
}
EOF

cat << EOF | tr -d '\n' > ${ALERT6}
{"resource":"urn:plasmacutter-test:xxxx","event":"Test event"};{
  "resource": "urn:plasmacutter-test:xxxx",
  "event": "Test event",
  "environment": "Development",
  "service": [
    "E2E test"
  ],
  "severity": "flush",
  "customer": "test",
  "text": "criticalx"
}
EOF

compare_attributes1() {
    cat << EOF | diff "$1" - >&3
{"resource":"urn:plasmacutter-test:12345","event":"Test event","environment":"Development","service":["E2E test"],"severity":"ok","customer":"test","text":"OK"}
{"resource":"urn:plasmacutter-test:12345","event":"Test event","environment":"Development","service":["E2E test"],"severity":"warning","customer":"test","text":"Warning"}
{"resource":"urn:plasmacutter-test:12345","event":"Test event","environment":"Development","service":["E2E test"],"severity":"ok","customer":"test","text":"OK"}
{"resource":"urn:plasmacutter-test:12345","event":"Test event","environment":"Development","service":["E2E test"],"severity":"critical","customer":"test","text":"critical"}
{"resource":"urn:plasmacutter-test:12345","event":"Test event","environment":"Development","service":["E2E test"],"severity":"ok","customer":"test","text":"OK"}
EOF
}

setup() {
    # shellcheck disable=SC2086
    [ $DEBUG = "true" ] || (exec ${SUDO} kubefwd -n iff -l app.kubernetes.io/name=kafka svc  >/dev/null 2>&1) &
    echo "# launched kubefwd for kafka, wait some seconds to give kubefwd to launch the services"
    sleep 2
}
teardown(){
    echo "# now killing kubefwd"
    # shellcheck disable=SC2086
    [ $DEBUG = "true" ]  || ${SUDO} killall kubefwd
}


# This tests check whether Flink filters the alert correcty. The filtering
# uses late data arrival, e.g. every event is allowed to arrive 200ms late
# and still will be assigned to the window before. This is to make sure that
# no short term event shows up in the Alerta dashboard.
# This test looks overcomplicated. Reason is a bug in Flink late data handling
# It seems not to update the watermark when data only with the same key is sent
# That is there are two different keys: ALERTS1-4 and ALERTS5-6
@test "verify only changes of alert sequence from alerts.bulk are forwarded to alerts topic" {
    (exec stdbuf -oL kafkacat -C -t ${ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end -f '%s\n'>${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT4}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT5}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT1}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT6}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT2}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT5}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT1}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT6}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT1}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT5}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT3}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT6}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT3}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT5}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT1}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT6}
    sleep 0.2
    kafkacat -P -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -K';' <${ALERT1}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2
    killall kafkacat
    grep -v flush  < ${KAFKACAT_ATTRIBUTES} | grep -v '^$' > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes1 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
