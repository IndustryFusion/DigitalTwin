# tests/test_entity.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, OWL, RDFS
from lib.entity import Entity
import lib.utils as utils

class TestEntity(unittest.TestCase):

    def setUp(self):
        """Set up common test data."""
        self.namespace_prefix = "http://example.org/"
        self.basens = Namespace("http://example.org/base/")
        self.opcuans = Namespace("http://example.org/opcua/")
        self.entity_instance = Entity(self.namespace_prefix, self.basens, self.opcuans)

    def test_add_type(self):
        """Test adding a type to the internal list."""
        type_uri = URIRef("http://example.org/type")
        self.entity_instance.add_type(type_uri)
        self.assertIn(type_uri, self.entity_instance.types)

    def test_add_instancetype(self):
        """Test adding instance type information to the RDF graph."""
        instancetype = URIRef("http://example.org/type")
        attributename = "attributeName"
        self.entity_instance.add_instancetype(instancetype, attributename)

        triples = list(self.entity_instance.get_graph())
        self.assertIn((self.entity_instance.entity_namespace[attributename], RDF.type, OWL.ObjectProperty), triples)
        self.assertIn((self.entity_instance.entity_namespace[attributename], RDFS.domain, instancetype), triples)
        self.assertIn((self.entity_instance.entity_namespace[attributename], RDF.type, OWL.NamedIndividual), triples)

    @patch.object(Graph, 'serialize', return_value=None)
    def test_serialize(self, mock_serialize):
        """Test serializing the RDF graph to a file."""
        destination = "test_output.ttl"
        
        # Add a triple to the graph
        self.entity_instance.add((URIRef("http://example.org/s"), RDF.type, URIRef("http://example.org/o")))

        # Call the serialize method
        self.entity_instance.serialize(destination)

        # Check that e.serialize was called with the correct arguments
        mock_serialize.assert_called_once_with(destination)


    def test_add_enum_class(self):
        """Test adding an enum class to the RDF graph."""
        contentclass = URIRef("http://example.org/enumClass")
        graph = Graph()

        # Mocking query results
        mock_result = [(URIRef("http://example.org/s"), URIRef("http://example.org/p"), URIRef("http://example.org/o"))]
        graph.query = MagicMock(return_value=mock_result)

        self.entity_instance.add_enum_class(graph, contentclass)

        triples = list(self.entity_instance.get_graph())
        self.assertIn((URIRef("http://example.org/s"), URIRef("http://example.org/p"), URIRef("http://example.org/o")), triples)
        graph.query.assert_called_once()

if __name__ == "__main__":
    unittest.main()
