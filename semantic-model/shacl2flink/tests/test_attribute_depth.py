#
# Copyright (c) 2026 Intel Corporation
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

"""
How deep an attribute may be nested is a number, not a rewrite.

Nesting is resolved by one LEFT JOIN of attributes_view per level. That chain
was written out by hand for exactly two levels, so a third was rejected at
build time -- an OPC UA model with `hasC ==> hasE ==> hasValueList` could not be
compiled at all, though nothing about the semantics stopped at two.

The chain and the path columns are now generated from MAX_SUBPROPERTY_DEPTH
together, so they cannot drift apart. That the generated chain actually
resolves is pinned end to end by tests/sql-tests/kms-constraints/test17, which
puts a three-level and a two-level constraint on the same entity.
"""

import lib.shacl_properties_to_sql as props
import lib.utils as utils


def test_path_columns_follow_the_depth_limit():
    """
    The join chain and the path columns are generated from one number, so they
    cannot drift apart. They were written out by hand for two levels, which is
    the only reason a third was ever rejected.
    """
    assert utils.path_columns(1) == ['propertyPath', 'subpropertyPath']
    assert utils.path_columns(2) == ['propertyPath', 'subpropertyPath',
                                     'subpropertyPath2']
    assert len(utils.path_columns(4)) == 5
    # the first two keep their names at every limit
    assert utils.path_columns(4)[:2] == utils.path_columns(1)


def test_every_level_gets_a_join_hanging_off_the_previous_one():
    context = props.attribute_level_context()
    joins = context['attribute_joins']
    aliases = props.ATTRIBUTE_ALIASES[:len(utils.path_columns())]

    assert joins.count('LEFT JOIN attributes_view') == len(aliases)
    # the outermost level hangs off the entity, every other off its parent
    assert f'AS {aliases[0]} ' in joins and f'{aliases[0]}.parentId IS NULL' in joins
    for level in range(1, len(aliases)):
        assert f'{aliases[level]}.parentId = {aliases[level - 1]}.id' in joins, \
            f'level {level} is not anchored to its parent'


def test_values_come_from_the_declared_depth_not_the_deepest_match():
    """
    Reading the innermost row that EXISTS is not the same as reading the level
    the constraint declared. With COALESCE, a constraint naming a sub-attribute
    fell back to the PARENT's values whenever that sub-attribute was absent --
    so A1 had to exclude such rows outright, and a sh:minCount on a missing
    sub-attribute could never fire.
    """
    context = props.attribute_level_context()
    columns = utils.path_columns()
    aliases = props.ATTRIBUTE_ALIASES[:len(columns)]
    expr = context['deepest']('nodeType')
    assert expr.startswith('CASE WHEN'), 'must select by declared depth'
    assert 'COALESCE' not in expr
    for level in range(len(columns) - 1, 0, -1):
        assert (f'WHEN D.`{columns[level]}` IS NOT NULL '
                f'THEN {aliases[level]}.`nodeType`') in expr
    assert expr.endswith(f'ELSE {aliases[0]}.`nodeType` END')


def test_a_missing_sub_attribute_still_yields_a_row():
    """
    ...which is what lets its count see the zero. The parent must still have
    matched: with no parent there are no value nodes for the child to be
    missing from, and a value path never has a row of its own.
    """
    guard = props.attribute_level_context()['level_guard']
    aliases = props.ATTRIBUTE_ALIASES[:len(utils.path_columns())]
    assert f'{aliases[0]}.id is not NULL' in guard, 'parent must be required'
    assert 'hasValue' in guard and 'hasValueList' in guard, \
        'value paths must stay excluded'


def test_regexp_argument_order_differs_per_dialect():
    """
    SQLite follows the SQL convention that `X REGEXP Y` is regexp(Y, X), so its
    function takes (pattern, subject); Flink's REGEXP(str, regex) takes
    (subject, pattern). Passing SQLite the subject first compiles the VALUE as
    a pattern -- for ["abc","def"] that is a valid character class, so it
    matched everything and the check silently passed.
    """
    sqlite = props.list_element_checks(True)
    flink = props.list_element_checks(False)
    assert '`val` REGEXP ' in sqlite and 'REGEXP(`val`,' not in sqlite
    assert 'REGEXP(`val`,' in flink and '`val` REGEXP ' not in flink


def test_every_common_datatype_has_an_element_pattern():
    assert set(LIST_PATTERNS) == {'integer', 'double', 'boolean', 'string'}


import re  # noqa: E402

LIST_PATTERNS = dict(props.LIST_ELEMENT_PATTERNS)


def test_the_element_patterns_accept_and_reject_the_right_lists():
    """The patterns match the serialised array, so pin them directly."""
    integer = re.compile(LIST_PATTERNS['integer'])
    assert integer.match('[1,2,3]') and integer.match('[]') and integer.match('[-4]')
    assert not integer.match('["abc","def"]')
    assert not integer.match('[1,"abc"]')
    assert not integer.match('[1.5,2]')

    double = re.compile(LIST_PATTERNS['double'])
    assert double.match('[1.5,2]') and double.match('[]') and double.match('[1e5]')
    assert not double.match('["a"]')

    boolean = re.compile(LIST_PATTERNS['boolean'])
    assert boolean.match('[true,false]') and boolean.match('[]')
    assert not boolean.match('[1]')

    string = re.compile(LIST_PATTERNS['string'])
    assert string.match('["abc","def"]') and string.match('[]')
    assert string.match(r'["say \"hi\""]'), 'an escaped quote must not end the element'
    assert not string.match('[1,2]')
