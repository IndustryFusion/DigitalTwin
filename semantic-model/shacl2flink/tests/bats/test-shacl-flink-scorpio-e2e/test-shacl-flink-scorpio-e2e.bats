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

# End-to-end tests driven through Scorpio, and read back from Alerta.
#
# test-shacl-flink-e2e publishes to iff.ngsild.entities and
# iff.ngsild.attributes directly, so that a failure there points at Flink and
# the generated SQL rather than at everything upstream of it. This file starts
# one layer up and finishes one layer further down: entities are created and
# deleted with the NGSI-LD API, and the assertions are made against the alerts
# an operator actually looks at.
#
# Between those two ends lie Postgres, the Debezium connector, the
# debezium-bridge and the alerta-bridge -- the part of the chain that has to
# turn "the operator deleted this entity" into the records Flink consumes, and
# Flink's retraction back into a closed alert. Neither end is exercised by the
# Kafka-level suite, and both have been the cause of alerts that would not go
# away. The question these tests answer is the one that gets asked in
# practice: I deleted the entity, why is the alert still there?
#
# Like its sibling, this file is not run from test/bats. It is driven by
# `make test-flink-e2e`, which compiles and deploys tests/e2e-kms first, so
# every shape asserted here comes from that KMS and nothing else.

DEBUG=${DEBUG:-false}
NAMESPACE=${NAMESPACE:-iff}

