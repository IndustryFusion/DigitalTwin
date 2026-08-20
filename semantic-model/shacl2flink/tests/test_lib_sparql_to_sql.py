import lib.configs as configs
import hashlib
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
from munch import Munch
from rdflib import term
import pytest
from rdflib import Variable


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
    result = lib.sparql_to_sql.translate_query(query, target_class, 'query')
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
        },
        'entity_variables': {},
        'property_variables': {},
        'time_variables': {}
    }
    monkeypatch.setattr(lib.sparql_to_sql.utils, "create_varname", create_varname)

    ctx = MagicMock()
    ctx.__getitem__.side_effect = hash.__getitem__
    function = MagicMock()
    function.iri = term.URIRef('http://www.w3.org/2001/XMLSchema#float')
    function.expr = [term.Variable('var')]
    result = lib.sparql_to_sql.translate_function(ctx, function)
    assert result == 'SQL_DIALECT_CAST(SQL_DIALECT_STRIP_LITERAL{vartest} as FLOAT)'
    function = MagicMock()
    function.iri = term.URIRef('https://industry-fusion.com/aggregators/v0.9/test')
    function.expr = [term.Variable('var')]
    result = lib.sparql_to_sql.translate_function(ctx, function)
    assert result == 'test(vartest)'
    function = MagicMock()
    function.iri = term.URIRef('https://industry-fusion.com/functions/v0.9/test')
    function.expr = [term.Variable('var')]
    result = lib.sparql_to_sql.translate_function(ctx, function)
    assert result == 'test(vartest)'


@patch('lib.sparql_to_sql.translate')
def test_translate_builtin_if(mock_translate, monkeypatch):
    ctx = MagicMock()
    mock_translate.side_effect = ["condition", "<arg2>", "<arg3>"]
    builtin_if = MagicMock()
    result = lib.sparql_to_sql.translate_builtin_if(ctx, builtin_if)
    assert result == "CASE WHEN condition THEN <arg2> ELSE <arg3> END"
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
        'tables': {'tables': 'tables'},
        'entity_variables': {},
        'property_variables': {},
        'time_variables': {}
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
        },
        'entity_variables': {},
        'property_variables': {},
        'time_variables': {}
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
    join = Munch()
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
    join = Munch()
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
    row1 = Munch()
    row2 = Munch()
    row1.property = term.URIRef('property')
    row1.relationship = term.URIRef('relationship')
    row1.kind = term.URIRef('kind')
    row2.property = term.URIRef('property2')
    row2.relationship = term.URIRef('relationship2')
    row2.kind = term.URIRef('kind')
    g.query = MagicMock(side_effect=[[row1], [row2]])
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
    filter = Munch()
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


@patch('lib.sparql_to_sql.translate')
@patch('lib.sparql_to_sql.bgp_translation_utils')
def test_translate_aggregate_join(mock_translation_utils, mock_translate):
    ctx = MagicMock()
    elem = Munch()
    p = {
        'target_sql': 'target_sql',
        'where': 'where'
    }
    elem.p = p
    lib.sparql_to_sql.translate_aggregate_join(ctx, elem)
    assert mock_translate.called
    assert mock_translation_utils.replace_attributes_table_expression.called
    assert elem['where'] == 'where'


def test_get_attribute_column_value(monkeypatch):
    ctx = {
        'bounds': {'var': 'TABLE.`id`'},
        'PV': ['var'],
        'property_variables': {term.Variable('y'): False},
        'tables': {},
        'properties': {
            "https://industry-fusion.com/types/v0.9/state": True
        },
        'relationships': {
            "https://industry-fusion.com/types/v0.9/hasFilter": True
        }
    }
    node = {
        'template': [
            (term.Variable("var"), term.URIRef("https://industry-fusion.com/types/v0.9/state"), term.BNode("x")),
            (term.BNode("x"), term.URIRef("https://uri.etsi.org/ngsi-ld/hasValue"), term.Variable("y"))
        ]
    }
    result = lib.sparql_to_sql.get_attribute_columns(ctx, node)
    assert result[0][0] == term.Variable('var')
    assert result[0][1] == 'https://industry-fusion.com/types/v0.9/state'
    assert result[0][2] == 'https://uri.etsi.org/ngsi-ld/Property'
    assert result[0][3] == term.Variable('y')
    assert result[0][4] == '@value'


