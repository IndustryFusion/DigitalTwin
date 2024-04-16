# tests/test_utils.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDFS, XSD, OWL
from lib.utils import RdfUtils, downcase_string, isNodeId, convert_to_json_type, idtype2String, extract_namespaces, get_datatype, attributename_from_type, get_default_value, normalize_angle_bracket_name, contains_both_angle_brackets, get_typename

class TestUtils(unittest.TestCase):

    def setUp(self):
        """Set up common test data."""
        self.basens = Namespace("http://example.org/base/")
        self.opcuans = Namespace("http://example.org/opcua/")
        self.rdf_utils = RdfUtils(self.basens, self.opcuans)

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
        self.assertEqual(get_default_value(XSD.integer), 0)
        self.assertEqual(get_default_value(XSD.double), 0.0)
        self.assertEqual(get_default_value(XSD.string), '')
        self.assertEqual(get_default_value(XSD.boolean), False)

    def test_normalize_angle_bracket_name(self):
        """Test normalizing a name by removing angle bracket content."""
        input_str = "example<test>123"
        result = normalize_angle_bracket_name(input_str)
        self.assertEqual(result, "example")

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

if __name__ == "__main__":
    unittest.main()
