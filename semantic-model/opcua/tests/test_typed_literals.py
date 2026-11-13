#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Typed literals (#961, contracts/typed-literals): the instance tool declares its doubles.

JSON-LD 1.1 makes a plain whole number an integer, 80.0 included, so a value
of a Double, Float, Decimal or Duration variable -- all mapped to xsd:double --
is written as {"@value": <float>, "@type": <the full XSD IRI>}, whatever its
value. A Number variable admits integers too and is written plain.
"""
import json
import unittest

from rdflib import BNode, Graph, Literal
from rdflib.collection import Collection
from rdflib.namespace import XSD

from lib.jsonld import JsonLd

DOUBLE = [XSD.double]                 # Float, Double, Decimal, Duration
NUMBER = [XSD.double, XSD.integer]    # Number: double or integer


def declared(number):
    return {'@value': float(number), '@type': 'http://www.w3.org/2001/XMLSchema#double'}


class TestDoubleValues(unittest.TestCase):
    def test_a_whole_double_is_declared(self):
        self.assertEqual(JsonLd.get_value(Graph(), Literal('80.0', datatype=XSD.double), DOUBLE),
                         declared(80))

    def test_a_fractional_double_is_declared_too(self):
        self.assertEqual(JsonLd.get_value(Graph(), Literal('80.5', datatype=XSD.double), DOUBLE),
                         declared(80.5))

    def test_an_integer_literal_on_a_double_variable_is_a_declared_double(self):
        value = JsonLd.get_value(Graph(), Literal(80, datatype=XSD.integer), DOUBLE)
        self.assertEqual(value, declared(80))
        self.assertIsInstance(value['@value'], float)

    def test_the_type_is_the_full_iri(self):
        value = JsonLd.get_value(Graph(), Literal('1.5', datatype=XSD.double), DOUBLE)
        self.assertEqual(value['@type'], str(XSD.double))

    def test_the_default_is_a_declared_zero(self):
        self.assertEqual(JsonLd.get_default_value(DOUBLE), declared(0))

    def test_an_array_default_stays_a_list_of_plain_numbers(self):
        g = Graph()
        dimensions = BNode()
        Collection(g, dimensions, [Literal(3)])
        self.assertEqual(JsonLd.get_default_value(DOUBLE, value_rank=1, array_dimensions=dimensions, g=g),
                         [0.0, 0.0, 0.0])

    def test_an_array_value_stays_a_list_of_plain_numbers(self):
        g = Graph()
        items = BNode()
        Collection(g, items, [Literal(1.0), Literal(2.5)])
        self.assertEqual(JsonLd.get_value(g, items, DOUBLE), [1.0, 2.5])

    def test_a_decimal_literal_is_a_declared_double_and_serialisable(self):
        """nodeset2owl writes no xsd:decimal today; read from other RDF, a Decimal
        would otherwise pass undeclared and json.dump could not write it."""
        value = JsonLd.get_value(Graph(), Literal('2.5', datatype=XSD.decimal), DOUBLE)
        self.assertEqual(value, declared(2.5))
        self.assertIsInstance(value['@value'], float)
        json.dumps(value)

    def test_the_property_carries_the_declared_value(self):
        prop = JsonLd.get_ngsild_property(declared(80), datatype=DOUBLE)
        self.assertEqual(prop, {'type': 'Property', 'value': declared(80)})
        json.dumps(prop)  # serialisable as it is written


class TestNumberValues(unittest.TestCase):
    def test_a_whole_number_is_a_plain_integer(self):
        value = JsonLd.get_value(Graph(), Literal('80.0', datatype=XSD.double), NUMBER)
        self.assertEqual(value, 80)
        self.assertIsInstance(value, int)

    def test_a_fractional_number_is_plain(self):
        self.assertEqual(JsonLd.get_value(Graph(), Literal('3.5', datatype=XSD.double), NUMBER), 3.5)

    def test_an_integer_number_is_plain(self):
        self.assertEqual(JsonLd.get_value(Graph(), Literal(80, datatype=XSD.integer), NUMBER), 80)

    def test_the_default_is_a_plain_zero(self):
        value = JsonLd.get_default_value(NUMBER)
        self.assertEqual(value, 0)
        self.assertIsInstance(value, int)


class TestOtherValuesStayPlain(unittest.TestCase):
    def test_integer_boolean_string(self):
        g = Graph()
        self.assertEqual(JsonLd.get_value(g, Literal(80, datatype=XSD.integer), [XSD.integer]), 80)
        self.assertIs(JsonLd.get_value(g, Literal('true', datatype=XSD.boolean), [XSD.boolean]), True)
        self.assertEqual(JsonLd.get_value(g, Literal('80', datatype=XSD.string), [XSD.string]), '80')
        self.assertEqual(JsonLd.get_default_value([XSD.integer]), 0)


if __name__ == '__main__':
    unittest.main()
