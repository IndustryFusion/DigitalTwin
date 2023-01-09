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
import lib.sparql_to_sql
from bunch import Bunch
from rdflib import term, RDF, Graph as rGraph
import pytest

hasObjectURI = term.URIRef("https://uri.etsi.org/ngsi-ld/hasObject")
stateURI = term.URIRef("https://industry-fusion.com/types/v0.9/state")
hasFilterURI = term.URIRef("https://industry-fusion.com/types/v0.9/hasFilter")
hasValueURI = term.URIRef("https://uri.etsi.org/ngsi-ld/hasValue")
target_class = term.URIRef("https://industry-fusion.com/types/v0.9/cutter")
target_class_filter = term.URIRef("https://industry-fusion.com/types/v0.9/filter")
cutter = term.URIRef("cutter")


def test_create_ngsild_mappings(monkeypatch):
    class Graph:
        def query(self, sparql):
            assert "?this rdfs:subClassOf <https://industry-fusion.com/types/v0.9/cutter> ." in sparql
            assert "?thisshape sh:targetClass ?this .\n?thisshape sh:property [ sh:path \
<https://industry-fusion.com/types/v0.9/hasFilter> ; sh:property [ sh:path \
ngsild:hasObject;  sh:class ?f ] ] ." in sparql
            assert "?v2shape sh:targetClass ?v2 .\n?v2shape sh:property [ sh:path \
<https://industry-fusion.com/types/v0.9/state> ; ] ." in sparql
            assert "?v1shape sh:targetClass ?v1 .\n?v1shape sh:property [ sh:path \
<https://industry-fusion.com/types/v0.9/state> ; ] ." in sparql
            assert "?thisshape = ?v1shape" in sparql
            assert "?fshape = ?v2shape" in sparql
            return ['row']
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    g = Graph()
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "g", g)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
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
        'target_modifiers': []
    }

    graph = rGraph()
    graph.add((term.BNode('1'), hasObjectURI, term.Variable('f')))
    graph.add((term.Variable('f'), stateURI, term.BNode('2')))
    graph.add((term.Variable('this'), hasFilterURI, term.BNode('1')))
    graph.add((term.Variable('this'), stateURI, term.BNode('3')))
    graph.add((term.BNode('2'), hasValueURI, term.Variable('v2')))
    graph.add((term.BNode('3'), hasValueURI, term.Variable('v1')))

    property_variables, entity_variables, row = lib.sparql_to_sql.create_ngsild_mappings(ctx, graph)
    assert property_variables == {
        term.Variable('v2'): True,
        term.Variable('v1'): True
    }
    assert entity_variables == {
        term.Variable('f'): True,
        term.Variable('this'): True
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
            assert "?thisshape = ?v1shape" in sparql
            assert "?pcshape = ?v2shape" in sparql
            return ['row']

    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    g = Graph()
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "g", g)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
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
        'target_modifiers': []
    }

    graph = rGraph()
    graph.add((term.Variable('this'), stateURI, term.BNode('1')))
    graph.add((term.Variable('pc'), hasFilterURI, term.BNode('2')))
    graph.add((term.BNode('2'), hasObjectURI, term.Variable('this')))
    graph.add((term.Variable('pc'), stateURI, term.BNode('3')))
    graph.add((term.BNode('1'), hasValueURI, term.Variable('v1')))
    graph.add((term.BNode('3'), hasValueURI, term.Variable('v2')))

    property_variables, entity_variables, row = lib.sparql_to_sql.create_ngsild_mappings(ctx, graph)
    assert property_variables == {
        term.Variable('v2'): True,
        term.Variable('v1'): True
    }
    assert entity_variables == {
        term.Variable('pc'): True,
        term.Variable('this'): True
    }
    assert row == 'row'


@patch('lib.sparql_to_sql.get_random_string')
@patch('lib.sparql_to_sql.create_varname')
@patch('lib.sparql_to_sql.create_tablename')
@patch('lib.sparql_to_sql.isentity')
def test_process_rdf_spo_predicate_is_rdftype_object_is_iri(mock_isentity, mock_create_table_name,
                                                            mock_create_varname, mock_get_random_string, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = True
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']}
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'h': {},
        'row': 'row'
    }
    s = term.Variable('f')
    p = RDF['type']
    o = term.URIRef('https://example.com/obj')
    lib.sparql_to_sql.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['where'] == "FILTER.type = 'https://example.com/obj'"
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id'}


