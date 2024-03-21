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

import asyncio
import random
from random import randint
from rdflib import Literal
from rdflib.namespace import XSD


##########################################################################################
# This function will receive an array of dictionaries containing the needed parameters
# to read out data from machines or databases.
# It will update the values in regular intervals
##########################################################################################
async def subscribe(connector_attribute_dict, firmware):
    while True:
        logic_var_type = connector_attribute_dict['logicVarType']
        if logic_var_type == XSD.boolean:
            connector_attribute_dict['value'] = Literal(random.choice([True, False]))
        elif logic_var_type == XSD.integer:
            connector_attribute_dict['value'] = Literal(randint(0, 1000))
        elif logic_var_type == XSD.decimal or logic_var_type == XSD.float or logic_var_type == XSD.double:
            connector_attribute_dict['value'] = Literal(float(randint(0, 100000)) / 100.0)
        connector_attribute_dict['firmware'] = firmware

        await asyncio.sleep(1)
