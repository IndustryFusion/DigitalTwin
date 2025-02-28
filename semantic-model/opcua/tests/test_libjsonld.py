# tests/test_jsonld.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from lib.jsonld import JsonLd
import lib.utils as utils
from rdflib.namespace import XSD, RDF
from lib.jsonld import nested_json_from_graph
import json


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
        result, _ = JsonLd.map_datatype_to_jsonld(self.opcuans['Boolean'], self.opcuans)
        self.assertEqual(result, [XSD.boolean])

        # Integer type test
        result, _ = JsonLd.map_datatype_to_jsonld(self.opcuans['Int32'], self.opcuans)
        self.assertEqual(result, [XSD.integer])

        # Double type test
        result, _ = JsonLd.map_datatype_to_jsonld(self.opcuans['Double'], self.opcuans)
        self.assertEqual(result, [XSD.double])
        

        # Unknown type test
        result, _ = JsonLd.map_datatype_to_jsonld(self.opcuans['UnknownType'], self.opcuans)
        self.assertEqual(result, [RDF.JSON])
        
        # Test Number
        result, regexp = JsonLd.map_datatype_to_jsonld(self.opcuans['Number'], self.opcuans)
        self.assertEqual(result, [XSD.double, XSD.integer])

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

class TestNestedJsonFromGraph(unittest.TestCase):
    def test_nested_json_from_graph_valid(self):
        """Test converting a graph with a blank node to a nested JSON object."""
        # Set up a simple graph
        graph = Graph()
        ex = Namespace("http://example.org/")
        person = URIRef(ex + "person/1")
        name = URIRef(ex + "name")
        knows = URIRef(ex + "knows")
        blank = BNode()

        # Add triples:
        # person has a name "Alice"
        graph.add((person, name, Literal("Alice")))
        # person knows someone (a blank node) who has a name "John Doe"
        graph.add((person, knows, blank))
        graph.add((blank, name, Literal("John Doe")))

        # Convert the graph to nested JSON (root will be auto‑selected as person)
        nested = nested_json_from_graph(graph)

        # Assert that the root node is the non‑blank node "person"
        self.assertEqual(nested.get("@id"), str(person))
        # Check that the direct property (name) is set correctly
        self.assertEqual(nested.get(str(name)), {'@value': 'Alice'})
        # Check that the blank node linked via "knows" is inlined (and its @id is omitted)
        knows_value = nested.get(str(knows))
        self.assertIsInstance(knows_value, dict)
        self.assertNotIn("@id", knows_value)
        self.assertEqual(knows_value.get(str(name)), {'@value': 'John Doe'})

    def test_nested_json_from_graph_invalid_root(self):
        """Test that specifying a non‑existent root node raises a ValueError."""
        graph = Graph()
        ex = Namespace("http://example.org/")
        person = URIRef(ex + "person/1")
        # Add a simple triple
        graph.add((person, URIRef(ex + "name"), Literal("Alice")))

        # Passing a root that does not exist in the graph should raise a ValueError
        with self.assertRaises(ValueError) as context:
            nested_json_from_graph(graph, root="http://nonexistent.org")
        self.assertIn("Specified root node not found in the graph.", str(context.exception))

class TestNestedJsonFromGraphAdditional(unittest.TestCase):
    @patch("pyld.jsonld.flatten")
    def test_dict_without_id(self, mock_flatten):
        """
        Test that when a property value is a dictionary without an "@id",
        it is not processed further and remains unchanged.
        """
        # Define a custom flattened structure where the "prop" key's value is a dict without "@id".
        custom_flattened = [{
            "@id": "http://example.org/root",
            "prop": {"value": "something"}
        }]
        mock_flatten.return_value = custom_flattened

        # Create a dummy graph; its contents won't matter due to our patches.
        graph = Graph()
        # Patch the graph.serialize method to return valid JSON (the content here is irrelevant).
        with patch.object(graph, "serialize", return_value=json.dumps({})):
            nested = nested_json_from_graph(graph)

        # The branch under test (a dict without "@id") should simply return the dict as is.
        self.assertEqual(nested.get("prop"), {"value": "something"})

if __name__ == "__main__":
    unittest.main()