def test_get_attribute_column_iri(monkeypatch):
    ctx = {
        'bounds': {'var': 'TABLE.`id`'},
        'PV': ['var'],
        'property_variables': {term.Variable('y'): True},
        'tables': {},
        'properties': {
            "https://industry-fusion.com/types/v0.9/state": True
        },
        'relationships': {
            "https://industry-fusion.com/types/v0.9/hasFilter": True
        }
    }
    node = {
        'template': [
            (term.Variable("var"), term.URIRef("https://industry-fusion.com/types/v0.9/state"), term.BNode("x")),
            (term.BNode("x"), term.URIRef("https://uri.etsi.org/ngsi-ld/hasValue"), term.Variable("y"))
        ]
    }
    result = lib.sparql_to_sql.get_attribute_columns(ctx, node)
    assert result[0][0] == term.Variable('var')
    assert result[0][1] == 'https://industry-fusion.com/types/v0.9/state'
    assert result[0][2] == 'https://uri.etsi.org/ngsi-ld/Property'
    assert result[0][3] == term.Variable('y')
    assert result[0][4] == '@id'


@patch('lib.sparql_to_sql.get_bound_trim_string')
@patch('lib.sparql_to_sql.get_attribute_columns')
def test_wrap_sql_construct(attribute_column_mock, get_bound_trim_string_mock):
    attribute_column_mock.return_value = [(term.Variable("var"), 'name', 'type', 'value', 'nodetype')]
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
    assert node['target_sql'] == "SQL_DIALECT_INSERT_ATTRIBUTES\
\nSELECT DISTINCT TABLE.`id` || SQL_DIALECT_ATTRIBUTE_ID{name} as id,\
\nCAST(NULL as STRING) as parentId,\
\nTABLE.`id` as entityId,\
\n'name' as name,\
\n'nodetype' as nodeType,\
\nCAST(NULL as STRING) as valueType,\
\n'type' as `type`,\
\nbound_trim_string as `attributeValue`,\
\n'@none' as `datasetId`,\
\nCAST(NULL as STRING) as unitCode,\
\nCAST(NULL as STRING) as lang,\
\nfalse as `deleted`,\
\nfalse as `synched`\
\n,SQL_DIALECT_SQLITE_TIMESTAMP\
\nFROM target_sql WHERE where"


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


@patch('lib.utils.unwrap_variables')
def test_translate_additive_expression(mock_unwrap_variables):
    ctx = MagicMock()
    elem = MagicMock()
    elem.expr = term.Variable('var1')
    elem.op = ['+']
    elem.other = [term.Variable('var2')]

    # Mocking utility functions
    def unwrap_mock(ctx, variable):
        if variable.toPython() == '?var1':
            return 'var1_value'
        elif variable.toPython() == '?var2':
            return 'var2_value'
        return ''

    mock_unwrap_variables.side_effect = unwrap_mock

    result = lib.sparql_to_sql.translate_additive_expression(ctx, elem)
    assert result == "var1_value + var2_value "
    assert mock_unwrap_variables.call_count == 2


