#
# Copyright (c) 2024, 2025 Intel Corporation
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
from rdflib import Graph, Namespace, Literal, XSD
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
        """
        Create a binding for a variable node and associate it with an attribute IRI.

        Args:
            g (rdflib.Graph): The RDF graph to which the binding will be added.
            parent_node_id (rdflib.term.Identifier): The identifier of the parent node to bind.
            var_node (rdflib.term.Identifier): The identifier of the variable node to bind.
            attribute_iri (rdflib.term.Identifier): The IRI of the attribute to bind.
            version (str, optional): The version of the binding. Defaults to '0.1'.
            firmware (str, optional): The firmware associated with the binding. Defaults to 'firmware'.
        """
        bindingiri = self.create_attribute_binding(parent_node_id, attribute_iri, None, version, firmware)
        self.add_map_to_attribute(g, bindingiri, 'var1', var_node, self.basens['OPCUAConnector'])

    def create_attribute_binding(self, parent_node_id,
                                 attribute_iri,
                                 logic_transform=None,
                                 version='0.1',
                                 firmware='firmware'):
        """
        Create a binding for an attribute.
        This function generates a unique binding ID and associates it with the given parent node ID and attribute IRI.
        Args:
            parent_node_id (rdflib.term.Identifier): The identifier of the parent node to bind.
            attribute_iri (rdflib.term.Identifier): The IRI of the attribute to bind.
            version (str, optional): The version of the binding. Defaults to '0.1'.
            firmware (str, optional): The firmware associated with the binding. Defaults to 'firmware'.

        Returns:
            rdflib.term.Identifier: The IRI of the created map.
        """
        randname = ''.join(random.choices(string.ascii_uppercase + string.digits, k=randnamelength))
        bindingiri = self.binding_namespace['binding_' + randname]
        self.bindingsg.add((bindingiri, RDF['type'], self.basens['Binding']))
        self.bindingsg.add((bindingiri, self.basens['bindsEntity'], parent_node_id))
        self.bindingsg.add((bindingiri, self.basens['bindingVersion'], Literal(version)))
        self.bindingsg.add((bindingiri, self.basens['bindsFirmware'], Literal(firmware)))
        self.bindingsg.add((bindingiri, self.basens['bindsAttributeType'], utils.NGSILD['Property']))
        if logic_transform is not None:
            self.bindingsg.add((bindingiri, self.basens['bindsLogic'], Literal(logic_transform)))
        self.bindingsg.add((attribute_iri, self.basens['boundBy'], bindingiri))
        return bindingiri

    def add_map_to_attribute(self, g, attribute_iri, varname, var_node, connector):
        """
        Add a map to an attribute.
        This function associates a OPC Ua variable with a given attribute IRI in the graph.
        Args:
            g (rdflib.Graph): The RDF graph to which the map will be added.
            attribute_iri (rdflib.term.Identifier): The IRI of the attribute to bind.
            varname (str): The name of the variable to bind.
            var_node (rdflib.term.Identifier): The identifier of the variable node in the graph.
            connector (rdflib.term.Identifier): The identifier of the connector to bind.

        """
        randname = ''.join(random.choices(string.ascii_uppercase + string.digits, k=randnamelength))
        mapiri = self.binding_namespace['map_' + randname]
        dtype = next(g.objects(var_node, self.basens['hasDatatype']), XSD.anyType)
        node_id = next(g.objects(var_node, self.basens['hasNodeId']))
        idtype = next(g.objects(var_node, self.basens['hasIdentifierType']))
        ns = next(g.objects(var_node, self.basens['hasNamespace']))
        nsuri = next(g.objects(ns, self.basens['hasUri']))
        self.bindingsg.add((mapiri, RDF['type'], self.basens['BoundMap']))
        self.bindingsg.add((mapiri, self.basens['bindsConnector'], connector))
        self.bindingsg.add((mapiri, self.basens['bindsLogicVar'], Literal(varname)))
        self.bindingsg.add((mapiri, self.basens['bindsMapDatatype'], dtype))
        self.bindingsg.add((attribute_iri, self.basens['bindsMap'], mapiri))
        self.bindingsg.add((mapiri,
                            self.basens['bindsConnectorParameter'],
                            Literal(f'nsu={nsuri};{utils.idtype2String(idtype, self.basens)}={node_id}')))

    def bind(self, prefix, namespace):
        self.bindingsg.bind(prefix, namespace)

    def len(self):
        return len(self.bindingsg)

    def get_binding_graph(self):
        """
        Get the RDF graph containing all bindings.
        Returns:
            rdflib.Graph: The graph containing all bindings.
        """
        return self.bindingsg

    def serialize(self, destination):
        self.bindingsg.serialize(destination)
