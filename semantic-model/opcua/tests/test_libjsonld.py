# tests/test_jsonld.py
import unittest
from unittest.mock import patch, mock_open
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import XSD, RDF, RDFS
from rdflib.collection import Collection
import json

from lib.jsonld import JsonLd, nested_json_from_graph

class TestJsonLd(unittest.TestCase):
    def setUp(self):
        self.basens = Namespace("http://example.org/base/")
        self.opcuans = Namespace("http://example.org/opcua/")
        self.jsonld_instance = JsonLd(self.basens, self.opcuans)

    def test_add_instance(self):
        instance = {"id": "testId", "type": "TestType"}
        self.jsonld_instance.add_instance(instance)
        self.assertIn(instance, self.jsonld_instance.instances)

    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    def test_serialize(self, mock_json_dump, mock_open_fn):
        instance = {"id": "testId", "type": "TestType"}
        self.jsonld_instance.add_instance(instance)

        self.jsonld_instance.serialize("test_output.json")

        mock_open_fn.assert_called_once_with("test_output.json", "w")
        mock_json_dump.assert_called_once_with(
            self.jsonld_instance.instances,
            mock_open_fn(),
            ensure_ascii=False,
            indent=4
        )

    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    def test_dump_context(self, mock_json_dump, mock_open_fn):
        namespaces = {
            "base": {"@id": str(self.basens), "@prefix": True}
        }
        self.jsonld_instance.dump_context("context_output.json", namespaces)

        mock_open_fn.assert_called_once_with("context_output.json", "w")
        mock_json_dump.assert_called_once_with(
            {
                "@context": [
                    namespaces,
                    "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.8.jsonld"
                ]
            },
            mock_open_fn(),
            indent=2
        )

    def test_map_datatype_to_jsonld_basic(self):
        g = Graph()
        # Boolean type
        result, _ = JsonLd.map_datatype_to_jsonld(g, self.opcuans['Boolean'], self.opcuans)
        self.assertEqual(result, [XSD.boolean])
        # Integer type
        result, _ = JsonLd.map_datatype_to_jsonld(g, self.opcuans['Int32'], self.opcuans)
        self.assertEqual(result, [XSD.integer])
        # Double type
        result, _ = JsonLd.map_datatype_to_jsonld(g, self.opcuans['Double'], self.opcuans)
        self.assertEqual(result, [XSD.double])
        # Number type
        result, _ = JsonLd.map_datatype_to_jsonld(g, self.opcuans['Number'], self.opcuans)
        self.assertEqual(result, [XSD.double, XSD.integer])
        # Unknown type
        unknown = URIRef("http://example.org/UnknownType")
        result, _ = JsonLd.map_datatype_to_jsonld(g, unknown, self.opcuans)
        self.assertEqual(result, [RDF.JSON])
        # Enumeration subclass detection
        g.add((self.opcuans['MyType'], RDFS.subClassOf, self.opcuans['Enumeration']))
        result_enum, _ = JsonLd.map_datatype_to_jsonld(g, self.opcuans['MyType'], self.opcuans)
        # Current implementation falls back to JSON for enumeration in absence of subclass handling
        self.assertEqual(result_enum, [XSD.enumeration])

    def test_map_datatype_to_jsonld_string_and_datetime(self):
        g = Graph()
        # String type
        result_str, _ = JsonLd.map_datatype_to_jsonld(g, self.opcuans['String'], self.opcuans)
        self.assertEqual(result_str, [XSD.string])
        # DateTime type
        result_dt, _ = JsonLd.map_datatype_to_jsonld(g, self.opcuans['DateTime'], self.opcuans)
        self.assertEqual(result_dt, [XSD.dateTime])

    def test_get_ngsild_property_list(self):
        data_list = [1, 2, 3]
        prop = JsonLd.get_ngsild_property(data_list)
        self.assertEqual(prop['type'], 'ListProperty')
        self.assertEqual(prop['valueList'], data_list)

    def test_get_ngsild_property_dict(self):
        data_dict = {"a": 1}
        prop = JsonLd.get_ngsild_property(data_dict)
        self.assertEqual(prop['type'], 'JsonProperty')
        self.assertEqual(prop['json'], data_dict)

    def test_get_ngsild_property_iri_and_literal(self):
        iri_value = URIRef("http://example.org/iri")
        prop = JsonLd.get_ngsild_property(iri_value, isiri=True)
        self.assertEqual(prop, {'type': 'Property', 'value': {'@id': str(iri_value)}})
        literal_value = "some string"
        prop2 = JsonLd.get_ngsild_property(literal_value)
        self.assertEqual(prop2, {'type': 'Property', 'value': literal_value})

    def test_get_ngsild_relationship(self):
        rel_obj = "someObj"
        rel = JsonLd.get_ngsild_relationship(rel_obj)
        self.assertEqual(rel, {'type': 'Relationship', 'object': rel_obj})

    def test_get_default_value_scalars(self):
        # integer
        self.assertEqual(JsonLd.get_default_value([XSD.integer]), 0)
        # double
        self.assertEqual(JsonLd.get_default_value([XSD.double]), 0.0)
        # string
        self.assertEqual(JsonLd.get_default_value([XSD.string]), '')
        # boolean
        self.assertEqual(JsonLd.get_default_value([XSD.boolean]), False)
        # JSON
        self.assertEqual(JsonLd.get_default_value([RDF.JSON]), {})
        # dateTime: check fields individually
        dt_val = JsonLd.get_default_value([XSD.dateTime])
        self.assertIsInstance(dt_val, dict)
        self.assertEqual(dt_val.get('@value'), '1970-1-1T00:00:00')
        self.assertEqual(dt_val.get('@type'), 'xsd:dateTime')
        # unknown
        self.assertEqual(JsonLd.get_default_value([]), 'null')

    def test_get_default_value_with_orig_datatype(self):
        self.assertEqual(JsonLd.get_default_value([], orig_datatype=XSD.string), '')

    def test_get_default_value_array(self):
        g = Graph()
        bnode = BNode()
        Collection(g, bnode, [Literal(2), Literal(3)])
        array_output = JsonLd.get_default_value([XSD.integer], orig_datatype=None,
                                               value_rank=0, array_dimensions=bnode, g=g)
        # array of two elements with value 0 => length=2*3? Actually 2*3=6 zeros
        self.assertEqual(array_output, [0] * 6)

    def test_get_default_value_array_empty_dimensions(self):
        g = Graph()
        bnode = BNode()
        Collection(g, bnode, [])
        result = JsonLd.get_default_value([XSD.integer], orig_datatype=None,
                                          value_rank=0, array_dimensions=bnode, g=g)
        self.assertEqual(result, [])

    def test_get_value_scalar(self):
        g = Graph()
        val = Literal(123, datatype=XSD.integer)
        result = JsonLd.get_value(g, val, [XSD.integer])
        self.assertEqual(result, 123)
        val2 = Literal('3.14', datatype=XSD.double)
        result2 = JsonLd.get_value(g, val2, [XSD.double])
        self.assertAlmostEqual(result2, 3.14)
        val3 = Literal('true', datatype=XSD.boolean)
        result3 = JsonLd.get_value(g, val3, [XSD.boolean])
        self.assertTrue(result3)
        val4 = Literal('hello', datatype=XSD.string)
        result4 = JsonLd.get_value(g, val4, [XSD.string])
        self.assertEqual(result4, 'hello')

    def test_get_value_no_match_datatype(self):
        g = Graph()
        val = Literal('123', datatype=XSD.integer)
        with patch('builtins.print') as mock_print:
            result = JsonLd.get_value(g, val, [XSD.boolean, XSD.double])
        self.assertTrue(mock_print.called)
        # Current behavior returns the literal's Python value
        self.assertEqual(result, val.toPython())

    def test_get_value_array(self):
        g = Graph()
        bnode = BNode()
        Collection(g, bnode, [Literal(1), Literal(2)])
        result = JsonLd.get_value(g, bnode, [XSD.integer])
        self.assertEqual(result, [1, 2])

