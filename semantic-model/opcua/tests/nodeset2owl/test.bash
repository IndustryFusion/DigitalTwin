#
# Copyright (c) 2024 Intel Corporation
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

export CORE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/Schema/Opc.Ua.NodeSet2.xml
export CORE_SERVICES_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/Schema/Opc.Ua.NodeSet2.Services.xml
export DI_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/DI/Opc.Ua.Di.NodeSet2.xml
export PADIM_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/PADIM/Opc.Ua.PADIM.NodeSet2.xml
export DICTIONARY_IRDI=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/PADIM/Opc.Ua.IRDI.NodeSet2.xml
export IA_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/IA/Opc.Ua.IA.NodeSet2.xml
export MACHINERY_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/Machinery/Opc.Ua.Machinery.NodeSet2.xml
export MACHINERY_PROCESSVALUES_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/Machinery/ProcessValues/opc.ua.machinery.processvalues.xml
export MACHINERY_JOBS_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/ISA95-JOBCONTROL/opc.ua.isa95-jobcontrol.nodeset2.xml
export LASERSYSTEMS_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/LaserSystems/Opc.Ua.LaserSystems.NodeSet2.xml
export MACHINERY_EXAMPLE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/Machinery/Opc.Ua.Machinery.Examples.NodeSet2.xml
export MACHINETOOL_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/MachineTool/Opc.Ua.MachineTool.NodeSet2.xml
export PUMPS_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/Pumps/Opc.Ua.Pumps.NodeSet2.xml
export PUMP_EXAMPLE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/Pumps/instanceexample.xml
export MACHINETOOL_EXAMPLE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/MachineTool/Machinetool-Example.xml
export LASERSYSTEMS_EXAMPLE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/LaserSystems/LaserSystem-Example.NodeSet2.xml
export BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl
export PACKML_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/UA-1.05.03-2023-12-15/PackML/Opc.Ua.PackML.NodeSet2.xml


function mydiff() {
    result="$1"
    expected="$2"
    echo "Compare expected <=> result" 
    diff $result $expected || exit 1

}
RESULT=result.ttl
CLEANED=cleaned.ttl
# DEBUG=false
# if [ "$DEBUG"="true" ]; then
#     DEBUG_CMDLINE="-m debugpy --listen 5678"
# fi
TESTNODESETS=(test_object_types.NodeSet2 test_objects.NodeSet2 test_reference_reused.NodeSet2 test_references_special.NodeSet2)
CLEANGRAPH=cleangraph.py
NODESET2OWL=../../nodeset2owl.py
echo Starting Feature Tests
echo -------------------------------- 
for nodeset in "${TESTNODESETS[@]}"; do
    echo test $nodeset
    if [ "$DEBUG"="true" ]; then
        echo DEBUG: python3 -m debugpy --listen 5678 --wait-for-client ${NODESET2OWL} ${nodeset}.xml -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p test -o ${RESULT}
    fi
    python3 ${NODESET2OWL} ${nodeset}.xml -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p test -o ${RESULT}
    echo "Comparing expected <=> result"
    diff ${nodeset}.ttl ${RESULT} || exit 1
done
echo Starting E2E specification tests
echo -------------------------------- 
comparewith=core_cleaned.ttl
echo Test ${CORE_NODESET}
echo --------------------
python3 ${NODESET2OWL} ${CORE_NODESET} -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p opcua -o ${RESULT}
python3 $CLEANGRAPH $RESULT $CLEANED 
mydiff $comparewith $CLEANED
nodeset=$DI_NODESET
comparewith=devices_cleaned.ttl
echo Test $DI_NODESET
echo --------------------
echo Prepare core.ttl
python3 ${NODESET2OWL} ${CORE_NODESET} -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p opcua -o core.ttl
echo test devices
python3 ${NODESET2OWL}  ${DI_NODESET} -i ${BASE_ONTOLOGY} core.ttl -v http://example.com/v0.1/DI/ -p devices -o ${RESULT}
python3 $CLEANGRAPH $RESULT $CLEANED 
mydiff $comparewith $CLEANED
rm -f core.ttl
comparewith=machinery_cleaned.ttl
echo Test $MACHINERY_NODESET
echo -----------------------
echo Prepare core.ttl
python3 ${NODESET2OWL} ${CORE_NODESET} -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p opcua -o core.ttl
echo Prepare devices.ttl
python3 ${NODESET2OWL}  ${DI_NODESET} -i ${BASE_ONTOLOGY} core.ttl -v http://example.com/v0.1/DI/ -p devices -o devices.ttl
echo test machinery
echo --------------
python3 ${NODESET2OWL} ${MACHINERY_NODESET} -i ${BASE_ONTOLOGY} core.ttl devices.ttl -v http://example.com/v0.1/Machinery/ -p machinery -o ${RESULT}
python3 $CLEANGRAPH $RESULT $CLEANED 
mydiff $comparewith $CLEANED
rm -f core.ttl device.ttl
comparewith=pumps_cleaned.ttl
echo Test $PUMPS_NODESET
echo -------------------
echo Prepare core.ttl
python3 ${NODESET2OWL} ${CORE_NODESET} -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p opcua -o core.ttl
echo Prepare devices.ttl
python3 ${NODESET2OWL}  ${DI_NODESET} -i ${BASE_ONTOLOGY} core.ttl -v http://example.com/v0.1/DI/ -p devices -o devices.ttl
echo Prepare machinery
python3 ${NODESET2OWL} ${MACHINERY_NODESET} -i ${BASE_ONTOLOGY} core.ttl devices.ttl -v http://example.com/v0.1/Machinery/ -p machinery -o machinery.ttl
echo Test pumps
echo ----------
python3 ${NODESET2OWL}  ${PUMPS_NODESET} -i ${BASE_ONTOLOGY} core.ttl devices.ttl machinery.ttl -v http://example.com/v0.1/Pumps/ -p pumps -o ${RESULT}
python3 $CLEANGRAPH $RESULT $CLEANED
mydiff $CLEANED $comparewith
rm -f core.ttl device.ttl machinery.ttl

if [ "$DEBUG" != "true" ]; then
    rm -f ${CLEANED} ${RESULT}
fi