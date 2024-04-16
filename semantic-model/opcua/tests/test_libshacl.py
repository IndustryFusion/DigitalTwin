# tests/test_shacl.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS, SH
from urllib.parse import urlparse
from lib.shacl import Shacl
import lib.utils as utils
from lib.jsonld import JsonLd

class TestShacl(unittest.TestCase):

    def setUp(self):
        """Set up common test data."""
        self.namespace_prefix = "http://example.org/"
        self.basens = Namespace("http://example.org/base/")
        self.opcuans = Namespace("http://example.org/opcua/")
        self.shacl_instance = Shacl(self.namespace_prefix, self.basens, self.opcuans)

    def test_create_shacl_type(self):
        """Test creating a SHACL type in the RDF graph."""
        targetclass = "http://example.org/TargetClass"
        shapename = self.shacl_instance.create_shacl_type(targetclass)

        triples = list(self.shacl_instance.get_graph())
        self.assertIn((shapename, RDF.type, SH.NodeShape), triples)
        self.assertIn((shapename, SH.targetClass, URIRef(targetclass)), triples)

    def test_create_shacl_property(self):
        """Test creating a SHACL property in the RDF graph."""
        shapename = URIRef("http://example.org/shacl/ShapeName")
        path = URIRef("http://example.org/path")
        optional = True
        is_array = False
        is_property = True
        is_iri = False
        contentclass = None
        datatype = URIRef("http://www.w3.org/2001/XMLSchema#string")

        self.shacl_instance.create_shacl_property(shapename, path, optional, is_array, is_property, is_iri, contentclass, datatype)

        triples = list(self.shacl_instance.get_graph())
        
        # Find the bnodes created for property and innerproperty
        property_bnode = None
        innerproperty_bnode = None

        for s, p, o in triples:
            if s == shapename and p == SH.property:
                property_bnode = o
            elif p == SH.path and o == path:
                property_bnode = s
            elif p == SH.path and (o == self.shacl_instance.ngsildns['hasValue'] or o == self.shacl_instance.ngsildns['hasObject']):
                innerproperty_bnode = s

        # Check that the BNodes exist and are properly linked
        self.assertIsNotNone(property_bnode)
        self.assertIsInstance(property_bnode, BNode)
        self.assertIn((shapename, SH.property, property_bnode), triples)
        self.assertIn((property_bnode, SH.path, path), triples)

        self.assertIsNotNone(innerproperty_bnode)
        self.assertIsInstance(innerproperty_bnode, BNode)
        self.assertIn((property_bnode, SH.property, innerproperty_bnode), triples)

    def test_get_typename(self):
        """Test extracting type name from a URL."""
        url = "http://example.org/Type#MyType"
        result = self.shacl_instance.get_typename(url)
        self.assertEqual(result, "MyType")

        url = "http://example.org/Type/MyType"
        result = self.shacl_instance.get_typename(url)
        self.assertEqual(result, "MyType")

    def test_bind(self):
        """Test binding a prefix to a namespace in the RDF graph."""
        prefix = 'ex'
        namespace = Namespace('http://example.org/ex/')
        self.shacl_instance.bind(prefix, namespace)

        bindings = dict(self.shacl_instance.get_graph().namespaces())
        self.assertIn(prefix, bindings)
        self.assertEqual(str(bindings[prefix]), str(namespace))

    @patch.object(Graph, 'serialize', return_value=None)
    def test_serialize(self, mock_serialize):
        """Test serializing the RDF graph to a file."""
        destination = "test_output.ttl"
        
        # Add a triple to the graph
        self.shacl_instance.shaclg.add((URIRef("http://example.org/s"), RDF.type, URIRef("http://example.org/o")))

        # Call the serialize method
        self.shacl_instance.serialize(destination)

        # Check that shaclg.serialize was called with the correct arguments
        mock_serialize.assert_called_once_with(destination)

    @patch('lib.utils.get_datatype', return_value=URIRef("http://example.org/datatype"))
    @patch('lib.jsonld.JsonLd.map_datatype_to_jsonld', return_value=Literal("xsd:string"))
    def test_get_shacl_iri_and_contentclass(self, mock_map_datatype_to_jsonld, mock_get_datatype):
        """Test retrieving SHACL IRI and content class."""
        g = Graph()
        node = URIRef("http://example.org/node")
        shacl_rule = {}

        # Mocking graph objects
        g.objects = MagicMock(side_effect=[
            iter([URIRef("http://example.org/Enumeration")]),  # RDFS.subClassOf
        ])

        self.shacl_instance.get_shacl_iri_and_contentclass(g, node, shacl_rule)

        self.assertFalse(shacl_rule['is_iri'])
        self.assertIsNone(shacl_rule['contentclass'])
        mock_get_datatype.assert_called_once_with(g, node, self.basens)

    @patch.object(Graph, 'query', return_value=[(Literal(0), Literal(1))])
    def test_get_modelling_rule(self, mock_query):
        """Test retrieving modeling rules from SHACL graph."""
        path = URIRef("http://example.org/path")
        target_class = URIRef("http://example.org/TargetClass")

        optional, array = self.shacl_instance.get_modelling_rule(path, target_class)
        
        self.assertTrue(optional)
        self.assertFalse(array)
        mock_query.assert_called_once()

if __name__ == "__main__":
    unittest.main()
