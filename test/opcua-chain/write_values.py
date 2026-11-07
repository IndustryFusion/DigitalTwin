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

"""Writes through a plain OPC UA client, like a machine changing its values. Usage: write_values.py all|after"""
import asyncio
import datetime
import sys
from asyncua import Client, ua

V = ua.VariantType
SETS = {
    'all': [
        ('i=6020', 71.25, V.Double),  # hasMotorTemperature
        ('i=6119', 17, V.UInt32),  # hasNumberOfStarts
        ('i=6029', True, V.Boolean),  # hasRotorBlocked
        ('i=6023', 'with "quotes"', V.String),  # hasTechnicalDataLink
        # hasInstallationDate
        ('i=6101', datetime.datetime(2025, 7, 14, 8, 30, tzinfo=datetime.timezone.utc), V.DateTime),
        ('i=6097', 1, V.Int32),  # hasPumpClass, an enumeration
        ('i=6095', ua.OptionSet(Value=b'\x01\x00', ValidBits=b'\x80\x0f'), None),  # hasOfferedControlModes, a structure
    ],
}
# A restarted server is back at its nodeset defaults, so everything is written again
SETS['after'] = [('i=6020', 42.5, V.Double)] + SETS['all'][1:]


async def main():
    async with Client('opc.tcp://127.0.0.1:4840/') as client:
        index = await client.get_namespace_index('http://yourorganisation.org/InstanceExample/')
        for nodeid, value, kind in SETS[sys.argv[1]]:
            variant = ua.Variant(value, kind) if kind else ua.Variant(value)
            await client.get_node(f'ns={index};{nodeid}').write_value(ua.DataValue(variant))


asyncio.run(main())
