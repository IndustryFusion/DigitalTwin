# tests/test_utils.py
import io
import sys
import os
from pathlib import Path
from urllib.parse import quote
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDFS, XSD, OWL, RDF
from rdflib.collection import Collection
from lib.utils import RdfUtils, downcase_string, isNodeId, convert_to_json_type, idtype2String, extract_namespaces, \
                                get_datatype, attributename_from_type, get_default_value, get_value, normalize_angle_bracket_name, \
                                contains_both_angle_brackets, get_typename, get_common_supertype, rdfStringToPythonBool, \
                                get_rank_dimensions, get_type_and_template, OntologyLoader, file_path_to_uri, create_list, \
                                extract_subgraph, dump_without_prefixes, get_contentclass, quote_url, merge_attributes, dump_graph, \
                                is_subclass, create_list, get_contentclass, RdfUtils

class TestIsSubclass(unittest.TestCase):
    def test_direct_subclass(self):
        graph = Graph()
        class1 = URIRef("http://example.org/A")
        class2 = URIRef("http://example.org/B")
        graph.add((class1, RDFS.subClassOf, class2))
        self.assertTrue(is_subclass(graph, class1, class2))

    def test_indirect_subclass(self):
        graph = Graph()
        class1 = URIRef("http://example.org/A")
        mid = URIRef("http://example.org/Mid")
        class2 = URIRef("http://example.org/B")
        graph.add((class1, RDFS.subClassOf, mid))
        graph.add((mid, RDFS.subClassOf, class2))
        self.assertTrue(is_subclass(graph, class1, class2))

    def test_not_subclass(self):
        graph = Graph()
        class1 = URIRef("http://example.org/A")
        class2 = URIRef("http://example.org/B")
        self.assertFalse(is_subclass(graph, class1, class2))

class TestCreateListEmptyAndContentclassNone(unittest.TestCase):
    def setUp(self):
        self.basens = Namespace("http://example.org/base/")

    def test_create_list_empty(self):
        g = Graph()
        empty = create_list(g, [], int)
        self.assertEqual(empty, RDF.nil)

    def test_get_contentclass_no_match(self):
        g = Graph()
        result = get_contentclass(str(URIRef("http://example.org/TestClass")), "1", g, self.basens)
        self.assertIsNone(result)

class TestRdfUtilsNodeClassAndInterfaces(unittest.TestCase):
    def setUp(self):
        self.basens = Namespace("http://example.org/base/")
        self.opcuans = Namespace("http://example.org/opcua/")
        self.rdf_utils = RdfUtils(self.basens, self.opcuans)
        self.graph = Graph()
        self.node = URIRef("http://example.org/Node")

    def test_is_object_node_class(self):
        self.assertTrue(self.rdf_utils.isObjectNodeClass(self.opcuans['ObjectNodeClass']))
        self.assertFalse(self.rdf_utils.isObjectNodeClass(URIRef("http://example.org/notObjectNode")))

    def test_is_object_type_node_class(self):
        self.assertTrue(self.rdf_utils.isObjectTypeNodeClass(self.opcuans['ObjectTypeNodeClass']))
        self.assertFalse(self.rdf_utils.isObjectTypeNodeClass(URIRef("http://example.org/notObjectType")))

    def test_is_variable_node_class(self):
        self.assertTrue(self.rdf_utils.isVariableNodeClass(self.opcuans['VariableNodeClass']))
        self.assertFalse(self.rdf_utils.isVariableNodeClass(URIRef("http://example.org/notVariable")))

    def test_get_interfaces_no_interface(self):
        self.assertEqual(self.rdf_utils.get_interfaces(self.graph, self.node), [])

    def test_get_interfaces_with_chain(self):
        interface_node = URIRef("http://example.org/interfaceNode")
        # Add HasInterface on node
        self.graph.add((self.node, self.opcuans['HasInterface'], interface_node))
        # Define a first interface type
        type1 = URIRef("http://example.org/InterfaceType1")
        self.graph.add((interface_node, self.basens['definesType'], type1))
        # Terminate the chain by subclassing BaseInterfaceType
        self.graph.add((type1, RDFS.subClassOf, self.opcuans['BaseInterfaceType']))
        result = self.rdf_utils.get_interfaces(self.graph, self.node)
        self.assertEqual(result, [(type1, interface_node)])

