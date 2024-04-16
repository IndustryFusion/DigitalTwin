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


def split_params(param):
    try:
        # Split the input string by comma
        parts = param.split(',')
        # Strip any leading/trailing whitespace from the parts
        upper = int(parts[1].strip())
        lower = int(parts[0].strip())
    except IndexError:
        raise ValueError("TestConnector Parameter must be in the format 'lower(int), upper(int)'")
    return lower, upper


##########################################################################################
# This function will receive an array of dictionaries containing the needed parameters
# to read out data from machines or databases.
# It will update the values in regular intervals
##########################################################################################
async def subscribe(map, firmware):
    while True:
        logic_var_type = map['logicVarType']
        try:
            connector_attr = map['connectorAttribute']
        except:
            pass
        if logic_var_type == XSD.boolean:
            map['value'] = Literal(random.choice([True, False]))
        elif logic_var_type == XSD.integer:
            lower, upper = split_params(connector_attr)
            map['value'] = Literal(randint(lower, upper))
        elif logic_var_type == XSD.decimal or logic_var_type == XSD.float or logic_var_type == XSD.double:
            lower, upper = split_params(connector_attr)
            map['value'] = Literal(float(randint(lower, upper)) / 100.0)
        map['updated'] = True
        map['firmware'] = firmware

        await asyncio.sleep(1)
