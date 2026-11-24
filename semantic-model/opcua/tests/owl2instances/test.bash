#
# Copyright (c) 2024, 2025 Intel Corporation
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
set -e
NODESET_VERSION=UA-1.05.03-2023-12-15
CORE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Schema/Opc.Ua.NodeSet2.xml
DI_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/DI/Opc.Ua.Di.NodeSet2.xml
MACHINERY_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Machinery/Opc.Ua.Machinery.NodeSet2.xml
PUMPS_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Pumps/Opc.Ua.Pumps.NodeSet2.xml
BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl
CORE_ONTOLOGY=core.ttl
DEVICES_ONTOLOGY=devices.ttl
MACHINERY_ONTOLOGY=machinery.ttl
PUMPS_ONTOLOGY=pumps.ttl
RESULT=result.ttl
NODESET2OWL_RESULT=nodeset2owl_result.ttl
CORE_RESULT=core.ttl
CLEANED=cleaned.ttl
NODESET2OWL=../../nodeset2owl.py
TESTURI=http://my.test/
# Instance nodes are dynamic, nodeset2owl exports them only with a server URI
SERVER_URI=urn:test:server
EXURI=http://example.org/
DEBUG=${DEBUG:-false}
if [ "$DEBUG" = "true" ]; then
    DEBUG_CMDLINE="-m debugpy --listen 5678"
fi
TESTNODESETS=(
    test_full_id.Nodeset2,http://example.org/MinimalNodeset/ObjectType,,,,,,http://example.org/FullId/
    test_eid_switch.NodeSet2,,,,"--type-all;-eid"
    test_type_all_switch.NodeSet2,,,,--type-all
    test_object_types.NodeSet2,${TESTURI}AlphaType
    test_minimal_object.NodeSet2,http://example.org/MinimalNodeset/ObjectType
    test_references_to_typedefinitions.NodeSet2,${TESTURI}AlphaType
    test_ignore_references.NodeSet2,${TESTURI}AlphaType
    test_object_hierarchies_no_DataValue,${TESTURI}AlphaType
    test_object_subtypes.NodeSet2,${TESTURI}AlphaType
    test_variable_enum.NodeSet2,${TESTURI}AlphaType
    test_object_wrong.NodeSet2,${TESTURI}AlphaType
    test_object_subtypes_inheritance.Nodeset2,${TESTURI}AlphaType
    test_object_subtypes_inheritance_wrong.Nodeset2,${TESTURI}AlphaSubType,,,,SUBCLASS_INCONSISTENCY
    test_reference_types_properties.Nodeset2,${TESTURI}AlphaType,,,-p
    test_variable_arrays_vrs.NodeSet2,${TESTURI}AlphaType,,,-vrs
    test_semantic_bridge.Nodeset2,${EXURI}AlphaType,,,-sb,,${EXURI}
    test_interfaces.NodeSet2,${TESTURI}AlphaType,,machinery,-p,INTERFACE_NOT_SUBTYPE_OF_INTERFACETYPE
    test_object_example.NodeSet2,${EXURI}AlphaType,,,,,${EXURI}
    test_pumps_instanceexample,http://opcfoundation.org/UA/Pumps/PumpType,http://yourorganisation.org/InstanceExample/,pumps
    test_variable_arrays.NodeSet2,${TESTURI}AlphaType
    test_declaration_additions.NodeSet2,${TESTURI}AlphaType,,,,DEEP_DECLARATION_ADDITIONS
    test_declaration_additions_violations.NodeSet2,${TESTURI}AlphaType,,,,DEEP_DECLARATION_ADDITIONS
    test_placeholder_empty_types.NodeSet2,${TESTURI}AlphaType
    test_browsename_namespaces.NodeSet2,${TESTURI}AlphaType
    test_browsename_namespaces_deep.NodeSet2,${TESTURI}AlphaType
    test_placeholder_membership.NodeSet2,${TESTURI}AlphaType
    test_declaration_types.NodeSet2,${TESTURI}AlphaType,,,,UNCOVERED_INSTANCE_TERMS
    test_instance_types.NodeSet2,${TESTURI}AlphaType,,,,UNCOVERED_INSTANCE_TERMS
    )
