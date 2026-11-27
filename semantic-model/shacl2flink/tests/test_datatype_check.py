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
"""The generated sh:datatype check on xsd:double and xsd:integer (#958, task 1.4).

The SQLite form of the check runs on rows filled the way each side fills
them -- text and declared type as Flink gets them from the bridge, and as the
SQLite checks get them from the model -- and the verdict must be the one the
specification shacl2flink/literal-datatypes gives the source value.
"""
import json
import os
import re
import sqlite3

import pytest
from jinja2 import Template

import lib.utils as utils
from lib.shacl_properties_to_sql import (DATATYPE_ONLY, NOT_A_LITERAL, sql_check_literal_datatypes,
                                         sql_check_literal_hasvalue, sql_check_literal_in,
                                         sql_check_literal_pattern, sql_check_property_minmax,
                                         sql_check_string_length,
                                         sql_check_property_iri_base, sql_check_property_nodeType,
                                         sql_check_relationship_nodeType, list_element_checks)

XSD = 'http://www.w3.org/2001/XMLSchema#'
DOUBLE, INTEGER, STRING = XSD + 'double', XSD + 'integer', XSD + 'string'

# (source value, shape datatype, alert?, Flink row, SQLite row); a row is
# (text, valueType). Flink's text is what JavaScript writes; SQLite's what
# lib/jsonld_numbers.py and the store make of the model (create_ngsild_models
# turns a string's implicit xsd:string into no type).
CASES = [
    ('80.5', DOUBLE, False, ('80.5', None), ('80.5', DOUBLE)),
    ('80', DOUBLE, True, ('80', None), ('80', INTEGER)),
    ('80.0', DOUBLE, True, ('80', None), ('80', INTEGER)),
    ('0.0', DOUBLE, True, ('0', None), ('0', INTEGER)),
    ('1e21', DOUBLE, False, ('1e+21', None), ('1e+21', DOUBLE)),
    ('1.5e-7', DOUBLE, False, ('1.5e-7', None), ('1.5e-07', DOUBLE)),
    ('{"@value": 80, "@type": "xsd:double"}', DOUBLE, False, ('80', DOUBLE), ('80.0', DOUBLE)),
    ('{"@value": 0.0, "@type": "xsd:double"}', DOUBLE, False, ('0', DOUBLE), ('0.0', DOUBLE)),
    ('{"@value": 80.5, "@type": "xsd:double"}', DOUBLE, False, ('80.5', DOUBLE), ('80.5', DOUBLE)),
    ('{"@value": 80, "@type": "xsd:integer"}', DOUBLE, True, ('80', INTEGER), ('80', INTEGER)),
    ('"80.0"', DOUBLE, False, ('80.0', None), ('80.0', None)),
    ('"2.5E-3"', DOUBLE, False, ('2.5E-3', None), ('2.5E-3', None)),
    ('"80"', DOUBLE, True, ('80', None), ('80', None)),
    ('"0"', DOUBLE, True, ('0', None), ('0', None)),
    ('"eighty"', DOUBLE, True, ('eighty', None), ('eighty', None)),
    ('80.0', INTEGER, False, ('80', None), ('80', INTEGER)),
    ('80.5', INTEGER, True, ('80.5', None), ('80.5', DOUBLE)),
    ('{"@value": 80, "@type": "xsd:double"}', INTEGER, True, ('80', DOUBLE), ('80.0', DOUBLE)),
    ('"80"', INTEGER, False, ('80', None), ('80', None)),
]

COLUMNS = ('this', 'constraint_id', 'severity', 'parentPath', 'printPath', 'propertyPath',
           'val', 'valueType', 'datatypes', 'propertyNodetype', '`index`', 'edeleted',
           'adeleted', 'attr_typ', 'nodeType', 'attributeType')

NGSILD = 'https://uri.etsi.org/ngsi-ld/'
PROPERTY = NGSILD + 'Property'
# The propertyNodetype of the row that holds the datatype of a value shape without sh:nodeKind.
NO_KIND = DATATYPE_ONLY


def _check_sql():
    sql = Template(sql_check_literal_datatypes).render(
        constraintname='DatatypeConstraintComponent',
        check_list_elements=list_element_checks(True), sqlite=True)
    return utils.process_sql_dialect(sql, True)


def _base_value_type():
    """The valueType expression of A1, as sql_check_property_iri_base has it, on the columns of one row."""
    expression = re.search(r"CASE WHEN D.propertyNodetype = .*?END (?=as `valueType`)",
                           sql_check_property_iri_base, re.DOTALL).group()
    return Template(expression.replace('D.', '')).render(deepest=lambda column: column)


