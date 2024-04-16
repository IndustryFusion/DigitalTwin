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
DEBUG=${DEBUG:-false}
if [ "$DEBUG" = "true" ]; then
    DEBUG_CMDLINE="-m debugpy --listen 5678"
fi
TESTNODESETS=(
    test_object_wrong.NodeSet2,${TESTURI}AlphaType
    test_object_overwrite_type.NodeSet2,${TESTURI}AlphaType
    test_variable_enum.NodeSet2,${TESTURI}AlphaType
    test_object_subtypes.NodeSet2,${TESTURI}AlphaType
    test_object_hierarchies_no_DataValue,${TESTURI}AlphaType
    test_ignore_references.NodeSet2,${TESTURI}AlphaType
    test_references_to_typedefinitions.NodeSet2,${TESTURI}AlphaType
    test_minimal_object.NodeSet2,http://example.org/MinimalNodeset/ObjectType 
    test_object_types.NodeSet2,${TESTURI}AlphaType
    test_pumps_instanceexample,http://opcfoundation.org/UA/Pumps/PumpType,http://yourorganisation.org/InstanceExample/,pumps
    )
#TESTNODESETS=(test_object_types.NodeSet2,http://my.demo/AlphaType )
CLEANGRAPH=cleangraph.py
TYPEURI=http://example.org/MinimalNodeset
TESTURN=urn:test
SHACL=shacl.ttl
ENTITIES_FILE=entities.ttl
INSTANCES=instances.jsonld
SPARQLQUERY=query.py
SERVE_CONTEXT=serve_context.py
SERVE_CONTEXT_PORT=8099
CONTEXT_FILE=context.jsonld
LOCAL_CONTEXT=http://localhost:${SERVE_CONTEXT_PORT}/${CONTEXT_FILE}
PYSHACL_RESULT=pyshacl.ttl
EXTRACTTYPE="../../extractType.py"
COMPARE_GRAPHS="./compare_graphs.py"


function mydiff() {
    format="$4"
    echo "$1"
    result="$2"
    expected="$3"
    echo "expected <=> result"
    python3 ${COMPARE_GRAPHS} -f ${format} ${expected} ${result} || exit 1
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
        (python3 ${SERVE_CONTEXT} -p ${SERVE_CONTEXT_PORT} ${CONTEXT_FILE} &) 
    else
        pkill -f ${SERVE_CONTEXT}
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
        return 1
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
    if [ -n "$instancenamespace" ]; then
        echo "Insancenamespace defined: '$instancenamespace'"
        INSTANCENAMESPACE=("-n" "$instancenamespace")
    else
        INSTANCENAMESPACE=()
    fi
    if [ "$imports" = "pumps" ]; then
        IMPORTS=("${BASE_ONTOLOGY}" "${CORE_ONTOLOGY}" "${DEVICES_ONTOLOGY}" "${MACHINERY_ONTOLOGY}" "${PUMPS_ONTOLOGY}")
    else
        IMPORTS=("${BASE_ONTOLOGY}" "${CORE_ONTOLOGY}")
    fi
    echo "==> test $nodeset with instancetype $instancetype"
    echo --------------------------------------------------
    if [ "$DEBUG" = "true" ]; then
        echo DEBUG: python3 ${NODESET2OWL} ${nodeset}.xml -i ${IMPORTS[@]} ${INSTANCENAMESPACE[@]} -v http://example.com/v0.1/UA/ -p test -o ${NODESET2OWL_RESULT}
        echo DEBUG: python3 ${EXTRACTTYPE} -t ${instancetype} -n ${TESTURI} ${NODESET2OWL_RESULT} -i ${TESTURN} -xc ${LOCAL_CONTEXT}
    fi
    echo Create owl nodesets
    echo -------------------
    python3 ${NODESET2OWL} ${nodeset}.xml -i ${IMPORTS[@]} ${INSTANCENAMESPACE[@]} -v http://example.com/v0.1/UA/ -p test -o ${NODESET2OWL_RESULT} || exit 1
    echo Extract types and instances
    echo ---------------------------
    python3 ${EXTRACTTYPE} -t ${instancetype} -n ${TESTURI} ${NODESET2OWL_RESULT} -i ${TESTURN} -xc ${LOCAL_CONTEXT} || exit 1
    startstop_context_server "Starting context server" true 
    #ask "Compare SHACL" ${SHACL} ${nodeset}.shacl
    mydiff "Compare SHACL" "${nodeset}.shacl" "${SHACL}" "ttl"
    mydiff "Compare instances" "${nodeset}.instances" "${INSTANCES}" "json-ld"
    #ask "Compare INSTANCE" ${INSTANCES} ${nodeset}.instances json-ld
    checkqueries "Check basic entities structure" ${nodeset}
    echo SHACL test
    echo ----------
    if [ -f ${nodeset}.pyshacl ]; then
        echo "Testing custom shacl result"
        pyshacl -s ${SHACL} -df json-ld -e ${ENTITIES_FILE} ${INSTANCES} -f turtle -o ${PYSHACL_RESULT}
        echo "expected <=> result"
        mydiff "Compare CUSTOM SHACL RESULTS" ${nodeset}.pyshacl ${PYSHACL_RESULT} "ttl"
        echo OK
    else
        echo executing pyshacl -s ${SHACL} -df json-ld -e ${ENTITIES_FILE} ${INSTANCES}
        pyshacl -s ${SHACL} -df json-ld -e ${ENTITIES_FILE} ${INSTANCES} || exit 1
    fi
    startstop_context_server "Stopping context server" false
    echo "Test finished successfully"
done
