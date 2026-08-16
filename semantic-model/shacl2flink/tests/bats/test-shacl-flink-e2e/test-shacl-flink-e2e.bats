#!/usr/bin/env bats
# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# End-to-end tests for the SHACL -> Flink validation pipeline.
#
# A standard platform install carries NO shacl-validation deployment: the
# pipeline is compiled from whatever KMS an operator supplies, so there is
# nothing to test against by default. These tests therefore do not run from
# test/bats -- they are driven by `make test-flink-e2e`, which compiles and
# deploys tests/e2e-kms, runs this file, and tears the deployment down again.
# Everything asserted here is a shape from that KMS and nothing else.
#
# Within the deployment the tests drive Kafka directly rather than going
# through Scorpio and the bridges, so a failure points at Flink and the
# generated SQL rather than at everything upstream of it.

if [ -z "${SELF_HOSTED_RUNNER}" ]; then
    SUDO="sudo -E"
fi
DEBUG=${DEBUG:-false}          # set true to skip kubefwd (assumes forwarding is already up)
NAMESPACE=${NAMESPACE:-iff}
KAFKA_BOOTSTRAP=my-cluster-kafka-bootstrap:9092
ENTITY_TOPIC=iff.ngsild.entities
ATTRIBUTES_TOPIC=iff.ngsild.attributes
BULK_ALERTS_TOPIC=iff.alerts.bulk
TRIGGER_TOPIC=iff.ngsild.flink.constraint_trigger_table
STATEMENTSET=shacl-validation

# Classes and properties from tests/e2e-kms. E2EFreeMachine deliberately has no
# shape.
E2E=https://industryfusion.github.io/contexts/example/v0/base_entities
MACHINE_TYPE=${E2E}/E2EMachine
RANGE_TYPE=${E2E}/E2ERangeMachine
FREE_TYPE=${E2E}/E2EFreeMachine
LINKED_TYPE=${E2E}/E2ELinkedMachine
CARTRIDGE_TYPE=${E2E}/E2ECartridge
STATE_PROP=${E2E}/hasE2EState
RANGE_PROP=${E2E}/hasE2ERange
CARTRIDGE_REL=${E2E}/hasE2ECartridge

ALERTS_OUT=/tmp/SHACL_FLINK_ALERTS
TRIGGER_ERR=/tmp/SHACL_FLINK_TRIGGER_ERR
# A fresh id per run: alerts_bulk is an upsert topic keyed by (resource, event),
# so reusing an id from an earlier run would produce an identical value that
# Flink has no reason to re-emit, and the test would hang waiting for it.
RUN_ID=$(date +%s)
TEST_MISSING="urn:e2e-flink-missing:${RUN_ID}"
TEST_CLEAR="urn:e2e-flink-clear:${RUN_ID}"
TEST_XONE_BAD="urn:e2e-flink-xone-bad:${RUN_ID}"
TEST_XONE_COUNT="urn:e2e-flink-xone-count:${RUN_ID}"
TEST_XONE_OK="urn:e2e-flink-xone-ok:${RUN_ID}"
TEST_UNKNOWN="urn:e2e-flink-unknown:${RUN_ID}"
TEST_DEL_ENTITY="urn:e2e-flink-del-entity:${RUN_ID}"
TEST_DEL_ATTR="urn:e2e-flink-del-attr:${RUN_ID}"
TEST_DEL_LINKED="urn:e2e-flink-del-linked:${RUN_ID}"
TEST_DEL_TARGET="urn:e2e-flink-del-target:${RUN_ID}"

setup() {
    # shellcheck disable=SC2086
    [ "$DEBUG" = "true" ] || (exec ${SUDO} kubefwd -n ${NAMESPACE} -l app.kubernetes.io/name=kafka svc >/dev/null 2>&1) &
    echo "# launched kubefwd for kafka" >&3
    sleep 3
}

teardown() {
    # shellcheck disable=SC2086
    [ "$DEBUG" = "true" ] || ${SUDO} killall kubefwd 2>/dev/null || true
    rm -f ${ALERTS_OUT}
}