def _alerts(text, value_type, datatype, kind='@value', attr_typ=PROPERTY, node_type='@value',
            attribute_type=PROPERTY, deleted=False):
    """The alerts of the SQLite check on one attribute with this text and type."""
    conn = sqlite3.connect(':memory:')
    # SQLite's `X REGEXP Y` is regexp(Y, X): pattern first.
    conn.create_function('regexp', 2, lambda p, v: v is not None and re.search(p, v) is not None)
    conn.execute(f"CREATE TABLE A1 ({', '.join(COLUMNS)}, `instance` DEFAULT '[0]')")
    value_type = conn.execute(f'SELECT {_base_value_type()} FROM (SELECT ? AS propertyNodetype, ? AS nodeType, '
                              '? AS valueType)', (kind, node_type, value_type)).fetchone()[0]
    conn.execute(f"INSERT INTO A1 ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                 ('urn:x:1', 1, 'warning', '', '', 'p', text, value_type, datatype, kind, 0,
                  deleted, False, attr_typ, node_type, attribute_type))
    # Without the CURRENT_TIMESTAMP column: two calls compared whole would
    # differ whenever a second boundary falls between them.
    return [row[:6] + row[7:] for row in conn.execute(_check_sql()).fetchall()]


def _fires(text, value_type, datatype, **row):
    return len(_alerts(text, value_type, datatype, **row)) > 0


@pytest.mark.parametrize('source,datatype,alert,flink,sqlite', CASES,
                         ids=[f'{c[0]} on {c[1].split("#")[1]}' for c in CASES])
def test_the_verdict_is_the_specified_one_on_both_sides(source, datatype, alert, flink, sqlite):
    assert _fires(*flink, datatype) is alert, f'Flink row {flink}'
    assert _fires(*sqlite, datatype) is alert, f'SQLite row {sqlite}'


def test_a_string_of_digits_is_reported_not_lost_in_a_null():
    """NULL = '...' is NULL, not false: compared without IFNULL, one NULL inside
    NOT ( ... OR ... ) made the whole check NULL and "80" was never reported."""
    assert _fires('80', None, DOUBLE)
    assert 'IFNULL(`valueType`, \'\') = \'http://www.w3.org/2001/XMLSchema#double\'' in _check_sql()


def test_both_dialects_use_the_same_patterns():
    sqlite = _check_sql()
    flink = utils.process_sql_dialect(Template(sql_check_literal_datatypes).render(
        constraintname='DatatypeConstraintComponent',
        check_list_elements=list_element_checks(False), sqlite=False), False)
    patterns = re.findall(r"'(\^\[\+-\]\?\(\?:\\d[^']*)'", sqlite)
    assert len(patterns) == 2
    for pattern in patterns:
        assert f"REGEXP(val, '{pattern}')" in flink


@pytest.mark.parametrize('source,datatype,alert,flink,sqlite', CASES,
                         ids=[f'{c[0]} on {c[1].split("#")[1]}' for c in CASES])
def test_without_a_node_kind_the_verdict_is_the_same(source, datatype, alert, flink, sqlite):
    """#1097: a value shape without sh:nodeKind was never checked."""
    assert _fires(*flink, datatype, kind=NO_KIND) is alert, f'Flink row {flink}'
    assert _fires(*sqlite, datatype, kind=NO_KIND) is alert, f'SQLite row {sqlite}'


def test_without_a_node_kind_a_custom_datatype_is_checked():
    assert _fires('x', DOUBLE, 'http://example.org/custom', kind=NO_KIND)
    assert not _fires('x', 'http://example.org/custom', 'http://example.org/custom', kind=NO_KIND)
    assert not _fires('x', None, 'http://example.org/custom', kind=NO_KIND)


def test_a_datatype_whose_name_starts_like_the_required_one_violates_it():
    kind = NO_KIND
    assert _fires('2020', XSD + 'gYear', XSD + 'gYearMonth', kind=kind)
    assert not _fires('2020-01', XSD + 'gYearMonth', XSD + 'gYearMonth', kind=kind)
    assert not _fires('2020', XSD + 'gYear', XSD + 'date,' + XSD + 'gYear', kind=kind)
    assert not _fires('2020', None, XSD + 'gYearMonth', kind=kind)


