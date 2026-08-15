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
Executes the *generated* circuit-evaluation SQL against SQLite.

This is deliberately not a string comparison: the template from
shacl_properties_to_sql is rendered and run, so the truth table below is a
statement about what Flink will compute, not about how the SQL happens to be
spelled today.
"""

import sqlite3
from jinja2 import Template

import lib.utils as utils
from lib.shacl_properties_to_sql import sql_combine_logic, ABSENCE_FIRING_OPERATIONS


DDL = """
CREATE TABLE entities (id TEXT, `type` TEXT, `deleted` BOOLEAN);
CREATE VIEW entities_view AS SELECT id, `type`, `deleted` FROM entities;

CREATE TABLE constraint_table (
    id INTEGER, operation TEXT, circuit_level INTEGER, targetClass TEXT,
    severity TEXT, eventName TEXT);

CREATE TABLE constraint_combination_table (
    member_constraint_id INTEGER, operation TEXT, target_constraint_id INTEGER);

CREATE TABLE constraint_trigger_table (
    resource TEXT, event TEXT, constraint_id INTEGER, triggered BOOLEAN,
    severity TEXT, text TEXT, ts TIMESTAMP);
"""

# Leaves 1,2,3 are level 0. Every connective sits at level 1 over the same
# two (or one) leaves so the truth tables can be compared side by side.
CIRCUIT = """
INSERT INTO constraint_table VALUES
    (1, NULL, 0, 'Cutter', 'warning', 'Component(1)'),
    (2, NULL, 0, 'Cutter', 'warning', 'Component(2)'),
    (3, NULL, 0, 'Cutter', 'warning', 'Component(3)'),
    (10, 'AND', 1, 'Cutter', 'critical', 'Component(10)'),
    (11, 'NOT', 1, 'Cutter', 'critical', 'Component(11)'),
    (12, 'XONE', 1, 'Cutter', 'critical', 'Component(12)'),
    (13, 'OR', 1, 'Cutter', 'critical', 'Component(13)');

INSERT INTO constraint_combination_table VALUES
    (1, 'AND', 10), (2, 'AND', 10),
    (3, 'NOT', 11),
    (1, 'XONE',12), (2, 'XONE',12),
    (1, 'OR',  13), (2, 'OR',  13),
    (10,'PUBLISH', -1), (11,'PUBLISH', -1),
    (12,'PUBLISH', -1), (13,'PUBLISH', -1);

INSERT INTO entities VALUES
    ('e1','Cutter',0), ('e2','Cutter',0), ('e3','Cutter',0), ('e4','Cutter',0);

-- e1: nothing fired   e2: leaf 1   e3: leaves 1+2   e4: leaf 3
INSERT INTO constraint_trigger_table VALUES
    ('e2','ev1',1,1,'warning','leaf1 failed',NULL),
    ('e3','ev1',1,1,'warning','leaf1 failed',NULL),
    ('e3','ev2',2,1,'warning','leaf2 failed',NULL),
    ('e4','ev3',3,1,'warning','leaf3 failed',NULL);
"""

# Verdict per focus node, keyed by circuit node id:
#   10 = AND(1,2)   11 = NOT(3)   12 = XONE(1,2)   13 = OR(1,2)
EXPECTED = {
    # nothing fired at all
    'e1': {10: False, 11: True, 12: True, 13: False},
    # exactly one of leaves 1,2 fired
    'e2': {10: True, 11: True, 12: False, 13: False},
    # both of leaves 1,2 fired
    'e3': {10: True, 11: True, 12: True, 13: True},
    # only leaf 3 fired
    'e4': {10: False, 11: False, 12: True, 13: False},
}


def _evaluate():
    conn = sqlite3.connect(':memory:')
    conn.executescript(DDL)
    conn.executescript(CIRCUIT)

    sql = Template(sql_combine_logic).render(
        target_class='entities',
        level=1,
        needs_universe=True,
        sqlite=True)
    conn.executescript(utils.process_sql_dialect(sql, True))

    rows = conn.execute(
        'SELECT resource, constraint_id, triggered FROM constraint_trigger_table '
        'WHERE constraint_id >= 10').fetchall()
    conn.close()
    return {(resource, cid): bool(triggered) for resource, cid, triggered in rows}


def test_circuit_truth_table():
    """All four connectives evaluate correctly from one template."""
    result = _evaluate()
    for resource, expected in EXPECTED.items():
        for constraint_id, want in expected.items():
            assert (resource, constraint_id) in result, \
                f'no verdict emitted for {resource}/{constraint_id}'
            assert result[(resource, constraint_id)] is want, \
                f'{resource}/{constraint_id}: expected {want}, ' \
                f'got {result[(resource, constraint_id)]}'


def test_absence_firing_needs_every_focus_node():
    """
    NOT and XONE fire when NOTHING fired, so a verdict must be produced even
    for focus nodes that have no trigger rows at all (e1 here). This is the
    reason those levels re-join the entity view.
    """
    result = _evaluate()
    assert result[('e1', 11)] is True
    assert result[('e1', 12)] is True


def test_or_semantics_unchanged():
    """OR still means 'every member violated' - the pre-existing behaviour."""
    result = _evaluate()
    assert result[('e3', 13)] is True     # both members fired
    assert result[('e2', 13)] is False    # only one member fired


def test_absence_firing_operations_are_the_non_monotone_ones():
    assert set(ABSENCE_FIRING_OPERATIONS) == {'NOT', 'XONE'}


def test_constraint_table_carries_the_circuit():
    columns = [name for column in utils.constraint_table for name in column]
    assert 'operation' in columns
    assert 'circuit_level' in columns


# ---------------------------------------------------------------- 2-level circuit
# Leaves 1,2,3 -> level 1: 10=AND(1,2), 11=NOT(3) -> level 2: 20=AND(10,11).
# Level 2 consumes verdicts written by level 1, which is the multi-level unroll.
CIRCUIT_2LEVEL = """
INSERT INTO constraint_table VALUES
    (1, NULL, 0, 'Cutter', 'warning', 'Component(1)'),
    (2, NULL, 0, 'Cutter', 'warning', 'Component(2)'),
    (3, NULL, 0, 'Cutter', 'warning', 'Component(3)'),
    (10, 'AND', 1, 'Cutter', 'warning', 'Component(10)'),
    (11, 'NOT', 1, 'Cutter', 'warning', 'Component(11)'),
    (20, 'AND', 2, 'Cutter', 'critical', 'Component(20)');

