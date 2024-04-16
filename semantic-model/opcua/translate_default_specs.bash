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

NODESET_VERSION=UA-1.05.03-2023-12-15
CORE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Schema/Opc.Ua.NodeSet2.xml
CORE_SERVICES_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Schema/Opc.Ua.NodeSet2.Services.xml
DI_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/DI/Opc.Ua.Di.NodeSet2.xml
PADIM_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/PADIM/Opc.Ua.PADIM.NodeSet2.xml
DICTIONARY_IRDI=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/PADIM/Opc.Ua.IRDI.NodeSet2.xml
IA_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/IA/Opc.Ua.IA.NodeSet2.xml
MACHINERY_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Machinery/Opc.Ua.Machinery.NodeSet2.xml
MACHINERY_PROCESSVALUES_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Machinery/ProcessValues/opc.ua.machinery.processvalues.xml
MACHINERY_JOBS_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/ISA95-JOBCONTROL/opc.ua.isa95-jobcontrol.nodeset2.xml
LASERSYSTEMS_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/LaserSystems/Opc.Ua.LaserSystems.NodeSet2.xml
MACHINERY_EXAMPLE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Machinery/Opc.Ua.Machinery.Examples.NodeSet2.xml
MACHINETOOL_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/MachineTool/Opc.Ua.MachineTool.NodeSet2.xml
PUMPS_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Pumps/Opc.Ua.Pumps.NodeSet2.xml
PUMP_EXAMPLE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/Pumps/instanceexample.xml
MACHINETOOL_EXAMPLE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/MachineTool/Machinetool-Example.xml
LASERSYSTEMS_EXAMPLE_NODESET=https://raw.githubusercontent.com/OPCFoundation/UA-Nodeset/${NODESET_VERSION}/LaserSystems/LaserSystem-Example.NodeSet2.xml
BASE_ONTOLOGY=https://industryfusion.github.io/contexts/staging/ontology/v0.1/base.ttl
if [ "$1" = "remote" ]; then
    OPCUA_PREFIX=https://industryfusion.github.io/contexts/staging/opcua/v0.1/
    echo "Remote mode selected"
fi
CORE_ONTOLOGY=${OPCUA_PREFIX}core.ttl
DEVICES_ONTOLOGY=${OPCUA_PREFIX}devices.ttl
MACHINERY_ONTOLOGY=${OPCUA_PREFIX}machinery.ttl
PUMPS_ONTOLOGY=${OPCUA_PREFIX}pumps.ttl
IA_ONTOLOGY=${OPCUA_PREFIX}ia.ttl
MACHINETOOL_ONTOLOGY=${OPCUA_PREFIX}machinetool.ttl
LASERSYSTEMS_ONTOLOGY=${OPCUA_PREFIX}lasersystems.ttl
DICTIONARY_IRDI_ONTOLOGY=${OPCUA_PREFIX}dictionary_irdi.ttl
PADIM_ONTOLOGY=${OPCUA_PREFIX}padim.ttl

echo create core.ttl
python3 nodeset2owl.py ${CORE_NODESET} -i ${BASE_ONTOLOGY} -v http://example.com/v0.1/UA/ -p opcua -o core.ttl
echo create devices.ttl
python3 nodeset2owl.py  ${DI_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} -v http://example.com/v0.1/DI/ -p devices -o devices.ttl
echo create ia.ttl \(industrial automation\)
python3 nodeset2owl.py  ${IA_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} -v http://example.com/v0.1/IA/ -p ia -o ia.ttl
echo create machinery.ttl
python3 nodeset2owl.py ${MACHINERY_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} -v http://example.com/v0.1/Machinery/ -p machinery -o machinery.ttl
echo create pumps.ttl
python3 nodeset2owl.py  ${PUMPS_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} ${MACHINERY_ONTOLOGY} -v http://example.com/v0.1/Pumps/ -p pumps -o pumps.ttl
echo create pumpexample.ttl
python3 nodeset2owl.py  ${PUMP_EXAMPLE_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} ${MACHINERY_ONTOLOGY} ${PUMPS_ONTOLOGY} -n http://yourorganisation.org/InstanceExample/ -v http://example.com/v0.1/pumpexample/ -p pumpexample -o pumpexample.ttl
echo create machinetool.ttl
python3 nodeset2owl.py  ${MACHINETOOL_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} ${MACHINERY_ONTOLOGY} ${IA_ONTOLOGY} -v http://example.com/v0.1/MachineTool/ -p machinetool -o machinetool.ttl
echo create lasersystems.ttl
python3 nodeset2owl.py  ${LASERSYSTEMS_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} ${MACHINERY_ONTOLOGY} ${IA_ONTOLOGY} ${MACHINETOOL_ONTOLOGY} -v http://example.com/v0.1/LaserSystems/ -p lasersystems -o lasersystems.ttl
echo create lasersystemsexample.ttl
python3 nodeset2owl.py  ${LASERSYSTEMS_EXAMPLE_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} ${MACHINERY_ONTOLOGY} ${IA_ONTOLOGY} ${MACHINETOOL_ONTOLOGY} ${LASERSYSTEMS_ONTOLOGY} -v http://example.com/v0.1/LaserSystems/ -p lasersystemsexample -o lasersystemsexample.ttl
echo create machinetoolexample.ttl
python3 nodeset2owl.py  ${MACHINETOOL_EXAMPLE_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} ${MACHINERY_ONTOLOGY} ${MACHINETOOL_ONTOLOGY} ${IA_ONTOLOGY} -n http://yourorganisation.org/MachineTool-Example/ -v http://example.com/MachineToolExample/v0.1/pumpexample/ -p machinetoolexample -o machinetoolexample.ttl
echo create machineryexample.ttl
python3 nodeset2owl.py  ${MACHINERY_EXAMPLE_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DEVICES_ONTOLOGY} ${MACHINERY_ONTOLOGY} -v http://example.com/MachineryExample/v0.1/pumpexample/ -p machineryexample -o machineryexample.ttl
echo create dictionary_irdi.ttl
python3 nodeset2owl.py  ${DICTIONARY_IRDI} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} -v http://example.com/v0.1/Dictionary/IRDI -p dictionary_irdi -o dictionary_irdi.ttl
echo create padim.ttl
python3 nodeset2owl.py  ${PADIM_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${DICTIONARY_IRDI_ONTOLOGY} ${DEVICES_ONTOLOGY} -v http://example.com/v0.1/PADIM -p padim -o padim.ttl
echo create machinery_processvalues.ttl
python3 nodeset2owl.py  ${MACHINERY_PROCESSVALUES_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY} ${PADIM_ONTOLOGY} -v http://example.com/v0.1/Machinery/ProcessValues -p machinery_processvalues -o machinery_processvalues.ttl
echo create machinery_jobs.ttl
python3 nodeset2owl.py  ${MACHINERY_JOBS_NODESET} -i ${BASE_ONTOLOGY} ${CORE_ONTOLOGY}  -v http://example.com/v0.1/Machinery/Jobs -p machinery_jobs -o machinery_jobs.ttl