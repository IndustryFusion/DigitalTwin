# tests/test_utils.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDFS, XSD, OWL, RDF
from rdflib.collection import Collection
from lib.utils import RdfUtils, downcase_string, isNodeId, convert_to_json_type, idtype2String, extract_namespaces, \
                                get_datatype, attributename_from_type, get_default_value, get_value, normalize_angle_bracket_name, \
                                contains_both_angle_brackets, get_typename, get_common_supertype, rdfStringToPythonBool, \
                                get_rank_dimensions, get_type_and_template, OntologyLoader

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
        self.assertEqual(get_value(g, '99', [XSD.integer]), int(99))
        self.assertEqual(get_value(g, '0.123', [XSD.double]), float(0.123))
        self.assertEqual(get_value(g, 'hello', [XSD.string]), str('hello'))
        self.assertEqual(get_value(g, 'True', [XSD.boolean]), True)
        self.assertEqual(get_value(g, bnode, [XSD.integer]), {'@list': [ 0, 1, 2 ]})
        self.assertEqual(get_value(g, Literal(99), [XSD.integer, XSD.double]), int(99))
        self.assertEqual(get_value(g, Literal(99), [XSD.boolean, XSD.double]), True)
        self.assertEqual(get_value(g, "{}", [RDF.JSON]), {'@value': '{}', '@type': '@json'})
        self.assertEqual(get_value(g, '1970-2-1T00:00:00', [XSD.dateTime]), {'@value': '1970-2-1T00:00:00', '@type': 'xsd:dateTime'})


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
        self.graph.add((self.parenttypenode, self.basens['hasComponent'], templatenode))
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
