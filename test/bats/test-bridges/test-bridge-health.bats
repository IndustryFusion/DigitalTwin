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
# The bridges can stop doing their job while still reporting themselves
# healthy: alerta-bridge was observed 1/1 Ready with its Kafka consumer group
# Empty, forwarding nothing, because the liveness file is written once at
# startup and the heartbeat producer kept logging success from a separate
# code path. These tests assert on what the bridge is actually attached to --
# its consumer group, its broker connection -- rather than on the pod phase,
# which is the thing that lied.
#
# No kubefwd: everything here runs through kubectl exec, so the tests do not
# depend on a forwarded port being up.

SKIP= # set =skip to skip all tests (and only remove $SKIP from the test you are interested in)
NAMESPACE=iff
KAFKA_LABEL=app.kubernetes.io/name=kafka
EMQX_LABEL=apps.emqx.io/instance=emqx

# Bridges that consume from Kafka, with the consumer group each one joins.
# Group ids come from GROUPID in the respective KafkaBridge/*/app.js.
KAFKA_BRIDGES="alerta-bridge:alertakafkabridge \
debezium-bridge:debeziumBridgeGroup \
ngsild-updates-bridge:statekafkabridge \
timescaledb-bridge:timescaledbkafkabridge"

ALL_BRIDGES="alerta-bridge debezium-bridge ngsild-updates-bridge timescaledb-bridge mqtt-bridge"

# $1: label selector
get_pod() {
    kubectl -n ${NAMESPACE} get pods -l "$1" \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

kafka_pod() {
    get_pod ${KAFKA_LABEL}
}

# Ask Kafka about a consumer group.
# $1: group id
describe_group_state() {
    kubectl -n ${NAMESPACE} exec "$(kafka_pod)" -- \
        bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
        --group "$1" --describe --state 2>/dev/null
}

# $1: deployment/app name
pod_is_ready() {
    kubectl -n ${NAMESPACE} get pods -l app="$1" \
        -o jsonpath='{.items[0].status.containerStatuses[0].ready}' 2>/dev/null
}

# $1: app name, $2: file
pod_has_file() {
    kubectl -n ${NAMESPACE} exec "$(get_pod app="$1")" -- cat "$2" >/dev/null 2>&1
}

# $1: app name
restart_count() {
    kubectl -n ${NAMESPACE} get pods -l app="$1" \
        -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}' 2>/dev/null
}

@test "every Kafka bridge has actually joined its consumer group" {
    $SKIP
    failures=""
    for entry in ${KAFKA_BRIDGES}; do
        app=${entry%%:*}
        group=${entry##*:}
        ready=$(pod_is_ready "$app")
        if [ "$ready" != "true" ]; then
            echo "# $app is not Ready, skipping its group check"
            continue
        fi
        state=$(describe_group_state "$group")
        echo "# $app / $group -> $(echo "$state" | tail -1)"
        # STATE and #MEMBERS are the last two columns of the single data row.
        # Read from the right: when a group is Empty the ASSIGNMENT-STRATEGY
        # column is blank, so counting from the left shifts by one.
        members=$(echo "$state" | tail -1 | awk '{print $NF}')
        stable=$(echo "$state" | tail -1 | awk '{print $(NF-1)}')
        case "$members" in
            ''|*[!0-9]*) members=0 ;;
        esac
        # A pod that is Ready but whose group is Empty is exactly the failure
        # this suite exists for: it forwards nothing and nothing complains.
        if [ "$stable" != "Stable" ] || [ "$members" -lt 1 ]; then
            failures="${failures} ${app}(group=${group},state=${stable},members=${members})"
        fi
    done
    [ -z "$failures" ] || { echo "# bridges Ready but not consuming:${failures}"; false; }
}

@test "every Ready bridge exposes the liveness and readiness files its probes read" {
    $SKIP
    failures=""
    for app in ${ALL_BRIDGES}; do
        ready=$(pod_is_ready "$app")
        if [ "$ready" != "true" ]; then
            echo "# $app is not Ready, skipping"
            continue
        fi
        pod_has_file "$app" /tmp/ready || failures="${failures} ${app}:/tmp/ready"
        pod_has_file "$app" /tmp/healthy || failures="${failures} ${app}:/tmp/healthy"
    done
    [ -z "$failures" ] || { echo "# missing probe files:${failures}"; false; }
}

