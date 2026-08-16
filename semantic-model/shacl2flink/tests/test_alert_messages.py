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
The alert message is a product surface, so it is tested like one.

Nothing asserted it before. The fixtures compared (resource, event, severity)
and the Flink e2e matched on event-name substrings, so the only part of an
alert a human actually reads was the one part no test looked at. What shipped:

    Model validation for Property .../hasStrength failed for urn:filter:1.
    Found 0 relationships instead of [[1, 1]!

on a *Property* check -- the wrong noun, a doubled opening bracket and a
missing closing one -- and every test stayed green. Elsewhere:

    Model validation for relationshiphttps://...hasCartridgefailed for ...
    Model validation for Property propertyPath failed for urn:plasmacutter:1.

a message with the concatenation spaces missing on both sides, and one printing
the literal string "propertyPath" because the column reference was left inside
the quotes.

Rendered messages are now pinned against real data by the sql-cases fixtures
(tests/sql-tests/sql-cases/*/expected compare `text`). These tests cover what a
fixture cannot: they read every message the compiler can emit, including the
ones no fixture happens to trigger.
"""

import re

import lib.shacl_properties_to_sql as props

# Columns that are selected in A1 and must therefore be referenced, never
# spelled out inside a string literal.
A1_COLUMNS = ['propertyPath', 'parentPath', 'printPath', 'minCount',
              'maxCount', 'propertyClass', 'nodeType', 'attributeType']

LITERAL = re.compile(r"'((?:[^']|'')*)'")


def _generated_sql():
    flink_relationship, sqlite_relationship = props.create_relationship_sql()
    flink_property, sqlite_property = props.create_property_sql()
    return {
        'relationship (flink)': flink_relationship,
        'relationship (sqlite)': sqlite_relationship,
        'property (flink)': flink_property,
        'property (sqlite)': sqlite_property,
    }


def _message_literals(sql):
    """Every string literal of every generated `text` expression."""
    messages = re.findall(r"'Model validation.*?as\s+`?text`?", sql,
                          re.IGNORECASE | re.DOTALL)
    assert messages, 'no alert message found to check'
    return [(message, LITERAL.findall(message)) for message in messages]


def test_no_message_spells_out_a_column_name():
    """
    `'Model validation for Property propertyPath failed for '` printed the word
    "propertyPath" to the operator instead of the path, for every sh:in
    violation. The column reference had been left inside the quotes.
    """
    for name, sql in _generated_sql().items():
        for message, literals in _message_literals(sql):
            for literal in literals:
                for column in A1_COLUMNS:
                    assert not re.search(rf'\b{column}\b', literal), \
                        f'{name}: message literal spells out the column ' \
                        f'{column!r} instead of referencing it: {literal!r}'


def test_message_brackets_balance():
    """
    The Property count reported `instead of [[1, 1]!` -- the range was built as
    a literal '[' plus an IFNULL arm that opened a SECOND one, and the closing
    bracket lived inside the other arm, so it went missing whenever maxCount
    was NULL. Counting brackets across a message's literals catches that
    without pinning the wording.
    """
    for name, sql in _generated_sql().items():
        for message, literals in _message_literals(sql):
            text = ''.join(literals)
            assert text.count('[') == text.count(']'), \
                f'{name}: unbalanced brackets in message: {text!r}'


def test_concatenations_are_spaced():
    """
    `'... for relationship' || propertyPath || 'failed for '` ran the words
    into the URI on both sides: "relationshiphttps://...hasCartridgefailed".
    A literal that abuts a column reference must end (or start) with a space or
    a punctuation mark that legitimately touches the value.
    """
    boundary = re.compile(r"'((?:[^']|'')*)'\s*\|\|\s*`?(\w+)`?|"
                          r"`?(\w+)`?\s*\|\|\s*'((?:[^']|'')*)'")
    for name, sql in _generated_sql().items():
        for message, _ in _message_literals(sql):
            for match in boundary.finditer(message):
                before, after_col, before_col, after = match.groups()
                if before is not None and after_col:
                    assert before == '' or before[-1] in ' ("\'[<', \
                        f'{name}: {before!r} runs into {after_col}'
                if after is not None and before_col:
                    assert after == '' or after[0] in ' .,;:!)"\']>', \
                        f'{name}: {before_col} runs into {after!r}'
