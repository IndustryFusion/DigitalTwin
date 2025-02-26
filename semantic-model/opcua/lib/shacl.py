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
from difflib import SequenceMatcher
from urllib.parse import urlparse
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS, SH
from rdflib.collection import Collection
import lib.utils as utils
from lib.jsonld import JsonLd
from functools import reduce
import operator

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
    def __init__(self, data_graph, namespace_prefix, basens, opcuans):
        self.shaclg = Graph()
        self.shacl_namespace = Namespace(f'{namespace_prefix}shacl/')
        self.shaclg.bind('shacl', self.shacl_namespace)
        self.shaclg.bind('sh', SH)
        self.ngsildns = Namespace('https://uri.etsi.org/ngsi-ld/')
        self.shaclg.bind('ngsi-ld', self.ngsildns)
        self.basens = basens
        self.opcuans = opcuans
        self.data_graph = data_graph

    def create_shacl_type(self, targetclass):
        name = self.get_typename(targetclass) + 'Shape'
        shapename = self.shacl_namespace[name]
        self.shaclg.add((shapename, RDF.type, SH.NodeShape))
        self.shaclg.add((shapename, SH.targetClass, URIRef(targetclass)))
        return shapename

    def get_array_validation_shape(self, datatype, pattern, value_rank, array_dimensions):
        property_shape = BNode()
        zero_or_more_node = BNode()
        self.shaclg.add((zero_or_more_node, SH.zeroOrMorePath, RDF.rest))
        path_list_head = BNode()
        # The list items: first element is zero_or_more_node, second is rdf:first.
        items = [zero_or_more_node, RDF.first]
        Collection(self.shaclg, path_list_head, items)
        self.shaclg.add((property_shape, SH.path, path_list_head))
        if datatype is not None:
            shapes = self.create_datatype_shapes(datatype)
            pred, obj = self.shacl_or(shapes)
            self.shacl_add_to_shape(property_shape, pred, obj)
        if pattern is not None:
            self.shaclg.add((property_shape, SH.pattern, Literal(pattern)))
        array_length = None
        if array_dimensions is not None:
            ad = Collection(self.data_graph, array_dimensions)
            if len(ad) > 0:
                array_length = reduce(operator.mul, (item.toPython() for item in ad), 1)
        if array_length is not None and array_length > 0:
            self.shaclg.add((property_shape, SH.minCount, Literal(array_length)))
            self.shaclg.add((property_shape, SH.maxCount, Literal(array_length)))
        property_node = BNode()
        self.shaclg.add((property_node, SH.property, property_shape))
        return property_node

    def create_shacl_property(self,
                              shapename,
                              path,
                              optional,
                              is_array,
                              is_property,
                              is_iri,
                              contentclass,
                              datatype,
                              is_subcomponent=False,
                              placeholder_pattern=None,
                              pattern=None,
                              value_rank=-1,
                              array_dimensions=None):
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
            if value_rank is None or int(value_rank) == -1:
                self.shaclg.add((innerproperty, SH.nodeKind, SH.Literal))
                shapes = self.create_datatype_shapes(datatype)
                pred, obj = self.shacl_or(shapes)
                self.shacl_add_to_shape(innerproperty, pred, obj)
            elif int(value_rank) >= 0:
                array_validation_shape = self.get_array_validation_shape(datatype,
                                                                         pattern,
                                                                         value_rank,
                                                                         array_dimensions)
                pred, obj = self.shacl_or([array_validation_shape])
                self.shaclg.add((innerproperty, pred, obj))
                blank_node_shape = BNode()
                self.shaclg.add((blank_node_shape, SH.nodeKind, SH.BlankNode))
                rdf_nil_value_shape = BNode()
                self.shaclg.add((rdf_nil_value_shape, SH.hasValue, RDF.nil))
                pred, obj = self.shacl_or([blank_node_shape, rdf_nil_value_shape])
                self.shaclg.add((innerproperty, pred, obj))
            elif int(value_rank) < -1:
                dt_array = self.create_datatype_shapes(datatype)
                array_validation_shape = self.get_array_validation_shape(datatype,
                                                                         pattern,
                                                                         value_rank,
                                                                         array_dimensions)
                dt_array.append(array_validation_shape)
                pred, obj = self.shacl_or(dt_array)
                self.shacl_add_to_shape(innerproperty, pred, obj)
        if pattern is not None:
            self.shaclg.add((innerproperty, SH['pattern'], Literal(pattern)))
        self.shaclg.add((innerproperty, SH.minCount, Literal(1)))
        self.shaclg.add((innerproperty, SH.maxCount, Literal(1)))

    def shacl_add_to_shape(self, property_shape, pred, obj):
        if pred is not None:
            self.shaclg.add((property_shape, pred, obj))

    def create_datatype_shapes(self, datatypes):
        if datatypes is None or len(datatypes) == 0:
            return []
        else:
            dt_items = []
            for dt in datatypes:
                dt_node = BNode()
                self.shaclg.add((dt_node, SH.datatype, dt))
                dt_items.append(dt_node)
            return dt_items

    def shacl_or(self, shapes):
        """Creates shacl_or node if more than one shape is provided

           In case only one shape is provided, then the "inner" properties are returned
           In case of more shapes, it is wrapped in an SHACL OR expression
        Args:
            shapes (): shapes to or, e.g. (in turtle notation) ( [sh:datatype xsd:integer] [sh:datatype xsd:string])

        Returns:
            RDF Nodes: predicate, object
        """
        if len(shapes) == 1:
            # only one OR element
            # must start with BNode
            s, p, o = next(self.shaclg.triples((shapes[0], None, None)))
            # remove subject, it is expected to be relinked by the caller
            self.shaclg.remove((s, p, o))
            return p, o
        or_node = BNode()
        Collection(self.shaclg, or_node, shapes)
        return SH['or'], or_node

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

    def get_shacl_iri_and_contentclass(self, g, node, parentnode, shacl_rule):
        typenode, templatenode = utils.get_type_and_template(g, node, parentnode, self.basens, self.opcuans)
        data_type = utils.get_datatype(g, node, typenode, templatenode, self.basens)
        value_rank, array_dimensions = utils.get_rank_dimensions(g, node, typenode, templatenode, self.basens,
                                                                 self.opcuans)
        shacl_rule['value_rank'] = value_rank
        shacl_rule['array_dimensions'] = array_dimensions
        shacl_rule['orig_datatype'] = data_type
        shacl_type, shacl_pattern = JsonLd.map_datatype_to_jsonld(data_type, self.opcuans)
        shacl_rule['pattern'] = shacl_pattern
        if data_type is not None:
            base_data_type = next(g.objects(data_type, RDFS.subClassOf))  # Todo: This must become a sparql query
            is_abstract = None
            try:
                is_abstract = bool(next(g.objects(data_type, self.basens['isAbstract'])))
            except:
                pass
            shacl_rule['isAbstract'] = is_abstract
            shacl_rule['datatype'] = shacl_type
            shacl_rule['pattern'] = shacl_pattern
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
            shacl_rule['isAbstract'] = None

    def get_modelling_rule_and_path(self, name, target_class, attributeclass, prefix):
        bindings = {'targetclass': target_class, 'name': Literal(name), 'attributeclass': attributeclass,
                    'prefixname': Literal(f'{prefix}{name}')}
        optional = True
        array = True
        path = None
        try:
            results = list(self.shaclg.query(query_minmax, initBindings=bindings,
                                             initNs={'sh': SH, 'base': self.basens}))
            if len(results) > 1:  # try similarity between options
                print("Warning, found ambigous path match. Most likely due to use of generic FolderType \
or placeholders or both. Will try to guess the right value, but this can go wrong ...")
                similarity = []
                for result in results:
                    similarity.append(SequenceMatcher(None, name, str(result[4])).ratio())
                target_index = similarity.index(max(similarity))
            if len(results) == 1:
                target_index = 0
            if len(results) > 0:
                if results[target_index][0] is not None:
                    path = results[target_index][0]
                if int(results[target_index][2]) > 0:
                    optional = False
                if int(results[target_index][3]) <= 1:
                    array = False
            if len(results) > 1:
                print(f"Guessed to use {path} for {name} and class {target_class}")
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