class TestUtilityFunctions(unittest.TestCase):

    def setUp(self):
        # Initialize a base namespace for tests where needed.
        self.basens = Namespace("http://example.org/base/")

    def test_file_path_to_uri_http(self):
        """Test that an HTTP URL remains unchanged when converting to a URI."""
        test_url = "http://example.org/test"
        result = file_path_to_uri(test_url)
        self.assertEqual(result, URIRef(test_url))

    def test_file_path_to_uri_local(self):
        """Test that a local file path is converted to a proper file URI."""
        test_path = "dummy_test.txt"
        expected = URIRef(Path(os.path.abspath(test_path)).as_uri())
        result = file_path_to_uri(test_path)
        self.assertEqual(result, expected)

    def test_create_list(self):
        """Test that create_list builds a proper RDF collection from a Python list."""
        graph = Graph()
        arr = ['a', 'b', 'c']
        list_start = create_list(graph, arr, str)
        col = Collection(graph, list_start)
        expected = [Literal(item) for item in arr]
        self.assertEqual(list(col), expected)

    def test_extract_subgraph_no_predicates(self):
        """Test that extract_subgraph returns all triples recursively when no predicates are provided."""
        graph = Graph()
        a = URIRef("http://example.org/A")
        b = BNode()
        graph.add((a, URIRef("http://example.org/hasChild"), b))
        graph.add((b, URIRef("http://example.org/type"), Literal("Child")))
        subg = extract_subgraph(graph, a)
        self.assertTrue((a, URIRef("http://example.org/hasChild"), b) in subg)
        self.assertTrue((b, URIRef("http://example.org/type"), Literal("Child")) in subg)

    def test_extract_subgraph_with_predicates(self):
        """Test extract_subgraph when a list of predicates is provided."""
        graph = Graph()
        a = URIRef("http://example.org/A")
        pred1 = URIRef("http://example.org/pred1")
        pred2 = URIRef("http://example.org/pred2")
        b = BNode()
        c = BNode()
        graph.add((a, pred1, b))
        graph.add((b, pred2, c))
        predicates = [pred2, pred1]
        subg = extract_subgraph(graph, a, predicates=predicates.copy())
        self.assertTrue((a, pred1, b) in subg)
        self.assertTrue((b, pred2, c) in subg)

    def test_dump_without_prefixes_turtle(self):
        """Test that dump_without_prefixes removes prefix declarations in Turtle serialization."""
        graph = Graph()
        graph.bind("base", self.basens)
        a = URIRef("http://example.org/A")
        b = URIRef("http://example.org/B")
        graph.add((a, RDF.type, b))
        dumped = dump_without_prefixes(graph, format='turtle')
        self.assertNotIn("@prefix", dumped)
        self.assertNotIn("PREFIX", dumped)
        self.assertIn("http://example.org/A", dumped)
        self.assertIn("http://example.org/B", dumped)

    def test_get_contentclass(self):
        """Test that get_contentclass returns the expected instance given a content class and value."""
        graph = Graph()
        test_type = URIRef("http://example.org/TestClass")
        instance = URIRef("http://example.org/instance")
        value_str = '"test"'
        value_node = BNode()
        graph.add((instance, RDF.type, test_type))
        graph.add((instance, self.basens['hasValueNode'], value_node))
        graph.add((value_node, self.basens['hasEnumValue'], Literal("test")))
        graph.add((value_node, self.basens['hasValueClass'], test_type))
        result = get_contentclass(str(test_type), value_str, graph, self.basens)
        self.assertEqual(result, instance)

    def test_quote_url(self):
        """Test that quote_url correctly percent-encodes a URL."""
        test_input = "http://example.org/test?query=1"
        expected = quote(test_input)
        result = quote_url(test_input)
        self.assertEqual(result, expected)

    def test_merge_attributes(self):
        """Test that merge_attributes correctly merges dictionary attributes."""
        instance = {"a": 1}
        attributes = {"b": 2, "a": 3}
        merge_attributes(instance, attributes)
        self.assertEqual(instance, {"a": 3, "b": 2})

    def test_dump_graph(self):
        """Test that dump_graph prints the triples in the graph."""
        graph = Graph()
        triple = (URIRef("http://example.org/A"), RDF.type, Literal("Test"))
        graph.add(triple)
        captured_output = io.StringIO()
        original_stdout = sys.stdout
        try:
            sys.stdout = captured_output
            dump_graph(graph)
        finally:
            sys.stdout = original_stdout
        output = captured_output.getvalue()
        self.assertIn("http://example.org/A", output)
        self.assertIn("Test", output)