@patch('lib.sparql_to_sql.get_rdf_join_condition')
@patch('lib.sparql_to_sql.get_random_string')
@patch('lib.sparql_to_sql.create_tablename')
@patch('lib.sparql_to_sql.isentity')
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
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
    monkeypatch.setattr(lib.sparql_to_sql, "create_varname", create_varname)
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = True
    mock_get_random_string.return_value = ''
    mock_get_rdf_join_condiion.return_value = 'condition'
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']}
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'x': 'xtable.subject'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'h': {},
        'row': 'row'
    }
    s = term.Variable('f')
    p = RDF['type']
    o = term.Variable('x')
    lib.sparql_to_sql.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['where'] == 'FILTER.type = xtable.subject'
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'x': 'xtable.subject'}
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']}
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'x': 'xtable.subject'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'h': {},
        'row': 'row'
    }
    mock_get_rdf_join_condiion.return_value = None

    s = term.Variable('f')
    p = RDF['type']
    o = term.Variable('x')
    lib.sparql_to_sql.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['selvars'] == {'x': 'FILTER.type'}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'x': 'FILTER.type'}


@patch('lib.sparql_to_sql.get_rdf_join_condition')
@patch('lib.sparql_to_sql.get_random_string')
@patch('lib.sparql_to_sql.create_varname')
@patch('lib.sparql_to_sql.create_tablename')
@patch('lib.sparql_to_sql.isentity')
def test_process_rdf_spo_subject_is_no_entity(mock_isentity, mock_create_table_name, mock_create_varname,
                                              mock_get_random_string, mock_get_rdf_join_condition,
                                              monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = False
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_get_rdf_join_condition.return_value = 'condition'
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']}
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'h': {},
        'row': 'row'
    }
    s = term.Variable('f')
    p = term.URIRef('predicate')
    o = term.URIRef('https://example.com/obj')
    lib.sparql_to_sql.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'rdf AS testtable',
                                                'join_condition': "testtable.subject = condition and \
testtable.predicate = 'predicate' and testtable.object = condition"}]
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id'}
    assert local_ctx['bgp_tables'] == {'testtable': []}

    mock_get_rdf_join_condition.return_value = None
    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']}
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'h': {},
        'row': 'row'
    }
    p = term.URIRef('test')
    o = term.Variable('x')
    lib.sparql_to_sql.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'rdf AS testtable',
                                                'join_condition': "testtable.predicate = 'test'"}]
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'testtable.object'}
    assert local_ctx['bgp_tables'] == {'testtable': []}
    assert local_ctx['selvars'] == {'f': 'testtable.object'}


@patch('lib.sparql_to_sql.utils')
@patch('lib.sparql_to_sql.get_rdf_join_condition')
@patch('lib.sparql_to_sql.get_random_string')
@patch('lib.sparql_to_sql.create_varname')
@patch('lib.sparql_to_sql.create_tablename')
@patch('lib.sparql_to_sql.isentity')
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
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
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
        'sql_tables': []
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'h': {},
        'row': {'f': 'f'}
    }
    s = term.Variable('f')
    p = RDF['type']
    o = term.URIRef('https://example.com/obj')
    lib.sparql_to_sql.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'camelcase_to_snake_case_view AS FTABLE',
                                                'join_condition': ''},
                                               {'statement': 'rdf as testtable',
                                                'join_condition': "testtable.subject = FTABLE.`type` and \
testtable.predicate = 'http://www.w3.org/2000/01/rdf-schema#subClassOf' and testtable.object = \
'https://example.com/obj'"}]
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FTABLE.`id`'}
    assert local_ctx['bgp_tables'] == {'FTABLE': []}


@patch('lib.sparql_to_sql.get_rdf_join_condition')
@patch('lib.sparql_to_sql.get_random_string')
@patch('lib.sparql_to_sql.create_varname')
@patch('lib.sparql_to_sql.create_tablename')
@patch('lib.sparql_to_sql.isentity')
def test_process_rdf_spo_subject_is_entity_and_predicate_is_type(mock_isentity, mock_create_table_name,
                                                                 mock_create_varname, mock_get_random_string,
                                                                 mock_get_rdf_join_condition, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
    mock_create_table_name.return_value = 'testtable'
    mock_isentity.return_value = False
    mock_create_varname.return_value = 'f'
    mock_get_random_string.return_value = ''
    mock_get_rdf_join_condition.return_value = 'condition'

    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']}
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.`id`'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {term.Variable('f'): True},
        'h': {},
        'row': 'row'
    }
    s = term.Variable('f')
    p = RDF['type']
    o = term.URIRef('https://example.com/obj')
    lib.sparql_to_sql.process_rdf_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['where'] == "FILTER.type = 'https://example.com/obj'"