publish_entity() {
    local id=$1 type=$2
    echo "{\"id\":\"${id}\",\"type\":\"${type}\",\"deleted\":false}" \
        | kafkacat -P -t ${ENTITY_TOPIC} -b ${KAFKA_BOOTSTRAP}
}

# Mirrors exactly what create_ngsild_models.py emits for a Property: the
# attributes key is entityId\name\datasetId, and the literal carries an
# explicit valueType because the range checks cast it.
publish_property() {
    local entity=$1 name=$2 value=$3 valuetype=${4:-http://www.w3.org/2001/XMLSchema#integer}
    printf '{"id":"%s\\\\%s\\\\@none","entityId":"%s","name":"%s","nodeType":"@value","valueType":"%s","type":"https://uri.etsi.org/ngsi-ld/Property","attributeValue":"%s","datasetId":"@none","deleted":false,"synced":true}\n' \
        "${entity}" "${name}" "${entity}" "${name}" "${valuetype}" "${value}" \
        | kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
}

# Deleting an entity in Scorpio does NOT produce a Kafka tombstone. The
# debezium bridge republishes the entity with deleted=true (app.js, the
# removeType branch), so a delete is an ordinary row that happens to carry a
# flag. Anything downstream that treats "the key went away" as the delete
# signal will never see one.
publish_entity_deleted() {
    local id=$1 type=$2
    echo "{\"id\":\"${id}\",\"type\":\"${type}\",\"deleted\":true}" \
        | kafkacat -P -t ${ENTITY_TOPIC} -b ${KAFKA_BOOTSTRAP}
}

publish_relationship() {
    local entity=$1 name=$2 target=$3
    printf '{"id":"%s\\\\%s\\\\@none","entityId":"%s","name":"%s","nodeType":"@id","type":"https://uri.etsi.org/ngsi-ld/Relationship","attributeValue":"%s","datasetId":"@none","deleted":false,"synced":true}\n' \
        "${entity}" "${name}" "${entity}" "${name}" "${target}" \
        | kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
}

# A deleted attribute arrives STRIPPED. debeziumBridge.js keeps only id,
# parentId, name, entityId, type, datasetId and nodeType (diffAttributes, the
# pickFields call) and adds deleted/synced; attributeValue, valueType, unitCode
# and lang are dropped. Publishing a delete that still carried its value would
# be testing a message the bridge never sends -- and the count checks read
# `type`, which survives, so the difference is not cosmetic.
publish_attribute_deleted() {
    local entity=$1 name=$2 nodetype=${3:-@value} \
          attrtype=${4:-https://uri.etsi.org/ngsi-ld/Property}
    printf '{"id":"%s\\\\%s\\\\@none","parentId":null,"entityId":"%s","name":"%s","nodeType":"%s","type":"%s","datasetId":"@none","deleted":true,"synced":true}\n' \
        "${entity}" "${name}" "${entity}" "${name}" "${nodetype}" "${attrtype}" \
        | kafkacat -P -t ${ATTRIBUTES_TOPIC} -b ${KAFKA_BOOTSTRAP}
}

# "Found -1 relationships instead of [1, 1]" is what prompted these tests. The
# count is SUM(CASE WHEN ... THEN 1 ELSE 0 END), so in batch it cannot go below
# zero -- which is why the SQLite oracle agreed while Flink was wrong. On Flink
# it reads negative when the aggregate has applied more retractions than
# accumulations for the group, the signature of state expiring underneath it.
#
# Match any negative count rather than -1 specifically: the number depends on
# how much state was lost, and every one of them is the same defect.
negative_counts() {
    local resource=$1
    awk -v r="${resource}" 'index($0,r) && /Found -[0-9]/' "${ALERTS_OUT}" 2>/dev/null
}

# Tail alerts into a file so the consumer is already attached before the entity
# is published -- otherwise the alert can be produced before we start listening.
start_alert_capture() {
    # Capture key AND value. An alert is retracted by a TOMBSTONE -- a record
    # whose value is empty and whose resource lives only in the key. Consuming
    # values alone makes every retraction invisible.
    (exec stdbuf -oL kafkacat -C -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} -o end -f '%k;%s\n' >${ALERTS_OUT}) &
    sleep 3
}

stop_alert_capture() {
    killall kafkacat 2>/dev/null || true
}

# Throw away what has been captured and start listening again.
#
# A test that waits for an alert to APPEAR after some change must not be
# allowed to match one raised before it. Publishing an entity and its attribute
# are two separate records, so the entity spends a moment violating minCount
# and alerts for it -- and a later wait_for_alert would find that transient
# immediately and report success without the change under test having done
# anything at all.
rearm_alert_capture() {
    stop_alert_capture
    : >${ALERTS_OUT}
    start_alert_capture
}

# Poll rather than sleep a fixed amount: validation normally lands in a couple
# of seconds, but a busy cluster can be slower and a fixed sleep makes the test
# either flaky or needlessly slow.
# Why an expected alert never arrived. A circuit node writes its verdict into
# constraint_trigger_table before anything reaches alerts_bulk, so the trigger
# rows split the question in two: no row means the level statement never
# produced the verdict, a row means it did and the failure is downstream in the
# PUBLISH join. Without this the two are indistinguishable from the outside and
# a missing alert says only "something, somewhere".
#
# Read from a bounded point BEFORE the end rather than -o end: the records were
# written before this runs, so a consumer starting at the end would show
# nothing and wrongly look like the first case.
# Why an expected alert never arrived. A circuit node writes its verdict into
# constraint_trigger_table before anything reaches alerts_bulk, so the trigger
# rows split the question in two: no verdict row means the level statement
# never produced it, a verdict row means it did and the loss is downstream in
# the PUBLISH join.
#
# It MUST match the resource AND the constraint component. Matching the
# resource alone finds the unrelated leaf alerts that a failing entity also
# raises -- a bare E2ERangeMachine always has a CountConstraintComponent row --
# and reports "verdict produced" when the verdict is exactly what is missing.
# That is not hypothetical: it is what the first version of this helper did,
# and it pointed at the wrong half of the pipeline.
# Did the harness actually deliver the entity? kubefwd sits on the PUBLISH
# path but not between Flink and Kafka, so this separates "the forwarder
# swallowed it" from "Flink received it and computed no verdict". Exactly one
# record means the publish was clean and any missing verdict is the product's.
dump_entity_records() {
    local resource=$1 rows rc
    rows=$(timeout 30 kafkacat -C -t ${ENTITY_TOPIC} -b ${KAFKA_BOOTSTRAP} \
        -o -2000 -e -f '%s\n' 2>${TRIGGER_ERR}); rc=$?
    if [ "${rc}" -ne 0 ]; then
        echo "# could not read ${ENTITY_TOPIC} (rc=${rc}) -- delivery unknown" >&3
        return
    fi
    local n
    n=$(echo "${rows}" | awk -v r="${resource}" 'index($0,r)' | wc -l)
    echo "# entity records on ${ENTITY_TOPIC} for ${resource}: ${n}" >&3
    if [ "${n}" -eq 0 ]; then
        echo "#   => the publish never reached Kafka: HARNESS problem, not the job" >&3
    else
        echo "#   => the entity was delivered; a missing verdict is the job's" >&3
    fi
}

dump_trigger_rows() {
    local resource=$1 fragment=$2 rows rc matched present
    rows=$(timeout 30 kafkacat -C -t ${TRIGGER_TOPIC} -b ${KAFKA_BOOTSTRAP} \
        -o -2000 -e -f '%k;%s\n' 2>${TRIGGER_ERR}); rc=$?
    # A diagnostic that cannot fail loudly is worth nothing: a broken consumer
    # and an empty result must not look the same.
    if [ "${rc}" -ne 0 ]; then
        echo "# could not read ${TRIGGER_TOPIC} (rc=${rc}) -- diagnosis unavailable" >&3
        tail -2 ${TRIGGER_ERR} | sed 's/^/#   /' >&3
        return
    fi
    matched=$(echo "${rows}" | awk -v r="${resource}" -v f="${fragment}" \
        'index($0,r) && index($0,f)')
    if [ -n "${matched}" ]; then
        echo "# constraint_trigger_table HAS ${fragment} rows for ${resource}:" >&3
        echo "${matched}" | sed 's/^/#   /' >&3
        echo "#   => verdict produced; the loss is downstream, in PUBLISH" >&3
        return
    fi
    present=$(echo "${rows}" | awk -v r="${resource}" 'index($0,r)' \
        | grep -o '"event":"[A-Za-z]*ConstraintComponent' | sort -u \
        | sed 's/.*:"//' | paste -sd' ' -)
    echo "# constraint_trigger_table has NO ${fragment} row for ${resource}" >&3
    echo "#   other events present for it: ${present:-<none>}" >&3
    echo "#   => the circuit level statement never produced the verdict" >&3

    # Late or never? The alert wait already spent its timeout, so give the
    # verdict a further grace period and say which it was. Without this the
    # next investigation starts by re-asking the same question.
    local waited=0
    while [ "${waited}" -lt 120 ]; do
        sleep 15; waited=$((waited + 15))
        rows=$(timeout 30 kafkacat -C -t ${TRIGGER_TOPIC} -b ${KAFKA_BOOTSTRAP} \
            -o -2000 -e -f '%k;%s\n' 2>/dev/null)
        if echo "${rows}" | awk -v r="${resource}" -v f="${fragment}" \
                'index($0,r) && index($0,f) {found=1} END {exit !found}'; then
            echo "#   LATE: verdict appeared ${waited}s after the wait expired" >&3
            return
        fi
    done
    echo "#   NEVER: no verdict after a further ${waited}s" >&3
}

wait_for_alert() {
    local resource=$1 fragment=$2 timeout=${3:-90} waited=0
    while [ "${waited}" -lt "${timeout}" ]; do
        # Literal substring match via awk: the event names contain "(", ")" and
        # "}", which are ERE metacharacters and silently break a grep pattern.
        if awk -v r="${resource}" -v f="${fragment}" \
            'index($0,r) && index($0,f) {found=1} END {exit !found}' \
            "${ALERTS_OUT}" 2>/dev/null; then
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

# The suite's FIRST publish races the job's startup, and loses. The entities
# table is `scan.startup.mode: latest-offset`, so the source resolves where to
# begin only once its task actually starts reading -- seconds after the
# statementset reports RUNNING and after the jobs overview calls every task
# running. Neither of those says "the source is positioned". A record written
# into that gap is not consumed late, it is never consumed at all: two
# consecutive CI runs showed no alert for it at any point in the run, while
# every later test in the same run passed on the same code path.
#
# Waiting longer cannot fix that, so re-send the record instead. The entities
# table is append-only with the Kafka timestamp as its watermark and is
# deduplicated by a view keyed on id, so a re-send is a genuinely new row that
# retriggers the join rather than an identical value Flink may ignore. The
# assertion is unchanged -- only the delivery is retried.
publish_entity_until_alert() {
    local id=$1 type=$2 fragment=$3 timeout=${4:-180} waited=0 interval=30
    while :; do
        publish_entity "${id}" "${type}"
        wait_for_alert "${id}" "${fragment}" "${interval}" && return 0
        waited=$((waited + interval))
        [ "${waited}" -ge "${timeout}" ] && return 1
        # tolerated: this runs under `run`, where fd 3 may not be attached
        echo "# no verdict after ${waited}s; re-publishing ${id}" >&3 2>/dev/null || true
    done
}

# Final state of an alert key: ALERT if the LAST record for this resource
# carries a value, CLEAR if it is a tombstone or never appeared.
#
# Counting records cannot express what these tests mean. Publishing an entity
# and its attribute are two separate Kafka records, so between them the entity
# genuinely has no attribute -- and an absence-firing operator like XONE
# correctly alerts during that window. A transient alert followed by a
# retraction is right; a LIVE alert once everything has landed is wrong. Only
# the converged state distinguishes the two.
final_alert_state() {
    local resource=$1
    awk -F';' -v r="${resource}" \
        'index($1,r) {last=$2; seen=1} END {print (seen && last!="") ? "ALERT" : "CLEAR"}' \
        "${ALERTS_OUT}" 2>/dev/null
}

# Poll until the converged state is what we expect. A fixed sleep cannot
# express "has settled": retraction here travels the same path as test 4, which
# polls up to 90s and passes, so a 30s wait was simply sometimes too short --
# and it failed as ALERT with the retraction still in flight.
wait_for_converged() {
    local resource=$1 expected=$2 timeout=${3:-90} waited=0
    while [ "${waited}" -lt "${timeout}" ]; do
        [ "$(final_alert_state "${resource}")" = "${expected}" ] && return 0
        sleep 3
        waited=$((waited + 3))
    done
    return 1
}

wait_for_retraction() {
    # A retraction is a tombstone: key;<empty value>.
    local resource=$1 fragment=$2 timeout=${3:-90} waited=0
    while [ "${waited}" -lt "${timeout}" ]; do
        if awk -F';' -v r="${resource}" -v f="${fragment}" \
            'index($1,r) && index($1,f) && $2=="" {found=1} END {exit !found}' \
            "${ALERTS_OUT}" 2>/dev/null; then
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 1
}

@test "shacl-validation statementset is deployed and running" {
    run kubectl -n "${NAMESPACE}" get beamsqlstatementsets "${STATEMENTSET}" -o jsonpath='{.status.state}'
    [ "$status" -eq 0 ]
    echo "# statementset state: ${output}" >&3
    [ "$output" = "RUNNING" ]
}

@test "flink job for shacl-validation has every task running" {
    pod=$(kubectl -n "${NAMESPACE}" get pods -l component=jobmanager -o jsonpath='{.items[0].metadata.name}')
    [ -n "${pod}" ]
    run kubectl -n "${NAMESPACE}" exec "${pod}" -c flink-main-container -- \
        curl -s http://localhost:8081/jobs/overview
    [ "$status" -eq 0 ]
    # every task of the shacl job must be running, not merely most of them:
    # a partially deployed job silently validates only part of the model
    result=$(echo "${output}" | python3 -c "
import json, sys
jobs = [j for j in json.load(sys.stdin)['jobs']
        if 'shacl-validation' in j['name'] and j['state'] == 'RUNNING']
if not jobs:
    print('NO_RUNNING_JOB')
else:
    j = jobs[0]
    print('OK' if j['tasks']['running'] == j['tasks']['total'] else
          f\"PARTIAL {j['tasks']['running']}/{j['tasks']['total']}\")")
    echo "# flink job task state: ${result}" >&3
    [ "${result}" = "OK" ]
}

@test "an E2EMachine without the mandatory attribute raises a minCount alert" {
    start_alert_capture
    echo "# publishing ${TEST_MISSING}" >&3

    # E2EMachineShape requires hasE2EState, so an entity carrying no attribute
    # at all must be reported. This exercises the whole compiled pipeline:
    # entity source -> constraint join -> trigger table -> alerts.
    run publish_entity_until_alert "${TEST_MISSING}" "${MACHINE_TYPE}" \
        "CountConstraintComponent" 180
    stop_alert_capture
    if [ "$status" -ne 0 ]; then
        echo "# no alert seen for ${TEST_MISSING}; captured alerts were:" >&3
        grep "e2e-flink" ${ALERTS_OUT} >&3 || echo "# (none)" >&3
        # Say which half failed. Without these the report is only "no alert",
        # which is exactly the ambiguity that cost two CI runs to resolve here.
        dump_entity_records "${TEST_MISSING}"
        dump_trigger_rows "${TEST_MISSING}" "CountConstraintComponent"
    fi
    [ "$status" -eq 0 ]

    run grep "${TEST_MISSING}" ${ALERTS_OUT}
    echo "# ${output}" >&3
    [[ "${output}" == *"hasE2EState"* ]]
    [[ "${output}" == *"warning"* ]]
}

@test "supplying the missing attribute retracts the minCount alert" {
    start_alert_capture
    publish_entity "${TEST_CLEAR}" "${MACHINE_TYPE}"
    run wait_for_alert "${TEST_CLEAR}" "hasE2EState" 90
    [ "$status" -eq 0 ]
    echo "# minCount alert raised for ${TEST_CLEAR}" >&3

    # Now satisfy hasE2EState. The alert must be RETRACTED, which on an upsert
    # topic means a tombstone rather than a new value -- a test that only reads
    # values would never see the clear and would wrongly report a stuck alert.
    publish_property "${TEST_CLEAR}" "${STATE_PROP}" "running" \
        "http://www.w3.org/2001/XMLSchema#string"
    run wait_for_retraction "${TEST_CLEAR}" "hasE2EState" 90
    stop_alert_capture
    if [ "$status" -ne 0 ]; then
        echo "# no retraction seen; captured:" >&3
        grep -c "${TEST_CLEAR}" "${ALERTS_OUT}" >&3 || echo "# (no lines captured)" >&3
    fi
    [ "$status" -eq 0 ]
}

@test "a value satisfying neither xone branch stays alerting" {
    start_alert_capture
    publish_entity "${TEST_XONE_BAD}" "${RANGE_TYPE}"
    # 50 satisfies neither >=100 nor <=10, so XONE is violated. sh:or cannot
    # express this, so reaching the alert proves the circuit layer -- not just
    # the leaf checks -- is evaluated on Flink.
    publish_property "${TEST_XONE_BAD}" "${RANGE_PROP}" 50
    echo "# published ${TEST_XONE_BAD} with hasE2ERange=50" >&3

    run wait_for_alert "${TEST_XONE_BAD}" "XoneConstraintComponent" 90
    if [ "$status" -ne 0 ]; then
        echo "# no XONE alert seen; captured alerts were:" >&3
        grep "e2e-flink" ${ALERTS_OUT} >&3 || echo "# (none)" >&3
    fi
    [ "$status" -eq 0 ]

    # Merely SEEING an alert proves nothing here: XONE fires on absence, so the
    # entity alerts before its attribute even arrives. The alert must still be
    # live after the value has landed and the pipeline settled -- that is what
    # distinguishes "50 fails the ranges" from "the attribute was missing".
    sleep 30
    stop_alert_capture
    result=$(final_alert_state "${TEST_XONE_BAD}")
    echo "# converged state for failing xone: ${result}" >&3
    [ "${result}" = "ALERT" ]
}

@test "a count parameter written beside sh:xone is enforced" {
    start_alert_capture
    publish_entity "${TEST_XONE_COUNT}" "${RANGE_TYPE}"
    echo "# published ${TEST_XONE_COUNT} with no hasE2ERange at all" >&3

    # E2ERangeMachineShape carries sh:minCount 1 NEXT TO its sh:xone. Those
    # parameters used to be lost before extraction -- dropped outright, or
    # folded in as a third xone member -- so this asserts the count alert
    # specifically, not merely that something alerted. The xone alerts here too
    # (it fires on absence), which is exactly why matching on the count
    # component rather than on "any alert" is what makes this test meaningful.
    run wait_for_alert "${TEST_XONE_COUNT}" "CountConstraintComponent" 90
    stop_alert_capture
    if [ "$status" -ne 0 ]; then
        echo "# no count alert for the xone path; captured:" >&3
        grep "${TEST_XONE_COUNT}" ${ALERTS_OUT} >&3 || echo "# (none)" >&3
    fi
    [ "$status" -eq 0 ]

    run grep "${TEST_XONE_COUNT}" ${ALERTS_OUT}
    [[ "${output}" == *"hasE2ERange"* ]]
}

@test "a value satisfying exactly one xone branch converges to cleared" {
    start_alert_capture
    # Publish the entity ALONE first and wait for the alert. Publishing the
    # attribute in the same breath let the entity be validated only once both
    # had landed, so no alert was ever raised and "converged to clear" was
    # trivially true against an empty stream -- green for the wrong reason.
    # XONE fires on absence, so an entity with no hasE2ERange must alert.
    publish_entity "${TEST_XONE_OK}" "${RANGE_TYPE}"
    run wait_for_alert "${TEST_XONE_OK}" "XoneConstraintComponent" 90
    if [ "$status" -ne 0 ]; then
        echo "# no transient alert to converge from; captured:" >&3
        grep "${TEST_XONE_OK}" ${ALERTS_OUT} >&3 || echo "# (none)" >&3
        dump_entity_records "${TEST_XONE_OK}"
        dump_trigger_rows "${TEST_XONE_OK}" "XoneConstraintComponent"
    fi
    [ "$status" -eq 0 ]
    echo "# transient xone alert raised for ${TEST_XONE_OK}" >&3

    # Now satisfy exactly one branch. The alert must be retracted.
    publish_property "${TEST_XONE_OK}" "${RANGE_PROP}" 5
    wait_for_converged "${TEST_XONE_OK}" CLEAR 90
    stop_alert_capture
    result=$(final_alert_state "${TEST_XONE_OK}")
    records=$(grep -c "${TEST_XONE_OK}" ${ALERTS_OUT} || true)
    echo "# converged state for satisfied xone: ${result} (records: ${records})" >&3
    # a real transient must have existed for the convergence to mean anything
    [ "${records}" -ge 2 ]
    [ "${result}" = "CLEAR" ]
}

## --------------------------------------------------------------- deletion
##
## Nothing in this suite -- or in the 101 kms fixtures, or anywhere else in
## shacl2flink -- ever set deleted=true before these tests. The delete path was
## entirely uncovered, in an engine whose whole job is to decide when an alert
## should stop.
##
## What these can and cannot catch. They run minutes after a deploy, so no
## state has expired yet; they cannot reproduce the hour of TTL that made the
## reported symptom appear. What they do pin is that the delete path WORKS at
## all -- that a deletion reaches Flink, is understood as a deletion, and
## retracts what it should. The settings that stop state expiring underneath it
## are pinned separately, and cheaply, in tests/test_delete_semantics.py.

@test "deleting an entity retracts the alert it raised" {
    start_alert_capture
    # An E2EMachine with no attribute violates minCount, so it alerts.
    run publish_entity_until_alert "${TEST_DEL_ENTITY}" "${MACHINE_TYPE}" \
        "CountConstraintComponent" 180
    if [ "$status" -ne 0 ]; then
        echo "# no alert to retract; captured:" >&3
        grep "${TEST_DEL_ENTITY}" ${ALERTS_OUT} >&3 || echo "# (none)" >&3
        dump_entity_records "${TEST_DEL_ENTITY}"
    fi
    [ "$status" -eq 0 ]
    echo "# alert raised for ${TEST_DEL_ENTITY}, now deleting it" >&3

    # The entity is gone: the alert is about something that no longer exists
    # and must be retracted. This is the reported symptom -- alerts outliving
    # the entity they were raised against.
    publish_entity_deleted "${TEST_DEL_ENTITY}" "${MACHINE_TYPE}"
    wait_for_converged "${TEST_DEL_ENTITY}" CLEAR 90
    stop_alert_capture

    result=$(final_alert_state "${TEST_DEL_ENTITY}")
    echo "# converged state after deleting the entity: ${result}" >&3
    if [ "${result}" != "CLEAR" ]; then
        echo "# alert survived the entity; records were:" >&3
        grep "${TEST_DEL_ENTITY}" ${ALERTS_OUT} >&3 || true
    fi
    [ "${result}" = "CLEAR" ]
}

@test "deleting a mandatory attribute reports zero, never a negative count" {
    start_alert_capture
    publish_entity "${TEST_DEL_ATTR}" "${MACHINE_TYPE}"
    publish_property "${TEST_DEL_ATTR}" "${STATE_PROP}" "running" \
        "http://www.w3.org/2001/XMLSchema#string"
    # Satisfied first, so the alert that follows is caused by the deletion
    # rather than by the attribute never having arrived.
    wait_for_converged "${TEST_DEL_ATTR}" CLEAR 90
    [ "$(final_alert_state "${TEST_DEL_ATTR}")" = "CLEAR" ]
    echo "# ${TEST_DEL_ATTR} satisfied, now deleting its attribute" >&3

    # Only alerts raised AFTER the deletion count -- see rearm_alert_capture.
    rearm_alert_capture
    publish_attribute_deleted "${TEST_DEL_ATTR}" "${STATE_PROP}"
    run wait_for_alert "${TEST_DEL_ATTR}" "CountConstraintComponent" 90
    if [ "$status" -ne 0 ]; then
        echo "# deleting the attribute raised no count alert; captured:" >&3
        grep "${TEST_DEL_ATTR}" ${ALERTS_OUT} >&3 || echo "# (none)" >&3
        dump_trigger_rows "${TEST_DEL_ATTR}" "CountConstraintComponent"
    fi
    [ "$status" -eq 0 ]
    stop_alert_capture

    run grep "${TEST_DEL_ATTR}" ${ALERTS_OUT}
    [[ "${output}" == *"hasE2EState"* ]]

    # The count must read 0. A negative one means the aggregate lost track of
    # what it had accumulated -- the defect these tests exist for.
    bad=$(negative_counts "${TEST_DEL_ATTR}")
    if [ -n "${bad}" ]; then
        echo "# NEGATIVE COUNT reported after a deletion:" >&3
        echo "${bad}" | sed 's/^/#   /' >&3
    fi
    [ -z "${bad}" ]
}

@test "deleting the entity a relationship points at is reported as a dangling link" {
    start_alert_capture
    # The far end first, so the link resolves and the machine starts clean.
    publish_entity "${TEST_DEL_TARGET}" "${CARTRIDGE_TYPE}"
    publish_entity "${TEST_DEL_LINKED}" "${LINKED_TYPE}"
    publish_relationship "${TEST_DEL_LINKED}" "${CARTRIDGE_REL}" "${TEST_DEL_TARGET}"
    wait_for_converged "${TEST_DEL_LINKED}" CLEAR 120
    [ "$(final_alert_state "${TEST_DEL_LINKED}")" = "CLEAR" ]
    echo "# ${TEST_DEL_LINKED} links to ${TEST_DEL_TARGET} and is clean" >&3

    # Delete the CARTRIDGE. Nothing about the linking machine changes -- it
    # still has exactly one relationship -- so the count must stay satisfied
    # and the class check must report that the link no longer resolves. This is
    # the reported case: deleting the object, not the subject.
    rearm_alert_capture
    publish_entity_deleted "${TEST_DEL_TARGET}" "${CARTRIDGE_TYPE}"
    run wait_for_alert "${TEST_DEL_LINKED}" "ClassConstraintComponent" 120
    if [ "$status" -ne 0 ]; then
        echo "# deleting the target raised no class alert; captured:" >&3
        grep "${TEST_DEL_LINKED}" ${ALERTS_OUT} >&3 || echo "# (none)" >&3
        dump_trigger_rows "${TEST_DEL_LINKED}" "ClassConstraintComponent"
    fi
    [ "$status" -eq 0 ]
    stop_alert_capture

    # And it must be reported as a dangling link, not as a miscounted one.
    bad=$(negative_counts "${TEST_DEL_LINKED}")
    if [ -n "${bad}" ]; then
        echo "# NEGATIVE COUNT after deleting the relationship target:" >&3
        echo "${bad}" | sed 's/^/#   /' >&3
    fi
    [ -z "${bad}" ]
}

@test "no alert produced during this run reports a negative count" {
    # A backstop over everything the suite published, not just the resources
    # the deletion tests own: the count expression is shared by every shape, so
    # a regression could surface first on any of them.
    #
    # Read BACK over the topic rather than tailing it. The alerts this is
    # judging were written by the tests above, so a consumer starting at the
    # end would see an empty stream and pass without having looked at anything.
    local rows rc
    rows=$(timeout 60 kafkacat -C -t ${BULK_ALERTS_TOPIC} -b ${KAFKA_BOOTSTRAP} \
        -o -5000 -e -f '%s\n' 2>/dev/null); rc=$?
    # A consumer that failed must not read as "nothing negative found".
    [ "${rc}" -eq 0 ]
    [ -n "${rows}" ]

    bad=$(echo "${rows}" | awk -v r="${RUN_ID}" 'index($0,r) && /Found -[0-9]/')
    if [ -n "${bad}" ]; then
        echo "# negative counts seen in this run:" >&3
        echo "${bad}" | sed 's/^/#   /' >&3
    fi
    [ -z "${bad}" ]
}

@test "an entity of an unconstrained type raises no shacl alerts" {
    start_alert_capture
    publish_entity "${TEST_UNKNOWN}" "${FREE_TYPE}"
    echo "# published ${TEST_UNKNOWN}" >&3

    # No shape targets E2EFreeMachine. Validating it would mean targetClass is
    # not being honoured.
    sleep 30
    stop_alert_capture
    run grep -c "${TEST_UNKNOWN}" ${ALERTS_OUT}
    echo "# alerts for unconstrained entity: ${output}" >&3
    [ "${output}" = "0" ]
}
