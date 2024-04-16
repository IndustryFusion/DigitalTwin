# tests/test_jsonld.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal
from lib.jsonld import JsonLd
import lib.utils as utils
from rdflib.namespace import XSD


class TestJsonLd(unittest.TestCase):

    def setUp(self):
        """Set up common test data."""
        self.basens = Namespace("http://example.org/base/")
        self.opcuans = Namespace("http://example.org/opcua/")
        self.jsonld_instance = JsonLd(self.basens, self.opcuans)

    def test_add_instance(self):
        """Test adding an instance to the JSON-LD data."""
        instance = {"id": "testId", "type": "TestType"}
        self.jsonld_instance.add_instance(instance)
        self.assertIn(instance, self.jsonld_instance.instances)

    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    @patch("json.dump")
    def test_serialize(self, mock_json_dump, mock_open):
        """Test serializing JSON-LD instances to a file."""
        instance = {"id": "testId", "type": "TestType"}
        self.jsonld_instance.add_instance(instance)

        # Call the serialize method
        self.jsonld_instance.serialize("test_output.json")

        # Check that open was called correctly
        mock_open.assert_called_once_with("test_output.json", "w")

        # Check that json.dump was called with correct data
        mock_json_dump.assert_called_once_with(
            self.jsonld_instance.instances, mock_open(), ensure_ascii=False, indent=4
        )

    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    @patch("json.dump")
    def test_dump_context(self, mock_json_dump, mock_open):
        """Test dumping JSON-LD context to a file."""
        namespaces = {
            "base": {"@id": str(self.basens), "@prefix": True}
        }
        self.jsonld_instance.dump_context("context_output.json", namespaces)

        # Check that open was called correctly
        mock_open.assert_called_once_with("context_output.json", "w")

        # Check that json.dump was called with correct data
        mock_json_dump.assert_called_once_with(
            {
                "@context": [
                    namespaces,
                    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
                ]
            },
            mock_open(),
            indent=2
        )

    def test_map_datatype_to_jsonld(self):
        """Test mapping OPC UA data types to JSON-LD data types."""
        # Boolean type test
        result = JsonLd.map_datatype_to_jsonld(self.opcuans['Boolean'], self.opcuans)
        self.assertEqual(result, XSD.boolean)

        # Integer type test
        result = JsonLd.map_datatype_to_jsonld(self.opcuans['Int32'], self.opcuans)
        self.assertEqual(result, XSD.integer)

        # Double type test
        result = JsonLd.map_datatype_to_jsonld(self.opcuans['Double'], self.opcuans)
        self.assertEqual(result, XSD.double)

        # Unknown type test
        result = JsonLd.map_datatype_to_jsonld(self.opcuans['UnknownType'], self.opcuans)
        self.assertEqual(result, XSD.string)

    @patch("lib.utils.idtype2String", return_value="i")
    def test_generate_node_id(self, mock_idtype2string):
        """Test generating node ID."""
        graph = Graph()
        rootentity = URIRef("http://example.org/root")
        node = URIRef("http://example.org/node")
        id = "testId"

        # Mocking graph objects
        graph.objects = MagicMock(side_effect=[
            iter([Literal("123")]),  # hasNodeId
            iter([Literal("numericID")]),  # hasIdentifierType
            iter([Literal("RootName")])  # hasBrowseName
        ])

        # Test for root entity
        result = self.jsonld_instance.generate_node_id(graph, rootentity, rootentity, id)
        self.assertEqual(result, "testId:RootName")

        graph.objects = MagicMock(side_effect=[
            iter([Literal("123")]),  # hasNodeId
            iter([Literal("numericID")]),  # hasIdentifierType
            iter([Literal("RootName")])  # hasBrowseName
        ])
        # Test for a non-root entity
        result = self.jsonld_instance.generate_node_id(graph, rootentity, node, id)
        self.assertEqual(result, "testId:RootName:sub:i123")


if __name__ == "__main__":
    unittest.main()