@patch('lib.sparql_to_sql.get_random_string')
@patch('lib.sparql_to_sql.create_varname')
@patch('lib.sparql_to_sql.create_tablename')
@patch('lib.sparql_to_sql.isentity')
def test_process_ngsild_spo_hasValue(mock_isentity, mock_create_table_name, mock_create_varname,
                                     mock_get_random_string, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
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
        'tables': {'THISTABLE': ['id']}
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
        'h': mock_h,
        'row': {'f': 'ftable'}
    }
    s = term.Variable('f')
    p = stateURI
    o = term.URIRef('https://example.com/obj')
    lib.sparql_to_sql.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'FSTATETABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'v1': '`FSTATETABLE`.\
`https://uri.etsi.org/ngsi-ld/hasValue`'}
    assert local_ctx['selvars'] == {'v1': '`FSTATETABLE`.`https://uri.etsi.org/ngsi-ld/hasValue`'}
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'attributes_view AS FSTATETABLE', 'join_condition':
                                               'FSTATETABLE.id = FTABLE.\
`https://industry-fusion.com/types/v0.9/state`'}]

    # Test with bound v1
    mock_create_varname.return_value = 'v1'

    ctx = {
        'namespace_manager': None,
        'bounds': {'this': 'THISTABLE.id'},
        'tables': {'THISTABLE': ['id']}
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'v1': 'V1TABLE.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'h': mock_h,
        'row': {'f': 'ftable'}
    }
    s = term.Variable('f')
    p = stateURI
    o = term.URIRef('https://example.com/obj')

    lib.sparql_to_sql.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'FSTATETABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FILTER.id', 'v1': 'V1TABLE.id'}
    assert local_ctx['selvars'] == {}
    assert local_ctx['bgp_sql_expression'] == [{'statement': 'attributes_view AS FSTATETABLE', 'join_condition':
                                               'FSTATETABLE.id = FTABLE.`\
https://industry-fusion.com/types/v0.9/state`'}]


@patch('lib.sparql_to_sql.get_random_string')
@patch('lib.sparql_to_sql.create_varname')
@patch('lib.sparql_to_sql.create_tablename')
@patch('lib.sparql_to_sql.isentity')
def test_process_ngsild_spo_hasObject(mock_isentity, mock_create_table_name, mock_create_varname,
                                      mock_get_random_string, monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
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
        'sql_tables': []
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
        'h': mock_h,
        'row': {'f': 'ftable'}
    }
    s = term.Variable('f')
    p = hasFilterURI
    o = term.BNode('1')
    lib.sparql_to_sql.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'FHAS_FILTERTABLE': [], 'FTABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'f': 'FTABLE.`id`'}
    assert local_ctx['selvars'] == {'f': 'FTABLE.`id`'}
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
        'sql_tables': []
    }
    local_ctx = {
        'bounds': {'this': 'THISTABLE.id', 'c': 'CUTTER.id'},
        'selvars': {},
        'where': '',
        'bgp_sql_expression': [],
        'bgp_tables': {},
        'property_variables': {},
        'entity_variables': {},
        'h': mock_h,
        'row': {'c': 'ctable', 'f': 'ftable'}
    }
    s = term.Variable('c')
    p = hasFilterURI
    o = term.URIRef('https://example.com/obj')

    lib.sparql_to_sql.process_ngsild_spo(ctx, local_ctx, s, p, o)
    assert local_ctx['bgp_tables'] == {'CHAS_FILTERTABLE': [], 'FTABLE': []}
    assert local_ctx['bounds'] == {'this': 'THISTABLE.id', 'c': 'CUTTER.id', 'f': 'FTABLE.`id`'}
    assert local_ctx['selvars'] == {'f': 'FTABLE.`id`'}
    assert local_ctx['bgp_sql_expression'] == [
        {'statement': 'attributes_view AS CHAS_FILTERTABLE', 'join_condition': 'CHAS_FILTERTABLE.id = \
CTABLE.`https://industry-fusion.com/types/v0.9/hasFilter`'},
        {'statement': 'ftable_view AS FTABLE', 'join_condition': 'FTABLE.id = CHAS_FILTERTABLE.\
`https://uri.etsi.org/ngsi-ld/hasObject`'}]


