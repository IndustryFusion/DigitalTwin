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
import lib.utils
from bunch import Bunch
from rdflib import term
import pytest

hasObjectURI = term.URIRef("https://uri.etsi.org/ngsi-ld/hasObject")
stateURI = term.URIRef("https://industry-fusion.com/types/v0.9/state")
hasFilterURI = term.URIRef("https://industry-fusion.com/types/v0.9/hasFilter")
hasValueURI = term.URIRef("https://uri.etsi.org/ngsi-ld/hasValue")
target_class = term.URIRef("https://industry-fusion.com/types/v0.9/cutter")
target_class_filter = term.URIRef("https://industry-fusion.com/types/v0.9/filter")
cutter = term.URIRef("cutter")


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
    with pytest.raises(lib.sparql_to_sql.utils.WrongSparqlStructure):
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
    monkeypatch.setattr(lib.sparql_to_sql.utils, "create_varname", create_varname)

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
    assert result == "CASE WHEN condition THEN '<arg2>' ELSE '<arg3>' END"
    assert mock_translate.called


@patch('lib.sparql_to_sql.bgp_translation_utils.process_ngsild_spo')
@patch('lib.sparql_to_sql.bgp_translation_utils.process_rdf_spo')
@patch('lib.sparql_to_sql.bgp_translation_utils.sort_triples')
@patch('lib.sparql_to_sql.bgp_translation_utils.create_ngsild_mappings')
def test_translate_BGP(mock_create_ngsild_mappings, mock_sort_triples, mock_process_rdf_spo, mock_process_ngsild_spo):
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


@patch('lib.sparql_to_sql.translate')
def test_translate_relational_expression(monkeypatch):
    def create_varname(var):
        return var.toPython()[1:]
    hash = {
        'bounds': {
            'var': 'vartest'
        }
    }
    monkeypatch.setattr(lib.sparql_to_sql.utils, "create_varname", create_varname)

    ctx = MagicMock()
    ctx.__getitem__.side_effect = hash.__getitem__
    elem = MagicMock()
    elem.other = term.URIRef('testuri')
    elem.expr = term.Literal('literal')
    elem.op = '<='
    result = lib.sparql_to_sql.translate_relational_expression(ctx, elem)
    assert result == "'\"literal\"' <= '<testuri>'"


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


@patch('lib.sparql_to_sql.utils.create_varname')
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
@patch('lib.sparql_to_sql.Graph')
def test_translate_sparql(mock_graph, mock_translate_query, mock_parseQuery, mock_translateQuery,
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
    result = lib.sparql_to_sql.translate_sparql(shaclfile, knowledgefile, sparql_query, target_class, g)
    assert result == ('target_sql', 'sql_tables')
    assert mock_translate_query.called
    assert mock_translateQuery.called
    assert mock_parseQuery.called


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


def test_get_attribute_column(monkeypatch):
    relationships = {
        "https://industry-fusion.com/types/v0.9/hasFilter": True
    }
    properties = {
        "https://industry-fusion.com/types/v0.9/state": True
    }
    monkeypatch.setattr(lib.sparql_to_sql, "properties", properties)
    monkeypatch.setattr(lib.sparql_to_sql, "relationships", relationships)
    ctx = {
        'bounds': {'var': 'TABLE.`id`'},
        'PV': ['var'],
        'property_variables': {term.Variable('y')},
        'tables': {}
    }
    node = {
        'template': [
            (term.Variable("var"), term.URIRef("https://industry-fusion.com/types/v0.9/state"), term.BNode("x")),
            (term.BNode("x"), term.URIRef("https://uri.etsi.org/ngsi-ld/hasValue"), term.Variable("y"))
        ]
    }
    (entityid_var, name, attribute_type, value_var, nodetype) = lib.sparql_to_sql.get_attribute_column(ctx, node)
    assert entityid_var == term.Variable('var')
    assert name == 'https://industry-fusion.com/types/v0.9/state'
    assert attribute_type == 'https://uri.etsi.org/ngsi-ld/Property'
    assert value_var == term.Variable('y')
    assert nodetype == '@value'


@patch('lib.sparql_to_sql.get_bound_trim_string')
@patch('lib.sparql_to_sql.get_attribute_column')
def test_wrap_sql_construct(attribute_column_mock, get_bound_trim_string_mock):
    attribute_column_mock.return_value = (term.Variable("var"), 'name', 'type', 'value', 'nodetype')
    get_bound_trim_string_mock.return_value = 'bound_trim_string'
    ctx = {
        'bounds': {'var': 'TABLE.`id`'},
        'PV': ['var'],
        'property_variables': {term.Variable('y')},
        'tables': {}
    }
    node = {
        'target_sql': 'target_sql',
        'where': 'where'
    }
    lib.sparql_to_sql.wrap_sql_construct(ctx, node)
    assert node['target_sql'] == "SQL_DIALECT_INSERT_ATTRIBUTES\nSELECT TABLE.`id` || '\\' || 'name',\
\nTABLE.`id`,\
\n'name',\
\n'nodetype',\
\nCAST(NULL as STRING),\
\n0,\
\n'type',\
\nbound_trim_string,\
\nCAST(NULL as STRING)\n,\
SQL_DIALECT_SQLITE_TIMESTAMP\nFROM target_sql WHERE where"


@patch('lib.sparql_to_sql.translate')
@patch('lib.sparql_to_sql.wrap_sql_construct')
@patch('lib.sparql_to_sql.bgp_translation_utils.merge_vartypes')
@patch('lib.sparql_to_sql.bgp_translation_utils.create_ngsild_mappings')
def test_translate_construct_query(create_ngsild_mappings_mock, merge_vartypes_mock,
                                   wrap_sql_construct_mock, translate_mock):
    ctx = {}
    query = MagicMock()
    query.p = {
        'target_sql': 'target_sql',
        'where': 'where'
    }
    d = {}
    query.__setitem__.side_effect = d.__setitem__
    create_ngsild_mappings_mock.return_value = ({}, {}, {})
    lib.sparql_to_sql.translate_construct_query(ctx, query)
    assert d['where'] == 'where'
    assert d['target_sql'] == 'target_sql'


def test_merge_bgp_context():
    bgp_context = [
        {
            'statement': 'statement',
            'join_condition': 'join_condition',
        },
        {
            'statement': 'statement2',
            'join_condition': 'join_condition2',
        }
    ]
    expression, where = lib.sparql_to_sql.merge_bgp_context(bgp_context, True)
    assert where == 'join_condition'
    assert expression == 'statement JOIN statement2 ON join_condition2'