@patch('lib.utils.set_is_aggregate_var')
@patch('lib.sparql_to_sql.translate')
@patch('lib.utils.create_varname')
def test_process_aggregate(mock_create_varname, mock_translate, mock_set_is_aggregate_var):
    ctx = {
        'bounds': {'var': 'resolved_var'},
        'time_variables': {},
    }
    elem = MagicMock()
    elem.distinct = 'DISTINCT'
    elem.vars = term.Variable('var')

    # Mocking utility functions
    mock_create_varname.return_value = 'var'
    mock_translate.return_value = 'translated_var'

    # Run the function
    result_expression, result_distinct = lib.sparql_to_sql.process_aggregate(ctx, elem)

    # Asserting the results
    assert result_expression == 'translated_var'
    assert result_distinct == 'DISTINCT'
    assert mock_translate.called
    assert mock_set_is_aggregate_var.call_count == 2


# Tests for get_bound_trim_string function
def test_get_bound_trim_string_property_variable():
    ctx = {
        'bounds': {'foo': 'bar'},
        'property_variables': {Variable('foo'): True},
        'time_variables': {},
        'query': 'SELECT ?foo WHERE { ... }'
    }
    result = lib.sparql_to_sql.get_bound_trim_string(ctx, Variable('foo'))
    assert result == "SQL_DIALECT_STRIP_IRI{bar}"


def test_get_bound_trim_string_property_variable_false():
    ctx = {
        'bounds': {'foo': 'bar'},
        'property_variables': {Variable('foo'): False},
        'time_variables': {},
        'query': 'SELECT ?foo WHERE { ... }'
    }
    result = lib.sparql_to_sql.get_bound_trim_string(ctx, Variable('foo'))
    assert result == "SQL_DIALECT_STRIP_LITERAL{bar}"


def test_get_bound_trim_string_time_variable():
    ctx = {
        'bounds': {'foo': 'bar'},
        'property_variables': {},
        'time_variables': {Variable('foo'): True},
        'query': 'SELECT ?foo WHERE { ... }'
    }
    result = lib.sparql_to_sql.get_bound_trim_string(ctx, Variable('foo'))
    # Note: There's a typo in the original function - "DIALIFAECT" should be "DIALECT"
    assert result == "SQL_DIALIFAECT_STRIP_LITERAL{bar}"


def test_get_bound_trim_string_complex_variable_name():
    """Test with more complex variable names"""
    ctx = {
        'bounds': {'entityId': 'urn:ngsi-ld:Entity:123'},
        'property_variables': {Variable('entityId'): True},
        'time_variables': {},
        'query': 'SELECT ?entityId WHERE { ... }'
    }
    result = lib.sparql_to_sql.get_bound_trim_string(ctx, Variable('entityId'))
    assert result == "SQL_DIALECT_STRIP_IRI{urn:ngsi-ld:Entity:123}"


def test_get_bound_trim_string_literal_value():
    """Test with literal value in bounds"""
    ctx = {
        'bounds': {'value': '"42"^^xsd:int'},
        'property_variables': {Variable('value'): False},
        'time_variables': {},
        'query': 'SELECT ?value WHERE { ... }'
    }
    result = lib.sparql_to_sql.get_bound_trim_string(ctx, Variable('value'))
    assert result == 'SQL_DIALECT_STRIP_LITERAL{"42"^^xsd:int}'


def test_get_bound_trim_string_time_variable_with_timestamp():
    """Test time variable with actual timestamp value"""
    ctx = {
        'bounds': {'timestamp': '2023-07-25T10:30:00Z'},
        'property_variables': {},
        'time_variables': {Variable('timestamp'): True},
        'query': 'SELECT ?timestamp WHERE { ... }'
    }
    result = lib.sparql_to_sql.get_bound_trim_string(ctx, Variable('timestamp'))
    # Note: There's a typo in the original function - "DIALIFAECT" should be "DIALECT"
    assert result == "SQL_DIALIFAECT_STRIP_LITERAL{2023-07-25T10:30:00Z}"


def test_get_bound_trim_string_variable_in_both_collections():
    """Test when variable exists in both property_variables and time_variables (property takes precedence)"""
    ctx = {
        'bounds': {'foo': 'bar'},
        'property_variables': {Variable('foo'): True},
        'time_variables': {Variable('foo'): True},
        'query': 'SELECT ?foo WHERE { ... }'
    }
    result = lib.sparql_to_sql.get_bound_trim_string(ctx, Variable('foo'))
    # Property variables should take precedence
    assert result == "SQL_DIALECT_STRIP_IRI{bar}"


