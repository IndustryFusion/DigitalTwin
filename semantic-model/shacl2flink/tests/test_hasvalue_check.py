#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""The generated sh:hasValue check (#965, #1044, #1045).

A number required by sh:hasValue equals a value whose text is the same number,
however either is written: 80, 80.0 and a declared xsd:double 80 all equal
sh:hasValue 80.0 and sh:hasValue 80. Flink gets a plain 80.0 from the bridge
as the text 80 with no type, so comparing the texts there alerted on a value
SQLite accepted.

As in tests/test_datatype_check.py, the SQLite form of the check runs on rows
filled the way each side fills them, and both must give the same verdict.
tests/sql-tests/kms-constraints/test27 pins the SQLite side end to end, the
scorpio e2e suite the Flink side.

A string constant is compared with the text the platform sends (#1044): a
number meets it only when the constant is the text JavaScript writes for that
number. A boolean constant is met by the same boolean (#1045): a plain or
declared boolean, or the text true or false. kms-constraints/test28 pins both
on SQLite.
"""
import re
import sqlite3

import pytest
from jinja2 import Template
from rdflib import Literal, URIRef

import lib.utils as utils
from create_ngsild_models import value_as_sent
from lib.utils import UnsupportedShape
from lib.shacl_properties_to_sql import sql_check_literal_hasvalue, sql_check_literal_datatypes, \
    platform_number_text, is_platform_number_text, NUMBER_TEXT_MARK
from tests.test_zero_valued_parameters import VALUE_SHAPE, compile_shapes, compiled_value

XSD = 'http://www.w3.org/2001/XMLSchema#'
DOUBLE, INTEGER, DECIMAL, STRING = XSD + 'double', XSD + 'integer', XSD + 'decimal', XSD + 'string'
BOOLEAN, GYEAR, GYEARMONTH = XSD + 'boolean', XSD + 'gYear', XSD + 'gYearMonth'

# The constant as the constraint table holds it: (hasValue, hasValueType).
# test_the_constraint_table_holds_the_constant_and_its_type pins that the
# compiler writes exactly these.
REQUIRED = {
    '80.0': ('80.0', DECIMAL),    # Turtle 80.0 is an xsd:decimal
    '80': ('80', INTEGER),
    '"80.0"^^xsd:double': ('80.0', DOUBLE),
    '"1.0"': ('1.0', None),       # a plain string literal, not the platform's text of 1
    '"1"': ('1', NUMBER_TEXT_MARK),  # the text the platform writes for the number 1
    '"1"^^xsd:string': ('1', NUMBER_TEXT_MARK),
    '"0.5"': ('0.5', NUMBER_TEXT_MARK),
    '"1e+21"': ('1e+21', NUMBER_TEXT_MARK),
    '"true"': ('true', None),
    'true': ('true', BOOLEAN),    # toPython() would give 'True'
    'false': ('false', BOOLEAN),
    '"1"^^xsd:boolean': ('true', BOOLEAN),
    # Another datatype is compared like a string, with the text as written
    # (toPython() would make 2020-01-01 of the year) and the same mark.
    '"2020"^^xsd:gYear': ('2020', NUMBER_TEXT_MARK),
    '"1"^^xsd:token': ('1', NUMBER_TEXT_MARK),
    '"1"^^<urn:example:customDatatype>': ('1', NUMBER_TEXT_MARK),
    '"2020-05"^^xsd:gYearMonth': ('2020-05', GYEARMONTH),
    '"NaN"': ('NaN', None),       # no text the platform writes for a number
}

# (source value, alert?, Flink row, SQLite row); a row is (text, valueType),
# filled as in tests/test_datatype_check.py.
NUMBER_CASES = [
    ('80', False, ('80', None), ('80', INTEGER)),
    ('80.0', False, ('80', None), ('80', INTEGER)),
    ('{"@value": 80, "@type": "xsd:double"}', False, ('80', DOUBLE), ('80.0', DOUBLE)),
    ('{"@value": 80, "@type": "xsd:integer"}', False, ('80', INTEGER), ('80', INTEGER)),
    ('"80.0"', False, ('80.0', None), ('80.0', None)),
    ('"80"', False, ('80', None), ('80', None)),
    ('80.5', True, ('80.5', None), ('80.5', DOUBLE)),
    ('{"@value": 80.5, "@type": "xsd:double"}', True, ('80.5', DOUBLE), ('80.5', DOUBLE)),
    ('"eighty"', True, ('eighty', None), ('eighty', None)),
    ('true', True, ('true', None), ('True', BOOLEAN)),
]

# Every value of kms-constraints/test28 as each side fills its row:
# (source value, Flink row, SQLite row). Flink's text is what JavaScript
# writes, with the type only when the value declares one; SQLite's is what
# create_ngsild_models.py makes of the model: a plain number typed by JSON-LD
# and written by Python, a boolean as Python's True or False.
VALUES = {
    'true': (('true', None), ('True', BOOLEAN)),
    'false': (('false', None), ('False', BOOLEAN)),
    '{"@value": true, "@type": "xsd:boolean"}': (('true', BOOLEAN), ('True', BOOLEAN)),
    '{"@value": "1", "@type": "xsd:boolean"}': (('1', BOOLEAN), ('True', BOOLEAN)),
    '{"@value": "0", "@type": "xsd:boolean"}': (('0', BOOLEAN), ('False', BOOLEAN)),
    '"true"': (('true', None), ('true', None)),
    '"false"': (('false', None), ('false', None)),
    '"True"': (('True', None), ('True', None)),
    '"TRUE"': (('TRUE', None), ('TRUE', None)),
    '"1"': (('1', None), ('1', None)),
    '"0"': (('0', None), ('0', None)),
    '"1.0"': (('1.0', None), ('1.0', None)),
    '1': (('1', None), ('1', INTEGER)),
    '0': (('0', None), ('0', INTEGER)),
    '1.0': (('1', None), ('1', INTEGER)),
    '{"@value": 1, "@type": "xsd:double"}': (('1', DOUBLE), ('1.0', DOUBLE)),
    '{"@value": 1, "@type": "xsd:integer"}': (('1', INTEGER), ('1', INTEGER)),
    '{"@value": "1", "@type": "xsd:string"}': (('1', STRING), ('1', None)),
    '0.5': (('0.5', None), ('0.5', DOUBLE)),
    '{"@value": 0.5, "@type": "xsd:double"}': (('0.5', DOUBLE), ('0.5', DOUBLE)),
    '"0.5"': (('0.5', None), ('0.5', None)),
    '".5"': (('.5', None), ('.5', None)),
    '1e21': (('1e+21', None), ('1e+21', DOUBLE)),
    '"1e21"': (('1e21', None), ('1e21', None)),
    # A declared number written as a string: the bridge sends the text as is,
    # SQLite holds the number 1.0.
    '{"@value": "1.0", "@type": "xsd:double"}': (('1.0', DOUBLE), ('1.0', DOUBLE)),
    '2020': (('2020', None), ('2020', INTEGER)),
    '"2020"': (('2020', None), ('2020', None)),
    '{"@value": "2020", "@type": "xsd:gYear"}': (('2020', GYEAR), ('2020', GYEAR)),
    '{"@value": "2020-05", "@type": "xsd:gYearMonth"}': (('2020-05', GYEARMONTH), ('2020-05', GYEARMONTH)),
    '"NaN"': (('NaN', None), ('NaN', None)),
    '{"@value": "true", "@type": "xsd:string"}': (('true', STRING), ('true', None)),
}

# The values that meet each constant (shacl2flink/literal-datatypes); every
# other value of VALUES violates it.
BOOLEAN_TRUE = {'true', '{"@value": true, "@type": "xsd:boolean"}',
                '{"@value": "1", "@type": "xsd:boolean"}', '"true"',
                '{"@value": "true", "@type": "xsd:string"}'}
NUMBER_ONE = {'"1"', '1', '1.0', '{"@value": 1, "@type": "xsd:double"}',
              '{"@value": 1, "@type": "xsd:integer"}', '{"@value": "1", "@type": "xsd:string"}',
              '{"@value": "1.0", "@type": "xsd:double"}'}
MEETS = {
    'true': BOOLEAN_TRUE,
    '"1"^^xsd:boolean': BOOLEAN_TRUE,
    'false': {'false', '{"@value": "0", "@type": "xsd:boolean"}', '"false"'},
    '"true"': BOOLEAN_TRUE,
    '"1"': NUMBER_ONE,
    '"1"^^xsd:string': NUMBER_ONE,
    '"1.0"': {'"1.0"'},
    '"0.5"': {'0.5', '{"@value": 0.5, "@type": "xsd:double"}', '"0.5"'},
    '"1e+21"': {'1e21'},
    '"2020"^^xsd:gYear': {'2020', '"2020"', '{"@value": "2020", "@type": "xsd:gYear"}'},
    '"1"^^xsd:token': NUMBER_ONE,
    '"1"^^<urn:example:customDatatype>': NUMBER_ONE,
    '"2020-05"^^xsd:gYearMonth': {'{"@value": "2020-05", "@type": "xsd:gYearMonth"}'},
    '"NaN"': {'"NaN"'},
}

COLUMNS = ('this', 'constraint_id', 'severity', 'parentPath', 'propertyPath', 'val',
           'valueType', 'hasValue', 'hasValueType', '`index`', 'edeleted', 'adeleted', 'attr_typ')


def _check_sql():
    return utils.process_sql_dialect(Template(sql_check_literal_hasvalue).render(sqlite=True), True)


def _flink_sql():
    return utils.process_sql_dialect(Template(sql_check_literal_hasvalue).render(sqlite=False), False)


def _fires(text, value_type, required):
    """Whether the SQLite check reports one attribute with this text and type."""
    has_value, has_value_type = REQUIRED[required]
    conn = sqlite3.connect(':memory:')
    # SQLite's `X REGEXP Y` is regexp(Y, X): pattern first.
    conn.create_function('regexp', 2, lambda p, v: v is not None and re.search(p, v) is not None)
    conn.execute(f"CREATE TABLE A1 ({', '.join(COLUMNS)}, `instance` DEFAULT '[0]')")
    conn.execute(f"INSERT INTO A1 ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                 ('urn:x:1', 1, 'warning', '', 'p', text, value_type, has_value, has_value_type,
                  0, False, False, 'https://uri.etsi.org/ngsi-ld/Property'))
    return len(conn.execute(_check_sql()).fetchall()) > 0


@pytest.mark.parametrize('required', ['80.0', '80', '"80.0"^^xsd:double'])
@pytest.mark.parametrize('source,alert,flink,sqlite', NUMBER_CASES,
                         ids=[case[0] for case in NUMBER_CASES])
def test_a_required_number_is_compared_as_a_number_on_both_sides(source, alert, flink, sqlite,
                                                                 required):
    assert _fires(*flink, required) is alert, f'Flink row {flink}'
    assert _fires(*sqlite, required) is alert, f'SQLite row {sqlite}'


@pytest.mark.parametrize('required', MEETS)
@pytest.mark.parametrize('source', VALUES)
def test_a_string_or_boolean_constant_gets_the_same_verdict_on_both_sides(source, required):
    """#1044 and #1045: a string constant is compared with the text the
    platform sends, a boolean constant is met by the same boolean."""
    flink, sqlite = VALUES[source]
    alert = source not in MEETS[required]
    assert _fires(*flink, required) is alert, f'Flink row {flink}'
    assert _fires(*sqlite, required) is alert, f'SQLite row {sqlite}'


def test_a_plain_number_against_a_required_string_agrees_between_the_sides():
    """A strict expected failure until #1044: Flink compared the untyped text
    1 with "1.0", SQLite cast both by the xsd:integer the model gives a plain 1."""
    assert _fires('1', None, '"1.0"') is _fires('1', INTEGER, '"1.0"') is True
    assert _fires('1', None, '"1"') is _fires('1', INTEGER, '"1"') is False


@pytest.mark.parametrize('number,text', [
    (1.0, '1'), (0.0, '0'), (-0.0, '0'), (80.5, '80.5'), (-2.5, '-2.5'), (0.5, '0.5'),
    (1e21, '1e+21'), (1e20, '100000000000000000000'),
    (123456789012345680000.0, '123456789012345680000'),
    (1.5e-7, '1.5e-7'), (1e-7, '1e-7'), (0.000001, '0.000001'), (0.0001234, '0.0001234'),
    (1.2345e25, '1.2345e+25'), (-1e-10, '-1e-10'), (0.1 + 0.2, '0.30000000000000004'),
    (2 ** 53 + 2, '9007199254740994'), (float('nan'), 'NaN'), (float('inf'), 'Infinity'),
    (float('-inf'), '-Infinity'),
])
def test_the_platform_writes_numbers_as_javascript_does(number, text):
    """The outputs of JavaScript's String(number), which the bridge's
    JSON.stringify writes and Flink receives."""
    assert platform_number_text(number) == text


@pytest.mark.parametrize('text,expected', [
    ('1', True), ('0.5', True), ('1e+21', True), ('-3', True), ('1.5e-7', True),
    ('1.0', False), ('01', False), ('.5', False), ('+1', False), ('1e21', False), ('-0', False),
    ('1.5e-07', False), ('1E+21', False), ('eighty', False), ('true', False), ('', False),
    # JSON.stringify writes no number as these, and SQLite casts them to 0.0.
    ('NaN', False), ('Infinity', False), ('-Infinity', False), ('inf', False),
])
def test_only_the_platform_text_of_a_number_is_marked(text, expected):
    assert is_platform_number_text(text) is expected


def test_a_declared_integer_is_not_truncated_to_match_a_fraction():
    """CAST('80.5' AS INTEGER) is 80 on SQLite: casting both sides to the
    declared integer made 80 equal a required 80.5."""
    REQUIRED['80.5'] = ('80.5', DECIMAL)
    try:
        assert _fires('80', INTEGER, '80.5')
        assert not _fires('80.5', DOUBLE, '80.5')
    finally:
        del REQUIRED['80.5']


@pytest.mark.parametrize('constant', REQUIRED)
def test_the_constraint_table_holds_the_constant_and_its_type(constant, tmp_path):
    body = VALUE_SHAPE.replace('{parameter}', 'hasValue').replace('{value}', constant)
    body = '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n' + body
    compiled = compile_shapes(body, tmp_path)
    has_value, has_value_type = REQUIRED[constant]
    assert compiled_value(compiled, 'hasValue') == {f"'{has_value}'"}
    expected_type = f"'{has_value_type}'" if has_value_type else 'CAST (NULL as TEXT)'
    assert compiled_value(compiled, 'hasValueType') == {expected_type}


@pytest.mark.parametrize('constant,message', [
    ('"abc"^^xsd:integer', 'is not a finite number'),
    ('"1e3"^^xsd:integer', 'is not a finite number'),
    ('"NaN"^^xsd:double', 'is not a finite number'),
    ('"INF"^^xsd:double', 'is not a finite number'),
    ('"-INF"^^xsd:float', 'is not a finite number'),
    ('"yes"^^xsd:boolean', 'xsd:boolean constant that is none of true, false, 1 and 0'),
])
def test_a_constant_the_sides_cannot_compare_alike_fails_the_build(constant, message, tmp_path):
    """An ill-typed or infinite number constant never alerts on Flink, whose
    TRY_CAST gives NULL, and SQLite casts its text to 0; an ill-typed boolean
    silently became false. Like every shape the compiler cannot translate, it
    fails the build instead."""
    body = VALUE_SHAPE.replace('{parameter}', 'hasValue').replace('{value}', constant)
    body = '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n' + body
    with pytest.raises(UnsupportedShape) as raised:
        compile_shapes(body, tmp_path)
    assert message in str(raised.value) and 'sh:hasValue' in str(raised.value)


def test_the_flink_check_casts_safely_and_reads_numbers_like_the_datatype_check():
    """Flink's CAST of a text that is no number fails the job; the check must
    only cast what the number pattern let through, with TRY_CAST, and the
    pattern must be the one sh:datatype uses for a number."""
    flink = _flink_sql()
    assert 'TRY_CAST(val AS DOUBLE)' in flink and 'TRY_CAST(hasValue AS DOUBLE)' in flink
    # No cast to the type a value declares (#1044, #1045): SQLite truncates an
    # INTEGER and reads every text as a BOOLEAN of 0, Flink's TRY_CAST gives NULL.
    for sql in (flink.upper(), _check_sql().upper()):
        assert 'AS INTEGER' not in sql and 'AS BOOLEAN' not in sql
    datatype = Template(sql_check_literal_datatypes).render(
        constraintname='DatatypeConstraintComponent', check_list_elements='true', sqlite=False)
    any_number = re.search(r"\{% set any_number %\}(.*?)\{% endset %\}",
                           sql_check_literal_datatypes).group(1)
    assert f"REGEXP(val, '{any_number}')" in datatype
    assert f"REGEXP(val, '{any_number}')" in flink


@pytest.mark.parametrize('literal,text', [
    (Literal('2020', datatype=URIRef(GYEAR)), '2020'),
    (Literal('1', datatype=URIRef('urn:example:customDatatype')), '1'),
    (Literal('1', datatype=URIRef(DOUBLE)), '1.0'),
    (Literal('true', datatype=URIRef(BOOLEAN)), 'True'),
    (Literal('80'), '80'),
])
def test_the_sqlite_side_holds_a_value_of_another_datatype_as_written(literal, text):
    """The bridge sends a declared xsd:gYear 2020 as the text 2020; SQLite held
    Python's date 2020-01-01. Numbers and booleans keep the text the checks
    are written against."""
    assert str(value_as_sent(literal).toPython()) == text