@patch('lib.sparql_to_sql.copy')
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
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
    monkeypatch.setattr(lib.sparql_to_sql, "create_varname", create_varname)
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
        [(term.BNode('2'), hasValueURI, term.Variable('v2'))]
    ])
    result = lib.sparql_to_sql.sort_triples(bounds, triples, graph)
    assert result[0] == (term.BNode('1'), hasObjectURI, term.Variable('f'))
    assert result[1] == (term.Variable('this'), hasFilterURI, term.BNode('1'))
    assert result[2] == (term.Variable('f'), stateURI, term.BNode('2'))
    assert result[3] == ((term.BNode('2'), hasValueURI, term.Variable('v2')))


def test_create_tablename():
    class Namespace_manager:
        def compute_qname(self, uri):
            return ['n', '', uri.toPython()]

    namespace_manager = Namespace_manager()
    result = lib.sparql_to_sql.create_tablename(term.Variable('variable'))
    assert result == 'VARIABLETABLE'
    result = lib.sparql_to_sql.create_tablename(term.Variable('variable'), term.URIRef('predicate'), namespace_manager)
    assert result == 'VARIABLEPREDICATETABLE'
    result = lib.sparql_to_sql.create_tablename(term.URIRef('subject'), term.URIRef('predicate'), namespace_manager)
    assert result == 'SUBJECTPREDICATETABLE'


def test_get_rdf_join_condition(monkeypatch):
    def create_varname(var):
        return var.toPython()[1:]

    monkeypatch.setattr(lib.sparql_to_sql, "create_varname", create_varname)

    property_variables = {
        term.Variable('v2'): True,
        term.Variable('v1'): True
    }
    entity_variables = {
        term.Variable('f'): True,
        term.Variable('this'): True
    }
    selectvars = {
        'v1': 'v1.id',
    }
    r = term.URIRef('test')
    result = lib.sparql_to_sql.get_rdf_join_condition(r, property_variables, entity_variables, selectvars)
    assert result == "'test'"
    r = term.Variable('v1')
    result = lib.sparql_to_sql.get_rdf_join_condition(r, property_variables, entity_variables, selectvars)
    assert result == 'v1.id'


@patch('lib.sparql_to_sql.translate')
def test_translate_query(mock_translate):
    query = MagicMock()
    algebra = MagicMock()
    algebra.name = 'SelectQuery'
    query.algebra = algebra
    algebra['target_sql'] = 'target_sql'
    target_class = 'class'
    result = lib.sparql_to_sql.translate_query(query, target_class)
    assert result['classes'] == {'this': target_class}
    assert mock_translate.called


@patch('lib.sparql_to_sql.translate_function')
def test_translate(mock_translate_function):
    elem = MagicMock()
    elem.name = 'test'
    ctx = MagicMock()
    with pytest.raises(lib.sparql_to_sql.WrongSparqlStructure):
        lib.sparql_to_sql.translate(ctx, elem)

    elem.name = 'Function'
    lib.sparql_to_sql.translate(ctx, elem)
    assert mock_translate_function.called


def test_translate_function(monkeypatch):
    def create_varname(var):
        return var.toPython()[1:]
    hash = {
        'bounds': {
            'var': 'vartest'
        }
    }
    monkeypatch.setattr(lib.sparql_to_sql, "create_varname", create_varname)

    ctx = MagicMock()
    ctx.__getitem__.side_effect = hash.__getitem__
    function = MagicMock()
    function.iri = term.URIRef('http://www.w3.org/2001/XMLSchema#float')
    function.expr = [term.Variable('var')]
    result = lib.sparql_to_sql.translate_function(ctx, function)
    assert result == 'CAST(vartest as FLOAT)'


