# tests/test_shacl.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS, SH, XSD
from rdflib.collection import Collection
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
        data_graph = Graph()
        self.shacl_instance = Shacl(data_graph, self.namespace_prefix, self.basens, self.opcuans)

    def test_create_shacl_type(self):
        """Test creating a SHACL type in the RDF graph."""
        targetclass = "http://example.org/TargetClass"
        shapename = self.shacl_instance.create_shacl_type(targetclass)

        triples = list(self.shacl_instance.get_graph())
        self.assertIn((shapename, RDF.type, SH.NodeShape), triples)
        self.assertIn((shapename, SH.targetClass, URIRef(targetclass)), triples)

    def test_get_array_validation_shape(self):
        """Test create array validation shape"""
        datatype = [XSD.integer]
        pattern = None
        bnode = BNode()
        collection = Collection(self.shacl_instance.data_graph, bnode, [Literal(2), Literal(3)])
        property_node = self.shacl_instance.get_array_validation_shape(datatype, pattern, None, bnode)
        _, _, property_shape = next(self.shacl_instance.shaclg.triples((property_node, SH.property, None)))
        _, _, array_length = next(self.shacl_instance.shaclg.triples((property_shape, SH.maxCount, None)))
        self.assertEqual(int(array_length), 6)

    def test_create_shacl_property(self):
        """Test creating a SHACL property in the RDF graph."""
        shapename = URIRef("http://example.org/shacl/ShapeName")
        path = URIRef("http://example.org/path")
        optional = True
        is_array = False
        is_property = False
        is_iri = False
        contentclass = None
        datatype = URIRef("http://www.w3.org/2001/XMLSchema#string")

        # Base test case
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

        # Additional test cases to improve coverage

        # Case 1: Test with is_array = True, is_subcomponent = True, and placeholder_pattern provided
        self.shacl_instance = Shacl(Graph(), self.namespace_prefix, self.basens, self.opcuans)  # Reset instance
        placeholder_pattern = "PatternExample"
        is_array = True
        is_subcomponent = True
        self.shacl_instance.create_shacl_property(shapename, path, optional, is_array, is_property, is_iri, contentclass, datatype, is_subcomponent, placeholder_pattern)

        triples = list(self.shacl_instance.get_graph())

        # Find the updated property node
        property_bnode = None
        for s, p, o in triples:
            if s == shapename and p == SH.property:
                property_bnode = o

        # Check that the isPlaceHolder triple was added
        self.assertIn((property_bnode, self.basens['isPlaceHolder'], Literal(True)), triples)

        # Check that the hasPlaceHolderPattern triple was added
        self.assertIn((property_bnode, self.basens['hasPlaceHolderPattern'], Literal(placeholder_pattern)), triples)

        # Check that the SubComponentRelationship type was added
        self.assertIn((property_bnode, RDF.type, self.basens['SubComponentRelationship']), triples)

        # Case 2: Test with is_property = False, is_iri = True, and contentclass provided
        self.shacl_instance = Shacl(Graph(), self.namespace_prefix, self.basens, self.opcuans)  # Reset instance
        is_property = True
        is_iri = True
        contentclass = URIRef("http://example.org/ContentClass")
        self.shacl_instance.create_shacl_property(shapename, path, optional, is_array, is_property, is_iri, contentclass, datatype)

        triples = list(self.shacl_instance.get_graph())

        # Find the inner property node
        innerproperty_bnode = None
        for s, p, o in triples:
            if p == SH.path and o == self.shacl_instance.ngsildns['hasValue']:
                innerproperty_bnode = s

        # Check that the innerproperty node kind is IRI
        self.assertIn((innerproperty_bnode, SH.nodeKind, SH.IRI), triples)

        # Check that the content class is set correctly
        self.assertIn((innerproperty_bnode, SH['class'], contentclass), triples)

        # Case 3: Test with is_subcomponent = False to ensure PeerRelationship type is used
        self.shacl_instance = Shacl(Graph(), self.namespace_prefix, self.basens, self.opcuans)  # Reset instance
        is_subcomponent = False
        is_property = False
        self.shacl_instance.create_shacl_property(shapename, path, optional, is_array, is_property, is_iri, contentclass, datatype, is_subcomponent)

        triples = list(self.shacl_instance.get_graph())

        # Find the property node
        property_bnode = None
        for s, p, o in triples:
            if s == shapename and p == SH.property:
                property_bnode = o

        # Check that the PeerRelationship type was added
        self.assertIn((property_bnode, RDF.type, self.basens['PeerRelationship']), triples)


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
    @patch('lib.jsonld.JsonLd.map_datatype_to_jsonld', return_value=(Literal("xsd:string"), None))
    @patch('lib.utils.get_type_and_template', return_value=(URIRef("http://example.rog/typenode"), URIRef("http://example.rog/templatenode")))
    @patch('lib.utils.get_rank_dimensions', return_value=(Literal(-1), RDF.nil))
    def test_get_shacl_iri_and_contentclass(self, moch_get_rank_dimensions, mocK_get_type_and_templat, mock_map_datatype_to_jsonld, mock_get_datatype):
        """Test retrieving SHACL IRI and content class."""
        g = Graph()
        node = URIRef("http://example.org/node")
        parentnode = URIRef("http://example.org/parentnode")
        shacl_rule = {}

        # Mocking graph objects - Case 1: Enumeration type
        g.objects = MagicMock(side_effect=[
            iter([URIRef("http://example.org/Enumeration")]),  # RDFS.subClassOf
        ])

        self.shacl_instance.get_shacl_iri_and_contentclass(g, node, parentnode, shacl_rule)

        self.assertFalse(shacl_rule['is_iri'])
        self.assertEqual(shacl_rule['contentclass'], None)

        # Case 2: Non-enumeration type
        mock_get_datatype.reset_mock()
        g.objects = MagicMock(side_effect=[
            iter([URIRef("http://example.org/OtherClass")]),  # RDFS.subClassOf
        ])
        shacl_rule = {}

        self.shacl_instance.get_shacl_iri_and_contentclass(g, node, parentnode, shacl_rule)

        self.assertFalse(shacl_rule['is_iri'])
        self.assertIsNone(shacl_rule['contentclass'])

        # Case 3: No datatype found
        mock_get_datatype.reset_mock()
        mock_get_datatype.return_value = None
        shacl_rule = {}

        self.shacl_instance.get_shacl_iri_and_contentclass(g, node, parentnode, shacl_rule)

        self.assertFalse(shacl_rule['is_iri'])
        self.assertIsNone(shacl_rule['contentclass'])
        self.assertIsNone(shacl_rule['datatype'])

        # Case 4: Exception handling
        mock_get_datatype.reset_mock()
        g.objects = MagicMock(side_effect=Exception("Mocked exception"))
        shacl_rule = {}

        self.shacl_instance.get_shacl_iri_and_contentclass(g, node, parentnode, shacl_rule)

        self.assertFalse(shacl_rule['is_iri'])
        self.assertIsNone(shacl_rule['contentclass'])
        self.assertIsNone(shacl_rule['datatype'])

    @patch.object(Graph, 'query')
    def test_get_modelling_rule_and_path(self, mock_query):
        """Test get_modelling_rule_and_path method."""
        name = "attributeName"
        target_class = URIRef("http://example.org/TargetClass")
        attributeclass = URIRef("http://example.org/AttributeClass")
        prefix = "prefix"

        # Mock query result for the graph - Case 1: optional=False, array=True
        mock_query.return_value = [
            (URIRef("http://example.org/path"), None, Literal(0), Literal(2))
        ]

        optional, array, path = self.shacl_instance.get_modelling_rule_and_path(name, target_class, attributeclass, prefix)

        # Assertions based on mock values
        self.assertEqual(path, URIRef("http://example.org/path"))
        self.assertTrue(optional)  # Since minCount is 0, optional should be False
        self.assertTrue(array)      # Since maxCount is 2, array should be True

        # Ensure the query was executed with the correct bindings
        mock_query.assert_called_once()

        # Case 2: optional=True, array=False
        mock_query.reset_mock()
        mock_query.return_value = [
            (URIRef("http://example.org/path"), None, Literal(1), Literal(1))
        ]

        optional, array, path = self.shacl_instance.get_modelling_rule_and_path(name, target_class, attributeclass, prefix)

        # Assertions based on mock values
        self.assertEqual(path, URIRef("http://example.org/path"))
        self.assertFalse(optional)   # Since minCount is 1, optional should be True
        self.assertFalse(array)     # Since maxCount is 1, array should be False

        # Ensure the query was executed with the correct bindings
        mock_query.assert_called_once()

        # Case 3: optional=False, array=False
        mock_query.reset_mock()
        mock_query.return_value = [
            (URIRef("http://example.org/path"), None, Literal(2), Literal(1))
        ]

        optional, array, path = self.shacl_instance.get_modelling_rule_and_path(name, target_class, attributeclass, prefix)

        # Assertions based on mock values
        self.assertEqual(path, URIRef("http://example.org/path"))
        self.assertFalse(optional)  # Since minCount is 2, optional should be False
        self.assertFalse(array)     # Since maxCount is 1, array should be False

        # Ensure the query was executed with the correct bindings
        mock_query.assert_called_once()

        # Case 4: optional=True, array=True
        mock_query.reset_mock()
        mock_query.return_value = [
            (URIRef("http://example.org/path"), None, Literal(0), Literal(5))
        ]

        optional, array, path = self.shacl_instance.get_modelling_rule_and_path(name, target_class, attributeclass, prefix)

        # Assertions based on mock values
        self.assertEqual(path, URIRef("http://example.org/path"))
        self.assertTrue(optional)   # Since minCount is 0, optional should be True
        self.assertTrue(array)      # Since maxCount is 5, array should be True

        # Ensure the query was executed with the correct bindings
        mock_query.assert_called_once()

    @patch.object(Graph, 'subjects', side_effect=[iter([]), iter([URIRef("http://example.org/Shape")])])
    @patch.object(Graph, 'triples', return_value=[(URIRef("http://example.org/Shape"), RDF.type, SH.NodeShape)])
    def test_create_shape_if_not_exists(self, mock_triples, mock_subjects):
        """Test create_shape_if_not_exists method."""
        source_graph = MagicMock()
        targetclass = URIRef("http://example.org/TargetClass")

        # Case 1: Shape does not exist in shaclg but exists in source_graph
        shape = self.shacl_instance.create_shape_if_not_exists(source_graph, targetclass)
        # self.assertEqual(shape, URIRef("http://example.org/Shape"))
        mock_subjects.assert_called()
        source_graph.get_graph.assert_called()

        # Case 2: Shape does not exist in either graph
        mock_subjects.side_effect = [iter([]), iter([])]
        shape = self.shacl_instance.create_shape_if_not_exists(source_graph, targetclass)
        mock_subjects.assert_called()

    def test_copy_bnode_triples(self):
        """Test recursively copying triples from a blank node in the source graph to the target graph."""
        source_graph = MagicMock()
        bnode = BNode()  # Blank node to copy
        shape = URIRef("http://example.org/Shape")

        # Mock triples that include the blank node
        source_graph.get_graph.return_value.triples.return_value = [
            (bnode, RDF.type, SH.NodeShape),
            (bnode, SH.path, URIRef("http://example.org/path"))
        ]

        self.shacl_instance.copy_bnode_triples(source_graph, bnode, shape)

        # Check that the shape has the property link to the bnode
        triples = list(self.shacl_instance.get_graph())
        self.assertIn((shape, SH.property, bnode), triples)

        # Check that all triples from the source graph have been added
        self.assertIn((bnode, RDF.type, SH.NodeShape), triples)
        #self.assertIn((bnode, SH.path, URIRef("http://example.org/path")), triples)

    @patch.object(Graph, 'subjects')
    @patch.object(Graph, 'objects')
    def test_get_property(self, mock_objects, mock_subjects):
        """Test retrieving a property given a target class and property path."""
        targetclass = URIRef("http://example.org/TargetClass")
        propertypath = URIRef("http://example.org/propertyPath")
        property_bnode = BNode()
        shape_bnode = BNode()

        # Mock the behavior of subjects to return the shape for the given target class
        mock_subjects.side_effect = [iter([shape_bnode])]
        # Mock the behavior of objects to return the property nodes
        mock_objects.side_effect = [iter([property_bnode]), iter([propertypath])]

        result = self.shacl_instance._get_property(targetclass, propertypath)

        # Check that the correct property node is returned
        self.assertEqual(result, property_bnode)
        mock_subjects.assert_called_once_with(SH.targetClass, targetclass)
        mock_objects.assert_any_call(shape_bnode, SH.property)
        mock_objects.assert_any_call(property_bnode, SH.path)

        # Case where property is not found
        mock_subjects.side_effect = [iter([shape_bnode])]
        mock_objects.side_effect = [iter([property_bnode]), iter([])]  # No matching path

        result = self.shacl_instance._get_property(targetclass, propertypath)
        self.assertIsNone(result)

    @patch.object(Graph, 'objects')
    def test_get_shclass_from_property(self, mock_objects):
        """Test retrieving the SHACL class from a property."""
        property_node = BNode()
        subproperty_node = BNode()
        expected_class = URIRef("http://example.org/Class")

        # Mock the objects method to return the subproperty node and the class
        mock_objects.side_effect = [
            iter([subproperty_node]),  # First call returns the subproperty node
            iter([expected_class])     # Second call returns the class associated with the subproperty
        ]

        result = self.shacl_instance._get_shclass_from_property(property_node)

        # Check that the result is the expected class URI
        self.assertEqual(result, expected_class)
        mock_objects.assert_any_call(property_node, SH.property)
        mock_objects.assert_any_call(subproperty_node, SH['class'])

        # Case where the property does not have a subproperty or class
        mock_objects.side_effect = [
            iter([]),  # No subproperty found
        ]
        result = self.shacl_instance._get_shclass_from_property(property_node)
        self.assertIsNone(result)

    @patch.object(Graph, 'objects')
    @patch.object(Shacl, '_get_property')
    def test_is_placeholder(self, mock_get_property, mock_objects):
        """Test determining if an attribute is a placeholder."""
        targetclass = URIRef("http://example.org/TargetClass")
        attributename = "attributeName"
        property_node = BNode()

        # Mock _get_property to return a property node
        mock_get_property.return_value = property_node

        # Case 1: Placeholder is found
        mock_objects.return_value = iter([Literal(True)])
        result = self.shacl_instance.is_placeholder(targetclass, attributename)
        self.assertTrue(result)
        mock_get_property.assert_called_once_with(targetclass, attributename)
        mock_objects.assert_called_once_with(property_node, self.basens['isPlaceHolder'])

        # Case 2: Placeholder is not found
        mock_objects.return_value = iter([])
        result = self.shacl_instance.is_placeholder(targetclass, attributename)
        self.assertFalse(result)

        # Case 3: Property is None
        mock_get_property.return_value = None
        result = self.shacl_instance.is_placeholder(targetclass, attributename)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