# The knowledge in `rdf` is written once when the KMS is deployed and never
# again -- unlike entities_view and attributes_view, which the debezium
# connector re-snapshots every flink.ttl/2 -- so nothing refreshes it. A join
# keeps its right side as STATE rather than as a table that is simply there, so
# under table.exec.state.ttl the ontology expires an hour after deployment and
# the join stops matching.
#
# Both directions are wrong and neither is loud. An inner join yields no rows,
# so a constraint goes silent and misses a real violation. A FILTER NOT EXISTS
# compiles to LEFT JOIN ... IS NULL, which then holds vacuously and fires
# against valid data. Measured on a live cluster with a 300 s ttl: the same
# violating entity alerted 100 s after the job started and not at all 531 s in.
# The SQLite oracle has no state and no ttl, so it answers correctly throughout
# and the divergence is invisible to the comparison.
@patch('lib.sparql_to_sql.utils.create_varname')
def test_wrap_sql_projection_pins_the_knowledge(mock_create_varname):
    ctx = {
        'bounds': {
            'var': 'bound'
        },
        'target_modifiers': [],
        'PV': ['varx']
    }
    node = {
        'where': '',
        'target_sql': 'entities_view AS A JOIN rdf AS KNOWTABLE ON KNOWTABLE.subject = A.id'
    }
    mock_create_varname.return_value = 'var'
    lib.sparql_to_sql.wrap_sql_projection(ctx, node)
    assert "STATE_TTL('KNOWTABLE' = '0d')" in node['target_sql'], \
        'a sparql query joins the knowledge without pinning it, so those rows ' \
        'expire at table.exec.state.ttl and the check stops seeing the ontology'
    # Position, not just presence. A hint anywhere other than immediately after
    # SELECT is parsed as a select item -- "Encountered \"/*+\"" -- and the whole
    # statement set fails to deploy. Asserting only that the hint exists let
    # exactly that ship: it sat after DISTINCT, the unit tests were green, and
    # Flink refused the SQL.
    assert node['target_sql'].startswith('SELECT /*+ STATE_TTL'), \
        f"the hint must follow SELECT immediately, got: {node['target_sql'][:60]}"


@patch('lib.sparql_to_sql.utils.create_varname')
def test_wrap_sql_projection_hints_only_what_it_joins(mock_create_varname):
    """No rdf in this block, no hint: STATE_TTL is query-block scoped, and an
    alias named in a block that does not join it is silently ignored by Flink,
    which would look like a fix without being one."""
    ctx = {
        'bounds': {
            'var': 'bound'
        },
        'target_modifiers': [],
        'PV': ['varx']
    }
    node = {
        'where': '',
        'target_sql': 'entities_view AS A JOIN attributes_view AS B ON B.entityId = A.id'
    }
    mock_create_varname.return_value = 'var'
    lib.sparql_to_sql.wrap_sql_projection(ctx, node)
    assert 'STATE_TTL' not in node['target_sql']


@patch('lib.sparql_to_sql.get_bound_trim_string')
@patch('lib.sparql_to_sql.get_attribute_columns')
def test_wrap_sql_construct_pins_the_knowledge(attribute_column_mock, get_bound_trim_string_mock):
    """A rule whose rdf join expires stops writing its attributes back, just as
    silently as a constraint stops reporting."""
    ctx = {
        'bounds': {
            'varx': 'bound'
        },
        'property_variables': {},
        'target_modifiers': [],
        'PV': ['varx']
    }
    node = {
        'where': '',
        'target_sql': 'entities_view AS A JOIN rdf AS RULETABLE ON RULETABLE.subject = A.id'
    }
    attribute_column_mock.return_value = [(Variable('varx'), 'name', 'type', Variable('varx'), '@id')]
    get_bound_trim_string_mock.return_value = 'bound'
    lib.sparql_to_sql.wrap_sql_construct(ctx, node)
    assert "STATE_TTL('RULETABLE' = '0d')" in node['target_sql']
    # A construct branch is SELECT DISTINCT, and the hint still belongs between
    # SELECT and DISTINCT rather than after both.
    assert 'SELECT /*+ STATE_TTL' in node['target_sql'], \
        'hint is not immediately after SELECT'
    assert 'SELECT DISTINCT /*+' not in node['target_sql'], \
        'hint sits after DISTINCT, which flink parses as a select item'


