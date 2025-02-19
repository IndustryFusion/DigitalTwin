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

ngsild_context = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"


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
        if str(node) == str(rootentity):
            return f'{id}:{bn}'
        else:
            return f'{id}:{bn}:sub:{idt}{node_id}'