class TestUtils(unittest.TestCase):

    def setUp(self):
        """Set up common test data."""
        self.basens = Namespace("http://example.org/base/")
        self.opcuans = Namespace("http://example.org/opcua/")
        self.rdf_utils = RdfUtils(self.basens, self.opcuans)
        self.graph = Graph()
        self.ns = Namespace("http://example.org/")
        self.class1 = URIRef(self.ns['Class1'])
        self.class2 = URIRef(self.ns['Class2'])
        self.node = URIRef(self.ns['Node'])
        self.shacl_rule = {}
        self.instancetype = URIRef(self.ns['InstanceType'])

    def test_downcase_string(self):
        """Test downcasing the first character of a string."""
        self.assertEqual(downcase_string("TestString"), "testString")
        self.assertEqual(downcase_string("anotherTest"), "anotherTest")

    def test_isNodeId(self):
        """Test checking if a string is a NodeId."""
        self.assertTrue(isNodeId("i=1234"))
        self.assertTrue(isNodeId("g=abcd"))
        self.assertTrue(isNodeId("s=test"))
        self.assertFalse(isNodeId("unknown"))

    def test_convert_to_json_type(self):
        """Test converting various types to JSON compatible types."""
        self.assertEqual(convert_to_json_type("123", "integer"), 123)
        self.assertEqual(convert_to_json_type("True", "boolean"), True)
        self.assertEqual(convert_to_json_type("123.45", "number"), 123.45)
        self.assertEqual(convert_to_json_type(123, "string"), "123")

    def test_idtype2String(self):
        """Test converting id types to their string representations."""
        self.assertEqual(idtype2String(self.basens['numericID'], self.basens), 'i')
        self.assertEqual(idtype2String(self.basens['stringID'], self.basens), 's')
        self.assertEqual(idtype2String(self.basens['guidID'], self.basens), 'g')
        self.assertEqual(idtype2String(self.basens['opaqueID'], self.basens), 'b')
        self.assertEqual(idtype2String(URIRef("http://example.org/unknownID"), self.basens), 'x')

    def test_extract_namespaces(self):
        """Test extracting namespaces from an RDF graph."""
        graph = Graph()
        graph.bind("base", self.basens)
        graph.bind("opcua", self.opcuans)

        expected_namespaces = {
            "base": {
                "@id": str(self.basens),
                "@prefix": True
            },
            "opcua": {
                "@id": str(self.opcuans),
                "@prefix": True
            }
        }

        result = extract_namespaces(graph)
        
        # Filter result to only include the namespaces of interest
        filtered_result = {k: v for k, v in result.items() if k in expected_namespaces}

        self.assertEqual(filtered_result, expected_namespaces)


    def test_get_datatype(self):
        """Test retrieving a datatype from the RDF graph."""
        graph = Graph()
        node = URIRef("http://example.org/node")
        typenode = URIRef("http://example.org/typenode")
        templatenode = URIRef("http://example.org/templatenode")
        
        graph.add((typenode, self.basens['hasDatatype'], XSD.string))
        result = get_datatype(graph, node, typenode, templatenode, self.basens)
        self.assertEqual(result, XSD.string)
        
        graph.add((templatenode, self.basens['hasDatatype'], XSD.double))
        result = get_datatype(graph, node, typenode, templatenode, self.basens)
        self.assertEqual(result, XSD.double)
        graph.add((node, self.basens['hasDatatype'], XSD.boolean))
        result = get_datatype(graph, node, typenode, templatenode, self.basens)
        self.assertEqual(result, XSD.boolean)
        
        
    def test_attributename_from_type(self):
        """Test extracting attribute name from a type."""
        type_uri = "http://example.org/SomeType"
        result = attributename_from_type(type_uri)
        self.assertEqual(result, "Some")

    def test_get_default_value(self):
        """Test getting the default value for a datatype."""
        self.assertEqual(get_default_value([XSD.integer]), 0)
        self.assertEqual(get_default_value([XSD.double]), 0.0)
        self.assertEqual(get_default_value([XSD.string]), '')
        self.assertEqual(get_default_value([XSD.boolean]), False)
        self.assertEqual(get_default_value([RDF.JSON]), {'@value': {}, '@type': '@json'})
        self.assertEqual(get_default_value([XSD.dateTime]), {'@value': '1970-1-1T00:00:00', '@type': 'xsd.dateTime'})
        self.assertEqual(get_default_value(None,orig_datatype=XSD.integer), 0)

        # No default value found
        self.assertEqual(get_default_value(datatypes=None, orig_datatype=[XSD.byte]), 'null')
        self.assertEqual(get_default_value(datatypes=[], orig_datatype=[XSD.byte]), 'null')

        # Test array values
        array_dimension_list = [Literal(1)]
        array_dimension_node = BNode()
        g = Graph()
        Collection(g, array_dimension_node, array_dimension_list)
        self.assertEqual(get_default_value([XSD.integer], value_rank=Literal(1), array_dimensions=array_dimension_node, g=g), {'@list': [0]})

        array_dimension_list = [Literal(1), Literal(2), Literal(3)]
        array_dimension_node = BNode()
        g = Graph()
        Collection(g, array_dimension_node, array_dimension_list)
        self.assertEqual(get_default_value([XSD.integer], value_rank=Literal(3), array_dimensions=array_dimension_node, g=g), {'@list': [0, 0, 0, 0, 0, 0]})


    def test_rdfStringToPythonBool(self):
        """Test getting the default value for a datatype."""
        self.assertEqual(rdfStringToPythonBool(Literal('false')), False)
        self.assertEqual(rdfStringToPythonBool(Literal('true')), True)

    def test_get_value(self):
        """Test getting the converted value for a datatype."""
        g = Graph()
        bnode = BNode()
        collection = Collection(g, bnode, [Literal(0), Literal(1), Literal(2)])
        self.assertEqual(get_value(g, Literal(int(99)), [XSD.integer]), int(99))
        self.assertEqual(get_value(g, Literal(float('0.123')), [XSD.double]), float(0.123))
        self.assertEqual(get_value(g, Literal('hello'), [XSD.string]), str('hello'))
        self.assertEqual(get_value(g, Literal(True), [XSD.boolean]), True)
        self.assertEqual(get_value(g, bnode, [XSD.integer]), {'@list': [ 0, 1, 2 ]})
        self.assertEqual(get_value(g, Literal(99), [XSD.integer, XSD.double]), int(99))
        self.assertEqual(get_value(g, Literal(True), [XSD.boolean, XSD.double]), True)
        self.assertEqual(get_value(g, "{}", [RDF.JSON]), {'@value': '{}', '@type': '@json'})
        self.assertEqual(get_value(g, '1970-2-1T00:00:00', [XSD.dateTime]), {'@value': '1970-2-1T00:00:00', '@type': 'xsd:dateTime'})
        self.assertEqual(get_value(g, RDF.nil, [RDF.JSON]), {'@list': [ ]})

    def test_get_value_collection_exception(self):
        """Test that get_value raises an exception when Collection() fails."""
        from rdflib import Graph, BNode
        from rdflib.namespace import XSD
        from lib.utils import get_value

        g = Graph()
        bnode = BNode()

        # Patch the Collection in the lib.utils namespace so that it raises an exception.
        with patch('lib.utils.Collection', side_effect=Exception("Test exception")):
            self.assertEqual(get_value(g, bnode, [XSD.integer]), None)


    def test_normalize_angle_bracket_name(self):
        """Test normalizing a name by removing angle bracket content."""
        input_str = "example<test>123"
        result = normalize_angle_bracket_name(input_str)
        self.assertEqual(result, ("example123", "example[a-zA-Z0-9_-]+123"))

    def test_contains_both_angle_brackets(self):
        """Test checking if a string contains both angle brackets."""
        self.assertTrue(contains_both_angle_brackets("example<test>"))
        self.assertFalse(contains_both_angle_brackets("example"))

    def test_get_typename(self):
        """Test getting type name from a URL."""
        url = "http://example.org/Type#MyType"
        result = get_typename(url)
        self.assertEqual(result, "MyType")

        url = "http://example.org/Type/MyType"
        result = get_typename(url)
        self.assertEqual(result, "MyType")

    @patch.object(Graph, 'query', return_value=[(None, URIRef("http://example.org/realtype"))])
    def test_get_type(self, mock_query):
        """Test retrieving the type of a node from the RDF graph."""
        g = Graph()
        node = URIRef("http://example.org/node")

        nodeclass, realtype = self.rdf_utils.get_type(g, node)

        # Check if the nodeclass is None and realtype is as expected
        self.assertIsNone(nodeclass)
        self.assertEqual(realtype, URIRef("http://example.org/realtype"))

        mock_query.assert_called_once()


    #@patch.object(Graph, 'query', return_value=[(URIRef("http://example.org/reference"), URIRef("http://example.org/target"))])
    def test_get_all_subreferences(self):
        """Test retrieving all subreferences from the RDF graph."""
        g = Graph()
        node = URIRef("http://example.org/node")
        targetnode = URIRef("http://example.org/targetnode")
        reference = URIRef('http://example.com/reference')
        subreference = URIRef('http://example.com/subreference')
        g.add((node, subreference, targetnode))
        g.add((subreference, RDFS.subClassOf, reference))

        references = self.rdf_utils.get_all_subreferences(g, node, reference)
        self.assertEqual(references, [(subreference, targetnode)])

    @patch.object(Graph, 'query', return_value=[(URIRef("http://example.org/subclass"),)])
    def test_get_ignored_references(self, mock_query):
        """Test retrieving ignored references from the RDF graph."""
        g = Graph()

        ignored_references = self.rdf_utils.get_ignored_references(g)
        self.assertEqual(ignored_references, [URIRef("http://example.org/subclass")])
        mock_query.assert_called_once()


    def test_get_all_supertypes(self):
        """Test retrieving all supertypes for a given node."""
        graph = MagicMock()
        instancetype = "http://example.org/InstanceType"
        node = URIRef("http://example.org/Node")

        # Prevent real interface traversal
        self.rdf_utils.get_interfaces = MagicMock(return_value=[])

        # Case 1: Node is an instancetype definition
        graph.objects.side_effect = [
            # 1) definesType on the instance node
            iter([URIRef("http://example.org/TypeNode")]),
            # 2) subClassOf on instancetype → SuperClass
            iter([URIRef("http://example.org/SuperClass")]),
            # 3) next subClassOf on SuperClass → no further superclass
            iter([])
        ]
        graph.subjects.side_effect = [
            # subjects(definesType, SuperClass) → TypeNode
            iter([URIRef("http://example.org/TypeNode")])
        ]
        supertypes = self.rdf_utils.get_all_supertypes_and_interfaces(graph, instancetype, node)
        expected = [
            (URIRef("http://example.org/InstanceType"), URIRef("http://example.org/Node")),
            (URIRef("http://example.org/SuperClass"),    URIRef("http://example.org/TypeNode")),
        ]
        self.assertEqual(supertypes, expected)

        graph.objects.reset_mock()
        graph.subjects.reset_mock()

        # Case 2: Node is not an instancetype definition
        graph.objects.side_effect = [
            # 1) definesType on instance node → none
            iter([]),
            # 2) subClassOf on instancetype → none
            iter([])
        ]
        graph.subjects.side_effect = [
            # subjects(definesType, instancetype) → TypeNode
            iter([URIRef("http://example.org/TypeNode")])
        ]
        supertypes = self.rdf_utils.get_all_supertypes_and_interfaces(graph, instancetype, node)
        expected = [
            (None, node),
            (URIRef("http://example.org/InstanceType"), URIRef("http://example.org/TypeNode")),
        ]
        self.assertEqual(supertypes, expected)

        graph.objects.reset_mock()
        graph.subjects.reset_mock()

        # Case 3: BaseObjectType is reached immediately
        graph.objects.side_effect = [
            # 1) definesType on instance node
            iter([URIRef("http://example.org/TypeNode")]),
            # 2) subClassOf on instancetype → BaseObjectType
            iter([self.opcuans['BaseObjectType']])
        ]
        graph.subjects.side_effect = [
            # subjects(definesType, BaseObjectType) → TypeNode
            iter([URIRef("http://example.org/TypeNode")])
        ]
        supertypes = self.rdf_utils.get_all_supertypes_and_interfaces(graph, instancetype, node)
        expected = [
            (URIRef("http://example.org/InstanceType"), node),
        ]
        self.assertEqual(supertypes, expected)

        graph.objects.reset_mock()
        graph.subjects.reset_mock()

        # Case 4: BaseObjectType then no further superclass
        graph.objects.side_effect = [
            # 1) definesType on instance node
            iter([URIRef("http://example.org/TypeNode")]),
            # 2) subClassOf on instancetype → BaseObjectType
            iter([self.opcuans['BaseObjectType']]),
            # 3) any further subClassOf → none
            iter([])
        ]
        graph.subjects.side_effect = [
            # subjects(definesType, BaseObjectType) → TypeNode
            iter([URIRef("http://example.org/TypeNode")]),
            # subjects(definesType, ?) → none
            iter([])
        ]
        supertypes = self.rdf_utils.get_all_supertypes_and_interfaces(graph, instancetype, node)
        expected = [
            (URIRef("http://example.org/InstanceType"), node),
        ]
        self.assertEqual(supertypes, expected)



    @patch.object(Graph, 'query')
    def test_get_common_supertype(self, mock_query):
        """Test finding common superclass of two classes."""
        # Set up the mocked return value of the query
        mock_query.return_value = [
            {
                'commonSuperclass': URIRef("http://example.org/CommonSuperclass")
            }
        ]

        # Call the function under test
        result = get_common_supertype(self.graph, self.class1, self.class2)

        # Check if the result is as expected
        self.assertEqual(result, URIRef("http://example.org/CommonSuperclass"))
        
        # Verify that the query was called once
        mock_query.assert_called_once()

    @patch.object(Graph, 'query', side_effect=Exception("Query failed"))
    def test_get_common_supertype_query_failure(self, mock_query):
        """Test handling of an exception when query fails."""
        # Call the function under test
        result = get_common_supertype(self.graph, self.class1, self.class2)

        # Ensure the result is None when an exception occurs
        self.assertIsNone(result)

    @patch.object(Graph, 'objects')
    def test_get_modelling_rule(self, mock_objects):
        """Test retrieving the modelling rule of a node."""
        # Set up the mocked return values for objects
        mock_objects.side_effect = [
            iter([URIRef("http://example.org/ModellingNode")]),
            iter([Literal(1)])  # Assuming modelling_nodeid_optional or similar value
        ]

        # Call the function under test
        is_optional, use_instance_declaration = self.rdf_utils.get_modelling_rule(self.graph, self.node, self.shacl_rule, self.instancetype)

        # Check if the results are as expected
        self.assertTrue(is_optional)
        self.assertFalse(use_instance_declaration)
        self.assertTrue(self.shacl_rule['optional'])
        self.assertFalse(self.shacl_rule['array'])

    @patch.object(Graph, 'objects', side_effect=StopIteration)
    def test_get_modelling_rule_no_modelling_node(self, mock_objects):
        """Test handling when there is no modelling node found."""
        # Call the function under test
        is_optional, use_instance_declaration = self.rdf_utils.get_modelling_rule(self.graph, self.node, self.shacl_rule, self.instancetype)

        # Ensure the default values are returned when no modelling node is found
        self.assertTrue(is_optional)
        self.assertFalse(use_instance_declaration)
        self.assertTrue(self.shacl_rule['optional'])
        self.assertFalse(self.shacl_rule['array'])

    def test_isNodeclass(self):
        """Test checking if a given type is recognized as a node class."""
        # These types (from the opcuans namespace) should be identified as node classes.
        self.assertTrue(self.rdf_utils.isNodeclass(self.opcuans['BaseNodeClass']))
        self.assertTrue(self.rdf_utils.isNodeclass(self.opcuans['DataTypeNodeClass']))
        self.assertTrue(self.rdf_utils.isNodeclass(self.opcuans['ObjectNodeClass']))
        self.assertTrue(self.rdf_utils.isNodeclass(self.opcuans['ObjectTypeNodeClass']))
        self.assertTrue(self.rdf_utils.isNodeclass(self.opcuans['ReferenceTypeNodeClass']))
        self.assertTrue(self.rdf_utils.isNodeclass(self.opcuans['VariableNodeClass']))

        # A type that is not in the list should return False.
        not_a_nodeclass = URIRef("http://example.org/opcua/NotANodeClass")
        self.assertFalse(self.rdf_utils.isNodeclass(not_a_nodeclass))

    def test_generate_node_id(self):
        """Test the generate_node_id method with various namespace and id scenarios."""
        # Scenario 1: id provided and node namespace equals root entity namespace.
        graph = Graph()
        node = URIRef("http://example.org/node")
        rootentity = URIRef("http://example.org/root")
        ns = URIRef("http://example.org/ns")
        # Set required triples for node
        graph.add((node, self.basens['hasNodeId'], Literal("12345")))
        graph.add((node, self.basens['hasIdentifierType'], self.basens['numericID']))  # Expect idtype 'i'
        graph.add((node, self.basens['hasNamespace'], ns))
        graph.add((ns, self.basens['hasUri'], Literal("ns://example")))
        # Set rootentity with matching namespace
        graph.add((rootentity, self.basens['hasNamespace'], ns))
        
        result1 = self.rdf_utils.generate_node_id(graph, rootentity, node, "testID")
        # Expected: "ns://example" + "testID" + ":" + "i" + "12345" => "ns://exampletestID:i12345"
        self.assertEqual(result1, "ns://exampletestID:i12345")
        
        # Scenario 2: id is None, so the extra id value is not included.
        graph2 = Graph()
        node2 = URIRef("http://example.org/node2")
        rootentity2 = URIRef("http://example.org/root2")
        ns2 = URIRef("http://example.org/ns2")
        graph2.add((node2, self.basens['hasNodeId'], Literal("67890")))
        graph2.add((node2, self.basens['hasIdentifierType'], self.basens['guidID']))  # Expect idtype 'g'
        graph2.add((node2, self.basens['hasNamespace'], ns2))
        graph2.add((ns2, self.basens['hasUri'], Literal("ns://another")))
        graph2.add((rootentity2, self.basens['hasNamespace'], ns2))
        
        result2 = self.rdf_utils.generate_node_id(graph2, rootentity2, node2, None)
        # Expected: "ns://another" + "g" + "67890" => "ns://anotherg67890"
        self.assertEqual(result2, "ns://anotherg67890")
        
        # Scenario 3: id provided but node namespace differs from root entity namespace.
        graph3 = Graph()
        node3 = URIRef("http://example.org/node3")
        rootentity3 = URIRef("http://example.org/root3")
        ns3_node = URIRef("http://example.org/nsnode")
        ns3_root = URIRef("http://example.org/nsroot")
        graph3.add((node3, self.basens['hasNodeId'], Literal("abcde")))
        graph3.add((node3, self.basens['hasIdentifierType'], self.basens['opaqueID']))  # Expect idtype 'b'
        graph3.add((node3, self.basens['hasNamespace'], ns3_node))
        graph3.add((ns3_node, self.basens['hasUri'], Literal("ns://node")))
        # Root entity with a different namespace
        graph3.add((rootentity3, self.basens['hasNamespace'], ns3_root))
        graph3.add((ns3_root, self.basens['hasUri'], Literal("ns://root")))
        
        result3 = self.rdf_utils.generate_node_id(graph3, rootentity3, node3, "whatever")
        # Expected: "ns://node" + "b" + "abcde" => "ns://nodebabcde"
        self.assertEqual(result3, "ns://nodebabcde")

    def test_get_object_types_from_namespace(self):
        """Test retrieving object types from the RDF graph within a specific namespace."""
        graph = Graph()
        # Use a test entity namespace as a string.
        entity_namespace = "http://example.org/object/"
        # Create a test object whose URI starts with the given namespace.
        test_obj = URIRef("http://example.org/object/TestObject")
        # Define a custom type for this object.
        custom_type = URIRef("http://example.org/object/CustomType")
        # Add the required triple to mark the object as an instance of the OPC UA Object Node Class.
        graph.add((test_obj, RDF.type, self.opcuans['ObjectNodeClass']))
        # Also, add a triple indicating the object is of a custom type.
        graph.add((test_obj, RDF.type, custom_type))
        # Call get_object_types_from_namespace to retrieve the types.
        found_types = self.rdf_utils.get_object_types_from_namespace(graph, entity_namespace)
        # Check that a list is returned and that the custom type is among the returned types.
        self.assertIsInstance(found_types, list)
        self.assertIn(custom_type, found_types)

    def test_get_machinery_nodes(self):
        """Test retrieving machinery nodes from the RDF graph."""
        graph = Graph()
        # Create a machine folder that is an instance of opcua:FolderType.
        machine_folder = URIRef("http://example.org/machine_folder")
        graph.add((machine_folder, RDF.type, self.opcuans['FolderType']))
        # The machine folder must have a namespace equal to machinery:MACHINERYNamespace.
        # Use the MACHINERY constant from utils.py.
        from lib.utils import MACHINERY
        graph.add((machine_folder, self.basens['hasNamespace'], MACHINERY['MACHINERYNamespace']))
        # It must have a node id "1001".
        graph.add((machine_folder, self.basens['hasNodeId'], Literal("1001")))
        
        # Create a machine node that is organized by the folder.
        machine = URIRef("http://example.org/machine")
        # The query uses opcua:Organizes OR opcua:HasComponent, here we use Organizes.
        graph.add((machine_folder, self.opcuans['Organizes'], machine))
        # Give the machine a type that is not a subclass of opcua:BaseNodeClass.
        custom_type = URIRef("http://example.org/customType")
        graph.add((machine, RDF.type, custom_type))
        # (Do not add any triple that would relate custom_type to opcua:BaseNodeClass)

        # Call get_machinery_nodes.
        result = self.rdf_utils.get_machinery_nodes(graph)
        # Verify that the result is a list
        self.assertIsInstance(result, list)
        # The SPARQL query returns rows with two columns: machine and type.
        # Check that the tuple (machine, custom_type) is present in the result.
        self.assertIn((machine, custom_type), result)

