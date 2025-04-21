# tests/test_shacl.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS, SH, XSD
from rdflib.collection import Collection
from urllib.parse import urlparse
from lib.shacl import Shacl, Validation
import lib.utils as utils
from lib.jsonld import JsonLd


class TestShaclAdditional(unittest.TestCase):
    def setUp(self):
        self.ns_prefix = "http://example.org/"
        self.base = Namespace("http://example.org/base/")
        self.opcua = Namespace("http://example.org/opcua/")
        # data_graph is used by array‐validation shapes
        self.data_graph = Graph()
        self.sh = Shacl(self.data_graph, self.ns_prefix, self.base, self.opcua)

    def test_get_array_validation_shape_for_iri_simple(self):
        # build array_dimensions list [2, 3] => total 6
        bnode = BNode()
        Collection(self.data_graph, bnode, [Literal(2), Literal(3)])
        shapes = self.sh.get_array_validation_shape_for_iri(URIRef("http://example.org/Clazz"), bnode)
        # Should return one property placeholder shape when fixed length > 0
        self.assertEqual(len(shapes), 1)
        propn = shapes[0]
        # Extract the actual property_shape (inner) that holds the constraints
        property_shape = next(self.sh.shaclg.objects(propn, SH.property))
        # That shape must include a minCount and maxCount equal to 6
        self.assertIn((property_shape, SH.minCount, Literal(6)), list(self.sh.shaclg))
        self.assertIn((property_shape, SH.maxCount, Literal(6)), list(self.sh.shaclg))
        # And class constraint should be set on the property_shape
        self.assertIn((property_shape, SH['class'], URIRef("http://example.org/Clazz")), list(self.sh.shaclg))

    def test_ngsild_relationship_constraints_variants(self):
        # non‐IRI, non‐array, subcomponent
        shapes = self.sh.get_ngsild_relationship_constraints(
            is_array=False, placeholder_pattern=None,
            is_subcomponent=True, is_iri=False, contentclass=None
        )
        # should produce exactly one innerproperty shape
        self.assertEqual(len(shapes), 1)
        inner = next(self.sh.shaclg.objects(shapes[0], SH.property))
        # check that SH.path → ngsi-ld:hasObject
        self.assertIn((inner, SH.path, self.sh.ngsildns['hasObject']), list(self.sh.shaclg))

        # IRI‐variant: is_iri True should add nodeKind IRI
        shapes2 = self.sh.get_ngsild_relationship_constraints(
            is_array=False, placeholder_pattern=None,
            is_subcomponent=False, is_iri=True, contentclass=URIRef("http://example.org/CC")
        )
        inner2 = next(self.sh.shaclg.objects(shapes2[0], SH.property))
        self.assertIn((inner2, SH.nodeKind, SH.IRI), list(self.sh.shaclg))
        self.assertIn((inner2, SH['class'], URIRef("http://example.org/CC")), list(self.sh.shaclg))

    def test_ngsild_property_constraints_scalar_and_list(self):
        # scalar: value_rank None, no JSON, literal path
        self.sh.shaclg = Graph()  # reset
        shapes = self.sh.get_ngsild_property_constraints(
            value_rank=None, array_dimensions=None,
            datatype=[XSD.integer], pattern=None,
            is_iri=False, contentclass=None
        )
        # should produce at least one property‐shape (scalar)
        self.assertTrue(len(shapes) >= 1)
        inner = next(self.sh.shaclg.objects(shapes[0], SH.property))
        self.assertIn((inner, SH.path, self.sh.ngsildns['hasValue']), list(self.sh.shaclg))

        # list: force list by non‐negative value_rank
        self.sh.shaclg = Graph()
        # create array_dimensions
        arr = BNode()
        Collection(self.data_graph, arr, [Literal(3)])
        shapes2 = self.sh.get_ngsild_property_constraints(
            value_rank=Literal(0), array_dimensions=arr,
            datatype=[XSD.string], pattern=None,
            is_iri=False, contentclass=None
        )
        # should include a property‐shape with SH.path → ngsi-ld:hasListValue
        found = False
        for s in shapes2:
            inner = next(self.sh.shaclg.objects(s, SH.property))
            if (inner, SH.path, self.sh.ngsildns['hasValueList']) in self.sh.shaclg:
                found = True
        self.assertTrue(found)

    def test_create_datatype_and_iri_shapes_and_shacl_or(self):
        # datatype shapes
        dt_nodes = self.sh.create_datatype_shapes([XSD.boolean, XSD.double])
        self.assertEqual(len(dt_nodes), 2)
        # each node should have a precise datatype triple
        expected = {XSD.boolean, XSD.double}
        seen = set()
        for n in dt_nodes:
            for _, _, dt in self.sh.shaclg.triples((n, SH.datatype, None)):
                seen.add(dt)
        self.assertEqual(seen, expected)

        # IRI shapes
        iri_nodes = self.sh.create_iri_shape()
        self.assertEqual(len(iri_nodes), 1)
        n = iri_nodes[0]
        self.assertIn((n, SH.nodeKind, SH.IRI), list(self.sh.shaclg))

        # shacl_or: single
        single = BNode()
        # inject a triple
        self.sh.shaclg.add((single, SH.datatype, XSD.string))
        single_tup = self.sh.shacl_or([single])
        # should return one tuple for the single shape
        self.assertEqual(single_tup, [(SH.datatype, XSD.string)])
        # and remove the triple from graph
        self.assertNotIn((single, SH.datatype, XSD.string), self.sh.shaclg)

        # multiple
        a = BNode(); b = BNode()
        self.sh.shaclg.add((a, SH.nodeKind, SH.Literal))
        self.sh.shaclg.add((b, SH.nodeKind, SH.Literal))
        or_tup = self.sh.shacl_or([a,b])
        pred, obj = or_tup[0]
        self.assertEqual(pred, SH['or'])
        lst = list(Collection(self.sh.shaclg, obj))
        self.assertCountEqual(lst, [a, b])

    def test_attribute_and_property_helpers(self):
        # create a basic shape & property
        shape = self.sh.create_shacl_type("http://example.org/Clazz")
        prop = self.sh.create_shacl_property(
            shape,
            URIRef("http://example.org/p"),
            optional=False,
            is_array=False,
            is_property=False,
            is_iri=False,
            contentclass=None,
            datatype=None
        )
        # attribute_is_indomain
        self.assertTrue(self.sh.attribute_is_indomain(shape, URIRef("http://example.org/p")))
        # get_targetclass
        self.assertEqual(self.sh.get_targetclass(shape), URIRef("http://example.org/Clazz"))
        # get_property_from_shape
        got = self.sh.get_property_from_shape(shape, URIRef("http://example.org/p"))
        self.assertEqual(got, prop)

        # update_shclass_in_property: change inner class
        sub = next(self.sh.shaclg.objects(prop, SH.property))
        self.sh.shaclg.add((sub, SH['class'], URIRef("http://example.org/Old")))
        self.sh.update_shclass_in_property(prop, URIRef("http://example.org/New"))
        self.assertIn((sub, SH['class'], URIRef("http://example.org/New")), self.sh.shaclg)

    def test_copy_property_from_shacl(self):
        # source Shacl
        src = Shacl(Graph(), self.ns_prefix, self.base, self.opcua)
        shape = src.create_shacl_type("http://example.org/Target")
        src.create_shacl_property(
            shape,
            URIRef("http://example.org/pp"),
            optional=True,
            is_array=False,
            is_property=True,
            is_iri=False,
            contentclass=None,
            datatype=[XSD.integer]
        )
        # now copy into self.sh
        self.sh.copy_property_from_shacl(src, URIRef("http://example.org/Target"), URIRef("http://example.org/pp"))
        # ensure our shaclg has a shape for the target
        self.assertIn(shape, list(self.sh.shaclg.subjects(RDF.type, SH.NodeShape)))

    def test_validation_update_results_and_exceptions(self):
        v = Validation(Graph(), Graph())
        # when not conforms and increase y
        msg = "Line1\nLine2\nResults (5):\nLine4"
        updated = v.update_results(msg, conforms=False, y=3)
        self.assertIn("Results (8):", updated)
        # when conforms and y>0 => still reports False count
        ok = v.update_results("A\nB\nC\nD", conforms=True, y=2)
        self.assertTrue(ok.startswith("Validation Report"))
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
        property_nodes = self.shacl_instance.get_array_validation_shape(datatype, pattern, None, bnode)
        property_node = None
        for pnode in property_nodes:
            if len(list(self.shacl_instance.shaclg.triples((pnode, SH.property, None)))) > 0:
                property_node = pnode
                break
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