# The ingress names that test/setup-local-ingress.sh puts in /etc/hosts. The
# Kafka-level suite reaches its topics with kubefwd; these three services are
# published, so no forwarding is needed.
KEYCLOAK_URL=${KEYCLOAK_URL:-http://keycloak.local/auth/realms}
NGSILD_URL=${NGSILD_URL:-http://ngsild.local/ngsi-ld/v1}
ALERTA_URL=${ALERTA_URL:-http://alerta.local/api}

CLIENT_ID=scorpio
REALM_USER=realm_user
USER_SECRET=secret/credential-iff-realm-user-iff

CONTEXT=https://industryfusion.github.io/contexts/staging/example/v0.2/context.jsonld
E2E=https://industryfusion.github.io/contexts/example/v0/base_entities
MACHINE_TYPE=${E2E}/E2EMachine
LINKED_TYPE=${E2E}/E2ELinkedMachine
CARTRIDGE_TYPE=${E2E}/E2ECartridge
CARTRIDGE_REL=${E2E}/hasE2ECartridge

# The constraint components as they appear in an alert's event field, which is
# where a shacl alert says which check it came from.
COUNT_CONSTRAINT=CountConstraintComponent
CLASS_CONSTRAINT=ClassConstraintComponent
SPARQL_CONSTRAINT=SPARQLConstraintComponent

# The knowledge-backed state, and two values from tests/e2e-kms/knowledge.ttl:
# e2e_state_GOOD is isValidForE2E the focus class, e2e_state_ELSEWHERE only an
# unrelated one. Deciding which is which means walking rdfs:subClassOf* through
# the rdf table, so this pair is the only thing in the suite that reaches the
# knowledge at all.
KNOWN_STATE_PROP=${E2E}/hasE2EKnownState
KNOWLEDGE_TYPE=${E2E}/E2EKnowledgeMachine
STATE_GOOD=${E2E}/e2e_state_GOOD
STATE_ELSEWHERE=${E2E}/e2e_state_ELSEWHERE

# A fresh id per run. Alerts are keyed by resource, and a resource that already
# carries a closed alert from an earlier run would let a test pass on history
# rather than on what this run produced.
# The whole-model cycle uses fixed ids, because the point of it is deploying
# and redeploying the SAME model instance rather than a fresh one each round.
CYCLE_MODEL="${BATS_TEST_DIRNAME}/model-cycle.jsonld"
CYCLE_GOOD="urn:e2e-cycle-good:1"
CYCLE_NOSTATE="urn:e2e-cycle-nostate:1"
CYCLE_CARTRIDGE="urn:e2e-cycle-cartridge:1"
CYCLE_LINKED="urn:e2e-cycle-linked:1"
CYCLE_DANGLING="urn:e2e-cycle-dangling:1"
CYCLE_IDS="${CYCLE_GOOD} ${CYCLE_NOSTATE} ${CYCLE_CARTRIDGE} ${CYCLE_LINKED} ${CYCLE_DANGLING}"

RUN_ID=$(date +%s)
TEST_MISSING="urn:e2e-scorpio-missing:${RUN_ID}"
TEST_LINKED="urn:e2e-scorpio-linked:${RUN_ID}"
TEST_TARGET="urn:e2e-scorpio-target:${RUN_ID}"
TEST_RECREATE="urn:e2e-scorpio-recreate:${RUN_ID}"
TEST_SPARQL="urn:e2e-scorpio-sparql:${RUN_ID}"

# On an idle cluster an alert appears about five seconds after the create and
# closes about five seconds after the delete. The timeout is set two orders of
# magnitude above that so a loaded runner cannot fail the suite, while a real
# regression -- an alert that never clears -- still terminates it.
TIMEOUT=${TIMEOUT:-180}
POLL=5

setup() {
    ALERTA_KEY=$(kubectl -n "${NAMESPACE}" get secret alerta \
        -o jsonpath='{.data.alerta-admin-key}' | base64 -d)
}

teardown() {
    for id in "${TEST_MISSING}" "${TEST_LINKED}" "${TEST_TARGET}" "${TEST_RECREATE}" \
              "${TEST_SPARQL}" ${CYCLE_IDS}; do
        delete_entity "${id}" >/dev/null 2>&1 || true
    done
}

# Function definitions

get_password() {
    kubectl -n "${NAMESPACE}" get "${USER_SECRET}" -o jsonpath='{.data.password}' | base64 -d
}

# Fetched per request rather than once per test: the tests can run for minutes
# and an expired token would surface as an unexplained 401 halfway through.
get_token() {
    local password
    password=$(get_password)
    curl -s -d "client_id=${CLIENT_ID}" -d "username=${REALM_USER}" \
        -d "password=${password}" -d 'grant_type=password' \
        "${KEYCLOAK_URL}/${NAMESPACE}/protocol/openid-connect/token" | jq -r '.access_token'
}

# create_entity <id> <type> [extra-json-members]
create_entity() {
    local id=$1 type=$2 extra=${3:-} body
    if [ -n "${extra}" ]; then
        body=$(printf '{"@context":"%s","id":"%s","type":"%s",%s}' \
            "${CONTEXT}" "${id}" "${type}" "${extra}")
    else
        body=$(printf '{"@context":"%s","id":"%s","type":"%s"}' \
            "${CONTEXT}" "${id}" "${type}")
    fi
    echo "${body}" | curl -s -o /dev/null -w '%{http_code}' -X POST \
        -H "Authorization: Bearer $(get_token)" \
        -H 'Content-Type: application/ld+json' \
        --data-binary @- "${NGSILD_URL}/entities/"
}

# A relationship to <target>, as the extra member of a create_entity body.
relationship_json() {
    printf '"%s":{"type":"Relationship","object":"%s"}' "$1" "$2"
}

# A Property whose value is an IRI, which is what a knowledge lookup needs: the
# SPARQL constraint resolves the value against the ontology, and a literal
# could never match.
iri_property_json() {
    printf '"%s":{"type":"Property","value":{"@id":"%s"}}' "$1" "$2"
}

# Replace the default instance of an attribute on an existing entity.
set_iri_property() {
    local id=$1 prop=$2 value=$3
    printf '{"@context":"%s",%s}' "${CONTEXT}" "$(iri_property_json "${prop}" "${value}")" \
        | curl -s -o /dev/null -w '%{http_code}' -X POST \
            -H "Authorization: Bearer $(get_token)" \
            -H 'Content-Type: application/ld+json' \
            --data-binary @- "${NGSILD_URL}/entities/${id}/attrs"
}

delete_entity() {
    curl -s -o /dev/null -w '%{http_code}' -X DELETE \
        -H "Authorization: Bearer $(get_token)" "${NGSILD_URL}/entities/$1"
}

# Deploy the whole model instance in one batch, the way an operator does.
#
# The response body matters as much as the status. A batch upsert answers 207
# when it created some entities and rejected others, which is how a model with
# an unparseable observedAt came to be half-deployed for weeks without anything
# looking wrong -- the missing entity showed up as dangling relationships on
# the ones that did load. Treat a partial success as a failure.
upsert_model() {
    local body code
    body=$(curl -s -w '\n%{http_code}' -X POST \
        -H "Authorization: Bearer $(get_token)" \
        -H 'Content-Type: application/ld+json' \
        --data-binary @"${CYCLE_MODEL}" "${NGSILD_URL}/entityOperations/upsert")
    code=$(echo "${body}" | tail -1)
    if [ "${code}" = "207" ]; then
        echo "# model upsert was only partially applied:" >&3
        echo "${body}" | head -n -1 | sed 's/^/#   /' >&3
        return 1
    fi
    case "${code}" in
        200|201|204) return 0 ;;
        *) echo "# model upsert -> HTTP ${code}" >&3
           echo "${body}" | head -n -1 | sed 's/^/#   /' >&3
           return 1 ;;
    esac
}

delete_model() {
    local id code
    for id in ${CYCLE_IDS}; do
        code=$(delete_entity "${id}")
        case "${code}" in
            204|404) ;;
            *) echo "# DELETE ${id} -> HTTP ${code}" >&3; return 1 ;;
        esac
    done
}

