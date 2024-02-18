#
# Copyright (c) 2022 Intel Corporation
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

from unittest.mock import MagicMock, patch
import lib.bgp_translation_utils
from rdflib import term, RDF, Graph as rGraph
import pytest

hasObjectURI = term.URIRef("https://uri.etsi.org/ngsi-ld/hasObject")
stateURI = term.URIRef("https://industry-fusion.com/types/v0.9/state")
hasFilterURI = term.URIRef("https://industry-fusion.com/types/v0.9/hasFilter")
hasValueURI = term.URIRef("https://uri.etsi.org/ngsi-ld/hasValue")
observedAtURI = term.URIRef("https://uri.etsi.org/ngsi-ld/observedAt")
target_class = term.URIRef("https://industry-fusion.com/types/v0.9/cutter")
target_class_filter = term.URIRef("https://industry-fusion.com/types/v0.9/filter")
cutter = term.URIRef("cutter")


def test_create_ngsild_mappings(monkeypatch):
    class Graph:
        def query(self, sparql):
            assert "?this rdfs:subClassOf <https://industry-fusion.com/types/v0.9/cutter> .\n" in sparql
            assert "?thisshape sh:targetClass ?this .\n?thisshape sh:property [ sh:path \
<https://industry-fusion.com/types/v0.9/hasFilter> ; sh:property [ sh:path \
ngsild:hasObject;  sh:class ?f ] ] ." in sparql
            assert "?v2shape sh:targetClass ?v2 .\n?v2shape sh:property [ sh:path \
<https://industry-fusion.com/types/v0.9/state> ; ] ." in sparql
            assert "?v1shape sh:targetClass ?v1 .\n?v1shape sh:property [ sh:path \
<https://industry-fusion.com/types/v0.9/state> ; ] ." in sparql
            return ['row']
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    g = Graph()
    ctx = {
        'namespace_manager': None,
        'PV': None,
        'pass': 0,
        'target_used': False,
        'table_id': 0,
        'classes': {'this': target_class},
        'sql_tables': ['cutter', 'attributes'],
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'target_sql': '',
        'target_where': '',
        'target_modifiers': [],
        'properties': properties,
        'relationships': relationships,
        'g': g
    }

    graph = rGraph()
    graph.add((term.BNode('1'), hasObjectURI, term.Variable('f')))
    graph.add((term.Variable('f'), stateURI, term.BNode('2')))
    graph.add((term.Variable('this'), hasFilterURI, term.BNode('1')))
    graph.add((term.Variable('this'), stateURI, term.BNode('3')))
    graph.add((term.BNode('2'), hasValueURI, term.Variable('v2')))
    graph.add((term.BNode('3'), hasValueURI, term.Variable('v1')))
    graph.add((term.BNode('3'), observedAtURI, term.Variable('v1_time')))

    property_variables, entity_variables, time_variables, row = \
        lib.bgp_translation_utils.create_ngsild_mappings(ctx, graph)
    assert property_variables == {
        term.Variable('v2'): True,
        term.Variable('v1'): True,
    }
    assert entity_variables == {
        term.Variable('f'): True,
        term.Variable('this'): True
    }
    assert time_variables == {
        term.Variable('v1_time'): False
    }
    assert row == 'row'


def test_create_ngsild_mappings_reverse(monkeypatch):
    class Graph:
        def query(self, sparql):
            assert "?this rdfs:subClassOf <https://industry-fusion.com/types/v0.9/filter> ." in sparql
            assert "pcshape sh:property [ sh:path <https://industry-fusion.com/types/v0.9/hasFilter> ; sh:property \
[ sh:path ngsild:hasObject;  sh:class ?this ] ]" in sparql
            assert "?v2shape sh:targetClass ?v2 .\n?v2shape sh:property [ sh:path \
<https://industry-fusion.com/types/v0.9/state> ; ] ." in sparql
            assert "?v1shape sh:targetClass ?v1 .\n?v1shape sh:property [ sh:path \
<https://industry-fusion.com/types/v0.9/state> ; ] ." in sparql
            return ['row']

    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    g = Graph()
    ctx = {
        'namespace_manager': None,
        'PV': None,
        'pass': 0,
        'target_used': False,
        'table_id': 0,
        'classes': {'this': target_class_filter},
        'sql_tables': ['cutter', 'attributes'],
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'target_sql': '',
        'target_where': '',
        'target_modifiers': [],
        'properties': properties,
        'relationships': relationships,
        'g': g
    }

    graph = rGraph()
    graph.add((term.Variable('this'), stateURI, term.BNode('1')))
    graph.add((term.Variable('pc'), hasFilterURI, term.BNode('2')))
    graph.add((term.BNode('2'), hasObjectURI, term.Variable('this')))
    graph.add((term.Variable('pc'), stateURI, term.BNode('3')))
    graph.add((term.BNode('1'), hasValueURI, term.Variable('v1')))
    graph.add((term.BNode('3'), hasValueURI, term.Variable('v2')))

    property_variables, entity_variables, \
        time_variables, row = lib.bgp_translation_utils.create_ngsild_mappings(ctx, graph)
    assert property_variables == {
        term.Variable('v2'): True,
        term.Variable('v1'): True
    }
    assert entity_variables == {
        term.Variable('pc'): True,
        term.Variable('this'): True
    }
    assert time_variables == {}
    assert row == 'row'


