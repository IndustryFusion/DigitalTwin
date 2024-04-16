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

def dump_graph(g):
    for s, p, o in g:
        print(s, p, o)


def downcase_string(s):
    return s[0].lower() + s[1:]


def isNodeId(nodeId):
    return 'i=' in nodeId or 'g=' in nodeId or 's=' in nodeId


def convert_to_json_type(result, basic_json_type):
    if basic_json_type == 'string':
        return str(result)
    if basic_json_type == 'boolean':
        return bool(result)
    if basic_json_type == 'integer':
        return int(result)
    if basic_json_type == 'number':
        return float(result)
