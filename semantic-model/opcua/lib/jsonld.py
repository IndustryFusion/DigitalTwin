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

import json
from rdflib.namespace import XSD, RDF
import lib.utils as utils
from pyld import jsonld
import urllib

ngsild_context = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"


def nested_json_from_graph(g, root=None):
    """
    Convert an rdflib graph to a single nested JSON object.

    This function:
      - Serializes the graph to JSON‑LD.
      - Flattens the JSON‑LD.
      - Recursively inlines blank node references.
      - Removes the "@id" field for blank nodes.

    If a root is not provided, it selects the first non‑blank node as the root.
    """
    # Step 1: Serialize and flatten
    data = g.serialize(format='json-ld')
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    jdata = json.loads(data)
    flattened = jsonld.flatten(jdata)

    # Build a mapping from @id to node definition.
    node_map = {node["@id"]: node for node in flattened if "@id" in node}

    def inline_node(node, visited=None):
        """
        Recursively inline blank node references.

        If the node's @id starts with "_:" (i.e. it is a blank node),
        its @id is omitted in the output.
        The visited set prevents infinite recursion in cyclic graphs.
        """
        if visited is None:
            visited = set()

        node_id = node.get("@id")
        # For blank nodes, prevent infinite loops.
        if node_id and node_id.startswith("_:"):
            if node_id in visited:
                return {}  # Avoid cycle by returning an empty dict.
            visited.add(node_id)

        # For non-blank nodes, optionally include the @id.
        result = {}
        if node_id and not node_id.startswith("_:"):
            result["@id"] = node_id

        # Process each key/value.
        for key, value in node.items():
            if key == "@id":
                continue  # Skip the @id for blank nodes.
            if isinstance(value, list):
                new_list = []
                for item in value:
                    if isinstance(item, dict) and "@id" in item:
                        if item["@id"].startswith("_:"):
                            # Inline the blank node content and remove its id.
                            bn = node_map.get(item["@id"], item)
                            new_list.append(inline_node(bn, visited.copy()))
                        else:
                            new_list.append(inline_node(item, visited.copy()))
                    else:
                        new_list.append(item)
                # Optionally collapse single-item lists.
                result[key] = new_list[0] if len(new_list) == 1 else new_list
            elif isinstance(value, dict):
                if "@id" in value:
                    if value["@id"].startswith("_:"):
                        bn = node_map.get(value["@id"], value)
                        result[key] = inline_node(bn, visited.copy())
                    else:
                        result[key] = inline_node(value, visited.copy())
                else:
                    result[key] = value
            else:
                result[key] = value
        return result

    # Step 3: Determine a root node if not provided.
    if root is None:
        # Choose a node that is not a blank node.
        for node in flattened:
            if "@id" in node and not node["@id"].startswith("_:"):
                root = node["@id"]
                break
        if root is None:
            # If all nodes are blank, fall back to the first one.
            root = flattened[0]["@id"]

    root_node = node_map.get(root)
    if not root_node:
        raise ValueError("Specified root node not found in the graph.")

    # Step 4: Inline the root node to create one nested JSON object.
    nested = inline_node(root_node)
    return nested


class JsonLd:
    def __init__(self, basens, opcuans):
        self.instances = []
        self.opcuans = opcuans
        self.basens = basens

    def add_instance(self, instance):
        self.instances.append(instance)

    def serialize(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.instances, f, ensure_ascii=False, indent=4)

    # def extract_namespaces(self, graph):
    #     return {
    #         str(prefix): {
    #             '@id': str(namespace),
    #             '@prefix': True
    #         } for prefix, namespace in graph.namespaces()
    #     }

    # def append(self, instance):
    #     self.instances.append(instance)

    def dump_context(self, filename, namespaces):
        jsonld_context = {
            "@context": [
                namespaces,
                ngsild_context
            ]
        }
        with open(filename, "w") as f:
            json.dump(jsonld_context, f, indent=2)

    @staticmethod
    def map_datatype_to_jsonld(data_type, opcuans):
        boolean_types = [opcuans['Boolean']]
        integer_types = [opcuans['Integer'],
                         opcuans['Int16'],
                         opcuans['Int32'],
                         opcuans['Int64'],
                         opcuans['SByte'],
                         opcuans['UInteger'],
                         opcuans['UInt16'],
                         opcuans['UInt32'],
                         opcuans['UInt64'],
                         opcuans['Byte']]
        number_types = [opcuans['Decimal'],
                        opcuans['Double'],
                        opcuans['Duration'],
                        opcuans['Float']]
        string_types = [opcuans['LocalizedText'],
                        opcuans['String'],
                        opcuans['DateString'],
                        opcuans['DecimalString'],
                        opcuans['NormalizedString'],
                        opcuans['SemanticVersionString'],
                        opcuans['UriString']]
        mixed_numeric_types = [opcuans['Number']]
        if data_type in boolean_types:
            return [XSD.boolean], None
        if data_type in integer_types:
            return [XSD.integer], None
        if data_type in number_types:
            return [XSD.double], None
        if data_type in string_types:
            return [XSD.string], None
        if data_type in mixed_numeric_types:
            return [XSD.double, XSD.integer], None
        if data_type == opcuans['DateTime']:
            return [XSD.dateTime], None
        return [RDF.JSON], None

    def generate_node_id(self, graph, rootentity, node, id):
        try:
            node_id = next(graph.objects(node, self.basens['hasNodeId']))
            idtype = next(graph.objects(node, self.basens['hasIdentifierType']))
            bn = next(graph.objects(rootentity, self.basens['hasBrowseName']))
        except:
            node_id = 'unknown'
        idt = utils.idtype2String(idtype, self.basens)
        quoted_node_id = urllib.parse.quote(node_id)
        quoted_id = urllib.parse.quote(id, safe='/:')
        quoted_bn = urllib.parse.quote(bn, safe='/:')
        if str(node) == str(rootentity):
            return f'{quoted_id}:{quoted_bn}'
        else:
            return f'{quoted_id}:{quoted_bn}:sub:{idt}{quoted_node_id}'