@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.utils.create_varname')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_rdf_spo_predicate_is_rdftype_object_is_iri(mock_isentity, mock_create_table_name,
                                                            mock_create_varname, mock_get_random_string, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = True
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'properties': properties,
        'relationships': relationships,
        'property_variables': {},
        'entity_variables': {}
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': {},
        'row': 'row'
    }
    s = term.Variable('f')
    p = RDF['type']
    o = term.URIRef('https://example.com/obj')
    lib.bgp_translation_utils.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['where'] == "'<'||FILTER.type||'>' = '<https://example.com/obj>'"
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id'}


@patch('lib.bgp_translation_utils.get_rdf_join_condition')
@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_rdf_spo_predicate_is_rdf_type_object_is_variable(mock_isentity, mock_create_table_name,
                                                                  mock_get_random_string, mock_get_rdf_join_condiion,
                                                                  monkeypatch):
    def create_varname(var):
        if var == term.Variable('f'):
            return 'f'
        if var == term.Variable('x'):
            return 'x'

    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    monkeypatch.setattr(lib.utils, "create_varname", create_varname)
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = True
    mock_get_random_string.return_value = ''
    mock_get_rdf_join_condiion.return_value = 'condition'
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'x': 'xtable.subject'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': {},
        'row': 'row'
    }
    s = term.Variable('f')
    p = RDF['type']
    o = term.Variable('x')
    lib.bgp_translation_utils.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['where'] == "'<'||FILTER.type||'>' = xtable.subject"
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'x': 'xtable.subject'}
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'x': 'xtable.subject'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': {},
        'row': 'row'
    }
    mock_get_rdf_join_condiion.return_value = None

    s = term.Variable('f')
    p = RDF['type']
    o = term.Variable('x')
    lib.bgp_translation_utils.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'x': 'FILTER.type'}


@patch('lib.bgp_translation_utils.get_rdf_join_condition')
@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.utils.create_varname')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_rdf_spo_subject_is_no_entity(mock_isentity, mock_create_table_name, mock_create_varname,
                                              mock_get_random_string, mock_get_rdf_join_condition,
                                              monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = False
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_get_rdf_join_condition.return_value = 'condition'
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': {},
        'row': 'row'
    }
    s = term.Variable('f')
    p = term.URIRef('predicate')
    o = term.URIRef('https://example.com/obj')
    lib.bgp_translation_utils.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'rdf AS testtable',
                                                'join_condition': "testtable.subject = condition and \
testtable.predicate = '<predicate>' and testtable.object = condition"}]
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id'}
    assert local_ctx['bgp_tables'] == {'testtable': []}

    mock_get_rdf_join_condition.return_value = None
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id'},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': {},
        'row': 'row'
    }
    p = term.URIRef('test')
    o = term.Variable('x')
    lib.bgp_translation_utils.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'rdf AS testtable',
                                                'join_condition': "testtable.predicate = '<test>'"}]
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': '`testtable`.`subject`', 'x': 'testtable.object'}
    assert local_ctx['bgp_tables'] == {'testtable': []}


@patch('lib.bgp_translation_utils.utils')
@patch('lib.bgp_translation_utils.get_rdf_join_condition')
@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.utils.create_varname')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_rdf_spo_subject_is_no_entity_and_predicate_is_type(mock_isentity, mock_create_table_name,
                                                                    mock_create_varname, mock_get_random_string,
                                                                    mock_get_rdf_join_condition, mock_utils,
                                                                    monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = True
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_get_rdf_join_condition.return_value = 'condition'
    mock_utils.camelcase_to_snake_case.return_value = 'camelcase_to_snake_case'
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'sql_tables': [],
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},

        'h': {},
        'row': {'f': 'f'}
    }
    s = term.Variable('f')
    p = RDF['type']
    o = term.URIRef('https://example.com/obj')
    lib.bgp_translation_utils.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'camelcase_to_snake_case_view AS FTABLE',
                                                'join_condition':
                                                "'<'||FTABLE.`type`||'>' = '<https://example.com/obj>'"}]
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FTABLE.`id`'}
    assert local_ctx['bgp_tables'] == {'FTABLE': []}


