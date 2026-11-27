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
from lib.shacl_properties_to_sql import sql_combine_logic, sql_insert_constraint_in_alerts, \
    ABSENCE_FIRING_OPERATIONS


DDL = """
CREATE TABLE entities (id TEXT, `type` TEXT, `deleted` BOOLEAN);
CREATE VIEW entities_view AS SELECT id, `type`, `deleted` FROM entities;

CREATE TABLE constraint_table (
    id INTEGER, operation TEXT, circuit_level INTEGER, targetClass TEXT,
    severity TEXT, eventName TEXT, instanceScoped INTEGER DEFAULT 0);

CREATE TABLE constraint_combination_table (
    member_constraint_id INTEGER, operation TEXT, target_constraint_id INTEGER);

CREATE TABLE constraint_trigger_table (
    resource TEXT, event TEXT, constraint_id INTEGER, triggered BOOLEAN,
    severity TEXT, text TEXT, ts TIMESTAMP, instance TEXT DEFAULT '');
"""

# Leaves 1,2,3 are level 0. Every connective sits at level 1 over the same
# two (or one) leaves so the truth tables can be compared side by side.
CIRCUIT = """
INSERT INTO constraint_table (id, operation, circuit_level, targetClass, severity, eventName) VALUES
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
INSERT INTO constraint_trigger_table (resource, event, constraint_id, triggered, severity, text, ts) VALUES
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


def _run_level(conn, level, operations):
    """Render a level as translate() does: a level with NOT or XONE gets the universe
    statement for them and a sparse one for OR and AND; any other level only the latter."""
    universe = bool(set(operations) & set(ABSENCE_FIRING_OPERATIONS))
    variants = [(True, True), (False, True)] if universe else [(False, False)]
    for needs_universe, split in variants:
        sql = Template(sql_combine_logic).render(
            target_class='entities',
            level=level,
            needs_universe=needs_universe,
            split_by_operation=split,
            sqlite=True)
        conn.executescript(utils.process_sql_dialect(sql, True))


def _verdict(result, resource, constraint_id, operation):
    """OR and AND are sparse: no verdict is a satisfied node. NOT and XONE must give one."""
    if operation in ABSENCE_FIRING_OPERATIONS:
        assert (resource, constraint_id) in result, \
            f'no verdict emitted for {resource}/{constraint_id}'
    return result.get((resource, constraint_id), False)


def _evaluate():
    conn = sqlite3.connect(':memory:')
    conn.executescript(DDL)
    conn.executescript(CIRCUIT)

    _run_level(conn, 1, ('AND', 'NOT', 'XONE', 'OR'))

    rows = conn.execute(
        'SELECT resource, constraint_id, triggered FROM constraint_trigger_table '
        'WHERE constraint_id >= 10').fetchall()
    conn.close()
    return {(resource, cid): bool(triggered) for resource, cid, triggered in rows}


def test_circuit_truth_table():
    """All four connectives evaluate correctly from one template."""
    result = _evaluate()
    operations = {10: 'AND', 11: 'NOT', 12: 'XONE', 13: 'OR'}
    for resource, expected in EXPECTED.items():
        for constraint_id, want in expected.items():
            got = _verdict(result, resource, constraint_id, operations[constraint_id])
            assert got is want, f'{resource}/{constraint_id}: expected {want}, got {got}'


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
    assert result[('e3', 13)] is True                     # both members fired
    assert _verdict(result, 'e2', 13, 'OR') is False      # only one member fired


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
INSERT INTO constraint_table (id, operation, circuit_level, targetClass, severity, eventName) VALUES
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

INSERT INTO constraint_trigger_table (resource, event, constraint_id, triggered, severity, text, ts) VALUES
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

    _run_level(conn, 1, ('AND', 'NOT'))
    _run_level(conn, 2, ('AND',))

    rows = conn.execute(
        'SELECT resource, constraint_id, triggered FROM constraint_trigger_table '
        'WHERE constraint_id >= 10').fetchall()
    conn.close()
    result = {(r, c): bool(t) for r, c, t in rows}

    operations = {10: 'AND', 11: 'NOT', 20: 'AND'}
    for resource, expected in EXPECTED_2LEVEL.items():
        for constraint_id, want in expected.items():
            got = _verdict(result, resource, constraint_id, operations[constraint_id])
            assert got is want, f'{resource}/{constraint_id}: expected {want}, got {got}'


def test_circuit_level_is_longest_path_from_leaf():
    checks = [{'id': 1, 'circuit_level': 0},
              {'id': 2, 'circuit_level': 3},
              {'id': 3, 'circuit_level': 1}]
    assert utils.circuit_level_of(checks, [1, 3]) == 2
    assert utils.circuit_level_of(checks, [1, 2, 3]) == 4
    assert utils.circuit_level_of(checks, []) == 1


# ------------------------------------------------------- per attribute instance
# #1106: 30 = OR(1,2) over the values of one attribute (instanceScoped), 31 =
# OR(1,2) of a node shape (not scoped). Leaves report their instance chain; a
# count of the attribute reports '' and counts for every instance.
CIRCUIT_INSTANCES = """
INSERT INTO constraint_table (id, operation, circuit_level, targetClass, severity, eventName, instanceScoped) VALUES
    (1, NULL, 0, 'Cutter', 'warning', 'Component(1)', 0),
    (2, NULL, 0, 'Cutter', 'warning', 'Component(2)', 0),
    (30, 'OR', 1, 'Cutter', 'warning', 'Or(30)', 1),
    (31, 'OR', 1, 'Cutter', 'warning', 'Or(31)', 0);