class TestGetRankDimensions(unittest.TestCase):

    def setUp(self):
        # Create a fresh graph and define namespaces.
        self.graph = Graph()
        self.basens = Namespace('http://example.org/base/')
        self.opcuans = Namespace('http://example.org/opcua/')
        # Define nodes for testing.
        self.node = URIRef('http://example.org/node')
        self.typenode = URIRef('http://example.org/type')
        self.templatenode = URIRef('http://example.org/template')

    def test_rank_from_node(self):
        """When the node has its own values, those are returned."""
        self.graph.add((self.node, self.basens['hasValueRank'], Literal(10)))
        self.graph.add((self.node, self.basens['hasArrayDimensions'], Literal(3)))
        # Even if type or template have values, the node's values take precedence.
        self.graph.add((self.typenode, self.basens['hasValueRank'], Literal(30)))
        self.graph.add((self.templatenode, self.basens['hasValueRank'], Literal(20)))
        result = get_rank_dimensions(self.graph, self.node, self.typenode, self.templatenode,
                                     self.basens, self.opcuans)
        self.assertEqual(result, (Literal(10), Literal(3)))

    def test_rank_from_template(self):
        """When the node is missing values but the template provides them, the template values are used."""
        # Do not add triples to self.node.
        self.graph.add((self.templatenode, self.basens['hasValueRank'], Literal(20)))
        self.graph.add((self.templatenode, self.basens['hasArrayDimensions'], Literal(5)))
        result = get_rank_dimensions(self.graph, self.node, self.typenode, self.templatenode,
                                     self.basens, self.opcuans)
        self.assertEqual(result, (Literal(20), Literal(5)))

    def test_rank_from_type(self):
        """When neither node nor template provide values but the type does, the type values are used."""
        # Do not add any triples to self.node or a template.
        self.graph.add((self.typenode, self.basens['hasValueRank'], Literal(30)))
        self.graph.add((self.typenode, self.basens['hasArrayDimensions'], Literal(7)))
        result = get_rank_dimensions(self.graph, self.node, self.typenode, None,
                                     self.basens, self.opcuans)
        self.assertEqual(result, (Literal(30), Literal(7)))

    def test_default_value(self):
        """
        When no value_rank is provided by node, template, or type,
        value_rank defaults to Literal(-1) and array_dimensions remains None.
        """
        result = get_rank_dimensions(self.graph, self.node, None, None,
                                     self.basens, self.opcuans)
        self.assertEqual(result, (Literal(-1), None))