@patch('lib.bgp_translation_utils.get_rdf_join_condition')
@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.utils.create_varname')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_rdf_spo_subject_is_entity_and_predicate_is_type(mock_isentity, mock_create_table_name,
                                                                 mock_create_varname, mock_get_random_string,
                                                                 mock_get_rdf_join_condition, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = False
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_get_rdf_join_condition.return_value = 'condition'

    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'property_variables': {},
        'entity_variables': {term.Variable('f'): True},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.`id`'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': {},
        'row': 'row'
    }
    s = term.Variable('f')
    p = RDF['type']
    o = term.URIRef('https://example.com/obj')
    lib.bgp_translation_utils.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['where'] == "'<'||FILTER.type||'>' = '<https://example.com/obj>'"


@patch('lib.bgp_translation_utils.get_rdf_join_condition')
@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.utils.create_varname')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_rdf_spo_blank_node(mock_isentity, mock_create_table_name, mock_create_varname,
                                    mock_get_random_string, mock_get_rdf_join_condition, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    mock_create_table_name.side_effect = ['testtable', 'testtable2']
    mock_isentity.return_value = False
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_get_rdf_join_condition.return_value = 'condition'
    h = rGraph()
    h.add((term.BNode('1'), term.URIRef('predicate2'), term.Variable('x')))
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': h,
        'row': 'row'
    }
    s = term.Variable('f')
    p = term.URIRef('predicate')
    o = term.BNode('1')
    lib.bgp_translation_utils.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_sql_expression'][0] == {'statement': 'rdf AS testtable',
                                                  'join_condition': "testtable.subject = condition and \
testtable.predicate = '<predicate>' and testtable.object LIKE '_:%'"}
    assert local_ctx['bgp_sql_expression'][1] == {'statement': 'rdf AS testtable2',
                                                  'join_condition': "testtable.subject = condition and \
testtable2.predicate = '<predicate2>' and testtable.object = testtable2.subject and testtable2.object = condition"}


@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.utils.create_varname')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_ngsild_spo_hasValue(mock_isentity, mock_create_table_name, mock_create_varname,
                                     mock_get_random_string, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = True
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_h = MagicMock()
    mock_h.predicates.return_value = [hasValueURI]
    mock_h.objects.return_value = [term.Variable('v1')]
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships,
        'tables': {'THISTABLE': ['id']}
    }
    # test with unbound v1
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': mock_h,
        'row': {'f': 'ftable'}
    }
    s = term.Variable('f')
    p = stateURI
    o = term.URIRef('https://example.com/obj')
    lib.bgp_translation_utils.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'FSTATETABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'v1': '`FSTATETABLE`.\
`https://uri.etsi.org/ngsi-ld/hasValue`'}
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'attributes_view AS FSTATETABLE', 'join_condition':
                                               'FSTATETABLE.id = FTABLE.\
`https://industry-fusion.com/types/v0.9/state`'}]

    # Test with bound v1
    mock_create_varname.return_value = 'v1'

    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'v1': 'V1TABLE.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': mock_h,
        'row': {'f': 'ftable'}
    }
    s = term.Variable('f')
    p = stateURI
    o = term.URIRef('https://example.com/obj')

    lib.bgp_translation_utils.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'FSTATETABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'v1': 'V1TABLE.id'}
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'attributes_view AS FSTATETABLE', 'join_condition':
                                               'FSTATETABLE.id = FTABLE.`\
https://industry-fusion.com/types/v0.9/state`'}]