class TestNestedJsonFromGraph(unittest.TestCase):
    def test_nested_json_from_graph_valid(self):
        graph = Graph()
        ex = Namespace("http://example.org/")
        person = URIRef(ex + "person/1")
        name = URIRef(ex + "name")
        knows = URIRef(ex + "knows")
        blank = BNode()
        graph.add((person, name, Literal("Alice")))
        graph.add((person, knows, blank))
        graph.add((blank, name, Literal("John Doe")))

        nested = nested_json_from_graph(graph)
        self.assertEqual(nested.get('@id'), str(person))
        self.assertEqual(nested.get(str(name)), {'@value': 'Alice'})
        k = nested.get(str(knows))
        self.assertIsInstance(k, dict)
        self.assertNotIn('@id', k)
        self.assertEqual(k.get(str(name)), {'@value': 'John Doe'})

    def test_nested_json_from_graph_invalid_root(self):
        graph = Graph()
        ex = Namespace("http://example.org/")
        person = URIRef(ex + "person/1")
        graph.add((person, URIRef(ex + "name"), Literal("Alice")))
        with self.assertRaises(ValueError) as cm:
            nested_json_from_graph(graph, root="http://nonexistent")
        self.assertIn("Specified root node not found in the graph.", str(cm.exception))

    def test_nested_json_from_graph_with_explicit_root(self):
        graph = Graph()
        ex = Namespace("http://example.org/")
        root1 = URIRef(ex + "root1")
        other = URIRef(ex + "other")
        name = URIRef(ex + "name")
        graph.add((root1, name, Literal("Val1")))
        graph.add((other, name, Literal("Val2")))
        nested = nested_json_from_graph(graph, root=str(other))
        self.assertEqual(nested.get('@id'), str(other))
        self.assertEqual(nested.get(str(name)), {'@value': 'Val2'})

if __name__ == '__main__':
    unittest.main()
