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
"""The generated sh:hasValue check on numbers (#965).

A number required by sh:hasValue equals a value whose text is the same number,
however either is written: 80, 80.0 and a declared xsd:double 80 all equal
sh:hasValue 80.0 and sh:hasValue 80. Flink gets a plain 80.0 from the bridge
as the text 80 with no type, so comparing the texts there alerted on a value
SQLite accepted.

As in tests/test_datatype_check.py, the SQLite form of the check runs on rows
filled the way each side fills them, and both must give the same verdict.
tests/sql-tests/kms-constraints/test27 pins the SQLite side end to end, the
scorpio e2e suite the Flink side.
"""
import re
import sqlite3

import pytest
from jinja2 import Template

import lib.utils as utils
from lib.shacl_properties_to_sql import sql_check_literal_hasvalue, sql_check_literal_datatypes
from tests.test_zero_valued_parameters import VALUE_SHAPE, compile_shapes, compiled_value

XSD = 'http://www.w3.org/2001/XMLSchema#'
DOUBLE, INTEGER, DECIMAL, STRING = XSD + 'double', XSD + 'integer', XSD + 'decimal', XSD + 'string'

# The constant as the constraint table holds it: (hasValue, hasValueType).
# test_the_constraint_table_holds_the_constant_and_its_type pins that the
# compiler writes exactly these.
REQUIRED = {
    '80.0': ('80.0', DECIMAL),    # Turtle 80.0 is an xsd:decimal
    '80': ('80', INTEGER),
    '"80.0"^^xsd:double': ('80.0', DOUBLE),
    '"1.0"': ('1.0', None),       # a plain string literal
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
    ('true', True, ('true', None), ('true', XSD + 'boolean')),
]

# A string constant keeps being compared as before #965: as text when the
# value declares no type (tests/sql-tests/sql-cases/untyped-hasvalue), so "1"
# is not the string "1.0".
STRING_CASES = [
    ('"1.0"', False, ('1.0', None), ('1.0', None)),
    ('"1"', True, ('1', None), ('1', None)),
]

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
    conn.execute(f"CREATE TABLE A1 ({', '.join(COLUMNS)})")
    conn.execute(f"INSERT INTO A1 VALUES ({', '.join('?' * len(COLUMNS))})",
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


@pytest.mark.parametrize('source,alert,flink,sqlite', STRING_CASES,
                         ids=[case[0] for case in STRING_CASES])
def test_a_required_string_is_compared_as_text_on_both_sides(source, alert, flink, sqlite):
    assert _fires(*flink, '"1.0"') is alert, f'Flink row {flink}'
    assert _fires(*sqlite, '"1.0"') is alert, f'SQLite row {sqlite}'


@pytest.mark.xfail(strict=True, reason='a string constant against a plain number: Flink compares '
                   'the untyped text, SQLite casts by the xsd:integer the model gives it; not '
                   'changed by #965, which is about number constants')
def test_a_plain_number_against_a_required_string_differs_between_the_sides():
    assert _fires('1', None, '"1.0"') is _fires('1', INTEGER, '"1.0"')


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


def test_the_flink_check_casts_safely_and_reads_numbers_like_the_datatype_check():
    """Flink's CAST of a text that is no number fails the job; the check must
    only cast what the number pattern let through, with TRY_CAST, and the
    pattern must be the one sh:datatype uses for a number."""
    flink = _flink_sql()
    assert 'TRY_CAST(val AS DOUBLE)' in flink and 'TRY_CAST(hasValue AS DOUBLE)' in flink
    datatype = Template(sql_check_literal_datatypes).render(
        constraintname='DatatypeConstraintComponent', check_list_elements='true', sqlite=False)
    any_number = re.search(r"\{% set any_number %\}(.*?)\{% endset %\}",
                           sql_check_literal_datatypes).group(1)
    assert f"REGEXP(val, '{any_number}')" in datatype
    assert f"REGEXP(val, '{any_number}')" in flink
