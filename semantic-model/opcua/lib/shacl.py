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

import os
from urllib.parse import urlparse
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS, SH
import lib.utils as utils
from lib.jsonld import JsonLd


query_minmax = """
SELECT ?path ?pattern ?mincount ?maxcount ?localName
WHERE {
    ?shape a sh:NodeShape ;
           sh:property ?property ;
           sh:targetClass ?targetclass .

    ?property sh:path ?path ;
        sh:property [ sh:class ?attributeclass ] .
    OPTIONAL {
        ?property base:hasPlaceHolderPattern ?pattern .
    }

    OPTIONAL {
        ?property sh:maxCount ?maxcount .
    }

    OPTIONAL {
        ?property sh:minCount ?mincount .
    }

    # Extract the local name from the path (after the last occurrence of '/', '#' or ':')
    BIND(REPLACE(str(?path), '.*[#/](?=[^#/]*$)', '') AS ?localName)

    # Conditional filtering based on whether the pattern exists
    FILTER (
        IF(bound(?pattern),
           regex(?name, ?pattern),  # If pattern exists, use regex
           ?localName = ?prefixname        # Otherwise, match the local name
        )
    )
  BIND(IF(?localName = ?prefixname, 0, 1) AS ?order)
}
ORDER BY ?order
"""


