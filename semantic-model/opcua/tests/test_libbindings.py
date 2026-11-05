# tests/test_bindings.py
import unittest
from unittest.mock import MagicMock, patch
from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.namespace import RDF
from lib.bindings import Bindings
import lib.utils as utils


class TestBindings(unittest.TestCase):

    def setUp(self):
        """Set up common test data."""
        self.namespace_prefix = "http://example.org/"
        self.basens = Namespace("http://example.org/base/")
        self.bindings_instance = Bindings(self.namespace_prefix, self.basens)

    @patch('random.choices', return_value=['A', 'B', 'C', 'D'])
    @patch('lib.utils.idtype2String', return_value='i')
    def test_create_binding(self, mock_idtype2string, mock_random_choices):
        """Test creating a binding and adding it to the RDF graph."""
        g = Graph()
        parent_node_id = URIRef("http://example.org/parentNode")
        var_node = URIRef("http://example.org/varNode")
        attribute_iri = URIRef("http://example.org/attributeIri")

        # Mocking objects in graph g
        g.objects = MagicMock(side_effect=[
            iter([URIRef("http://example.org/dtype")]),  # hasDatatype
            iter([Literal("nsu=http://example.org/nsuri;i=node123")]),  # uardf:nodeId
            iter([Literal("http://example.org/nsuri")])  # uardf:namespaceUri
        ])

        # Call the create_binding method
        self.bindings_instance.create_binding(g, parent_node_id, var_node, attribute_iri)

        # Check if the triples are added correctly
        triples = list(self.bindings_instance.bindingsg)
        self.assertEqual(len(triples), 12)  # Ensure 10 triples are added

        bindingiri = self.bindings_instance.binding_namespace['binding_ABCD']
        mapiri = self.bindings_instance.binding_namespace['map_ABCD']

        # Check specific triples to ensure correct addition
        self.assertIn((bindingiri, RDF['type'], self.basens['Binding']), triples)
        self.assertIn((bindingiri, self.basens['bindsEntity'], parent_node_id), triples)
        self.assertIn((bindingiri, self.basens['bindingVersion'], Literal('0.1')), triples)
        self.assertIn((bindingiri, self.basens['bindsFirmware'], Literal('firmware')), triples)
        self.assertIn((bindingiri, self.basens['bindsMap'], mapiri), triples)
        self.assertIn((attribute_iri, self.basens['boundBy'], bindingiri), triples)
        self.assertIn((mapiri, RDF['type'], self.basens['BoundMap']), triples)
        self.assertIn((mapiri, self.basens['bindsConnector'], self.basens['OPCUAConnector']), triples)
        self.assertIn((mapiri, self.basens['bindsMapDatatype'], URIRef("http://example.org/dtype")), triples)
        self.assertIn((mapiri, self.basens['bindsConnectorParameter'], Literal('nsu=http://example.org/nsuri;i=node123')), triples)

    @patch('lib.utils.idtype2String', return_value='i')
    def test_create_binding_with_logic_and_attribute_type(self, mock_idtype2string):
        """The logic and the NGSI-LD attribute type are part of the binding, the default type is Property."""
        g = Graph()
        g.objects = MagicMock(side_effect=lambda *args: iter([Literal("nsu=http://example.org/nsuri;i=1")]))
        attribute_iri = URIRef("http://example.org/attributeIri")
        ngsild = Namespace('https://uri.etsi.org/ngsi-ld/')

        self.bindings_instance.create_binding(g, URIRef("http://example.org/parentNode"),
                                              URIRef("http://example.org/varNode"), attribute_iri,
                                              logic_transform='WHERE { BIND(?var1 AS ?value) }',
                                              attribute_type=ngsild['JsonProperty'])

        bindings = self.bindings_instance.bindingsg
        bindingiri = next(bindings.objects(attribute_iri, self.basens['boundBy']))
        self.assertEqual(next(bindings.objects(bindingiri, self.basens['bindsAttributeType'])), ngsild['JsonProperty'])
        self.assertEqual(str(next(bindings.objects(bindingiri, self.basens['bindsLogic']))),
                         'WHERE { BIND(?var1 AS ?value) }')

    def test_enum_logic_translates_number_to_iri(self):
        """The logic of an Enumeration finds the IRI of the number in the knowledge, unknown numbers find nothing."""
        pumps = Namespace('http://example.org/pumps/')
        knowledge = Graph()
        value_node = pumps['liquidValueNode']
        knowledge.add((pumps['LiquidPump'], RDF['type'], pumps['PumpClassEnum']))
        knowledge.add((pumps['LiquidPump'], self.basens['hasValueNode'], value_node))
        knowledge.add((value_node, self.basens['hasEnumValue'], Literal(5)))
        query = 'SELECT ?type ?value ' + self.bindings_instance.enum_logic(pumps['PumpClassEnum'])

        found = list(knowledge.query(query, initBindings={'var1': Literal(5)}))
        self.assertEqual([row.value for row in found], [pumps['LiquidPump']])
        self.assertEqual(found[0].type, URIRef('https://uri.etsi.org/ngsi-ld/Property'))
        self.assertEqual(list(knowledge.query(query, initBindings={'var1': Literal(99)})), [])

    def test_bind(self):
        """Test binding a prefix to a namespace in the RDF graph."""
        prefix = 'ex'
        namespace = Namespace('http://example.org/ex/')
        self.bindings_instance.bind(prefix, namespace)

        # Check if the namespace binding is added correctly
        bindings = dict(self.bindings_instance.bindingsg.namespaces())
        self.assertIn(prefix, bindings)
        self.assertEqual(str(bindings[prefix]), str(namespace))

    def test_len(self):
        """Test getting the length of the RDF graph."""
        # Initially, the graph should be empty
        self.assertEqual(self.bindings_instance.len(), 0)

        # Add a triple and check the length
        self.bindings_instance.bindingsg.add((URIRef("http://example.org/s"), RDF.type, URIRef("http://example.org/o")))
        self.assertEqual(self.bindings_instance.len(), 1)

    @patch.object(Graph, 'serialize', return_value=None)
    def test_serialize(self, mock_serialize):
        """Test serializing the RDF graph to a file."""
        destination = "test_output.ttl"

        # Add a triple to the graph
        self.bindings_instance.bindingsg.add((URIRef("http://example.org/s"), RDF.type, URIRef("http://example.org/o")))

        # Call the serialize method
        self.bindings_instance.serialize(destination)

        # Check that bindingsg.serialize was called with the correct arguments
        mock_serialize.assert_called_once_with(destination)


if __name__ == "__main__":
    unittest.main()
