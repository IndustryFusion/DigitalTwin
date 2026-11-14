#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""How shacl2flink reads the numbers of a JSON-LD model (#958, task 1.3).

The reference is tests/jsonld-number-vectors.json, the table JSON-LD 1.1
defines and the SemForge SDK reads too. The pyshacl comparison loads its
models through the same reading, so it cannot catch a bug in it: these tests
are what does.
"""
import json
import os

import pytest
import rdflib
from rdflib import XSD

import lib.utils as utils
from lib.jsonld_numbers import as_jsonld_numbers, read_jsonld

VECTORS = os.path.join(os.path.dirname(__file__), 'jsonld-number-vectors.json')
with open(VECTORS, encoding='utf-8') as _handle:
    TABLE = json.load(_handle)['vectors']

PROPERTY = 'http://example.org/p'


def _model(tmp_path, value_json):
    path = tmp_path / 'model.jsonld'
    path.write_text('{"@id": "urn:x:1", "%s": %s}' % (PROPERTY, value_json))
    return str(path)


@pytest.mark.parametrize('vector', TABLE, ids=[v['json'] for v in TABLE])
def test_a_value_has_the_type_json_ld_gives_it(tmp_path, vector):
    graph = utils.load_graph(_model(tmp_path, vector['json']))
    [value] = list(graph.objects(None, rdflib.URIRef(PROPERTY)))
    datatype = value.datatype or XSD.string
    assert datatype == XSD[vector['datatype']], vector['json']
    if 'number' in vector:
        assert value.toPython() == vector['number']


def test_whole_valued_floats_become_integers_below_the_limit_only():
    assert as_jsonld_numbers(80.0) == 80 and isinstance(as_jsonld_numbers(80.0), int)
    assert as_jsonld_numbers(-0.0) == 0
    assert isinstance(as_jsonld_numbers(1e21), float), '10^21 and above stay doubles'
    assert isinstance(as_jsonld_numbers(-1e21), float)
    assert as_jsonld_numbers(80.5) == 80.5
    assert as_jsonld_numbers(True) is True, 'a boolean is not a number here'


def test_a_declared_type_is_left_alone():
    declared = {'@value': 80.0, '@type': 'xsd:double'}
    assert as_jsonld_numbers(declared) is declared
    assert as_jsonld_numbers({'@value': 80.0}) == {'@value': 80}


def test_the_context_is_not_data():
    document = {'@context': {'@version': 1.0, 'x': {'@id': 'http://x/'}}, 'x': 1.0}
    read = as_jsonld_numbers(document)
    assert read['@context'] is document['@context']
    assert read['x'] == 1 and isinstance(read['x'], int)


def test_sub_properties_and_lists_are_read_the_same_way():
    entity = {
        'id': 'urn:x:1',
        'temperature': {'type': 'Property', 'value': 80.0,
                        'accuracy': {'type': 'Property', 'value': 0.0}},
        'readings': {'type': 'ListProperty', 'valueList': [1.0, 2.5, 3.0]},
        'limits': [{'type': 'Property', 'value': 100.0, 'datasetId': 'urn:a'},
                   {'type': 'Property', 'value': {'@value': 100.0, '@type': 'xsd:double'},
                    'datasetId': 'urn:b'}],
    }
    read = as_jsonld_numbers(entity)
    assert read['temperature']['value'] == 80 and isinstance(read['temperature']['value'], int)
    assert isinstance(read['temperature']['accuracy']['value'], int)
    assert read['readings']['valueList'] == [1, 2.5, 3]
    assert [type(v) for v in read['readings']['valueList']] == [int, float, int]
    assert isinstance(read['limits'][0]['value'], int)
    assert read['limits'][1]['value'] == {'@value': 100.0, '@type': 'xsd:double'}


def test_the_file_is_read_with_its_own_location_as_base(tmp_path):
    path = _model(tmp_path, '80.0')
    data, base = read_jsonld(path)
    assert json.loads(data)[PROPERTY] == 80
    assert base == (tmp_path / 'model.jsonld').absolute().as_uri()


def test_a_relative_id_resolves_against_the_file_as_before(tmp_path):
    path = tmp_path / 'model.jsonld'
    path.write_text('{"@id": "thing", "%s": 1.0}' % PROPERTY)
    [subject] = set(utils.load_graph(str(path)).subjects())
    assert str(subject) == (tmp_path / 'thing').absolute().as_uri()
