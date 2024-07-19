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

import os
import asyncio
import importlib
from rdflib import Literal

asyncua_client = None

try:
    asyncua = importlib.import_module('asyncua')
    asyncua_client = asyncua.Client
except ImportError:
    asyncua_client = None
    print("The 'asyncua' library is not installed. Please install it separately to use this functionality.")


url = os.environ.get('OPCUA_TCP_CONNECT') or "opc.tcp://localhost:4840/"


async def update_namespace_parameter(client, connector_attribute_dict):
    nodeid = connector_attribute_dict['connectorAttribute']
    if 'nsu=' not in nodeid:
        return nodeid
    try:
        ns_part, i_part = nodeid.split(';')
    except:
        ns_part = None
        i_part = nodeid
    if ns_part is not None:
        namespace = ns_part.split('=')[1]
    nsidx = await client.get_namespace_index(namespace)
    nodeid = f'ns={nsidx};{i_part}'
    return nodeid


##########################################################################################
# This function will receive an array of dictionaries containing the needed parameters
# to read out data from machines or databases.
# It will update the values in regular intervals
##########################################################################################
async def subscribe(connector_attribute_dict, firmware, sleeptime=5):
    if asyncua_client is None:
        raise ImportError("The 'asyncua' library is required for this function. Please install it separately.")
    async with asyncua_client(url=url) as client:
        # first resolve explicit namespace when given
        connector_attribute_dict['connectorAttribute'] = \
            await update_namespace_parameter(client, connector_attribute_dict)
        while True:
            nodeset = connector_attribute_dict['connectorAttribute']
            var = client.get_node(nodeset)
            value = await var.get_value()
            print(f'In OPCUA Connector with parameters {nodeset} and value {value}')
            connector_attribute_dict['value'] = Literal(value)
            connector_attribute_dict['updated'] = True
            await asyncio.sleep(sleeptime)