@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.utils.create_varname')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_ngsild_spo_hasObject(mock_isentity, mock_create_table_name, mock_create_varname,
                                      mock_get_random_string, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = True
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_h = MagicMock()
    mock_h.predicates.return_value = [hasObjectURI]
    mock_h.objects.return_value = [term.Variable('f')]
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'sql_tables': [],
        'properties': properties,
        'relationships': relationships
    }
    # test with unbound v1
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'h': mock_h,
        'row': {'f': 'ftable'}
    }
    s = term.Variable('f')
    p = hasFilterURI
    o = term.BNode('1')
    lib.bgp_translation_utils.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'FHAS_FILTERTABLE': [], 'FTABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FTABLE.`id`'}
    assert local_ctx['bgp_sql_expression'] == [
        {'statement': 'attributes_view AS FHAS_FILTERTABLE', 'join_condition': 'FHAS_FILTERTABLE.id = \
FTABLE.`https://industry-fusion.com/types/v0.9/hasFilter`'},
        {'statement': 'ftable_view AS FTABLE', 'join_condition': 'FTABLE.id = FHAS_FILTERTABLE.\
`https://uri.etsi.org/ngsi-ld/hasObject`'}]

    # Test with bound v1
    mock_create_varname.return_value = 'v1'

    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'sql_tables': [],
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'c': 'CUTTER.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'h': mock_h,
        'row': {'c': 'ctable', 'f': 'ftable'}
    }
    s = term.Variable('c')
    p = hasFilterURI
    o = term.URIRef('https://example.com/obj')

    lib.bgp_translation_utils.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'CHAS_FILTERTABLE': [], 'FTABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'c': 'CUTTER.id', 'f': 'FTABLE.`id`'}
    assert local_ctx['bgp_sql_expression'] == [
        {'statement': 'attributes_view AS CHAS_FILTERTABLE', 'join_condition': 'CHAS_FILTERTABLE.id = \
CTABLE.`https://industry-fusion.com/types/v0.9/hasFilter`'},
        {'statement': 'ftable_view AS FTABLE', 'join_condition': 'FTABLE.id = CHAS_FILTERTABLE.\
`https://uri.etsi.org/ngsi-ld/hasObject`'}]


@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.utils.create_varname')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_ngsild_spo_obj_defined(mock_isentity, mock_create_table_name, mock_create_varname,
                                        mock_get_random_string, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = True
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_h = MagicMock()
    mock_h.predicates.return_value = [hasObjectURI]
    mock_h.objects.return_value = [term.Variable('f')]
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'sql_tables': [],
        'properties': properties,
        'relationships': relationships
    }
    # test with unbound v1
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FTABLE.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'h': mock_h,
        'row': {'f': 'ftable'}
    }
    s = term.Variable('f')
    p = hasFilterURI
    o = term.BNode('1')
    lib.bgp_translation_utils.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'FHAS_FILTERTABLE': [], 'FTABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FTABLE.id'}
    assert local_ctx['bgp_sql_expression'] == [
        {'statement': 'attributes_view AS FHAS_FILTERTABLE', 'join_condition': 'FHAS_FILTERTABLE.\
`https://uri.etsi.org/ngsi-ld/hasObject` = FTABLE.id'},
        {'statement': 'ftable_view AS FTABLE', 'join_condition': 'FHAS_FILTERTABLE.id = FTABLE.\
`https://industry-fusion.com/types/v0.9/hasFilter`'}]


@patch('lib.bgp_translation_utils.get_random_string')
@patch('lib.utils.create_varname')
@patch('lib.bgp_translation_utils.create_tablename')
@patch('lib.bgp_translation_utils.isentity')
def test_process_ngsild_spo_time_vars(mock_isentity, mock_create_table_name, mock_create_varname,
                                      mock_get_random_string, monkeypatch):
    relationships = {
    }
    properties = {
    }
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = True
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_h = MagicMock()
    mock_h.predicates.return_value = [observedAtURI]
    mock_h.objects.return_value = [term.Variable('f')]
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'sql_tables': [],
        'properties': properties,
        'relationships': relationships
    }
    # test with unbound v1
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FTABLE.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {'FOBSERVED_ATTABLE': []},
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'h': mock_h,
        'row': {'f': 'ftable'}
    }
    s = term.Variable('f')
    p = observedAtURI
    o = term.BNode('1')
    lib.bgp_translation_utils.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'FOBSERVED_ATTABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FTABLE.id'}
    assert local_ctx['bgp_sql_expression'] == []


@patch('lib.bgp_translation_utils.copy')
def test_sort_triples(mock_copy, monkeypatch):
    def create_varname(var):
        if var == term.Variable('f'):
            return 'f'
        if var == term.Variable('this'):
            return 'this'
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    monkeypatch.setattr(lib.utils, "create_varname", create_varname)
    bounds = {'this': 'THISTABLE.id'}
    triples = [
        (term.Variable('f'), stateURI, term.BNode('2')),
        (term.BNode('1'), hasObjectURI, term.Variable('f')),
        (term.Variable('this'), hasFilterURI, term.BNode('1')),
        ((term.BNode('2'), hasValueURI, term.Variable('v2')))
    ]
    mock_copy.deepcopy.return_value = bounds
    graph = MagicMock()
    graph.triples = MagicMock(side_effect=[
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('1'), hasObjectURI, term.Variable('f'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('1'), hasObjectURI, term.Variable('f'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))]
    ])
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'sql_tables': [],
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    result = lib.bgp_translation_utils.sort_triples(ctx, bounds, triples, graph)
    assert result[1] == (term.BNode('1'), hasObjectURI, term.Variable('f'))
    assert result[0] == (term.Variable('this'), hasFilterURI, term.BNode('1'))
    assert result[2] == (term.Variable('f'), stateURI, term.BNode('2'))
    assert result[3] == ((term.BNode('2'), hasValueURI, term.Variable('v2')))


