# tests/test_entity.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, OWL, RDFS
from lib.entity import Entity, query_instance, query_default_instance
import lib.utils as utils

class DummyRow:
    """Helper class to simulate a query result row with an 'instance' attribute."""
    def __init__(self, instance):
        self.instance = instance


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


    def test_get_contentclass_found(self):
        """Test get_contentclass when a matching instance is found."""
        # Create a dummy instance URI that the query should return.
        dummy_instance = URIRef("http://example.org/instance")
        dummy_result = [DummyRow(dummy_instance)]

        # Patch the query method on the internal graph to return our dummy result.
        self.entity_instance.e.query = MagicMock(return_value=dummy_result)

        contentclass = URIRef("http://example.org/enumClass")
        value = Literal("some value")

        result = self.entity_instance.get_contentclass(contentclass, value)

        # Verify that the query was called with the proper bindings.
        expected_bindings = {'c': contentclass, 'value': value}
        self.entity_instance.e.query.assert_called_once_with(
            query_instance,
            initBindings=expected_bindings,
            initNs={'base': self.basens, 'opcua': self.opcuans}
        )

        # The method should return our dummy instance.
        self.assertEqual(result, dummy_instance)

    def test_get_contentclass_not_found(self):
        """Test get_contentclass when no matching instance is found."""
        # Simulate an empty query result.
        self.entity_instance.e.query = MagicMock(return_value=[])

        contentclass = URIRef("http://example.org/enumClass")
        value = Literal("some value")

        # Use the patch context manager to intercept print calls.
        with patch('builtins.print') as mock_print:
            result = self.entity_instance.get_contentclass(contentclass, value)

        # Verify that the result is None.
        self.assertIsNone(result)

        # Verify that the warning message was printed.
        mock_print.assert_called_once_with(
            f'Warning: no instance found for class {contentclass} with value {value}'
        )

    def test_get_default_contentclass_found(self):
        """Test get_default_contentclass when a default instance is found."""
        dummy_instance = URIRef("http://example.org/default_instance")
        dummy_result = [DummyRow(dummy_instance)]

        self.entity_instance.e.query = MagicMock(return_value=dummy_result)

        contentclass = URIRef("http://example.org/enumClass")
        result = self.entity_instance.get_default_contentclass(contentclass)

        expected_bindings = {'c': contentclass}
        self.entity_instance.e.query.assert_called_once_with(
            query_default_instance,
            initBindings=expected_bindings,
            initNs={'base': self.basens, 'opcua': self.opcuans}
        )
        self.assertEqual(result, dummy_instance)

    def test_get_default_contentclass_not_found(self):
        """Test get_default_contentclass when no default instance is found."""
        self.entity_instance.e.query = MagicMock(return_value=[])

        contentclass = URIRef("http://example.org/enumClass")
        with patch('builtins.print') as mock_print:
            result = self.entity_instance.get_default_contentclass(contentclass)

        self.assertIsNone(result)

    def test_create_ontolgoy_header_default(self):
        """Test create_ontolgoy_header without providing a versionIRI."""
        entity_ns = "http://example.org/ontology"
        # Call the method without versionIRI.
        self.entity_instance.create_ontolgoy_header(entity_ns)
        graph = list(self.entity_instance.get_graph())

        # Check that the ontology triple was added.
        self.assertIn((URIRef(entity_ns), RDF.type, OWL.Ontology), graph)
        # Check that the versionInfo triple was added.
        self.assertIn((URIRef(entity_ns), OWL.versionInfo, Literal(0.1)), graph)
        # Verify that no versionIRI triple was added.
        versionIRI_triples = [triple for triple in graph if triple[0] == URIRef(entity_ns) and triple[1] == OWL.versionIRI]
        self.assertEqual(len(versionIRI_triples), 0)

    def test_create_ontolgoy_header_with_versionIRI(self):
        """Test create_ontolgoy_header when a versionIRI is provided."""
        entity_ns = "http://example.org/ontology"
        versionIRI_value = URIRef("http://example.org/version")
        # Call the method with a versionIRI.
        self.entity_instance.create_ontolgoy_header(entity_ns, version=0.1, versionIRI=versionIRI_value)
        graph = list(self.entity_instance.get_graph())

        # Check that the ontology triple was added.
        self.assertIn((URIRef(entity_ns), RDF.type, OWL.Ontology), graph)
        # Check that the versionInfo triple was added.
        self.assertIn((URIRef(entity_ns), OWL.versionInfo, Literal(0.1)), graph)
        # Check that the versionIRI triple was added.
        self.assertIn((URIRef(entity_ns), OWL.versionIRI, versionIRI_value), graph)
    def test_bind(self):
        """Test that the bind method correctly binds a prefix to a namespace."""
        test_prefix = "test"
        test_namespace = Namespace("http://example.org/test/")
        self.entity_instance.bind(test_prefix, test_namespace)
        # Convert the namespace bindings into a dictionary for easy lookup.
        namespaces = dict(self.entity_instance.get_graph().namespace_manager.namespaces())
        self.assertIn(test_prefix, namespaces)
        self.assertEqual(str(namespaces[test_prefix]), str(test_namespace))

    def test_add_subclass(self):
        """Test that add_subclass correctly adds the required triples to the RDF graph."""
        subclass_uri = URIRef("http://example.org/subclass")
        self.entity_instance.add_subclass(subclass_uri)
        triples = list(self.entity_instance.get_graph())
        # Verify that the triple for OWL.Class is added.
        self.assertIn((subclass_uri, RDF.type, OWL.Class), triples)
        # Verify that the triple for OWL.NamedIndividual is added.
        self.assertIn((subclass_uri, RDF.type, OWL.NamedIndividual), triples)
        # Verify that the triple for RDFS.subClassOf to BaseObjectType is added.
        expected_base_obj = self.opcuans['BaseObjectType']
        self.assertIn((subclass_uri, RDFS.subClassOf, expected_base_obj), triples)

    def test_add_subclasses(self):
        """Test that add_subclasses correctly adds all triples from a given Graph to the internal RDF graph."""
        # Create a temporary graph with some triples.
        temp_graph = Graph()
        triple1 = (URIRef("http://example.org/s"), RDF.type, URIRef("http://example.org/o"))
        triple2 = (URIRef("http://example.org/a"), RDFS.label, Literal("Test"))
        temp_graph.add(triple1)
        temp_graph.add(triple2)

        # Call add_subclasses to add triples from temp_graph to the entity's graph.
        self.entity_instance.add_subclasses(temp_graph)

        # Retrieve the triples from the internal RDF graph.
        entity_triples = list(self.entity_instance.get_graph())
        self.assertIn(triple1, entity_triples)
        self.assertIn(triple2, entity_triples)

if __name__ == "__main__":
    unittest.main()