INSERT INTO constraint_combination_table VALUES
    (1, 'AND', 10), (2, 'AND', 10),
    (3, 'NOT', 11),
    (10, 'AND', 20), (11, 'AND', 20),
    (20, 'PUBLISH', -1);

INSERT INTO entities VALUES
    ('e1','Cutter',0), ('e2','Cutter',0), ('e3','Cutter',0), ('e4','Cutter',0);

INSERT INTO constraint_trigger_table VALUES
    ('e2','ev1',1,1,'warning','leaf1 failed',NULL),
    ('e3','ev1',1,1,'warning','leaf1 failed',NULL),
    ('e3','ev2',2,1,'warning','leaf2 failed',NULL),
    ('e4','ev3',3,1,'warning','leaf3 failed',NULL);
"""

# level1: AND(1,2) and NOT(3);  level2: AND(10,11) -- fired>=1
EXPECTED_2LEVEL = {
    # nothing fired: AND(1,2)=F, NOT(3)=T -> level2 sees 1 fired -> True
    'e1': {10: False, 11: True, 20: True},
    # leaf1: AND(1,2)=T, NOT(3)=T -> 2 fired -> True
    'e2': {10: True, 11: True, 20: True},
    # leaves 1+2: AND=T, NOT=T -> 2 fired -> True
    'e3': {10: True, 11: True, 20: True},
    # only leaf3: AND(1,2)=F, NOT(3)=F -> 0 fired -> False
    'e4': {10: False, 11: False, 20: False},
}


def test_multi_level_circuit_unrolls():
    """
    A level-2 node correctly consumes verdicts produced by level 1.

    This is the property the Flink deployment has NOT exercised: today's
    builder only ever emits a single level.
    """
    conn = sqlite3.connect(':memory:')
    conn.executescript(DDL)
    conn.executescript(CIRCUIT_2LEVEL)

    for level in (1, 2):
        sql = Template(sql_combine_logic).render(
            target_class='entities',
            level=level,
            needs_universe=True,
            sqlite=True)
        conn.executescript(utils.process_sql_dialect(sql, True))

    rows = conn.execute(
        'SELECT resource, constraint_id, triggered FROM constraint_trigger_table '
        'WHERE constraint_id >= 10').fetchall()
    conn.close()
    result = {(r, c): bool(t) for r, c, t in rows}

    for resource, expected in EXPECTED_2LEVEL.items():
        for constraint_id, want in expected.items():
            assert (resource, constraint_id) in result, \
                f'level {constraint_id}: no verdict for {resource}'
            assert result[(resource, constraint_id)] is want, \
                f'{resource}/{constraint_id}: expected {want}, ' \
                f'got {result[(resource, constraint_id)]}'


def test_circuit_level_is_longest_path_from_leaf():
    checks = [{'id': 1, 'circuit_level': 0},
              {'id': 2, 'circuit_level': 3},
              {'id': 3, 'circuit_level': 1}]
    assert utils.circuit_level_of(checks, [1, 3]) == 2
    assert utils.circuit_level_of(checks, [1, 2, 3]) == 4
    assert utils.circuit_level_of(checks, []) == 1
