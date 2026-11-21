#!/usr/bin/env bats

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false} # set this to true to disable starting and stopping of kubefwd
SKIP= # set =skip to skip all test (and only comment out $SKIP from the test you are interested in)
ATTRIBUTE1=/tmp/ATTRIBUTE1
ATTRIBUTE2=/tmp/ATTRIBUTE2
ATTRIBUTE3=/tmp/ATTRIBUTE3
ATTRIBUTE4=/tmp/ATTRIBUTE4
ATTRIBUTE5=/tmp/ATTRIBUTE5
ATTRIBUTE6=/tmp/ATTRIBUTE6
ATTRIBUTE7=/tmp/ATTRIBUTE7
ATTRIBUTE8=/tmp/ATTRIBUTE8
ATTRIBUTE9=/tmp/ATTRIBUTE9
NULL_ATTRIBUTE=/tmp/NULL_ATTRIBUTE
NULL_ONLY_ATTRIBUTE=/tmp/NULL_ONLY_ATTRIBUTE
FLUSH_ATTRIBUTE=/tmp/FLUSH_ATTRIBUTE
ATTRIBUTES_TOPIC=iff.ngsild.attributes
KAFKACAT_ATTRIBUTES=/tmp/KAFKACAT_ATTRIBUTES
KAFKACAT_ATTRIBUTES_FILTERED=/tmp/KAFKACAT_ATTRIBUTES_FILTERED
KAFKACAT_ATTRIBUTES_FROMJSON=/tmp/KAFKACAT_ATTRIBUTES_FROMJSON
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
KAFKACAT_NGSILD_UPDATES_TOPIC=iff.ngsild-updates
CUTTER_ID=urn:plasmacutter-test:12345
NULL_ONLY_ID=urn:plasmacutter-test:null-only
COMPARE_ATTRIBUTE7='{"op":"update","overwriteOrReplace":true,"noForward":true,"entities":"[{\"id\":\"urn:plasmacutter-test:12345\",\"https://industry-fusion.com/types/v0.9/state\":[{\"type\":\"https://uri.etsi.org/ngsi-ld/Property\",\"datasetId\":\"@none\",\"value\":\"ON\"},{\"type\":\"https://uri.etsi.org/ngsi-ld/Property\",\"datasetId\":\"http://example.com/source2\",\"value\":\"OFF\"}]}]"}'

cat << EOF | tr -d '\n' > ${ATTRIBUTE1}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/state",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "attributeValue": "ON"
}
EOF

cat << EOF | tr -d '\n' > ${ATTRIBUTE8}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/state",
    "https://uri.etsi.org/ngsi-ld/datasetId": "http://example.com/source1",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "http://example.com/source1",
    "attributeValue": "ON"
}
EOF

printf '\n' >> ${ATTRIBUTE1}
cat << EOF | tr -d '\n' > ${ATTRIBUTE2}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/state",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "attributeValue": "OFF"
}
EOF
cat << EOF | tr -d '\n' > ${FLUSH_ATTRIBUTE}
{
    "id": "flush\\\https://industry-fusion.com/types/v0.9/state",
    "entityId": "flush",
    "name": "https://industry-fusion.com/types/v0.9/flush",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "attributeValue": "flush"
}
EOF
cat << EOF | tr -d '\n' > ${ATTRIBUTE3}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state2",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/state2",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "attributeValue": "ON"
}
EOF
printf '\n' >> ${ATTRIBUTE3}
cat << EOF | tr -d '\n' > ${ATTRIBUTE4}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/hasWorkpiece",
    "type": "https://uri.etsi.org/ngsi-ld/Relationship",
    "nodeType": "@id",
    "attributeValue": "urn:workpiece:1"
}
EOF
cat << EOF | tr -d '\n' > ${ATTRIBUTE9}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/hasWorkpiece",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/hasWorkpiece",
    "type": "https://uri.etsi.org/ngsi-ld/Relationship",
    "datasetId": "https://example.com/source4",
    "nodeType": "@id",
    "attributeValue": "urn:workpiece:1"
}
EOF
cat << EOF | tr -d '\n' > ${ATTRIBUTE5}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/refState",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/refState",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "attributeValue": "https://industry-fusion.com/v0.9/refStateIRI",
    "nodeType": "@id",
    "index": 0
}
EOF
cat << EOF | tr -d '\n' > ${ATTRIBUTE6}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/jsonValue",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/jsonValue",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "attributeValue": {
        "type": "https://industry-fusion.com/v0.9/refStateIRI",
        "key": "value"
    },
    "nodeType": "@json"
}
EOF
cat << EOF | tr -d '\n' > ${ATTRIBUTE7}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/state",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/state",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "datasetId": "http://example.com/source2",
    "attributeValue": "OFF"
}
EOF