INSERT INTO constraint_combination_table VALUES
    (1, 'OR', 30), (2, 'OR', 30), (1, 'OR', 31), (2, 'OR', 31),
    (30, 'PUBLISH', -1), (31, 'PUBLISH', -1);

INSERT INTO constraint_trigger_table (resource, event, constraint_id, triggered, severity, text, ts, instance) VALUES
    -- e1: instance a fails member 1, instance b member 2: each meets the other branch
    ('e1','ev1[a]',1,1,'warning','a fails 1',NULL,'[a]'),
    ('e1','ev2[b]',2,1,'warning','b fails 2',NULL,'[b]'),
    -- e2: instance a fails both members
    ('e2','ev1[a]',1,1,'warning','a fails 1',NULL,'[a]'),
    ('e2','ev2[a]',2,1,'warning','a fails 2',NULL,'[a]'),
    -- e3: member 1 is a count of the attribute (''), instance a fails member 2
    ('e3','count',1,1,'warning','count fails',NULL,''),
    ('e3','ev2[a]',2,1,'warning','a fails 2',NULL,'[a]'),
    -- e4: instance [a] fails member 1, instance [a][b] of a sub-attribute member 2
    ('e4','ev1[a]',1,1,'warning','a fails 1',NULL,'[a]'),
    ('e4','ev2[a][b]',2,1,'warning','ab fails 2',NULL,'[a][b]');
"""


def _evaluate_instances():
    conn = sqlite3.connect(':memory:')
    conn.executescript(DDL)
    conn.executescript(CIRCUIT_INSTANCES)
    _run_level(conn, 1, ('OR',))
    rows = conn.execute(
        'SELECT resource, constraint_id, instance, triggered FROM constraint_trigger_table '
        'WHERE constraint_id >= 30').fetchall()
    conn.close()
    return {(r, c, i): bool(t) for r, c, i, t in rows}


def test_a_connective_over_the_values_is_judged_per_instance():
    result = _evaluate_instances()
    # Each instance meets a branch: no instance violates the sh:or.
    assert not any(t for (r, c, _), t in result.items() if r == 'e1' and c == 30)
    # One instance meets none.
    assert result[('e2', 30, '[a]')] is True


def test_a_count_of_the_attribute_counts_for_every_instance():
    result = _evaluate_instances()
    assert result[('e3', 30, '[a]')] is True
    # A member row counts for the instances its chain is a prefix of.
    assert result[('e4', 30, '[a][b]')] is True
    assert result[('e4', 30, '[a]')] is False


def test_a_connective_of_a_node_shape_is_judged_for_the_entity():
    result = _evaluate_instances()
    assert result[('e1', 31, '')] is True
    assert {i for (r, c, i) in result if c == 31} == {''}


def test_the_generated_trigger_table_keys_a_verdict_by_its_instance():
    """The table has no copy in a chart: the shacl chart's table comes from this generator, so
    the key is checked on what it generates for Flink and for SQLite (#1106)."""
    table = utils.create_constraint_trigger_yaml_table('upsert-kafka', {'topic': 't'}, {'format': 'json'})
    assert table['spec']['primaryKey'] == ['resource', 'constraint_id', 'event', 'instance']
    assert {'instance': 'STRING'} in table['spec']['fields']
    assert 'PRIMARYKEY(`resource`,`constraint_id`,`event`,`instance`)' in \
        utils.create_constraint_trigger_sql_table().replace(' ', '').replace('\n', '')
    assert {'instanceScoped': 'INTEGER'} in utils.constraint_table


def test_the_alert_of_a_node_judged_per_instance_takes_the_violated_rows():
    """Several rows under one event, 'ok' ones among them: severity and text are the violated one's."""
    conn = sqlite3.connect(':memory:')
    conn.executescript(DDL)
    conn.executescript("""
        CREATE TABLE alerts_bulk (resource TEXT, event TEXT, environment TEXT, service TEXT,
            severity TEXT, customer TEXT, text TEXT, ts TIMESTAMP);
        ALTER TABLE constraint_table ADD COLUMN message TEXT;
        INSERT INTO constraint_table (id, operation, circuit_level, targetClass, severity, eventName)
            VALUES (30, 'OR', 1, 'Cutter', 'critical', 'Or(30)');
        INSERT INTO constraint_combination_table VALUES (30, 'PUBLISH', -1);
        INSERT INTO constraint_trigger_table VALUES
            ('e1','Or(30)',30,1,'critical','b fails',NULL,'[b]'),
            ('e1','Or(30)',30,0,'ok','All ok',NULL,'[a]');
    """)
    sql = Template(sql_insert_constraint_in_alerts).render(alerts_bulk_table='alerts_bulk', sqlite=True)
    conn.executescript(utils.process_sql_dialect(sql, True))
    rows = conn.execute('SELECT resource, event, severity, text FROM alerts_bulk').fetchall()
    conn.close()
    assert rows == [('e1', 'Or(30)', 'critical', 'b fails')]