@patch('lib.sparql_to_sql.translate')
def test_translate_builtin_if(mock_translate, monkeypatch):
    ctx = MagicMock()
    mock_translate.return_value = 'condition'
    builtin_if = MagicMock()
    builtin_if.arg2 = term.URIRef('arg2')
    builtin_if.arg3 = term.URIRef('arg3')
    result = lib.sparql_to_sql.translate_builtin_if(ctx, builtin_if)
    assert result == "CASE WHEN condition THEN 'arg2' ELSE 'arg3' END"
    assert mock_translate.called


@patch('lib.sparql_to_sql.create_bgp_context')
@patch('lib.sparql_to_sql.process_ngsild_spo')
@patch('lib.sparql_to_sql.process_rdf_spo')
@patch('lib.sparql_to_sql.sort_triples')
@patch('lib.sparql_to_sql.create_ngsild_mappings')
def test_translate_BGP(mock_create_ngsild_mappings, mock_sort_triples, mock_process_rdf_spo, mock_process_ngsild_spo,
                       mock_create_bgp_context):
    ctx = MagicMock()
    bgp = MagicMock()
    bgp.name = 'BGP'
    hash = {
        'add_triples': [],
        'bounds': {},
        'tables': ['tables']
    }
    bgp.triples = []
    ctx.__getitem__.side_effect = hash.__getitem__

    lib.sparql_to_sql.translate_BGP(ctx, bgp)
    assert not mock_create_ngsild_mappings.called

    mock_create_ngsild_mappings.return_value = ({}, {}, {})
    bgp.triples = [(term.Variable('this'), term.URIRef('hasValue'), term.Literal('test'))]
    mock_sort_triples.return_value = bgp.triples
    lib.sparql_to_sql.translate_BGP(ctx, bgp)
    assert mock_sort_triples.called
    assert mock_process_rdf_spo.called
    assert mock_create_ngsild_mappings.called
    assert not mock_process_ngsild_spo.called
    assert mock_create_bgp_context.called


@patch('lib.sparql_to_sql.translate')
def test_translate_relational_expression(monkeypatch):
    def create_varname(var):
        return var.toPython()[1:]
    hash = {
        'bounds': {
            'var': 'vartest'
        }
    }
    monkeypatch.setattr(lib.sparql_to_sql, "create_varname", create_varname)

    ctx = MagicMock()
    ctx.__getitem__.side_effect = hash.__getitem__
    elem = MagicMock()
    elem.other = term.URIRef('testuri')
    elem.expr = term.Literal('literal')
    elem.op = '<='
    result = lib.sparql_to_sql.translate_relational_expression(ctx, elem)
    assert result == "'literal' <= 'testuri'"


@patch('lib.sparql_to_sql.translate')
def test_translate_left_join(mock_translate):

    hash1 = {
        'target_sql': 'target_sql1',
        'where': 'where1'
    }
    hash2 = {
        'target_sql': 'target_sql2',
        'where': 'where2'
    }
    ctx = MagicMock()
    join = Bunch()
    join['target_sql'] = ''
    join.p1 = hash1
    join.p2 = hash2
    lib.sparql_to_sql.translate_left_join(ctx, join)
    assert join['target_sql'] == ' target_sql1 LEFT JOIN target_sql2 ON where2'
    assert join['where'] == 'where1'
    assert mock_translate.call_count == 2
    hash2 = {
        'target_sql': '',
        'where': 'where2'
    }
    join.p2 = hash2
    lib.sparql_to_sql.translate_left_join(ctx, join)
    assert join['target_sql'] == 'target_sql1'
    assert join['where'] == '((where1 and where2) or where1)'
    assert mock_translate.call_count == 4


@patch('lib.sparql_to_sql.translate')
def test_translate_join(mock_translate):

    hash1 = {
        'target_sql': 'target_sql1',
        'where': 'where1'
    }
    hash2 = {
        'target_sql': 'target_sql2',
        'where': 'where2'
    }
    ctx = MagicMock()
    join = Bunch()
    join['target_sql'] = ''
    join.p1 = hash1
    join.p2 = hash2
    lib.sparql_to_sql.translate_join(ctx, join)
    assert join['target_sql'] == ' target_sql1 JOIN target_sql2 ON where2'
    assert join['where'] == 'where1'
    assert mock_translate.call_count == 2
    hash2 = {
        'target_sql': '',
        'where': 'where2'
    }
    join.p2 = hash2
    lib.sparql_to_sql.translate_join(ctx, join)
    assert join['target_sql'] == ''
    assert join['where'] == '(where1 and where2)'
    assert mock_translate.call_count == 4