# A null value: NGSI-LD forbids it (ETSI GS CIM 009 V1.9.1, clause 4.5.0),
# so Core Services delivers nothing for this attribute instance.
cat << EOF | tr -d '\n' > ${NULL_ATTRIBUTE}
{
    "id": "${CUTTER_ID}\\\https://industry-fusion.com/types/v0.9/temperature",
    "entityId": "${CUTTER_ID}",
    "name": "https://industry-fusion.com/types/v0.9/temperature",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "nodeType": "@value",
    "attributeValue": "null"
}
EOF
printf '\n' >> ${NULL_ATTRIBUTE}
cat << EOF | tr -d '\n' > ${NULL_ONLY_ATTRIBUTE}
{
    "id": "${NULL_ONLY_ID}\\\https://industry-fusion.com/types/v0.9/temperature",
    "entityId": "${NULL_ONLY_ID}",
    "name": "https://industry-fusion.com/types/v0.9/temperature",
    "type": "https://uri.etsi.org/ngsi-ld/Property",
    "nodeType": "@value",
    "attributeValue": "null"
}
EOF
printf '\n' >> ${NULL_ONLY_ATTRIBUTE}

compare_attributes1() {
    cat << EOF | jq | diff -b "$1" - >&3
{"op":"update","overwriteOrReplace":true,"noForward":true,"entities":"[{\"id\":\"${CUTTER_ID}\",\"https://industry-fusion.com/types/v0.9/state\":[{\"type\":\"https://uri.etsi.org/ngsi-ld/Property\",\"datasetId\":\"@none\",\"value\":\"ON\"}]}]"}
EOF
}
compare_attributes8() {
    cat << EOF | jq | diff -b "$1" - >&3
{"op":"update","overwriteOrReplace":true,"noForward":true,"entities":"[{\"id\":\"${CUTTER_ID}\",\"https://industry-fusion.com/types/v0.9/state\":[{\"type\":\"https://uri.etsi.org/ngsi-ld/Property\",\"datasetId\":\"http://example.com/source1\",\"value\":\"ON\"}]}]"}
EOF
}
compare_attributes2() {
    cat << EOF | jq | diff -b "$1" - >&3
{"op":"update","overwriteOrReplace":true,"noForward":true,"entities":"[{\"id\":\"${CUTTER_ID}\",\"https://industry-fusion.com/types/v0.9/state\":[{\"type\":\"https://uri.etsi.org/ngsi-ld/Property\",\"datasetId\":\"@none\",\"value\":\"OFF\"}]}]"}
EOF
}
compare_attributes3() {
    cat << EOF | diff -b "$1" - >&3
{
  "noForward": true,
  "op": "update",
  "overwriteOrReplace": true
}
EOF
    cat << EOF | jq -S | diff -b "$2" - >&3
[
  {
    "id": "urn:plasmacutter-test:12345",
    "https://industry-fusion.com/types/v0.9/state": [{
      "datasetId": "@none",
      "type": "https://uri.etsi.org/ngsi-ld/Property",
      "value": "OFF"
    }],
    "https://industry-fusion.com/types/v0.9/state2": [{
      "datasetId": "@none",
      "type": "https://uri.etsi.org/ngsi-ld/Property",
      "value": "ON"
    }]
  }
]
EOF
}

compare_attributes4() {
    cat << EOF | jq | diff -b "$1" - >&3
{"op":"update","overwriteOrReplace":true,"noForward":true,"entities":"[{\"id\":\"${CUTTER_ID}\",\"https://industry-fusion.com/types/v0.9/hasWorkpiece\":[{\"type\":\"https://uri.etsi.org/ngsi-ld/Relationship\",\"datasetId\":\"@none\",\"object\":\"urn:workpiece:1\"}]}]"}
EOF
}

compare_attributes9() {
    cat << EOF | jq | diff -b "$1" - >&3
{"op":"update","overwriteOrReplace":true,"noForward":true,"entities":"[{\"id\":\"${CUTTER_ID}\",\"https://industry-fusion.com/types/v0.9/hasWorkpiece\":[{\"type\":\"https://uri.etsi.org/ngsi-ld/Relationship\",\"datasetId\":\"https://example.com/source4\",\"object\":\"urn:workpiece:1\"}]}]"}
EOF
}

compare_attributes5() {
    cat << EOF | jq | diff -b "$1" - >&3
{"op":"update","overwriteOrReplace":true,"noForward":true,"entities":"[{\"id\":\"${CUTTER_ID}\",\"https://industry-fusion.com/types/v0.9/refState\":[{\"type\":\"https://uri.etsi.org/ngsi-ld/Property\",\"datasetId\":\"@none\",\"value\":{\"@id\":\"https://industry-fusion.com/v0.9/refStateIRI\"}}]}]"}
EOF
}