# What the fixture is built to produce: two violations and three silent
# entities. Asserting the silent ones matters as much as the loud ones --
# a deployment that alerts on everything would satisfy a one-sided check.
assert_model_alerting() {
    assert_alert "${CYCLE_NOSTATE}" "${COUNT_CONSTRAINT}"
    # A count, not a class violation. Those are two different situations and
    # only one of them is this one: a link whose target existed and was then
    # DELETED still counts as one relationship and fails the class check, which
    # is what the test above asserts. A link to an id that never existed
    # resolves to nothing at all, so the count is 0 and it is minCount that
    # fails. Asserting the class component here passed locally only because the
    # fixture uses fixed ids and an earlier run had left a stale class alert on
    # this resource; a clean cluster reported the count, correctly.
    assert_alert "${CYCLE_DANGLING}" "${COUNT_CONSTRAINT}"
    assert_no_alert "${CYCLE_GOOD}"
    assert_no_alert "${CYCLE_LINKED}"
    assert_no_alert "${CYCLE_CARTRIDGE}"
}

assert_model_silent() {
    local id
    for id in ${CYCLE_IDS}; do
        assert_no_alert "${id}"
    done
}

# open_alerts_for <resource> [event-substring]
#
# Counting every alert on a resource would let an unrelated violation stand in
# for the one under test, and a shape usually constrains more than one path, so
# there is generally one available to do it. The event names the constraint
# component and the path it fired on, so naming it is what makes the assertion
# specific. Leave it out only where the claim really is "nothing at all is open
# on this resource" -- which is exactly the claim to make about an entity that
# has been deleted.
open_alerts_for() {
    curl -s -H "Authorization: Key ${ALERTA_KEY}" "${ALERTA_URL}/alerts?status=open" \
        | jq --arg r "$1" --arg e "${2:-}" \
            '[.alerts[] | select(.resource == $r)
                        | select($e == "" or (.event | contains($e)))] | length'
}

# Every open alert on a resource, one per line, for failure diagnostics.
alert_texts_for() {
    curl -s -H "Authorization: Key ${ALERTA_KEY}" "${ALERTA_URL}/alerts?status=open" \
        | jq -r --arg r "$1" '.alerts[] | select(.resource == $r) | "\(.event): \(.text)"'
}