def test_remap_join_constraint_to_where():

    node = {
        'where': 'where',
        'target_sql': 'target_sql'
    }
    lib.sparql_to_sql.remap_join_constraint_to_where(node)
    assert node == {'where': 'where', 'target_sql': 'target_sql'}

    node = {
        'where': 'A = B',
        'target_sql': 'A.subject = s and A.predicate = p and A.object = o'
    }
    lib.sparql_to_sql.remap_join_constraint_to_where(node)
    assert node['where'] == 'A = B and A.subject = s and A.object = o'
    assert node['target_sql'] == ' A.predicate = p '
    node = {
        'where': '',
        'target_sql': 'A.subject = s and A.predicate = p and A.object = o'
    }
    lib.sparql_to_sql.remap_join_constraint_to_where(node)
    assert node['where'] == 'A.subject = s and A.object = o'
    assert node['target_sql'] == ' A.predicate = p '


def test_map_join_condition():

    sql_expressions = [
        {'join_condition': 'select * from table1 join table2 on TABLE1.id = TABLE2.id'}
    ]
    local_tables = {
        'TABLE1': []
    }
    global_tables = {}
    lib.sparql_to_sql.map_join_condition(sql_expressions, local_tables, global_tables)
    assert global_tables == {'TABLE2': 'id'}


@patch('lib.sparql_to_sql.create_varname')
def test_wrap_sql_projection(mock_create_varname):
    ctx = {
        'bounds': {
            'var': 'bound'
        },
        'target_modifiers': [],
        'PV': ['varx']
    }
    node = {
        'where': 'where',
        'target_sql': 'target_sql'
    }
    mock_create_varname.return_value = 'var'
    lib.sparql_to_sql.wrap_sql_projection(ctx, node)
    assert node == {'where': 'where', 'target_sql': 'SELECT bound AS `var`  FROM target_sql WHERE where'}


@patch('lib.sparql_to_sql.translateQuery')
@patch('lib.sparql_to_sql.parseQuery')
@patch('lib.sparql_to_sql.translate_query')
@patch('lib.sparql_to_sql.owlrl')
@patch('lib.sparql_to_sql.Graph')
def test_translate_sparql(mock_graph, mock_owrl, mock_translate_query, mock_parseQuery, mock_translateQuery,
                          monkeypatch):

    g = MagicMock()
    monkeypatch.setattr(lib.sparql_to_sql, "g", g)
    shaclfile = MagicMock()
    knowledgefile = MagicMock()
    sparql_query = ''
    target_class = 'class'
    ctx = {
        'target_sql': 'target_sql',
        'sql_tables': 'sql_tables'
    }
    mock_translate_query.return_value = ctx
    row1 = Bunch()
    row2 = Bunch()
    row1.property = term.URIRef('property')
    row1.relationship = term.URIRef('relationship')
    row2.property = term.URIRef('property2')
    row2.relationship = term.URIRef('relationship2')
    g.__iadd__.return_value.query = MagicMock(side_effect=[[row1], [row2]])
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
    result = lib.sparql_to_sql.translate_sparql(shaclfile, knowledgefile, sparql_query, target_class)
    assert result == ('target_sql', 'sql_tables')
    assert mock_translate_query.called
    assert mock_translateQuery.called
    assert mock_parseQuery.called


@patch('lib.sparql_to_sql.create_varname')
def test_add_projection_vars_to_tables(mock_create_varname):
    mock_create_varname.return_value = 'var'
    ctx = {
        'bounds': {'var': 'TABLE.`id`'},
        'PV': ['var'],
        'tables': {}
    }
    lib.sparql_to_sql.add_projection_vars_to_tables(ctx)
    assert ctx['tables']['TABLE'] == ['id']


@patch('lib.sparql_to_sql.translate')
def test_translate_filter(mock_translate):
    filter = Bunch()
    p = {
        'where': 'where',
        'target_sql': 'target_sql'
    }
    p['where'] = 'where'
    filter.p = p
    filter.expr = 'expr'
    ctx = MagicMock()
    mock_translate.return_value = 'wherex'
    lib.sparql_to_sql.translate_filter(ctx, filter)
    assert mock_translate.called
    assert filter['where'] == 'wherex and where'