compare_attributes6() {
    cat << EOF | jq | diff -b "$1" - >&3
{"op":"update","overwriteOrReplace":true,"noForward":true,"entities":"[{\"id\":\"${CUTTER_ID}\",\"https://industry-fusion.com/types/v0.9/jsonValue\":[{\"type\":\"https://uri.etsi.org/ngsi-ld/Property\",\"datasetId\":\"@none\",\"value\":{\"type\":\"https://industry-fusion.com/v0.9/refStateIRI\",\"key\":\"value\"}}]}]"}
EOF
}

compare_attributes7() {
    echo "${COMPARE_ATTRIBUTE7}" | jq '.entities| fromjson' > /dev/null; res=$?
    if [ "$res" -ne 0 ];
        then echo "# Result term not a valid JSON - check COMPARE_ATTRIBUTE data" >&3; return 1;
    fi
    cat << EOF | jq | diff -b "$1" - >&3
${COMPARE_ATTRIBUTE7}
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
    [ $DEBUG = "true" ] || ${SUDO} killall kubefwd
}


@test "verify attribute is forwarded to ngsild-update bridge" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${ATTRIBUTE1}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush  < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)'  > ${KAFKACAT_ATTRIBUTES_FILTERED} 
    run compare_attributes1 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify attribute with datasetId is forwarded to ngsild-update bridge" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${ATTRIBUTE8}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush  < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)'  > ${KAFKACAT_ATTRIBUTES_FILTERED} 
    run compare_attributes8 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify last of 2 same attributes is forwarded to ngsild-update bridge" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    cat ${ATTRIBUTE1} ${ATTRIBUTE2} | kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)'  > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes2 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify last of 2 same attributes and 1 other attribute are jointly forwarded to ngsild-update bridge" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    cat ${ATTRIBUTE1} ${ATTRIBUTE3} ${ATTRIBUTE2} | kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq -S 'del (.entities)'> ${KAFKACAT_ATTRIBUTES_FILTERED}
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq -S '.entities | fromjson' | jq 'del(..|.observedAt?)' > ${KAFKACAT_ATTRIBUTES_FROMJSON}
    run compare_attributes3 ${KAFKACAT_ATTRIBUTES_FILTERED} ${KAFKACAT_ATTRIBUTES_FROMJSON}
    [ "$status" -eq 0 ]
}
@test "verify attribute is forwarded to ngsild-update bridge as relationship" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${ATTRIBUTE4}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)' > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes4 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify attribute is forwarded with datasetId to ngsild-update bridge as relationship" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${ATTRIBUTE9}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)' > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes9 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify attribute is forwarded to ngsild-update bridge as iri" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${ATTRIBUTE5}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush  < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)' > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes5 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify attribute is forwarded to ngsild-update bridge as json" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${ATTRIBUTE6}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)' > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes6 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify attribute is forwarded array to ngsild-update bridge" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    cat ${ATTRIBUTE1} ${ATTRIBUTE7} | kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
    #kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${ATTRIBUTE7}
    echo "# Sent attribute to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)' > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes7 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify null attribute is not forwarded, other attributes of the entity are" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    cat ${NULL_ATTRIBUTE} ${ATTRIBUTE1} | kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
    echo "# Sent attributes to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    run grep -c null ${KAFKACAT_ATTRIBUTES}
    [ "$output" = "0" ]
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)' > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes1 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify entity with only a null attribute gets no update" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${NULL_ONLY_ATTRIBUTE}
    sleep 2 # wait until the window of the null attribute is over
    # a plain attribute afterwards shows the pipeline delivered meanwhile
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${ATTRIBUTE1}
    echo "# Sent attributes to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    run grep -c "${NULL_ONLY_ID}" ${KAFKACAT_ATTRIBUTES}
    [ "$output" = "0" ]
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)' > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes1 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
@test "verify a latest null value does not fall back to an older value of the same attribute" {
    $SKIP
    (exec stdbuf -oL kafkacat -C -t ${KAFKACAT_NGSILD_UPDATES_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end >${KAFKACAT_ATTRIBUTES}) &
    sleep 2 # wait for next aggregation window
    # same instance in one batch, a value first and the null last: the null
    # is the latest row and must not let the value win
    sed 's/"attributeValue": *"null"/"attributeValue": "21"/' ${NULL_ATTRIBUTE} \
        | cat - ${NULL_ATTRIBUTE} ${ATTRIBUTE1} | kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
    echo "# Sent attributes to attribute topic, wait some time for aggregation"
    sleep 2 # wait until current window is over and send trigger
    kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP} <${FLUSH_ATTRIBUTE}
    sleep 1
    killall kafkacat
    grep -v flush < ${KAFKACAT_ATTRIBUTES} | jq '.entities |= (fromjson | map(del(.. | .observedAt?)) | tojson)' > ${KAFKACAT_ATTRIBUTES_FILTERED}
    run compare_attributes1 ${KAFKACAT_ATTRIBUTES_FILTERED}
    [ "$status" -eq 0 ]
}