# Assert a matching alert shows up, printing what Alerta holds if none does.
assert_alert() {
    local resource=$1 event=${2:-} waited=0
    while [ "${waited}" -lt "${TIMEOUT}" ]; do
        [ "$(open_alerts_for "${resource}" "${event}")" -gt 0 ] && return 0
        sleep "${POLL}"
        waited=$((waited + POLL))
    done
    echo "# no ${event:-shacl} alert on ${resource} within ${TIMEOUT}s; open now:" >&3
    alert_texts_for "${resource}" | sed 's/^/#   /' >&3 || true
    return 1
}

# Assert the matching alerts close -- the assertion this file exists for.
assert_no_alert() {
    local resource=$1 event=${2:-} waited=0
    while [ "${waited}" -lt "${TIMEOUT}" ]; do
        [ "$(open_alerts_for "${resource}" "${event}")" -eq 0 ] && return 0
        sleep "${POLL}"
        waited=$((waited + POLL))
    done
    echo "# alerts on ${resource} still open after ${TIMEOUT}s:" >&3
    alert_texts_for "${resource}" | sed 's/^/#   /' >&3
    return 1
}

@test "scorpio and alerta are reachable with the platform credentials" {
    token=$(get_token)
    [ -n "${token}" ] && [ "${token}" != "null" ]
    code=$(curl -s -o /dev/null -w '%{http_code}' \
        -H "Authorization: Bearer ${token}" "${NGSILD_URL}/entities/urn:no-such-entity:0")
    # 404 is the healthy answer here: authenticated, and the entity is absent.
    [ "${code}" = "404" ]
    code=$(curl -s -o /dev/null -w '%{http_code}' \
        -H "Authorization: Key ${ALERTA_KEY}" "${ALERTA_URL}/alerts?status=open")
    [ "${code}" = "200" ]
}

@test "an entity created in scorpio raises an alert, and deleting it clears the alert" {
    # The plainest statement of the reported problem. An E2EMachine must carry
    # exactly one hasE2EState; created without one it violates its shape, and
    # once the entity is gone there is nothing left to violate it.
    code=$(create_entity "${TEST_MISSING}" "${MACHINE_TYPE}")
    [ "${code}" = "201" ]
    echo "# created ${TEST_MISSING} without its mandatory attribute" >&3
    assert_alert "${TEST_MISSING}" "${COUNT_CONSTRAINT}"

    code=$(delete_entity "${TEST_MISSING}")
    [ "${code}" = "204" ]
    echo "# deleted ${TEST_MISSING} in scorpio" >&3
    assert_no_alert "${TEST_MISSING}"
}

@test "deleting the entity a relationship points at alerts, and restoring it clears" {
    # The far end first, so the link resolves and the machine starts clean.
    code=$(create_entity "${TEST_TARGET}" "${CARTRIDGE_TYPE}")
    [ "${code}" = "201" ]
    code=$(create_entity "${TEST_LINKED}" "${LINKED_TYPE}" \
        "$(relationship_json "${CARTRIDGE_REL}" "${TEST_TARGET}")")
    [ "${code}" = "201" ]
    echo "# ${TEST_LINKED} links to ${TEST_TARGET}" >&3

    # Deleting the object leaves the subject untouched -- it still has exactly
    # one relationship -- so this must be reported as a link that no longer
    # resolves, and it must be reported against the entity that still exists.
    code=$(delete_entity "${TEST_TARGET}")
    [ "${code}" = "204" ]
    assert_alert "${TEST_LINKED}" "${CLASS_CONSTRAINT}"

    # Putting the target back has to retract it again. An alert that survives
    # the condition that raised it is the failure this suite is here to catch.
    code=$(create_entity "${TEST_TARGET}" "${CARTRIDGE_TYPE}")
    [ "${code}" = "201" ]
    echo "# restored ${TEST_TARGET}" >&3
    assert_no_alert "${TEST_LINKED}"
}