@pytest.mark.parametrize('datatype', (DOUBLE, STRING, 'http://example.org/custom'))
@pytest.mark.parametrize('attr_typ,node_type', ((PROPERTY, '@id'), (NGSILD + 'GeoProperty', '@json')))
def test_without_a_node_kind_a_value_that_is_no_literal_is_reported(datatype, attr_typ, node_type):
    """An IRI is no literal of any datatype, xsd:string included."""
    assert _fires('urn:some:iri', None, datatype, kind=NO_KIND, attr_typ=attr_typ, node_type=node_type)


@pytest.mark.parametrize('attr_typ,node_type,text', (
    (NGSILD + 'Relationship', '@id', 'urn:some:iri'),
    (NGSILD + 'ListProperty', '@list', '["abc"]'),
    (NGSILD + 'JsonProperty', '@json', '{"a":1}'),
    (None, None, None)))
def test_without_a_node_kind_an_attribute_without_hasvalue_is_not_reported(attr_typ, node_type, text):
    """sh:datatype judges the value nodes of hasValue, and there are none."""
    assert not _fires(text, None, DOUBLE, kind=NO_KIND, attr_typ=attr_typ, node_type=node_type)


def test_without_a_node_kind_and_a_datatype_nothing_is_reported():
    assert not _fires('abc', None, None, kind=NO_KIND)
    # the row of the ordinary extraction, which a connective may read
    assert not _fires('abc', None, DOUBLE, kind='null')
    assert not _fires('abc', None, DOUBLE, kind=NO_KIND, deleted=True)


def test_other_node_kinds_keep_their_verdicts():
    assert not _fires('urn:some:iri', None, DOUBLE, kind='@id', node_type='@id')
    assert not _fires('urn:some:iri', None, STRING, node_type='@id')
    assert _fires('urn:some:iri', None, DOUBLE, attr_typ=NGSILD + 'Relationship', node_type='@id')


def test_the_message_is_the_same_with_and_without_a_node_kind():
    with_kind = _alerts('abc', None, DOUBLE)
    iri = _alerts('urn:some:iri', None, DOUBLE, kind=NO_KIND, node_type='@id')
    assert f'value="urn:some:iri" is no literal, expected datatypes="{DOUBLE}"' in str(iri[0])
    assert _base_value_type().count(NOT_A_LITERAL) == 1
    assert 'Datatype check failed: value="abc"' in str(with_kind[0])
    assert _alerts('abc', None, DOUBLE, kind=NO_KIND) == with_kind


def test_both_dialects_check_a_shape_without_a_node_kind():
    flink = utils.process_sql_dialect(Template(sql_check_literal_datatypes).render(
        constraintname='DatatypeConstraintComponent',
        check_list_elements=list_element_checks(False), sqlite=False), False)
    for sql in (_check_sql(), flink):
        assert "'@datatype'" in sql.split('FROM A1')[1]
        assert 'DATATYPE_ONLY' not in sql


DECIMAL, LANG = XSD + 'decimal', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#langString'


def test_a_list_with_another_datatype_accepts_a_value_declared_with_it():
    kind = NO_KIND
    both = f'{DECIMAL},{INTEGER}'
    assert not _fires('80.5', DECIMAL, both, kind=kind)
    assert not _fires('80', INTEGER, both, kind=kind)
    assert _fires('80.5', XSD + 'dec', both, kind=kind)
    assert _fires('80.5', DOUBLE, both, kind=kind)
    assert _fires('abc', None, both, kind=kind)
    assert not _fires('hallo', LANG, f'{LANG},{STRING}', kind=kind)
    assert not _fires('hallo', None, f'{LANG},{INTEGER}', kind=kind)
    assert _fires('1.5', DOUBLE, f'{LANG},{STRING}', kind=kind)


def test_a_declared_boolean_may_be_one_or_zero():
    kind = NO_KIND
    boolean = XSD + 'boolean'
    assert not _fires('1', boolean, boolean, kind=kind)
    assert not _fires('0', boolean, boolean, kind=kind)
    assert _fires('1', None, boolean, kind=kind)
    assert _fires('1', INTEGER, boolean, kind=kind)
    assert _fires('2', boolean, boolean, kind=kind)


