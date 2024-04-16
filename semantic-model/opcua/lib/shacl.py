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
SELECT ?mincount ?maxcount WHERE {
     ?shape sh:targetClass ?targetclass .
     OPTIONAL{
        ?shape sh:property [
            sh:path ?path;
            sh:maxCount ?maxcount
      ]
    }
     OPTIONAL{
        ?shape sh:property [
            sh:path ?path;
            sh:minCount ?mincount
      ]
    }
}
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
                              is_subcomponent=False):
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
        except:
            shacl_rule['is_iri'] = False
            shacl_rule['contentclass'] = None

    def get_modelling_rule(self, path, target_class):
        bindings = {'targetclass': target_class, 'path': path}
        optional = True
        array = True
        try:
            results = list(self.shaclg.query(query_minmax, initBindings=bindings, initNs={'sh': SH}))
            if len(results) > 0:
                if int(results[0][0]) > 0:
                    optional = False
                if int(results[0][1]) <= 1:
                    array = False
        except:
            pass
        return optional, array

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