CLEANGRAPH=cleangraph.py
TYPEURI=http://example.org/MinimalNodeset
SHACL=shacl.ttl
ENTITIES_FILE=entities.ttl
INSTANCES=instances.jsonld
SPARQLQUERY=query.py
SERVE_CONTEXT=serve_context.py
SERVE_CONTEXT_PORT=8099
TEST_CONTEXT_FILE=context.jsonld.test
CONTEXT_FILE=context.jsonld
LOCAL_CONTEXT=http://localhost:${SERVE_CONTEXT_PORT}/${CONTEXT_FILE}
PYSHACL_RESULT=pyshacl.ttl
OWL2INSTANCES="../../owl2instances.py"
COMPARE_GRAPHS="./compare_graphs.py"


function mydiff() {
    format="$4"
    echo "$1"
    result="$2"
    expected="$3"
    if [ -f "${expected}.nocompare" ]; then
        echo "Skipping test"
    else
        echo "expected <=> result"
        python3 ${COMPARE_GRAPHS} -f ${format} ${expected} ${result} || exit 1
    fi
    echo Done
}

function ask() {
    echo $1
    query=$3
    ENTITIES=$2
    FORMAT=${4:-ttl}

    result=$(python3 "${SPARQLQUERY}" -f ${FORMAT} "${ENTITIES}" "$query")
        
        if [ "$result" != "True" ]; then
            echo "Wrong result of query: ${result}."
            exit 1
        else
            echo "OK"
        fi
}

function startstop_context_server() {
    echo $1
    start=$2
    if [ "$start" = "true" ]; then
        (python3 ${SERVE_CONTEXT} -p ${SERVE_CONTEXT_PORT} ${TEST_CONTEXT_FILE} &)
    else
        pkill -f ${SERVE_CONTEXT} || echo "Server not running anyway"
        sleep 1
    fi
    sleep 1
}