class Shacl:
    def __init__(self, namespace_prefix, basens, opcuans):
        self.shaclg = Graph()
        self.shacl_namespace = Namespace(f'{namespace_prefix}shacl/')
        self.shaclg.bind('shacl', self.shacl_namespace)
        self.shaclg.bind('sh', SH)
        self.ngsildns = Namespace('https://uri.etsi.org/ngsi-ld/')
        self.shaclg.bind('ngsi-ld', self.ngsildns)
        self.basens = basens
        self.opcuans = opcuans

    def create_shacl_type(self, targetclass):
        name = self.get_typename(targetclass) + 'Shape'
        shapename = self.shacl_namespace[name]
        self.shaclg.add((shapename, RDF.type, SH.NodeShape))
        self.shaclg.add((shapename, SH.targetClass, URIRef(targetclass)))
        return shapename

    def create_shacl_property(self, shapename, path, optional, is_array, is_property, is_iri, contentclass, datatype,
                              is_subcomponent=False, placeholder_pattern=None):
        innerproperty = BNode()
        property = BNode()
        maxCount = 1
        minCount = 1
        if optional:
            minCount = 0
        self.shaclg.add((shapename, SH.property, property))
        self.shaclg.add((property, SH.path, path))
        self.shaclg.add((property, SH.nodeKind, SH.BlankNode))
        self.shaclg.add((property, SH.minCount, Literal(minCount)))
        if not is_array:
            self.shaclg.add((property, SH.maxCount, Literal(maxCount)))
        self.shaclg.add((property, SH.property, innerproperty))
        if is_property:
            self.shaclg.add((innerproperty, SH.path, self.ngsildns['hasValue']))
        else:
            self.shaclg.add((innerproperty, SH.path, self.ngsildns['hasObject']))
            if is_array:
                self.shaclg.add((property, self.basens['isPlaceHolder'], Literal(True)))
            if placeholder_pattern is not None:
                self.shaclg.add((property, self.basens['hasPlaceHolderPattern'], Literal(placeholder_pattern)))
            if is_subcomponent:
                self.shaclg.add((property, RDF.type, self.basens['SubComponentRelationship']))
            else:
                self.shaclg.add((property, RDF.type, self.basens['PeerRelationship']))
        if is_iri:
            self.shaclg.add((innerproperty, SH.nodeKind, SH.IRI))
            if contentclass is not None:
                self.shaclg.add((innerproperty, SH['class'], contentclass))
        elif is_property:
            self.shaclg.add((innerproperty, SH.nodeKind, SH.Literal))
            if datatype is not None:
                self.shaclg.add((innerproperty, SH.datatype, datatype))

        self.shaclg.add((innerproperty, SH.minCount, Literal(1)))
        self.shaclg.add((innerproperty, SH.maxCount, Literal(1)))

    def get_typename(self, url):
        result = urlparse(url)
        if result.fragment != '':
            return result.fragment
        else:
            basename = os.path.basename(result.path)
            return basename

    def bind(self, prefix, namespace):
        self.shaclg.bind(prefix, namespace)

    def serialize(self, destination):
        self.shaclg.serialize(destination)

    def get_graph(self):
        return self.shaclg

    def get_shacl_iri_and_contentclass(self, g, node, shacl_rule):
        try:
            data_type = utils.get_datatype(g, node, self.basens)
            if data_type is not None:
                shacl_rule['datatype'] = JsonLd.map_datatype_to_jsonld(data_type, self.opcuans)
                base_data_type = next(g.objects(data_type, RDFS.subClassOf))
                if base_data_type != self.opcuans['Enumeration']:
                    shacl_rule['is_iri'] = False
                    shacl_rule['contentclass'] = None
                else:
                    shacl_rule['is_iri'] = True
                    shacl_rule['contentclass'] = data_type
            else:
                shacl_rule['is_iri'] = False
                shacl_rule['contentclass'] = None
                shacl_rule['datatype'] = None
        except:
            shacl_rule['is_iri'] = False
            shacl_rule['contentclass'] = None
            shacl_rule['datatype'] = None

    def get_modelling_rule_and_path(self, name, target_class, attributeclass, prefix):
        bindings = {'targetclass': target_class, 'name': Literal(name), 'attributeclass': attributeclass,
                    'prefixname': Literal(f'{prefix}{name}')}
        optional = True
        array = True
        path = None
        try:
            results = list(self.shaclg.query(query_minmax, initBindings=bindings,
                                             initNs={'sh': SH, 'base': self.basens}))
            if len(results) > 0:
                if results[0][0] is not None:
                    path = results[0][0]
                if int(results[0][2]) > 0:
                    optional = False
                if int(results[0][3]) <= 1:
                    array = False
            if len(results) > 1:
                print("Warning: more than one path match for {path}")
        except:
            pass
        return optional, array, path

    def attribute_is_indomain(self, targetclass, attributename):
        property = self._get_property(targetclass, attributename)
        return property is not None

    def _get_property(self, targetclass, propertypath):
        result = None
        try:
            # First find the right nodeshape
            shape = next(self.shaclg.subjects(SH.targetClass, targetclass))
            properties = self.shaclg.objects(shape, SH.property)
            for property in properties:
                path = next(self.shaclg.objects(property, SH.path))
                if str(path) == str(propertypath):
                    result = property
                    break
        except:
            pass
        return result

    def is_placeholder(self, targetclass, attributename):
        property = self._get_property(targetclass, attributename)
        if property is None:
            return False
        try:
            return bool(next(self.shaclg.objects(property, self.basens['isPlaceHolder'])))
        except:
            return False

    def _get_shclass_from_property(self, property):
        result = None
        try:
            subproperty = next(self.shaclg.objects(property, SH.property))
            result = next(self.shaclg.objects(subproperty, SH['class']))
        except:
            pass
        return result

    def update_shclass_in_property(self, property, shclass):
        try:
            subproperty = next(self.shaclg.objects(property, SH.property))
            self.shaclg.remove((subproperty, SH['class'], None))
            self.shaclg.add((subproperty, SH['class'], shclass))
        except:
            pass

    def copy_property_from_shacl(self, source_graph, targetclass, propertypath):
        shape = self.create_shape_if_not_exists(source_graph, targetclass)
        if shape is None:
            return
        property = source_graph._get_property(targetclass, propertypath)
        if property is not None:
            self.copy_bnode_triples(source_graph, property, shape)

    def copy_bnode_triples(self, source_graph, bnode, shape):
        """
        Recursively copies all triples found inside a blank node (bnode)
        from the source graph to the target graph.
        """
        # Iterate over all triples where the blank node is the subject
        if shape is not None:
            self.shaclg.add((shape, SH.property, bnode))
        for s, p, o in source_graph.get_graph().triples((bnode, None, None)):
            # Add the triple to the target graph
            self.shaclg.add((s, p, o))
            # If the object is another blank node, recurse into it
            if isinstance(o, BNode):
                self.copy_bnode_triples(source_graph, o, None)

    def create_shape_if_not_exists(self, source_graph, targetclass):
        try:
            shape = next(self.shaclg.subjects(SH.targetClass, targetclass))
            return shape
        except:
            try:
                shape = next(source_graph.get_graph().subjects(SH.targetClass, targetclass))
            except:
                return None
            for s, p, o in source_graph.get_graph().triples((shape, None, None)):
                if not isinstance(o, BNode):
                    self.shaclg.add((s, p, o))
            return shape