@patch('lib.bgp_translation_utils.copy')
def test_sort_triples_rdf(mock_copy, monkeypatch):
    def create_varname(var):
        if var == term.Variable('f'):
            return 'f'
        if var == term.Variable('this'):
            return 'this'
    relationships = {
    }
    properties = {
    }
    monkeypatch.setattr(lib.utils, "create_varname", create_varname)
    bounds = {'this': 'THISTABLE.id'}
    triples = [
        (term.Variable('f'), stateURI, term.BNode('2')),
        (term.BNode('1'), hasObjectURI, term.Variable('f')),
        (term.Variable('this'), hasFilterURI, term.BNode('1')),
        ((term.BNode('2'), hasValueURI, term.Variable('v2')))
    ]
    mock_copy.deepcopy.return_value = bounds
    graph = MagicMock()
    graph.triples = MagicMock(side_effect=[
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('1'), hasObjectURI, term.Variable('f'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))],
        [(term.BNode('1'), hasObjectURI, term.Variable('f'))],
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))]
    ])
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']},
        'sql_tables': [],
        'property_variables': {},
        'entity_variables': {},
        'time_variables': {},
        'properties': properties,
        'relationships': relationships
    }
    result = lib.bgp_translation_utils.sort_triples(ctx, bounds, triples, graph)
    assert result[1] == (term.BNode('1'), hasObjectURI, term.Variable('f'))
    assert result[0] == (term.Variable('this'), hasFilterURI, term.BNode('1'))
    assert result[2] == (term.Variable('f'), stateURI, term.BNode('2'))
    assert result[3] == ((term.BNode('2'), hasValueURI, term.Variable('v2')))


def test_create_tablename():
    class Namespace_manager:
        def compute_qname(self, uri):
            return ['n', '', uri.toPython()]

    namespace_manager = Namespace_manager()
    result = lib.bgp_translation_utils.create_tablename(term.Variable('variable'))
    assert result == 'VARIABLETABLE'
    result = lib.bgp_translation_utils.create_tablename(term.Variable('variable'), term.URIRef('predicate'),
                                                        namespace_manager)
    assert result == 'VARIABLEPREDICATETABLE'
    result = lib.bgp_translation_utils.create_tablename(term.URIRef('subject'), term.URIRef('predicate'),
                                                        namespace_manager)
    assert result == 'SUBJECTPREDICATETABLE'


def test_get_rdf_join_condition(monkeypatch):
    def create_varname(var):
        return var.toPython()[1:]

    property_variables = {
        term.Variable('v2'): True,
        term.Variable('v1'): True
    }
    entity_variables = {
        term.Variable('f'): True,
        term.Variable('this'): True
    }
    time_variables = {}
    selectvars = {
        'v1': 'v1.id',
    }
    r = term.URIRef('test')
    result = lib.bgp_translation_utils.get_rdf_join_condition(r, property_variables,
                                                              entity_variables,
                                                              time_variables,
                                                              selectvars)
    assert result == "'<test>'"
    r = term.Variable('v1')
    result = lib.bgp_translation_utils.get_rdf_join_condition(r, property_variables,
                                                              entity_variables,
                                                              time_variables,
                                                              selectvars)
    assert result == "'<'||v1.id||'>'"


def test_get_rdf_join_condition_rdf(monkeypatch):
    def create_varname(var):
        return var.toPython()[1:]

    property_variables = {
        term.Variable('v2'): True,
    }
    entity_variables = {
        term.Variable('f'): True,
        term.Variable('this'): True
    }
    time_variables = {}
    selectvars = {
        'v1': 'v1.id',
    }
    r = term.Variable('f')
    with pytest.raises(Exception):
        result = lib.bgp_translation_utils.get_rdf_join_condition(r, property_variables,
                                                                  entity_variables,
                                                                  time_variables,
                                                                  selectvars)
    r = term.Variable('v1')
    result = lib.bgp_translation_utils.get_rdf_join_condition(r, property_variables, entity_variables,
                                                              time_variables,
                                                              selectvars)
    assert result == "v1.id"