class TestGetTypeAndTemplate(unittest.TestCase):

    def setUp(self):
        # Create a graph and define our namespaces.
        self.graph = Graph()
        self.basens = Namespace("http://example.org/base/")
        self.opcuans = Namespace("http://example.org/opcua/")
        # Define the node and its parent.
        self.node = URIRef("http://example.org/node")
        self.parentnode = URIRef("http://example.org/parent")
        # For the query to match, node must have a browse name.
        self.graph.add((self.node, self.basens['hasBrowseName'], Literal("browse1")))
        # And node must have a type.
        self.vartype = URIRef("http://example.org/vartype")
        self.graph.add((self.node, RDF.type, self.vartype))
        # Parent must have a type.
        self.parenttype = URIRef("http://example.org/parenttype")
        self.graph.add((self.parentnode, RDF.type, self.parenttype))
        # For the node type: add a triple linking vartypenode to vartype.
        self.vartypenode = URIRef("http://example.org/vartypenode")
        self.graph.add((self.vartypenode, self.basens['definesType'], self.vartype))
        # For the parent type: add a triple linking parenttypenode to parenttype.
        self.parenttypenode = URIRef("http://example.org/parenttypenode")
        self.graph.add((self.parenttypenode, self.basens['definesType'], self.parenttype))

    def test_get_type_and_template_with_template(self):
        """Test that get_type_and_template returns both vartypenode and templatenode when available."""
        # Add a template triple: parenttypenode hasComponent templatenode.
        templatenode = URIRef("http://example.org/templatenode")
        self.graph.add((self.parenttypenode, self.opcuans['HasComponent'], templatenode))
        # The template must also have the same browse name as the node.
        self.graph.add((templatenode, self.basens['hasBrowseName'], Literal("browse1")))

        typenode, returned_templatenode = get_type_and_template(
            self.graph, self.node, self.parentnode, self.basens, self.opcuans
        )
        self.assertEqual(typenode, self.vartypenode)
        self.assertEqual(returned_templatenode, templatenode)

    def test_get_type_and_template_without_template(self):
        """Test that get_type_and_template returns vartypenode and None when template is absent."""
        typenode, templatenode = get_type_and_template(
            self.graph, self.node, self.parentnode, self.basens, self.opcuans
        )
        self.assertEqual(typenode, self.vartypenode)
        self.assertIsNone(templatenode)

    def test_get_type_and_template_no_result(self):
        """Test that get_type_and_template returns (None, None) when the required triples are missing."""
        # Create an empty graph so the query returns no results.
        empty_graph = Graph()
        typenode, templatenode = get_type_and_template(
            empty_graph, self.node, self.parentnode, self.basens, self.opcuans
        )
        self.assertIsNone(typenode)
        self.assertIsNone(templatenode)
