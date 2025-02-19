# tests/test_utils.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDFS, XSD, OWL
from rdflib.collection import Collection
from lib.utils import RdfUtils, downcase_string, isNodeId, convert_to_json_type, idtype2String, extract_namespaces, \
                                get_datatype, attributename_from_type, get_default_value, get_value, normalize_angle_bracket_name, \
                                contains_both_angle_brackets, get_typename, get_common_supertype, rdfStringToPythonBool

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
        graph.add((node, self.basens['hasDatatype'], XSD.string))
        
        result = get_datatype(graph, node, self.basens)
        self.assertEqual(result, XSD.string)

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

    def test_rdfStringToPythonBool(self):
        """Test getting the default value for a datatype."""
        self.assertEqual(rdfStringToPythonBool(Literal('false')), False)
        self.assertEqual(rdfStringToPythonBool(Literal('true')), True)

    def test_get_value(self):
        """Test getting the converted value for a datatype."""
        g = Graph()
        bnode = BNode()
        collection = Collection(g, bnode, [Literal(0), Literal(1), Literal(2)])
        self.assertEqual(get_value(g, '99', [XSD.integer]), int(99))
        self.assertEqual(get_value(g, '0.123', [XSD.double]), float(0.123))
        self.assertEqual(get_value(g, 'hello', [XSD.string]), str('hello'))
        self.assertEqual(get_value(g, 'True', [XSD.boolean]), True)
        self.assertEqual(get_value(g, bnode, [XSD.integer]), {'@list': [ 0, 1, 2 ]})
        
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


    @patch.object(Graph, 'query', return_value=[(URIRef("http://example.org/reference"), URIRef("http://example.org/target"))])
    def test_get_generic_references(self, mock_query):
        """Test retrieving generic references from the RDF graph."""
        g = Graph()
        node = URIRef("http://example.org/node")

        references = self.rdf_utils.get_generic_references(g, node)
        self.assertEqual(references, [(URIRef("http://example.org/reference"), URIRef("http://example.org/target"))])
        mock_query.assert_called_once()

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

        # Case 1: Node is an instancetype definition
        graph.objects.side_effect = [
            iter([URIRef("http://example.org/TypeNode")]),  # definesType found
            iter([URIRef("http://example.org/SuperClass")]),  # RDFS.subClassOf found
        ]
        graph.subjects.side_effect = [
            iter([URIRef("http://example.org/TypeNode")]),  # definesType found for supertype
        ]

        supertypes = self.rdf_utils.get_all_supertypes(graph, instancetype, node)

        expected_supertypes = [
            (URIRef("http://example.org/InstanceType"), URIRef("http://example.org/Node")),
            (URIRef("http://example.org/SuperClass"), URIRef("http://example.org/TypeNode"))
        ]
        self.assertEqual(supertypes, expected_supertypes)

        # Reset mocks for next case
        graph.objects.reset_mock()
        graph.subjects.reset_mock()

        # Case 2: Node is not an instancetype definition, with no additional supertypes
        graph.objects.side_effect = [
            iter([]),  # No definesType found for the node
            iter([]),  # No RDFS.subClassOf found
        ]
        graph.subjects.side_effect = [
            iter([URIRef("http://example.org/TypeNode")]),  # definesType found for current type
        ]

        supertypes = self.rdf_utils.get_all_supertypes(graph, instancetype, node)
        expected_supertypes = [
            (None, node),
            (URIRef("http://example.org/InstanceType"), URIRef("http://example.org/TypeNode"))
        ]
        self.assertEqual(supertypes, expected_supertypes)

        # Reset mocks for next case
        graph.object.reset_mock()
        graph.subjects.reset_mock()

        # Case 3: BaseObjectType is reached, ending the loop
        graph.objects.side_effect = [
            iter([URIRef("http://example.org/TypeNode")]),  # definesType found
            iter([self.opcuans['BaseObjectType']]),  # BaseObjectType reached
        ]
        graph.subjects.side_effect = [
            iter([URIRef("http://example.org/TypeNode")]),  # definesType found for supertype
        ]

        supertypes = self.rdf_utils.get_all_supertypes(graph, instancetype, node)
        expected_supertypes = [
            (URIRef("http://example.org/InstanceType"), node)
        ]
        self.assertEqual(supertypes, expected_supertypes)

        # Reset mocks for next case
        graph.objects.reset_mock()
        graph.subjects.reset_mock()

        # Case 4: Properly terminate the loop when BaseObjectType is the highest superclass
        graph.objects.side_effect = [
            iter([URIRef("http://example.org/TypeNode")]),  # definesType found
            iter([self.opcuans['BaseObjectType']]),  # BaseObjectType reached
            iter([]),  # No further subclass
        ]
        graph.subjects.side_effect = [
            iter([URIRef("http://example.org/TypeNode")]),  # definesType for current type
            iter([]),  # No further subjects for definesType
        ]

        supertypes = self.rdf_utils.get_all_supertypes(graph, instancetype, node)
        expected_supertypes = [
            (URIRef("http://example.org/InstanceType"), node)
        ]
        self.assertEqual(supertypes, expected_supertypes)


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


if __name__ == "__main__":
    unittest.main()
