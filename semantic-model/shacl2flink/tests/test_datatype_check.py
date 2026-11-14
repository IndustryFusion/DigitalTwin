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
import re
import sqlite3

import pytest
from jinja2 import Template

import lib.utils as utils
from lib.shacl_properties_to_sql import sql_check_literal_datatypes, list_element_checks

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
           'adeleted', 'attr_typ')


def _check_sql():
    sql = Template(sql_check_literal_datatypes).render(
        constraintname='DatatypeConstraintComponent',
        check_list_elements=list_element_checks(True), sqlite=True)
    return utils.process_sql_dialect(sql, True)


def _fires(text, value_type, datatype):
    """Whether the SQLite check reports one attribute with this text and type."""
    conn = sqlite3.connect(':memory:')
    # SQLite's `X REGEXP Y` is regexp(Y, X): pattern first.
    conn.create_function('regexp', 2, lambda p, v: v is not None and re.search(p, v) is not None)
    conn.execute(f"CREATE TABLE A1 ({', '.join(COLUMNS)})")
    conn.execute(f"INSERT INTO A1 VALUES ({', '.join('?' * len(COLUMNS))})",
                 ('urn:x:1', 1, 'warning', '', '', 'p', text, value_type, datatype, '@value', 0,
                  False, False, 'https://uri.etsi.org/ngsi-ld/Property'))
    rows = conn.execute(_check_sql()).fetchall()
    return len(rows) > 0


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