def test_a_row_with_a_node_kind_judges_lists_and_declared_types_as_one_without():
    """A connective over the values is judged per instance (#1106), so a row with sh:nodeKind
    gets the verdict of a datatype-only row: a listed datatype declared, a language-tagged
    string the bridge passes on untyped, a declared boolean written 1, a datatype compared
    whole."""
    for kind in ('@value', NO_KIND):
        assert not _fires('80.5', DECIMAL, f'{DECIMAL},{INTEGER}', kind=kind)
        assert not _fires('hallo', None, f'{LANG},{STRING}', kind=kind)
        assert not _fires('1', XSD + 'boolean', XSD + 'boolean', kind=kind)
        assert _fires('2020', XSD + 'gYear', XSD + 'gYearMonth', kind=kind)
        assert _fires('2020-05', XSD + 'gYearMonth', XSD + 'gYear', kind=kind)


def test_the_node_kind_check_reads_a_blank_node_as_before():
    """The SQLite model reader marks a blank node '@blank' for the datatype check only."""
    sqlite = Template(sql_check_property_nodeType).render(sqlite=True)
    assert sqlite.count("REPLACE(`nodeType`, '@blank', '@value')") == 2
    assert '@blank' not in Template(sql_check_property_nodeType).render(sqlite=False)


# What the bridge makes of a value, and the datatypes it must and must not satisfy. The bridge's own
# tests hold it to the same file.
with open(os.path.join(os.path.dirname(__file__), '../../../KafkaBridge/test/valueForms.json')) as _handle:
    BRIDGE = [case for case in json.load(_handle)['forms'] if case['bridge'] is not None]


def _flink_text(value):
    """The text Flink's JSON format makes of an attributeValue for its STRING column."""
    if isinstance(value, str):
        return value
    if isinstance(value, float) and not value.is_integer():
        return repr(value)
    if isinstance(value, float):
        return '1e+21' if value == 1e21 else str(int(value))
    return json.dumps(value, separators=(',', ':'))


@pytest.mark.parametrize('case', BRIDGE, ids=[case['name'] for case in BRIDGE])
def test_the_forms_of_the_bridge_on_a_shape_without_a_node_kind(case):
    form = case['bridge']
    for datatypes, alert in [(d, False) for d in case['satisfies']] + [(d, True) for d in case['violates']]:
        assert _fires(_flink_text(form['attributeValue']), form.get('valueType'), datatypes, kind=NO_KIND,
                      node_type=form['nodeType'], attr_typ=form['type']) is alert, datatypes


def test_the_readers_forms_of_the_infinities_and_nan():
    for text in ('inf', '-inf', 'nan'):
        assert not _fires(text, DOUBLE, DOUBLE, kind=NO_KIND)
        assert _fires(text, None, DOUBLE, kind=NO_KIND)


def _state_columns(template, **render):
    """Which of nodeType and valueType a check reads of an attribute, through A1's own columns."""
    sql = Template(template).render(sqlite=False, constraintname='x', operator='<', comparison_value='maxLength',
                                    minmaxname='x', validationname='x', check_list_elements='true', **render)
    sql = re.sub(r'--.*', '', sql)
    read = {column for column in ('nodeType', 'valueType') if re.search(rf'(?<!property)\b{column}\b', sql)}
    # A1's valueType is told from both columns.
    return read | ({'nodeType'} if 'valueType' in read else set())


def test_the_datatype_check_keeps_no_attribute_state_of_its_own():
    """Flink keeps one deduplication of the attributes, with its joins, per set of columns the checks
    read. The datatype check reads the set the other checks of a value's type read; reading nodeType
    by itself beside valueType, it had a set of its own (224 tasks of the e2e job instead of 223)."""
    datatypes = _state_columns(sql_check_literal_datatypes)
    assert datatypes == _state_columns(sql_check_literal_in) == _state_columns(sql_check_literal_hasvalue)
    sets = {frozenset(_state_columns(check)) for check in (
        sql_check_literal_datatypes, sql_check_literal_in, sql_check_literal_hasvalue, sql_check_property_nodeType,
        sql_check_property_minmax, sql_check_string_length, sql_check_literal_pattern)}
    assert sets == {frozenset(), frozenset({'nodeType'}), frozenset({'nodeType', 'valueType'})}
    for sqlite in (True, False):
        sql = Template(sql_check_literal_datatypes).render(
            constraintname='x', check_list_elements=list_element_checks(sqlite), sqlite=sqlite)
        assert not re.search(r'\bnodeType\b', sql)


def test_the_relationship_check_names_a_blank_node_as_before():
    render = {'property_nodetype': '@id', 'property_nodetype_description': 'an IRI'}
    assert "|| REPLACE(nodeType, '@blank', '@value') ||" in Template(
        sql_check_relationship_nodeType).render(sqlite=True, **render)
    assert '@blank' not in Template(sql_check_relationship_nodeType).render(sqlite=False, **render)
