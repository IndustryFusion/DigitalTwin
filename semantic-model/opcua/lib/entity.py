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

from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

ngsildns = Namespace('https://uri.etsi.org/ngsi-ld/')

query_enumclass = """
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

CONSTRUCT { ?s ?p ?o .
            ?c ?classpred ?classobj .
            ?o2 base:hasEnumValue ?value .
            ?o2 base:hasValueClass ?class .
}
WHERE
 {
  ?s ?p ?o .
  ?s rdf:type ?c .
  ?c ?classpred ?classobj .
  ?s ?p2 ?o2 .
  ?o2 a base:ValueNode .
  ?o2 base:hasEnumValue ?value .
  ?o2 base:hasValueClass ?class .
}
"""

query_instance = """
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?instance WHERE {
    ?instance a ?c .
    ?instance base:hasValueNode ?valueNode .
    ?valueNode 	base:hasEnumValue ?value .
}
"""

query_default_instance = """
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?instance WHERE {
    ?instance a ?c .
    ?instance base:hasValueNode ?valueNode .
    ?valueNode 	base:hasEnumValue ?value .
} order by ?value limit 1
"""


class Entity:
    def __init__(self, namespace_prefix, basens, opcuans):
        self.e = Graph()
        self.basens = basens
        self.opcuans = opcuans
        self.entity_namespace = Namespace(f'{namespace_prefix}entity/')
        self.e.bind('uaentity', self.entity_namespace)
        self.ngsildns = Namespace('https://uri.etsi.org/ngsi-ld/')
        self.e.bind('ngsi-ld', self.ngsildns)
        self.types = []

    # def scan_type(self, g, node, instancetype):
    #     # Implementation of the scan_type logic
    #     pass

    # def scan_entity(self, g, node, instancetype, id, optional=False):
    #     # Implementation of the scan_entity logic
    #     pass

    # def generate_node_id(self, g, node, id, instancetype):
    #     # Implementation for generating node ID
    #     pass

    def bind(self, prefix, namespace):
        self.e.bind(prefix, namespace)

    def add_type(self, type):
        self.types.append(type)

    def add_instancetype(self, instancetype, attributename):
        if not isinstance(attributename, URIRef):
            iri = self.entity_namespace[attributename]
        else:
            iri = attributename
        self.e.add((iri, RDF.type, OWL.ObjectProperty))
        self.e.add((iri, RDFS.domain, URIRef(instancetype)))
        self.e.add((iri, RDF.type, OWL.NamedIndividual))

    # def add_relationship(self, attributename):
    #     if isinstance(attributename, URIRef):
    #         self.e.add((attributename, RDFS.range, ngsildns['Relationship']))
    #     else:
    #         self.e.add((self.entity_namespace[attributename], RDFS.range, ngsildns['Relationship']))

    # def add_subcomponent(self, attributename):
    #     self.e.add((self.entity_namespace[attributename], RDF.type, self.basens['SubComponentRelationship']))

    # def add_placeholder(self, attributename):
    #     self.e.add((self.entity_namespace[attributename], self.basens['isPlaceHolder'], Literal(True)))

    # def add_property(self, attributename):
    #     if isinstance(attributename, URIRef):
    #         self.e.add((attributename, RDFS.range, ngsildns['Property']))
    #     else:
    #         self.e.add((self.entity_namespace[attributename], RDFS.range, ngsildns['Property']))

    # def is_typematch(self, full_attribute_name, type):
    #     try:
    #         if len(list(self.e.triples((full_attribute_name, RDFS.domain, type)))) > 0:
    #             return True
    #     except:
    #         return False

    def add_subclass(self, type):
        self.e.add((type, RDF.type, OWL.Class))
        self.e.add((type, RDF.type, OWL.NamedIndividual))
        self.e.add((type, RDFS.subClassOf, self.opcuans['BaseObjectType']))

    def add_subclasses(self, classes):
        self.e += classes

    def serialize(self, destination):
        self.e.serialize(destination)

    def add(self, triple):
        self.e.add(triple)

    # def attritube_instance_exists(self, attributename):
    #     return len(list(self.e.objects(attributename, RDF.type))) > 0

    def get_graph(self):
        return self.e

    # def add_opcdatatype(self, attribute_name, data_type):
    #     self.e.add((attribute_name, self.basens['hasOPCUADatatype'], data_type))

    # def add_datatype(self, g, node, attribute_name):
    #     data_type = utils.get_datatype(g, node, self.basens)
    #     if data_type is not None:
    #         self.e.add((self.entity_namespace[attribute_name], self.basens['hasOPCUADatatype'], data_type))

    def create_ontolgoy_header(self, entity_namespace, version=0.1, versionIRI=None):
        self.e.add((URIRef(entity_namespace), RDF.type, OWL.Ontology))
        if versionIRI is not None:
            self.e.add((URIRef(entity_namespace), OWL.versionIRI, versionIRI))
        self.e.add((URIRef(entity_namespace), OWL.versionInfo, Literal(0.1)))

    def add_enum_class(self, graph, contentclass):
        if contentclass is None or not isinstance(contentclass, URIRef):
            return
        bindings = {'c': contentclass}
        print(f'Adding type {contentclass} to knowledge.')
        result = graph.query(query_enumclass, initBindings=bindings,
                             initNs={'base': self.basens, 'opcua': self.opcuans})
        self.e += result

    def get_contentclass(self, contentclass, value):
        bindings = {'c': contentclass, 'value': value}
        result = self.e.query(query_instance, initBindings=bindings,
                              initNs={'base': self.basens, 'opcua': self.opcuans})
        foundclass = None
        if len(result) > 0:
            foundclass = list(result)[0].instance
        if foundclass is None:
            print(f'Warning: no instance found for class {contentclass} with value {value}')
        return foundclass

    def get_default_contentclass(self, contentclass):
        bindings = {'c': contentclass}
        result = self.e.query(query_default_instance, initBindings=bindings,
                              initNs={'base': self.basens, 'opcua': self.opcuans})
        foundclass = None
        if len(result) > 0:
            foundclass = list(result)[0].instance
        if foundclass is None:
            print(f'Warning: no default instance found for class {contentclass}')
        return foundclass