@test "removing the liveness file makes the liveness probe fail" {
    $SKIP
    app=alerta-bridge
    ready=$(pod_is_ready "$app")
    [ "$ready" = "true" ] || skip "$app is not Ready"
    pod=$(get_pod app=${app})
    before=$(restart_count "$app")

    # The whole design rests on this: the bridge removes /tmp/healthy when its
    # input dies, and the kubelet then restarts it. Before, the file was written
    # once and never removed, so the probe could never fail no matter what
    # happened to the consumer. Assert the probe command itself reacts, rather
    # than waiting out initialDelaySeconds=300 plus three probe periods.
    kubectl -n ${NAMESPACE} exec "$pod" -- rm -f /tmp/healthy
    run kubectl -n ${NAMESPACE} exec "$pod" -- cat /tmp/healthy
    echo "# probe command exit status without the file: $status"
    [ "$status" -ne 0 ]

    # Put it back so the kubelet does not restart the bridge for a test.
    kubectl -n ${NAMESPACE} exec "$pod" -- sh -c 'echo -n healthy > /tmp/healthy'
    run kubectl -n ${NAMESPACE} exec "$pod" -- cat /tmp/healthy
    [ "$status" -eq 0 ]

    after=$(restart_count "$app")
    [ "$before" = "$after" ] || echo "# note: $app restarted during the test ($before -> $after)"
}

@test "a Ready mqtt bridge is connected to the broker and subscribed" {
    $SKIP
    ready=$(pod_is_ready mqtt-bridge)
    [ "$ready" = "true" ] || skip "mqtt-bridge is not Ready"
    emqx=$(get_pod ${EMQX_LABEL})
    [ -n "$emqx" ] || skip "no emqx pod found"

    # Readiness is supposed to mean the subscription exists. It used to be
    # written milliseconds after bind() was called, before the broker had even
    # answered, so a bridge that never connected still looked Ready.
    clients=$(kubectl -n ${NAMESPACE} exec "$emqx" -- emqx ctl clients list 2>/dev/null)
    echo "# emqx clients: $clients"
    # Deliberately not `grep -v`: with a single "No clients." line an inverted
    # match happens to fail for the right reason, but any banner line the broker
    # prints would make it pass while nothing is connected.
    if echo "$clients" | grep -q "No clients"; then
        echo "# mqtt-bridge reports Ready but the broker has no client connected"
        false
    fi

    # The connected client above is the hard gate, because that is unambiguous.
    # The subscription listing is only checked when the broker actually reports
    # subscriptions: the bridge subscribes as $share/kafka/spBv1.0/+/+/+/+, and
    # whether a shared subscription shows up here is an EMQX detail we should
    # not turn into a false red.
    subs=$(kubectl -n ${NAMESPACE} exec "$emqx" -- emqx ctl subscriptions list 2>/dev/null)
    echo "# emqx subscriptions: $subs"
    if echo "$subs" | grep -q "No subscriptions"; then
        echo "# broker lists no subscriptions; connected client is the only assertion here"
    else
        echo "$subs" | grep -q "spBv1.0" || { echo "# broker has subscriptions but none on the sparkplug topic"; false; }
    fi
}

@test "no bridge is stuck in a restart loop" {
    $SKIP
    # The bridges now exit non-zero when their input is broken, which is the
    # point -- but a bridge restarting over and over is a failure that should be
    # read as such and not mistaken for the fix working.
    failures=""
    for app in ${ALL_BRIDGES}; do
        pod=$(get_pod app="$app")
        [ -n "$pod" ] || continue
        waiting=$(kubectl -n ${NAMESPACE} get pod "$pod" \
            -o jsonpath='{.status.containerStatuses[0].state.waiting.reason}' 2>/dev/null)
        echo "# $app restarts=$(restart_count "$app") waiting=${waiting:-none}"
        [ "$waiting" != "CrashLoopBackOff" ] || failures="${failures} ${app}"
    done
    [ -z "$failures" ] || { echo "# bridges in CrashLoopBackOff:${failures}"; false; }
}