@test "a sparql constraint reads the knowledge, and clears when the value becomes valid" {
    # The production KMS carries four sh:sparql constraints and this suite
    # carried none, so no e2e test had ever run one against Flink -- they were
    # exercised offline against the SQLite oracle only. That gap hides a whole
    # class of divergence, because a SPARQL constraint reaches the ontology
    # through the `rdf` table, and in Flink that is join STATE rather than a
    # table that is simply there. State can go away; a table cannot. The oracle
    # cannot tell the difference and will happily keep agreeing with itself.
    #
    # e2e_state_ELSEWHERE is isValidForE2E E2ECartridge, not the focus class,
    # so a machine carrying it violates -- and deciding that requires walking
    # rdfs:subClassOf* through the knowledge rather than reading an attribute.
    code=$(create_entity "${TEST_SPARQL}" "${KNOWLEDGE_TYPE}" \
        "$(iri_property_json "${KNOWN_STATE_PROP}" "${STATE_ELSEWHERE}")")
    [ "${code}" = "201" ]
    echo "# ${TEST_SPARQL} carries a state valid only for another class" >&3
    assert_alert "${TEST_SPARQL}" "${SPARQL_CONSTRAINT}"

    # Swapping in a state that IS valid for this class has to retract it. This
    # half is what fails if the knowledge has gone out of the join: with no rdf
    # rows to match, the constraint answers the same way whatever the value is.
    code=$(set_iri_property "${TEST_SPARQL}" "${KNOWN_STATE_PROP}" "${STATE_GOOD}")
    [ "${code}" = "204" ]
    echo "# swapped it for a state that is valid" >&3
    assert_no_alert "${TEST_SPARQL}" "${SPARQL_CONSTRAINT}"
}

@test "the model instance survives being deployed, deleted and deployed again" {
    # The operator's actual loop, and the one that broke: deploy the model,
    # look at the alerts, delete it, look again -- twice, because a deployment
    # that only works the first time is not a working deployment.
    #
    # Deleting the model used to RAISE alerts rather than clear them. Every
    # entity loses its attributes at the same moment it is deleted, the count
    # of a mandatory property drops to zero, and unless the check can tell
    # "attribute gone" from "entity gone" it reports the missing property on an
    # entity that no longer exists -- permanently, because nothing recomputes a
    # verdict for something Scorpio no longer has. Measured on the kms model:
    # thirteen CountConstraint alerts that never cleared. So the assertion that
    # matters is not that deleting is quiet, but that it is quiet TWICE, with a
    # redeployment in between to prove the alerts still come back.

    echo "# round 1: deploy" >&3
    upsert_model
    assert_model_alerting

    echo "# round 1: delete" >&3
    delete_model
    assert_model_silent

    echo "# round 2: deploy the same model instance again" >&3
    upsert_model
    assert_model_alerting

    echo "# round 2: delete" >&3
    delete_model
    assert_model_silent
}

@test "an entity deleted in scorpio and created again alerts a second time" {
    # A deletion is recorded as a tombstone, and a tombstone that is allowed to
    # outrank everything written after it would suppress the entity for good --
    # silently, because a missing alert looks exactly like a healthy entity.
    # Recreating the same id has to raise the alert again.
    code=$(create_entity "${TEST_RECREATE}" "${MACHINE_TYPE}")
    [ "${code}" = "201" ]
    assert_alert "${TEST_RECREATE}" "${COUNT_CONSTRAINT}"

    code=$(delete_entity "${TEST_RECREATE}")
    [ "${code}" = "204" ]
    assert_no_alert "${TEST_RECREATE}"
    echo "# ${TEST_RECREATE} deleted and its alert closed" >&3

    code=$(create_entity "${TEST_RECREATE}" "${MACHINE_TYPE}")
    [ "${code}" = "201" ]
    echo "# recreated ${TEST_RECREATE} under the same id" >&3
    assert_alert "${TEST_RECREATE}" "${COUNT_CONSTRAINT}"
}