@patch('lib.sparql_to_sql.utils.create_varname')
def test_wrap_sql_projection_pins_the_knowledge_with_distinct(mock_create_varname):
    """The DISTINCT case specifically, because that is the one that broke.

    Without DISTINCT the hint lands after SELECT whether the splice is right or
    wrong, so a fixture with no modifiers cannot tell the two apart -- and did
    not: the bad version shipped and Flink rejected it with
    'Encountered "/*+" at line 2, column 17', column 17 being exactly the width
    of "SELECT DISTINCT ".
    """
    ctx = {
        'bounds': {
            'var': 'bound'
        },
        'target_modifiers': ['Distinct'],
        'PV': ['varx']
    }
    node = {
        'where': '',
        'target_sql': 'entities_view AS A JOIN rdf AS KNOWTABLE ON KNOWTABLE.subject = A.id'
    }
    mock_create_varname.return_value = 'var'
    lib.sparql_to_sql.wrap_sql_projection(ctx, node)
    assert node['target_sql'].startswith('SELECT /*+ STATE_TTL'), \
        f"the hint must sit between SELECT and DISTINCT, got: {node['target_sql'][:60]}"
    assert 'SELECT DISTINCT /*+' not in node['target_sql'], \
        'hint sits after DISTINCT, which flink parses as a select item'
    assert 'DISTINCT' in node['target_sql'], 'the DISTINCT modifier was dropped'


def test_attribute_id_matches_what_the_bridge_writes():
    """A rule must name an attribute exactly as debeziumBridge.js does.

    The bridge hashes everything after the urn prefix --
    sha256("<name>\\<datasetId>") truncated to kafkaBridge.hashlength -- and
    attributes_view partitions on (id, datasetId). Two spellings therefore land
    as two rows, and a [1,1] property is reported as "Found 2" for a value that
    exists once. Measured on a live cluster: the rule wrote
    urn:cartridge:1\\<full IRI>, the bridge wrote
    urn:cartridge:1\\6fb7b362d0a8eebcf7344a43, and isUsedUntil was counted twice.

    The expected value here is computed the way the bridge computes it rather
    than copied, so changing kafkaBridge.hashlength without recompiling the KMS
    shows up as a failure instead of as a duplicate attribute.
    """
    name = 'https://industryfusion.github.io/contexts/example/v0/base_entities/isUsedUntil'
    expected = hashlib.sha256(f'{name}\\@none'.encode()).hexdigest()[:configs.attribute_hash_length]
    assert lib.utils.attribute_id_suffix(name) == f'\\{expected}'
    # The one observed on the cluster, so the algorithm is pinned to reality
    # and not merely to itself.
    assert lib.utils.attribute_id_suffix(name) == '\\6fb7b362d0a8eebcf7344a43'


def test_attribute_id_keeps_the_parts_for_sqlite():
    """The oracle loads its attributes from create_ngsild_models, which writes
    the parts verbatim, so the sqlite spelling must stay unhashed -- matching
    its own loader rather than the bridge's."""
    name = 'https://industryfusion.github.io/contexts/example/v0/base_entities/isUsedUntil'
    assert lib.utils.attribute_id_suffix(name, sqlite=True) == f'\\{name}\\@none'