function checkqueries() {
    echo "$1"
    
    # Correctly capture the list of query files into an array
    queries=()
    while IFS= read -r -d '' file; do
        queries+=("$file")
    done < <(find . -maxdepth 1 -name "$2.query[0-9]*" -print0)

    # Check if the array is empty
    if [ ${#queries[@]} -eq 0 ]; then
        echo "Skipping advanced sparql tests: No queries found matching pattern $2.query[0-9]*"
        return
    fi
    for query in "${queries[@]}"; do
        echo "Executing query for entities $ENTITIES_FILE and query $query"
        result=$(python3 "${SPARQLQUERY}" "${ENTITIES_FILE}" "$query")
        
        if [ "$result" != "True" ]; then
            echo "Wrong result of query: ${result}."
            exit 1
        fi
    done
    
    echo "Done"
}

function checkshaclqueries() {
    echo "$1"
    queries=()
    while IFS= read -r -d '' file; do
        queries+=("$file")
    done < <(find . -maxdepth 1 -name "$2.shaclquery[0-9]*" -print0)
    if [ ${#queries[@]} -eq 0 ]; then
        echo "Skipping: No queries found matching pattern $2.shaclquery[0-9]*"
        return
    fi
    for query in "${queries[@]}"; do
        echo "Executing query for shapes $SHACL and query $query"
        result=$(python3 "${SPARQLQUERY}" "${SHACL}" "$query")
        if [ "$result" != "True" ]; then
            echo "Wrong result of query: ${result}."
            exit 1
        fi
    done
    echo "Done"
}

# Every type and attribute of the instances is covered by the shapes and the ontology (opcua/instance-coverage),
# so no case may report uncovered terms, except the cases listed here, whose instances carry members that no type
# and no declaration shape gives a rule (members only the instance adds, a placeholder variable without a value
# constraint, declaration additions more than one relationship deep, see DEEP_DECLARATION_ADDITIONS, or children
# whose BrowseName namespace differs from the type's member, see opcua/member-identity), or that expect the warning
# in their warning column.
UNCOVERED_ALLOWED=" test_object_types.NodeSet2 test_references_to_typedefinitions.NodeSet2 test_object_subtypes.NodeSet2 \
test_variable_enum.NodeSet2 test_object_wrong.NodeSet2 test_reference_types_properties.Nodeset2 \
test_variable_arrays_vrs.NodeSet2 test_variable_arrays.NodeSet2 test_declaration_additions.NodeSet2 \
test_declaration_additions_violations.NodeSet2 test_browsename_namespaces.NodeSet2 \
test_browsename_namespaces_deep.NodeSet2 test_placeholder_membership.NodeSet2 "

# Terms the warning has to name, per case: a member only the instance adds, a declaration addition more than one
# relationship deep, an Organizes reference only the instance has.
UNCOVERED_EXPECTED=(
    "test_declaration_types.NodeSet2 test:hasExtra"
    "test_declaration_additions.NodeSet2 test:hasDeep"
    "test_instance_types.NodeSet2 opcua:Organizes"
    )

function check_coverage_warning() {
    nodeset=$1
    warning=$2
    for entry in "${UNCOVERED_EXPECTED[@]}"; do
        if [ "${entry%% *}" = "$nodeset" ]; then
            term="${entry#* }"
            if ! grep UNCOVERED_INSTANCE_TERMS output.log | grep -qF "$term"; then
                echo "UNCOVERED_INSTANCE_TERMS of $nodeset does not name $term. Exiting with error."
                exit 1
            fi
            echo "UNCOVERED_INSTANCE_TERMS names $term"
        fi
    done
    if [ "$warning" = "UNCOVERED_INSTANCE_TERMS" ] || [[ "$UNCOVERED_ALLOWED" == *" $nodeset "* ]]; then
        return
    fi
    if grep -q UNCOVERED_INSTANCE_TERMS output.log; then
        echo "Unexpected UNCOVERED_INSTANCE_TERMS for $nodeset:"
        grep UNCOVERED_INSTANCE_TERMS output.log
        exit 1
    fi
    echo "No uncovered terms"
}

if [ ! "$DEBUG" = "true" ]; then
    echo Prepare core, device, machinery, pumps nodesets for testcases
    echo -------------------------
    echo create core
    python3 ${NODESET2OWL} ${CORE_NODESET} -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p opcua -o ${CORE_RESULT} || exit 1
    echo create devices.ttl
    python3 ${NODESET2OWL} ${DI_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} -v http://example.com/v0.1/DI/ -p devices -o devices.ttl
    echo create machinery.ttl
    python3 ${NODESET2OWL} ${MACHINERY_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} -v http://example.com/v0.1/Machinery/ -p machinery -o machinery.ttl
    echo create pumps.ttl
    python3 ${NODESET2OWL} ${PUMPS_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} ${MACHINERY_ONTOLOGY} -v http://example.com/v0.1/Pumps/ -p pumps -o pumps.ttl
else
    echo Skipping preparation of core, device, machinery, pumps nodesets due to DEBUG mode
fi

echo Starting Feature Tests
echo --------------------------------
echo --------------------------------
startstop_context_server "Stopping context server" false
for tuple in "${TESTNODESETS[@]}"; do IFS=","
    set -- $tuple;
    nodeset=$1
    instancetype=$2
    instancenamespace=$3
    imports=$4
    options=$5
    warning=$6
    testuri=$7
    testid=$8

    if [ -n "$testid" ]; then
        echo "Test ID defined: '$testid'"
        TESTID=(-i "$testid")
    else
        TESTID=() # Default: entity ids urn:uaentity:<base64url of the canonical ExpandedNodeId>
    fi
    if [ -n "$options" ]; then
    IFS=';' read -r -a OPTIONS_ARR <<< "$options"
    else
    OPTIONS_ARR=()
    fi

    if [ -n "$testuri" ]; then
        echo "Test URI defined: '$testuri'"
        THETESTURI="$testuri"
    else
        THETESTURI=${TESTURI} # Default
    fi
    if [ "$DEBUG" = "true" ]; then
        echo "Found parameters: nodeset=$nodeset, instancetype=$instancetype, instancenamespace=$instancenamespace, imports=$imports, options=${OPTIONS_ARR[@]}, warning=$warning, testid=$testid, testuri=$testuri "
    fi
    if [ -n "$instancenamespace" ]; then
        echo "Insancenamespace defined: '$instancenamespace'"
        INSTANCENAMESPACE=("-n" "$instancenamespace")
    else
        INSTANCENAMESPACE=()
    fi
    if [ "$imports" = "pumps" ]; then
        IMPORTS=("${BASE_ONTOLOGY}" "${CORE_ONTOLOGY}" "${DEVICES_ONTOLOGY}" "${MACHINERY_ONTOLOGY}" "${PUMPS_ONTOLOGY}")
    elif [ "$imports" = "machinery" ]; then
        IMPORTS=("${BASE_ONTOLOGY}" "${CORE_ONTOLOGY}" "${DEVICES_ONTOLOGY}" "${MACHINERY_ONTOLOGY}")
    else
        IMPORTS=("${BASE_ONTOLOGY}" "${CORE_ONTOLOGY}")
    fi
    if [ ! -z "$instancetype" ]; then
        echo "==> test $nodeset with instancetype $instancetype"
        echo --------------------------------------------------
        INSTANCETYPEOPTION="-t ${instancetype}"
    else
        echo "==> test $nodeset without instancetype"
        echo ----------------------------------------
    fi
    if [ "$DEBUG" = "true" ]; then
        echo DEBUG: python3 ${NODESET2OWL} ${nodeset}.xml -i ${IMPORTS[@]} ${INSTANCENAMESPACE[@]} -v http://example.com/v0.1/UA/ -p test --serverUri ${SERVER_URI} -o ${NODESET2OWL_RESULT}
        echo DEBUG: python3 ${OWL2INSTANCES} ${INSTANCETYPEOPTION} -n ${THETESTURI} ${NODESET2OWL_RESULT} ${TESTID[@]} -xc ${LOCAL_CONTEXT} ${OPTIONS_ARR[@]}
    fi
    echo Create owl nodesets
    echo -------------------
    python3 ${NODESET2OWL} ${nodeset}.xml -i ${IMPORTS[@]} ${INSTANCENAMESPACE[@]} -v http://example.com/v0.1/UA/ -p test --serverUri ${SERVER_URI} -o ${NODESET2OWL_RESULT} || exit 1
    startstop_context_server "Starting context server" true
    echo Extract types and instances
    echo ---------------------------
    rm -f "min_${SHACL}"
    if [ -z "$instancetype" ]; then
        python3 ${OWL2INSTANCES}  -n ${TESTURI} ${NODESET2OWL_RESULT} ${TESTID[@]} -xc ${LOCAL_CONTEXT} ${OPTIONS_ARR[@]} 2>&1 | tee output.log
    else
        python3 ${OWL2INSTANCES} -t ${instancetype} -n ${THETESTURI} ${NODESET2OWL_RESULT} ${TESTID[@]} -xc ${LOCAL_CONTEXT} ${OPTIONS_ARR[@]} 2>&1 | tee output.log
    fi
    if [ ! -z "$warning" ]; then
        if ! grep -q $warning output.log; then
            echo "No WARNING $warning found in the output. Exiting with error."
            exit 1
        else
            echo "Success: Warning including $warning found!"
        fi
    fi
    mydiff "Compare SHACL" "${SHACL}" "${nodeset}.shacl" "ttl"
    # The minimal SHACL is gone (#990): no min_shacl.ttl next to shacl.ttl
    if [ -e "min_${SHACL}" ]; then
        echo "min_${SHACL} was written. Exiting with error."
        exit 1
    fi
    mydiff "Compare instances" "${nodeset}.instances" "${INSTANCES}" "json-ld"
    checkqueries "Check basic entities structure" ${nodeset}
    checkshaclqueries "Check shapes" ${nodeset}
    check_coverage_warning "${nodeset}" "${warning}"
    ask "Check that the entities import the uardf ontology" ${ENTITIES_FILE} entities_import_uardf.query
    echo SHACL test
    echo ----------
    if [ -f ${nodeset}.pyshacl ]; then
        echo "Testing custom shacl result"
        pyshacl -s ${SHACL} -df json-ld -e ${ENTITIES_FILE} ${INSTANCES} -f turtle -o ${PYSHACL_RESULT} || true
        echo "expected <=> result"
        mydiff "Compare CUSTOM SHACL RESULTS" ${nodeset}.pyshacl ${PYSHACL_RESULT} "ttl"
        echo OK
    else
        echo executing pyshacl -s ${SHACL} -df json-ld -e ${ENTITIES_FILE} ${INSTANCES}
        pyshacl -s ${SHACL} -df json-ld -e ${ENTITIES_FILE} ${INSTANCES} || exit 1
    fi
    if [ -f ${nodeset}.context ]; then
        echo "Comparing context files"
        diff "${nodeset}.context" "${CONTEXT_FILE}" || exit 1
    else
        echo "No context file to compare"
    fi
    startstop_context_server "Stopping context server" false
    echo "Test finished successfully"
done

echo "==> --minimalshacl is no longer an option (#990)"
echo ----------------------------------------------------
if MINIMAL_OUT=$(python3 ${OWL2INSTANCES} --minimalshacl -n ${TESTURI} ${NODESET2OWL_RESULT} 2>&1); then
    echo "--minimalshacl was accepted. Exiting with error."
    exit 1
fi
if ! echo "${MINIMAL_OUT}" | grep -q "unrecognized arguments: --minimalshacl"; then
    echo "owl2instances failed, but not because --minimalshacl is unknown:"
    echo "${MINIMAL_OUT}" | tail -5
    exit 1
fi
echo "Success: --minimalshacl is rejected"

echo "==> test the node reference attribute is declared once and not reported"
echo ----------------------------------------------------------------------
python3 ${NODESET2OWL} test_instance_types.NodeSet2.xml -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p test --serverUri ${SERVER_URI} -o ${NODESET2OWL_RESULT} || exit 1
startstop_context_server "Starting context server" true
python3 ${OWL2INSTANCES} -nr -t ${TESTURI}AlphaType -n ${TESTURI} ${NODESET2OWL_RESULT} -xc ${LOCAL_CONTEXT} 2>&1 | tee output.log
OWL2INSTANCES_STATUS=${PIPESTATUS[0]}
startstop_context_server "Stopping context server" false
# The case has an uncovered reference: one warning, and the exit status is unchanged by it
if [ "$OWL2INSTANCES_STATUS" != "0" ] || [ "$(grep -c 'UNCOVERED_INSTANCE_TERMS' output.log)" != "1" ]; then
    echo "Expected exit status 0 and one UNCOVERED_INSTANCE_TERMS warning. Exiting with error."
    exit 1
fi
if ! grep -q 'hasNodeRef' ${INSTANCES}; then
    echo "The entities carry no node reference. Exiting with error."
    exit 1
fi
ask "Check that the node reference is declared once, for BaseObjectType" ${ENTITIES_FILE} entities_node_reference.query
if grep UNCOVERED_INSTANCE_TERMS output.log | grep -q 'hasNodeRef'; then
    echo "UNCOVERED_INSTANCE_TERMS names the node reference. Exiting with error."
    exit 1
fi
echo "Success: the node reference is declared once and not reported"
echo "==> test a type model without instances still gets its shapes"
echo --------------------------------------------------------------
# Without --serverUri nodeset2owl exports no (dynamic) instance nodes
python3 ${NODESET2OWL} test_instance_types.NodeSet2.xml -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p test -o ${NODESET2OWL_RESULT} || exit 1
startstop_context_server "Starting context server" true
for mode in "" "-so"; do
    rm -f ${SHACL}
    STATUS=0
    python3 ${OWL2INSTANCES} ${mode:+"$mode"} -t ${TESTURI}AlphaType -n ${TESTURI} ${NODESET2OWL_RESULT} -xc ${LOCAL_CONTEXT} > output.log 2>&1 || STATUS=$?
    EXPECTED_STATUS=1
    if [ -n "$mode" ]; then
        EXPECTED_STATUS=0
    fi
    if [ "$STATUS" != "$EXPECTED_STATUS" ] || ! grep -q 'sh:targetClass test:UnitType' ${SHACL}; then
        echo "Mode '$mode': exit status $STATUS (expected $EXPECTED_STATUS) or no shapes in ${SHACL}. Exiting with error."
        tail -3 output.log
        exit 1
    fi
done
startstop_context_server "Stopping context server" false
echo "Success: the shapes are written without instances"
echo "==> test the shape of a type does not depend on the path to it"
echo ----------------------------------------------------------------
# BetaType is reached through a folder's declaration in test_declaration_types.NodeSet2 (shapes compared above);
# with BetaType as root type, its node shape must be the same.
python3 ${NODESET2OWL} test_declaration_types.NodeSet2.xml -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p test --serverUri ${SERVER_URI} -o ${NODESET2OWL_RESULT} || exit 1
startstop_context_server "Starting context server" true
python3 ${OWL2INSTANCES} -so -t ${TESTURI}BetaType -n ${TESTURI} ${NODESET2OWL_RESULT} -xc ${LOCAL_CONTEXT} -s beta_root_shacl.ttl || exit 1
startstop_context_server "Stopping context server" false
python3 compare_type_shape.py beta_root_shacl.ttl test_declaration_types.NodeSet2.shacl ${TESTURI}BetaType || exit 1
echo "Test finished successfully"
