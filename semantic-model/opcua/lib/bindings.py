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

import random
import string
from rdflib import Graph, Namespace, Literal
from rdflib.namespace import RDF
import lib.utils as utils

randnamelength = 16


class Bindings:
    def __init__(self, namespace_prefix, basens):
        self.bindingsg = Graph()
        self.basens = basens
        self.binding_namespace = Namespace(f'{namespace_prefix}bindings/')
        self.bindingsg.bind('binding', self.binding_namespace)

    def create_binding(self, g, parent_node_id, var_node, attribute_iri, version='0.1', firmware='firmware'):
        randname = ''.join(random.choices(string.ascii_uppercase + string.digits, k=randnamelength))
        bindingiri = self.binding_namespace['binding_' + randname]
        mapiri = self.binding_namespace['map_' + randname]
        dtype = next(g.objects(var_node, self.basens['hasDatatype']))
        node_id = next(g.objects(var_node, self.basens['hasNodeId']))
        idtype = next(g.objects(var_node, self.basens['hasIdentifierType']))
        ns = next(g.objects(var_node, self.basens['hasNamespace']))
        nsuri = next(g.objects(ns, self.basens['hasUri']))
        self.bindingsg.add((bindingiri, RDF['type'], self.basens['Binding']))
        self.bindingsg.add((bindingiri, self.basens['bindsEntity'], parent_node_id))
        self.bindingsg.add((bindingiri, self.basens['bindingVersion'], Literal(version)))
        self.bindingsg.add((bindingiri, self.basens['bindsFirmware'], Literal(firmware)))
        self.bindingsg.add((bindingiri, self.basens['bindsMap'], mapiri))
        self.bindingsg.add((bindingiri, self.basens['bindsAttributeType'], utils.NGSILD['Property']))
        self.bindingsg.add((attribute_iri, self.basens['boundBy'], bindingiri))
        self.bindingsg.add((mapiri, RDF['type'], self.basens['BoundMap']))
        self.bindingsg.add((mapiri, self.basens['bindsConnector'], self.basens['OPCUAConnector']))
        self.bindingsg.add((mapiri, self.basens['bindsMapDatatype'], dtype))
        self.bindingsg.add((mapiri, self.basens['bindsLogicVar'], Literal('var1')))
        self.bindingsg.add((mapiri,
                            self.basens['bindsConnectorAttribute'],
                            Literal(f'nsu={nsuri};{utils.idtype2String(idtype, self.basens)}={node_id}')))

    def bind(self, prefix, namespace):
        self.bindingsg.bind(prefix, namespace)

    def len(self):
        return len(self.bindingsg)

    def serialize(self, destination):
        self.bindingsg.serialize(destination)
