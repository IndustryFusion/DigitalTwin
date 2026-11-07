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

"""Checks the dataservice's messages against contracts/opcua-live-data, after write_values.py all."""
import json
import sys

P = 'http://opcfoundation.org/UA/Pumps/'
messages = [json.loads(line) for line in open(sys.argv[1])]
last = {m['n'].rsplit('/', 1)[-1]: m for m in messages}


def check(ok, text):
    print(('ok   ' if ok else 'FAIL ') + text)
    if not ok:
        sys.exit(1)


check(len(last) == 40, f'distinct attributes sent: {len(last)}, the 6 unset nodes send nothing')
check(not any(m['v'] == 'None' for m in messages), 'no value is the string None')
check(all(m['t'] in ('Property', 'IriProperty', 'JsonProperty', 'Relationship') for m in messages), 'only known labels')
check(all('/' not in m['i'] for m in messages), 'no / in an entity id')
check(last['hasMotorTemperature']['v'] == '71.25', 'number')
check(last['hasNumberOfStarts']['v'] == '17', 'UInt32')
check(last['hasRotorBlocked']['v'] == 'true', 'lowercase boolean')
check(last['hasTechnicalDataLink']['v'] == 'with "quotes"', 'quotes survive the JSON message')
check(last['hasInstallationDate']['v'].startswith('2025-07-14T08:30:00'), 'ISO 8601 timestamp')
check(last['hasPumpClass']['v'] == P + 'PositiveDisplacementPump' and last['hasPumpClass']['t'] == 'IriProperty',
      'enum is the IRI of its value')
modes = last['hasOfferedControlModes']
check(modes['t'] == 'JsonProperty' and json.loads(modes['v'])['xsd:Body']['xsd:OptionSet']['xsd:Value'] == 'AQA=',
      'structure is JSON, with ByteStrings in base64')
check('hasOnOff' not in last, 'an unset node sends nothing')
