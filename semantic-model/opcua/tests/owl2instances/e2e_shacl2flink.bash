#
# Copyright (c) 2026 IndustryFusion Foundation
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
# End-to-end test of opcua/instance-coverage: from a nodeset through owl2instances.py and a KMS package to the
# alerts shacl2flink raises on SQLite.
#
# - test_declaration_types.NodeSet2 has a child "State" of BetaType which only a folder's declaration adds; its
#   instance lacks the mandatory variable "Level".
# - test_instance_types.NodeSet2 has a child whose instance uses a subtype that adds the mandatory variable "Extra",
#   an object of ZetaType that only an Organizes reference of the instance reaches and an object of EtaType that only
#   a variable's non-hierarchical reference reaches; all lack their mandatory variable. The alerts can only be raised
#   if UnitSubType, ZetaType and EtaType have their own shapes. Two more children use subtypes whose members give no
#   rule and lack a variable of their supertype: its shape raises the alerts for them.
# Expects core.ttl from test.bash in this directory, sqlite3 with the pcre2 extension, and shacl2flink's
# requirements installed. shacl2flink pins other rdflib versions than the opcua tools; SHACL2FLINK_PYTHON names the
# Python that has them (default python3), as the Build workflow sets it.
set -e
export LANG=en_EN.UTF-8
TESTURI=http://my.test/
SERVER_URI=urn:test:server
BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl
CORE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/Schema/Opc.Ua.NodeSet2.xml
OPCUADIR=$(cd ../..; echo $PWD)
TOOLDIR=$(cd ../../../shacl2flink; echo $PWD)
WORKDIR=$PWD/e2e-output
S2F_PYTHON=${SHACL2FLINK_PYTHON:-python3}
PACKAGE=$WORKDIR/package
# Entities are urn:uaentity:<base64url of svu=urn:test:server;nsu=http://my.test/;i=<n>>
ENTITY_2002=urn:uaentity:c3Z1PXVybjp0ZXN0OnNlcnZlcjtuc3U9aHR0cDovL215LnRlc3QvO2k9MjAwMg
ENTITY_2003=urn:uaentity:c3Z1PXVybjp0ZXN0OnNlcnZlcjtuc3U9aHR0cDovL215LnRlc3QvO2k9MjAwMw
ENTITY_2006=urn:uaentity:c3Z1PXVybjp0ZXN0OnNlcnZlcjtuc3U9aHR0cDovL215LnRlc3QvO2k9MjAwNg
ENTITY_2007=urn:uaentity:c3Z1PXVybjp0ZXN0OnNlcnZlcjtuc3U9aHR0cDovL215LnRlc3QvO2k9MjAwNw
ENTITY_2009=urn:uaentity:c3Z1PXVybjp0ZXN0OnNlcnZlcjtuc3U9aHR0cDovL215LnRlc3QvO2k9MjAwOQ

if [ ! -f core.ttl ]; then
    python3 ${OPCUADIR}/nodeset2owl.py ${CORE_NODESET} -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p opcua \
        -o core.ttl
fi

# run_case <nodeset> <description> <expected alert>...
run_case() {
    local nodeset=$1
    local description=$2
    shift 2
    rm -rf "$WORKDIR"
    mkdir -p "$WORKDIR"
    echo "==> e2e: ${nodeset} through a KMS package to shacl2flink"
    python3 ${OPCUADIR}/nodeset2owl.py ${nodeset}.xml -i ${BASE_ONTOLOGY} core.ttl -v http://example.com/v0.1/UA/ \
        -p test --serverUri ${SERVER_URI} -o ${WORKDIR}/instance.ttl
    (cd "$WORKDIR" && python3 ${OPCUADIR}/owl2instances.py -t ${TESTURI}AlphaType -n ${TESTURI} instance.ttl)
    (cd "$WORKDIR" && python3 ${OPCUADIR}/owl2kms.py entities.ttl -s shacl.ttl -m instances.jsonld -c context.jsonld \
        -n e2e-instance-coverage -v 0.1.0 -o ${PACKAGE})

    echo "==> e2e: SQLite checks of shacl2flink"
    (
        cd "$WORKDIR"
        if [ -f ${PACKAGE}/knowledge.ttl ]; then
            cp ${PACKAGE}/knowledge.ttl knowledge.ttl
        else
            rdfpipe -i ttl -o ttl ${PACKAGE}/knowledge/*.ttl > knowledge.ttl
        fi
        if [ -f ${PACKAGE}/shacl.ttl ]; then
            cp ${PACKAGE}/shacl.ttl shacl.ttl
        else
            rdfpipe -i ttl -o ttl ${PACKAGE}/shacl/*.ttl > shacl.ttl
        fi
        MODEL=$(ls ${PACKAGE}/model*.jsonld ${PACKAGE}/model/*.jsonld 2>/dev/null | head -1)
        CONTEXT=$(ls ${PACKAGE}/context.jsonld ${PACKAGE}/*context*.jsonld 2>/dev/null | head -1)
        mkdir -p output
        ${S2F_PYTHON} ${TOOLDIR}/create_rdf_table.py knowledge.ttl
        ${S2F_PYTHON} ${TOOLDIR}/create_core_tables.py
        ${S2F_PYTHON} ${TOOLDIR}/create_sql_checks_from_shacl.py -c ${CONTEXT} shacl.ttl knowledge.ttl
        ${S2F_PYTHON} ${TOOLDIR}/create_ngsild_models.py shacl.ttl knowledge.ttl ${MODEL}
        ${S2F_PYTHON} ${TOOLDIR}/create_ngsild_tables.py
        DATABASE=output/database.db
        for part in rdf core ngsild ngsild-models shacl-validation; do
            sqlite3 ${DATABASE} < output/${part}.sqlite
        done
        echo "select resource, event from alerts_bulk_view;" | sqlite3 -quote -noheader ${DATABASE} | sort > alerts.txt
        cat alerts.txt
        for expected in "$@"; do
            if ! grep -qxF "${expected}" alerts.txt; then
                echo "Missing alert ${expected}"
                exit 1
            fi
        done
    )
    echo "e2e: ${description}"
    rm -rf "$WORKDIR"
}

run_case test_declaration_types.NodeSet2 "the missing mandatory variable of the declared child is alerted" \
    "'${ENTITY_2003}','CountConstraintComponent(${TESTURI}hasLevel)'"
run_case test_instance_types.NodeSet2 \
    "the missing mandatory variables of the instance's subtypes and of the objects only references reach are alerted" \
    "'${ENTITY_2002}','CountConstraintComponent(${TESTURI}hasExtra)'" \
    "'${ENTITY_2003}','CountConstraintComponent(${TESTURI}hasLevel)'" \
    "'${ENTITY_2006}','CountConstraintComponent(${TESTURI}hasRate)'" \
    "'${ENTITY_2007}','CountConstraintComponent(${TESTURI}hasCount)'" \
    "'${ENTITY_2009}','CountConstraintComponent(${TESTURI}hasAmount)'"