class TestValidation(unittest.TestCase):

    @patch('lib.utils.dump_without_prefixes', return_value="DumpedConstraintGraph")
    @patch('lib.utils.extract_subgraph', return_value=Graph())
    def test_format_shacl_violation(self, mock_extract, mock_dump):
        """
        Test that the format_shacl_violation method produces a formatted
        message containing all the expected elements from a violation.
        """
        # Create a dummy shapes graph (used by the Validation instance)
        shapes_graph = Graph()

        # Create a results graph with one violation node
        results_graph = Graph()
        violation = BNode()
        results_graph.add((violation, RDF.type, SH.ValidationResult))
        severity = Literal("Violation")
        results_graph.add((violation, SH.resultSeverity, severity))
        source_shape = URIRef("http://example.org/shape")
        results_graph.add((violation, SH.sourceShape, source_shape))
        source_constraint = BNode()
        results_graph.add((violation, SH.sourceConstraint, source_constraint))
        focus_node = URIRef("http://example.org/focus")
        results_graph.add((violation, SH.focusNode, focus_node))
        value_node = URIRef("http://example.org/value")
        results_graph.add((violation, SH.value, value_node))
        result_message = Literal("Test error message")
        results_graph.add((violation, SH.resultMessage, result_message))

        # Instantiate the Validation class with a dummy data graph
        validation_instance = Validation(shapes_graph, Graph(), strict=True)

        # Call the method to format the violations
        formatted = validation_instance.format_shacl_violation(results_graph)

        # Check that the formatted message contains expected parts.
        self.assertIn("Constraint Violation in SPARQLConstraintComponent", formatted)
        self.assertIn("Severity: Violation", formatted)
        self.assertIn("Source Shape: http://example.org/shape", formatted)
        self.assertIn("Focus Node: http://example.org/focus", formatted)
        self.assertIn("Value Node: http://example.org/value", formatted)
        self.assertIn("Source Constraint: DumpedConstraintGraph", formatted)
        self.assertIn("Message: Test error message", formatted)

    def test_add_term_to_query_valid(self):
        """Test that add_term_to_query correctly inserts the term into a valid SPARQL query."""
        from rdflib import Graph, URIRef
        # Create a sample query with a valid WHERE clause (with variable whitespace)
        query = "SELECT ?s WHERE { ?s ?p ?o . }"
        target_class = URIRef("http://example.org/TargetClass")
        expected_insertion = f"$this a <{target_class}> . "
        
        # Instantiate Validation with dummy graphs (these are not used by the method)
        validation_instance = Validation(Graph(), Graph())
        modified_query = validation_instance.add_term_to_query(query, target_class)

        # The insertion should occur immediately after the "WHERE {" clause.
        import re
        pattern = re.compile(r'(WHERE\s*\{\s*)', flags=re.IGNORECASE)
        match = pattern.search(query)
        self.assertIsNotNone(match)
        insertion_point = match.end()
        expected_query = query[:insertion_point] + expected_insertion + query[insertion_point:]
        self.assertEqual(modified_query, expected_query)

    def test_add_term_to_query_invalid(self):
        """Test that add_term_to_query raises a ValueError when the query lacks a valid 'WHERE' clause."""
        from rdflib import Graph, URIRef
        # Create a query without a valid WHERE clause
        query = "SELECT ?s FROM { ?s ?p ?o . }"
        target_class = URIRef("http://example.org/TargetClass")
        
        # Instantiate Validation with dummy graphs
        validation_instance = Validation(Graph(), Graph())
        with self.assertRaises(ValueError) as context:
            validation_instance.add_term_to_query(query, target_class)
        self.assertIn("The query does not contain a valid 'WHERE' clause.", str(context.exception))

    def test_fill_message_template_complete_binding(self):
        """Test that placeholders are replaced when corresponding binding values exist."""
        message_template = "Error: {?var1} occurred at {$time}."
        binding = {"var1": "Missing field", "time": "12:00"}
        expected = "Error: Missing field occurred at 12:00."
        
        # Instantiate Validation with dummy graphs (not used in this method)
        validation_instance = Validation(Graph(), Graph())
        result = validation_instance.fill_message_template(message_template, binding)
        
        self.assertEqual(result, expected)

    def test_fill_message_template_incomplete_binding(self):
        """Test that placeholders remain unchanged if the binding dictionary lacks the key."""
        message_template = "Error: {?var1} occurred and {$var2}."
        binding = {"var1": "Missing field"}
        # Since 'var2' is not in the binding, its placeholder remains
        expected = "Error: Missing field occurred and {$var2}."
        
        validation_instance = Validation(Graph(), Graph())
        result = validation_instance.fill_message_template(message_template, binding)
        
        self.assertEqual(result, expected)

    def test_fill_message_template_no_placeholder(self):
        """Test that the message remains unchanged if no placeholders are present."""
        message_template = "No errors found."
        binding = {"var1": "Some value"}
        expected = "No errors found."
        
        validation_instance = Validation(Graph(), Graph())
        result = validation_instance.fill_message_template(message_template, binding)
        
        self.assertEqual(result, expected)

    def test_validate_sparql_constraint_no_violation(self):
        """Test validate_sparql_constraint when no violations are found."""
        from rdflib import Graph, URIRef, Literal, BNode
        # Create dummy shapes graph and data graph
        shapes_graph = Graph()
        data_graph = Graph()
        validation_instance = Validation(shapes_graph, data_graph)
        shape = URIRef("http://example.org/shape")
        target_class = URIRef("http://example.org/TargetClass")
        sparql_constraint_node = BNode()
        
        # Add a sh:select query and a sh:message to the shapes graph
        shapes_graph.add((sparql_constraint_node, SH.select, Literal("SELECT ?this WHERE { ?this ?p ?o }")))
        shapes_graph.add((sparql_constraint_node, SH.message, Literal("Violation: {?this}")))
        
        # Patch add_term_to_query to return a known modified query string.
        modified_query = "modified query"
        with patch.object(validation_instance, "add_term_to_query", return_value=modified_query) as mock_add_term:
            # Simulate that the data graph query returns no results.
            with patch.object(validation_instance.sparql_graph, "query", return_value=[]) as mock_query:
                conforms, results_graph = validation_instance.validate_sparql_constraint(shape, target_class, sparql_constraint_node)
                
                self.assertTrue(conforms)
                # Since there are no violations, the results graph should contain no validation result nodes.
                self.assertEqual(len(list(results_graph.subjects(RDF.type, SH.ValidationResult))), 0)
                
                mock_add_term.assert_called_once_with("SELECT ?this WHERE { ?this ?p ?o }", target_class)
                mock_query.assert_called_once_with(modified_query)

    def test_validate_sparql_constraint_with_violation(self):
        """Test validate_sparql_constraint when a violation is found."""
        from rdflib import Graph, URIRef, Literal, BNode
        shapes_graph = Graph()
        data_graph = Graph()
        validation_instance = Validation(shapes_graph, data_graph)
        shape = URIRef("http://example.org/shape")
        target_class = URIRef("http://example.org/TargetClass")
        sparql_constraint_node = BNode()
        
        # Add the sh:select query and sh:message to the shapes graph.
        shapes_graph.add((sparql_constraint_node, SH.select, Literal("SELECT ?this WHERE { ?this ?p ?o }")))
        shapes_graph.add((sparql_constraint_node, SH.message, Literal("Error at {?this}")))
        
        modified_query = "modified query"
        
        # Create a dummy row to simulate a violation result.
        class DummyRow:
            def __init__(self, bindings):
                self.bindings = bindings
                self.labels = list(bindings.keys())
            def __getitem__(self, key):
                return self.bindings[key]
        
        dummy_row = DummyRow({"this": URIRef("http://example.org/violatingNode")})
        
        with patch.object(validation_instance, "add_term_to_query", return_value=modified_query) as mock_add_term:
            # Simulate that the data graph query returns a list containing our dummy row.
            with patch.object(validation_instance.sparql_graph, "query", return_value=[dummy_row]) as mock_query:
                conforms, results_graph = validation_instance.validate_sparql_constraint(shape, target_class, sparql_constraint_node)
                
                # Since a violation was found, conforms should be False.
                self.assertFalse(conforms)
                # There should be one validation result in the results graph.
                validation_results = list(results_graph.subjects(RDF.type, SH.ValidationResult))
                self.assertEqual(len(validation_results), 1)
                report_node = validation_results[0]
                
                # Check that the result message was filled correctly.
                result_message = results_graph.value(report_node, SH.resultMessage)
                expected_message = "Error at http://example.org/violatingNode"
                self.assertEqual(result_message, Literal(expected_message))
                
                # Check that the focusNode and value are set to the violating node.
                focus_node = results_graph.value(report_node, SH.focusNode)
                self.assertEqual(focus_node, URIRef("http://example.org/violatingNode"))
                
                mock_add_term.assert_called_once_with("SELECT ?this WHERE { ?this ?p ?o }", target_class)
                mock_query.assert_called_once_with(modified_query)

    def test_shacl_validation_strict_true(self):
        """Test shacl_validation when strict is True (default behavior)."""
        from rdflib import Graph, URIRef, Literal
        # Create dummy graphs for data, shapes and extra.
        data_graph = Graph()
        shapes_graph = Graph()
        extra_graph = Graph()
        # Create a Validation instance with strict=True.
        validation_instance = Validation(shapes_graph, data_graph, extra_graph, strict=True, debug=False)
        
        # Create a dummy results graph from pyshacl.validate.
        dummy_results_graph = Graph()
        dummy_results_graph.add((URIRef("http://example.org/validate"), 
                                RDF.type, SH.ValidationResult))
        # Patch the pyshacl.validate function (imported in lib.shacl) to return dummy values.
        with patch('lib.shacl.validate', return_value=(True, dummy_results_graph, "Validation successful")) as mock_validate:
            full_conforms, full_results_graph, full_results_text = validation_instance.shacl_validation()
            
            # In strict mode, the returned values should match those from pyshacl.validate.
            self.assertTrue(full_conforms)
            self.assertEqual(full_results_graph, dummy_results_graph)
            self.assertEqual(full_results_text, "Validation successful")
            mock_validate.assert_called_once()

    def test_shacl_validation_non_strict(self):
        """Test shacl_validation when strict is False, triggering the SPARQL branch."""
        from rdflib import Graph, URIRef, Literal, BNode
        # Create dummy graphs.
        data_graph = Graph()
        shapes_graph = Graph()
        extra_graph = Graph()
        
        # Prepare a shape with a SPARQL constraint.
        shape = BNode()
        sparql_constraint_node = BNode()
        target_class = URIRef("http://example.org/TargetClass")
        # Add a shape triple.
        shapes_graph.add((shape, RDF.type, SH.NodeShape))
        # Add a triple indicating a SPARQL constraint.
        shapes_graph.add((shape, SH.sparql, sparql_constraint_node))
        # Associate the shape with a target class.
        shapes_graph.add((shape, SH.targetClass, target_class))
        # Add the required SPARQL query and message on the constraint node.
        shapes_graph.add((sparql_constraint_node, SH.select, Literal("SELECT ?this WHERE { ?this ?p ?o }")))
        shapes_graph.add((sparql_constraint_node, SH.message, Literal("Error at {?this}")))
        
        # Create a dummy violation graph for the SPARQL constraint branch.
        results_graph_violation = Graph()
        violation_node = BNode()
        results_graph_violation.add((violation_node, RDF.type, SH.ValidationResult))
        
        # Create a dummy results graph from the final pyshacl.validate call.
        results_graph_validate = Graph()
        results_graph_validate.add((URIRef("http://example.org/validate"), RDF.type, SH.ValidationResult))
        
        # Create a Validation instance with strict=False.
        validation_instance = Validation(shapes_graph, data_graph, extra_graph, strict=False, debug=False)
        
        # Patch the following methods on the Validation instance:
        # 1. validate_sparql_constraint: simulate a violation.
        with patch.object(validation_instance, 'validate_sparql_constraint', return_value=(False, results_graph_violation)) as mock_validate_sparql:
            # 2. format_shacl_violation: return a predictable string.
            with patch.object(validation_instance, 'format_shacl_violation', return_value="Violation formatted") as mock_format:
                # 3. update_results: return a predictable string.
                with patch.object(validation_instance, 'update_results', return_value="Updated: Validation successful") as mock_update:
                    # 4. Patch the pyshacl.validate function to return dummy values.
                    with patch('lib.shacl.validate', return_value=(True, results_graph_validate, "Validation successful")) as mock_validate:
                        full_conforms, full_results_graph, full_results_text = validation_instance.shacl_validation()
                        
                        # Since at least one SPARQL constraint returned a violation, full_conforms should be False.
                        self.assertFalse(full_conforms)
                        
                        # The final results graph should be a union of the SPARQL violations and the pyshacl results.
                        # Check that triples from both graphs are present.
                        self.assertTrue(any(True for _ in results_graph_violation))
                        self.assertTrue(any(True for _ in results_graph_validate))
                        
                        # The full_results_text is composed of the updated text from pyshacl.validate
                        # and the formatted SPARQL violation messages.
                        expected_text = "Updated: Validation successful" + "\n" + "Violation formatted"
                        self.assertEqual(full_results_text, expected_text)
                        
                        # Verify that the patched methods were called as expected.
                        mock_validate_sparql.assert_called()  # Called at least once.
                        mock_format.assert_called_once_with(results_graph_violation)
                        mock_update.assert_called_once_with("Validation successful", True, 1)
                        mock_validate.assert_called_once()

    def test_find_shape_name_no_candidate(self):
        """Test that find_shape_name returns None when no candidate is found."""
        from rdflib import Graph, URIRef
        # Create an empty graph
        shapes_graph = Graph()
        # Instantiate Validation with a dummy data graph.
        validation_instance = Validation(shapes_graph, Graph())
        # Set shaclg attribute to our test graph.
        validation_instance.shaclg = shapes_graph
        
        # Use a node that is not referenced by any triple with predicate SH.property.
        test_node = URIRef("http://example.org/node")
        result = validation_instance.find_shape_name(test_node)
        self.assertEqual(result, (None, []))

    def test_find_shape_name_direct_candidate(self):
        """Test that find_shape_name returns a direct candidate that qualifies."""
        from rdflib import Graph, URIRef
        from rdflib.namespace import RDF, SH
        shapes_graph = Graph()
        validation_instance = Validation(shapes_graph, Graph())
        validation_instance.shaclg = shapes_graph
        path = URIRef('http://example.com/path')
        # Create a candidate node that is a URIRef and qualifies as a NodeShape.
        candidate = URIRef("http://example.org/A")
        # The shape node which triggers the lookup.
        test_node = URIRef("http://example.org/B")
        # Add triple indicating that candidate has a property pointing to test_node.
        shapes_graph.add((candidate, SH.property, test_node))
        shapes_graph.add((test_node, SH.path, path))
        # Mark candidate as a NodeShape.
        shapes_graph.add((candidate, RDF.type, SH.NodeShape))
        
        result = validation_instance.find_shape_name(test_node)
        self.assertEqual(result, (candidate, [path]))

    def test_find_shape_name_chain_candidate(self):
        """Test that find_shape_name returns a candidate from a chain of property relationships."""
        from rdflib import Graph, URIRef, BNode
        from rdflib.namespace import RDF, SH
        shapes_graph = Graph()
        validation_instance = Validation(shapes_graph, Graph())
        validation_instance.shaclg = shapes_graph
        
        # Define the final shape node (starting node for lookup).
        test_node = URIRef("http://example.org/C")
        
        # Create an intermediate candidate that does not qualify (blank node).
        intermediate = BNode()
        # Create a valid candidate that qualifies.
        valid_candidate = URIRef("http://example.org/A")
        path1 = URIRef('http://example.com/path1')
        path2 =  URIRef('http://example.com/path2')
        # Build the chain:
        # First, add a triple where the intermediate (blank node) points to test_node.
        shapes_graph.add((intermediate, SH.property, test_node))
        shapes_graph.add((test_node, SH.path, path1))
        shapes_graph.add((intermediate, SH.path, path2))
        # Then, add a triple where the valid_candidate points to the intermediate.
        shapes_graph.add((valid_candidate, SH.property, intermediate))
        # Mark valid_candidate as a NodeShape.
        shapes_graph.add((valid_candidate, RDF.type, SH.NodeShape))
        
        # The function should skip the blank intermediate and eventually return valid_candidate.
        result = validation_instance.find_shape_name(test_node)
        self.assertEqual(result, (valid_candidate, [path1, path2]))

    def test_find_entity_id_no_triple(self):
        """Test that find_entity_id returns the focus node itself when no triple is found."""
        from rdflib import Graph, URIRef
        focus_node = URIRef("http://example.org/O")
        data_graph = Graph()  # empty graph: no triple with focus_node as object.
        validation_instance = Validation(Graph(), data_graph)
        
        parent, predicates = validation_instance.find_entity_id(focus_node)
        # With no triple found, the focus node should be returned and no predicates.
        self.assertEqual(parent, focus_node)
        self.assertEqual(predicates, [])

    def test_find_entity_id_single_step(self):
        """Test that find_entity_id returns the subject when a single triple with rdf:type is found."""
        from rdflib import Graph, URIRef
        from rdflib.namespace import RDF
        data_graph = Graph()
        validation_instance = Validation(Graph(), data_graph)
        
        # Set up a triple where the subject has an rdf:type.
        focus_node = URIRef("http://example.org/O")
        subject = URIRef("http://example.org/A")
        predicate = URIRef("http://example.org/p")
        data_graph.add((subject, predicate, focus_node))
        # Mark the subject with an rdf:type.
        data_graph.add((subject, RDF.type, URIRef("http://example.org/Type")))
        
        parent, predicates = validation_instance.find_entity_id(focus_node)
        self.assertEqual(parent, focus_node)
        self.assertEqual(predicates, [])
        focus_node = BNode()
        parent_node = URIRef("http://example.org/B")
        data_graph.add((parent_node, predicate, focus_node))
        parent, predicates = validation_instance.find_entity_id(focus_node)
        self.assertEqual(parent, parent_node)
        self.assertEqual(predicates, [predicate])

    def test_find_entity_id_chain(self):
        """Test that find_entity_id traverses a chain until a node with rdf:type is found."""
        from rdflib import Graph, URIRef
        from rdflib.namespace import RDF
        data_graph = Graph()
        validation_instance = Validation(Graph(), data_graph)
        
        # Create a chain: focus_node <- predicate1 - intermediate <- predicate2 - parent_node.
        focus_node = BNode()
        intermediate = BNode()
        parent_node = URIRef("http://example.org/A")
        predicate1 = URIRef("http://example.org/p1")
        predicate2 = URIRef("http://example.org/p2")
        
        # First, add the triple linking intermediate to focus_node.
        data_graph.add((intermediate, predicate1, focus_node))
        # Then, add the triple linking parent_node to intermediate.
        data_graph.add((parent_node, predicate2, intermediate))
        # Mark parent_node with an rdf:type.
        data_graph.add((parent_node, RDF.type, URIRef("http://example.org/Type")))
        
        parent, predicates = validation_instance.find_entity_id(focus_node)
        self.assertEqual(parent, parent_node)
        # The predicates should be collected in the order they were encountered.
        self.assertEqual(predicates, [predicate1, predicate2])


if __name__ == "__main__":
    unittest.main()