# A fake parse function to simulate ontology content.
def fake_parse(self, source, *args, **kwargs):
    """
    Depending on the source (a string), add triples to the graph.
    
    - For "ont1": adds an ontology triple for ont1 and an owl:imports triple for "ont2".
    - For "ont2": adds an ontology triple for ont2.
    - For "ont3": simulates an ontology without an explicit ontology IRI.
    """
    if str(source) == "ont1":
        # Simulate an ontology with IRI http://example.org/ont1 that imports ont2.
        self.add((URIRef("http://example.org/ont1"), RDF.type, OWL.Ontology))
        self.add((URIRef("http://example.org/ont1"), OWL.imports, Literal("ont2")))
    elif str(source) == "ont2":
        # Simulate an ontology with IRI http://example.org/ont2.
        self.add((URIRef("http://example.org/ont2"), RDF.type, OWL.Ontology))
    elif source == "ont3":
        # Simulate an ontology that does not define an owl:Ontology triple.
        pass

class TestOntologyLoader(unittest.TestCase):

    def setUp(self):
        # We create a fresh loader in each test.
        self.loader = OntologyLoader(verbose=False)

    def test_get_graph_initially_empty(self):
        """Test that get_graph returns an empty graph on initialization."""
        self.assertEqual(len(self.loader.get_graph()), 0)
    
    def test_load_ontology_simple(self):
        """Test that load_ontology loads a simple ontology (ont1) correctly."""
        with patch('rdflib.Graph.parse', new=fake_parse):
            self.loader.load_ontology("ont1")
            # "ont1" should be marked as visited.
            self.assertIn("ont1", self.loader.visited_files)
            # The ontology IRI (http://example.org/ont1) should be in loaded_ontologies.
            self.assertIn("http://example.org/ont1", self.loader.loaded_ontologies)
            # The main graph should now contain the ontology triple for ont1.
            self.assertIn(
                (URIRef("http://example.org/ont1"), RDF.type, OWL.Ontology),
                self.loader.get_graph()
            )

    def test_recursive_import(self):
        """Test that load_ontology loads imported ontologies recursively."""
        with patch('rdflib.Graph.parse', new=fake_parse):
            self.loader.load_ontology("ont1")
            # ont1 imports ont2, so both should be visited.
            self.assertIn("ont1", self.loader.visited_files)
            self.assertIn("ont2", self.loader.visited_files)
            # And both ontology IRIs should be registered.
            self.assertIn("http://example.org/ont1", self.loader.loaded_ontologies)
            # Check that ont2's triple is present.
            self.assertIn(
                (URIRef("http://example.org/ont2"), RDF.type, OWL.Ontology),
                self.loader.get_graph()
            )

    def test_prevent_duplicate_loading(self):
        """Test that an ontology is not loaded twice."""
        with patch('rdflib.Graph.parse', new=fake_parse):
            self.loader.load_ontology("ont1")
            visited_initial = set(self.loader.visited_files)
            loaded_initial = set(self.loader.loaded_ontologies)
            # Calling load_ontology with the same source should have no effect.
            self.loader.load_ontology("ont1")
            self.assertEqual(self.loader.visited_files, visited_initial)
            self.assertEqual(self.loader.loaded_ontologies, loaded_initial)

    def test_init_imports(self):
        """Test that init_imports loads multiple ontologies."""
        with patch('rdflib.Graph.parse', new=fake_parse):
            # Provide a list of ontology sources.
            self.loader.init_imports(["ont1", "ont3"])
            # Both should be marked as visited.
            self.assertIn("ont1", self.loader.visited_files)
            self.assertIn("ont3", self.loader.visited_files)
            # For ont1, the IRI is from its triple.
            self.assertIn("http://example.org/ont1", self.loader.loaded_ontologies)
            # For ont3, no owl:Ontology triple is added, so fallback uses the source string.
            self.assertIn("ont3", self.loader.loaded_ontologies)
            # Also, ont1 recursively loads ont2.
            self.assertIn("ont2", self.loader.visited_files)
            self.assertIn("http://example.org/ont2", self.loader.loaded_ontologies)

    def test_verbose_print(self):
        """Test that verbose mode prints the expected output during loading."""
        with patch('rdflib.Graph.parse', new=fake_parse):
            with patch('builtins.print') as mock_print:
                loader_verbose = OntologyLoader(verbose=True)
                loader_verbose.load_ontology("ont1")
                # Expect a print call with a message containing the ontology IRI and source.
                mock_print.assert_called_with(
                   'Importing http://example.org/ont2 from url ont2.'
                )

if __name__ == "__main__":
    unittest.main()
