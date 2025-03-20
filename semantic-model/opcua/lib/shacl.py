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
import re
from difflib import SequenceMatcher
from urllib.parse import urlparse
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS, SH
from rdflib.collection import Collection
from pyshacl import validate
import lib.utils as utils
from lib.jsonld import JsonLd
from functools import reduce
import operator


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


class Validation:
    """Stay compatible with Pyshacl - mid term replace it where possible
    """
    def __init__(self, shapes_graph, data_graph, extra_graph=None, strict=True, sparql_only=False,
                 no_sparql=False, debug=False):
        self.shapes_graph = shapes_graph
        self.data_graph = data_graph
        self.extra_graph = extra_graph
        self.strict = strict
        self.debug = debug
        self.sparql_only = sparql_only
        self.no_sparql = no_sparql
        self.sparql_graph = Graph()  # Will be replaced later by Oxigraph

    def update_results(self, message: str, conforms: bool, y: int) -> str:
        """
        This is a fix to keep complient with pyshacl.
        Update the number in the third line of a message by adding a given value y.

        Parameters:
            message (str): A multi-line string with at least three lines. The third line should
                contain a number in parentheses.
            y (int): The value to add to the extracted number.

        Returns:
            str: The updated message with the number in the third line increased by y.
        """
        lines = message.splitlines()
        if not conforms:
            lines[2] = re.sub(r'\((\d+)\)', lambda m: f'({int(m.group(1)) + y})', lines[2])
            return "\n".join(lines)
        elif y > 0:
            return f'Validation Report\nConforms: False\nResults ({y}):\n'
        else:
            return message

    def format_shacl_violation(self, results_graph):
        """
        Translates SHACL validation results into a human-readable SHACL message format.

        :param results_graph: An RDFLib Graph containing SHACL validation results.
        :return: A formatted string representation of the violations.
        """
        violations = []

        # Iterate over all validation result nodes
        for report_node in results_graph.subjects(RDF.type, SH.ValidationResult):
            severity = results_graph.value(report_node, SH.resultSeverity, None)
            source_shape = results_graph.value(report_node, SH.sourceShape, None)
            source_constraint_node = results_graph.value(report_node, SH.sourceConstraint, None)
            source_constraint_graph = utils.extract_subgraph(self.shapes_graph, source_constraint_node)
            source_constraint_dump = utils.dump_without_prefixes(source_constraint_graph)
            focus_node = results_graph.value(report_node, SH.focusNode, None)
            value_node = results_graph.value(report_node, SH.value, None)
            result_message = results_graph.value(report_node, SH.resultMessage, None)

            # Format the output
            violation_message = f"""\
    Constraint Violation in SPARQLConstraintComponent ({SH}SPARQLConstraintComponent):
        Severity: {severity}
        Source Shape: {source_shape}
        Focus Node: {focus_node}
        Value Node: {value_node}
        Source Constraint: {source_constraint_dump}
        Message: {result_message}
    """
            violations.append(violation_message)

        return "\n".join(violations)

    def add_term_to_query(self, query: str, target_class: URIRef) -> str:
        """
        Adds the term '$this a <target_class> .' immediately after the first occurrence
        of the 'WHERE { ' clause in the given SPARQL query, accommodating variable whitespace.

        Args:
            query: A SPARQL query string.
            target_class: An rdflib.URIRef representing the target class.

        Returns:
            The modified SPARQL query string with the new term inserted.

        Raises:
            ValueError: If no valid 'WHERE' clause is found in the query.
        """
        # This regex matches "WHERE" followed by any whitespace, an opening curly brace,
        # and any additional whitespace. It is case-insensitive.
        pattern = re.compile(r'(WHERE\s*\{\s*)', flags=re.IGNORECASE)
        match = pattern.search(query)
        if not match:
            raise ValueError("The query does not contain a valid 'WHERE' clause.")

        insertion = f"$this a <{target_class}> . "
        insertion_point = match.end()
        new_query = query[:insertion_point] + insertion + query[insertion_point:]
        return new_query

    def fill_message_template(self, message_template: str, binding: dict) -> str:
        """
        Replaces placeholders of the form {?var} and {$var} in the message_template with the
        corresponding value from the binding dictionary.

        :param message_template: The SHACL message template containing placeholders.
        :param binding: A dictionary containing variable values.
        :return: The formatted message with placeholders replaced.
        """
        def replacer(match):
            var = match.group(2)  # Extract variable name (without ? or $)
            return str(binding.get(var, match.group(0)))  # Keep original placeholder if not found

        # Matches both {?var} and {$var}
        return re.sub(r'\{([\?$])([^}]+)\}', replacer, message_template)

    def validate_sparql_constraint(self, shape: URIRef, target_class: URIRef, sparql_constraint_node: BNode):
        """
        Validates all nodes of type target_class against a SPARQL constraint (a sh:sparql node).

        This function:
        - Extracts the sh:select query and sh:message from the constraint node.
        - Modifies the query by inserting "$this a <target_class> ." after the first WHERE clause.
        - Executes the modified query on the provided data_graph.
        - For each violation (i.e. each result row), fills in the message template using
            the query bindings.

        Returns:
            A tuple (conforms, results_graph, results_text) similar to pySHACL.
        """

        # Extract the sh:select query from the SPARQL constraint node.
        query_literal = self.shapes_graph.value(sparql_constraint_node, SH.select)
        if query_literal is None:
            raise ValueError("No sh:select query found on the SPARQL constraint node.")
        query = str(query_literal)

        # Extract the sh:message (if provided).
        message_literal = self.shapes_graph.value(sparql_constraint_node, SH.message)
        message_template = str(message_literal) if message_literal is not None else "SPARQL constraint violation."

        # Modify the query by inserting the condition using the helper function.
        modified_query = self.add_term_to_query(query, target_class)

        # Note: Here we assume that the query itself is written to bind $this as a variable.
        # We do not replace $this with a specific node URI because we intend the query to check
        # all nodes of type target_class in the graph.

        # Execute the modified query on the data graph.
        query_results = self.sparql_graph.query(modified_query)

        # Process query results: each row is a set of variable bindings.
        violations = []
        for row in query_results:
            # Build a dictionary mapping variable names to their bound values.
            bindings = {str(var): row[var] for var in row.labels}
            violations.append(bindings)

        # Construct the results text from the message template.
        if not violations:
            conforms = True
        else:
            conforms = False
            messages = []
            for bindings in violations:
                result_message = self.fill_message_template(message_template, bindings)
                bindings['resultMessage'] = result_message
                messages.append(result_message)

        # Build a minimal results graph.
        results_graph = Graph()

        for bindings in violations:
            report_node = BNode()
            results_graph.add((report_node, SH.conforms, Literal(conforms)))
            results_graph.add((report_node, SH.resultMessage, Literal(bindings['resultMessage'])))
            results_graph.add((report_node, SH.focusNode, bindings['this']))
            results_graph.add((report_node, SH.value, bindings['this']))
            results_graph.add((report_node, SH.resultSeverity, SH.Violation))
            results_graph.add((report_node, SH.sourceShape, shape))
            results_graph.add((report_node, SH.sourceConstraint, sparql_constraint_node))
            results_graph.add((report_node, RDF.type, SH.ValidationResult))
        return conforms, results_graph

    def shacl_validation(self):
        """Execute a pyShacl validation but replace SPARQL queries
           because it is done suboptimal in pyShacl implementation

        Args:
            data_graph (_type_): _description_
            shapes_graph (_type_): _description_
            extra_graph (_type_): _description_
            strict (_type_): _description_
            debug (_type_): _description_

        Returns:
            _type_: _description_
        """
        full_results_graph = Graph()
        full_results_text = ''
        full_conforms = True
        # Remove al top level SPARQL queries which can be processed by
        # direct query
        # Precondition is a SH.targetClass and root level sh:sparql query
        if not self.strict:
            self.sparql_graph = Graph(store='Oxigraph')
            self.sparql_graph += self.data_graph + self.extra_graph
            for shape, _, _ in self.shapes_graph.triples((None, RDF.type, SH.NodeShape)):
                for s, p, o in self.shapes_graph.triples((shape, SH.sparql, None)):
                    list_of_target_classes = list(self.shapes_graph.objects(shape, SH.targetClass))
                    select_query = self.shapes_graph.value(o, SH.select)
                    for tc in list_of_target_classes:
                        if select_query is not None:
                            # Remove it from the Shapes Graph
                            if not self.no_sparql:
                                conforms, results_graph = self.validate_sparql_constraint(shape, tc, o)
                                full_results_graph += results_graph
                                full_results_text += self.format_shacl_violation(results_graph)
                                if not conforms:
                                    full_conforms = False
                            self.shapes_graph.remove((s, p, o))

        if not self.strict:
            data_graph = self.sparql_graph
            if self.sparql_only:
                data_graph = Graph()
            conforms, results_graph, results_text = validate(
                data_graph=data_graph,
                shacl_graph=self.shapes_graph,
                debug=self.debug
            )
            constraint_violations = len(list(full_results_graph.subjects(RDF.type, SH.ValidationResult)))
            full_results_graph += results_graph
            if not conforms:
                full_conforms = False
            results_text = self.update_results(results_text, conforms, constraint_violations)
            full_results_text = results_text + '\n' + full_results_text

        else:
            conforms, results_graph, results_text = validate(
                data_graph=self.data_graph,
                shacl_graph=self.shapes_graph,
                ont_graph=self.extra_graph,
                debug=self.debug
            )
            full_results_graph = results_graph
            full_conforms = conforms
            full_results_text = results_text
        return full_conforms, full_results_graph, full_results_text

    def find_shape_name(self, shape_node):
        """
        Traverse shape graph to find parent which is a Nodeshape and is a name
        Args:
            shape_node (node): Node which triggered the validation failure
        """
        parent_node = None
        inter_node = shape_node
        while parent_node is None and inter_node is not None:
            inter_node = next(self.shapes_graph.subjects(SH.property, inter_node), None)
            if inter_node is not None and (inter_node, RDF.type, SH.NodeShape) in self.shapes_graph and \
                    isinstance(inter_node, URIRef):
                parent_node = inter_node
        return parent_node

    def find_entity_id(self, focus_node):
        """
        Traverse data graph to find entity id and context

        Args:
            data_graph (Graph): RDF Graph
            focus_node (RDF Node): Data node which triggered the validation failure
        """
        parent_node = None
        inter_node = focus_node
        predicates = []
        while parent_node is None and inter_node is not None:
            s, p, _ = next(self.data_graph.triples((None, None, inter_node)), (None, None, None))
            if s is not None:
                inter_node = s
                if self.data_graph.value(subject=s, predicate=RDF.type) is not None:
                    parent_node = s
                    inter_node = None
            else:
                parent_node = inter_node
            if p is not None:
                predicates.append(p)
        return parent_node, predicates
