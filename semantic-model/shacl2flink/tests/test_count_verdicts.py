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

"""
A count check writes a verdict for every key it evaluates (issue #977).

A statementset redeploy replays constraint_trigger_table, so the new job starts
out reading the raises the previous job left there. A count check that emits
rows only while violated never writes those keys again once it finds them
satisfied, and the replayed raise is published as an open alert that nothing
closes. Every count check therefore writes a verdict per key -- the raise, or
an ok row in the form the circuit levels already use (triggered false,
severity 'ok', text 'All ok') -- so that the replayed record is overwritten.

The templates are rendered and executed against SQLite, which models the
replay exactly: the trigger table is upserted by key, so a planted raise is
either overwritten by the check or survives it.
"""

import re
import sqlite3

from jinja2 import Template

import lib.shacl_properties_to_sql as props
import lib.utils as utils


REL_PATH = 'https://example.org/hasCartridge'
PROP_PATH = 'https://example.org/hasStrength'
INV_PATH = 'https://example.org/hasFilter'
REL_EVENT = f'CountConstraintComponent({REL_PATH})'
PROP_EVENT = f'CountConstraintComponent({PROP_PATH})'
INV_EVENT = f'CountConstraintComponent(^{INV_PATH})'
REL_ID, PROP_ID, INV_ID = 1, 2, 3

DDL = """
CREATE TABLE constraint_trigger_table (
    resource TEXT, event TEXT, constraint_id INTEGER, triggered BOOLEAN,
    severity TEXT, text TEXT, ts TIMESTAMP,
    PRIMARY KEY (resource, constraint_id, event));
CREATE TABLE constraint_combination_table (
    member_constraint_id INTEGER, operation TEXT, target_constraint_id INTEGER);
CREATE TABLE constraint_table (
    id INTEGER, targetClass TEXT, propertyPath TEXT, attributeType TEXT,
    maxCount INTEGER, minCount INTEGER, severity TEXT, message TEXT);
CREATE TABLE alerts_bulk (
    resource TEXT, event TEXT, environment TEXT, service TEXT, severity TEXT,
    customer TEXT, text TEXT, ts TIMESTAMP, PRIMARY KEY (resource, event));
CREATE TABLE entities_view (id TEXT, `type` TEXT, `deleted` BOOLEAN);
CREATE TABLE attributes_view (
    entityId TEXT, name TEXT, `type` TEXT, attributeValue TEXT,
    parentId TEXT, `deleted` BOOLEAN);

-- The A1 rows a relationship count reads: one per attribute instance, or one
-- with link NULL for an entity without the attribute.
CREATE TABLE rel_a1 (
    this TEXT, edeleted BOOLEAN, adeleted BOOLEAN, link TEXT,
    propertyPath TEXT, parentPath TEXT, maxCount INTEGER, minCount INTEGER,
    severity TEXT, constraint_id INTEGER);
CREATE TABLE prop_a1 (
    this TEXT, typ TEXT, edeleted BOOLEAN, adeleted BOOLEAN, attr_typ TEXT,
    `index` TEXT, propertyPath TEXT, parentPath TEXT, maxCount INTEGER,
    minCount INTEGER, severity TEXT, constraint_id INTEGER);
"""

PROPERTY = 'https://uri.etsi.org/ngsi-ld/Property'
RELATIONSHIP = 'https://uri.etsi.org/ngsi-ld/Relationship'

# ok:   satisfied now            -> the replayed raise must be overwritten
# bad:  still violated           -> stays raised, with the fresh verdict
# del:  the entity was deleted   -> closes as well (a deleted entity is not
#                                   validated, see test_delete_semantics.py)
MODEL = f"""
INSERT INTO rel_a1 VALUES
    ('urn:ok',  0, 0, '{RELATIONSHIP}', '{REL_PATH}', '', 1, 1, 'warning', {REL_ID}),
    ('urn:bad', 0, NULL, NULL,          '{REL_PATH}', '', 1, 1, 'warning', {REL_ID}),
    ('urn:del', 1, 1, '{RELATIONSHIP}', '{REL_PATH}', '', 1, 1, 'warning', {REL_ID});

INSERT INTO prop_a1 VALUES
    ('urn:ok',  'T', 0, 0, '{PROPERTY}', '@none', '{PROP_PATH}', '', 1, 1, 'warning', {PROP_ID}),
    ('urn:bad', 'T', 0, 0, '{PROPERTY}', '@none', '{PROP_PATH}', '', 1, 1, 'warning', {PROP_ID}),
    ('urn:bad', 'T', 0, 0, '{PROPERTY}', 'urn:ds:1', '{PROP_PATH}', '', 1, 1, 'warning', {PROP_ID}),
    ('urn:del', 'T', 1, 1, '{PROPERTY}', '@none', '{PROP_PATH}', '', 1, 1, 'warning', {PROP_ID});

INSERT INTO constraint_table VALUES
    ({REL_ID}, 'T', '{REL_PATH}', '{RELATIONSHIP}', 1, 1, 'warning', NULL),
    ({PROP_ID}, 'T', '{PROP_PATH}', '{PROPERTY}', 1, 1, 'warning', NULL),
    ({INV_ID}, 'T', '{INV_PATH}', '{props.INVERSE_RELATIONSHIP_TYPE}', 1, 1, 'warning', NULL);
INSERT INTO constraint_combination_table VALUES
    ({REL_ID}, 'PUBLISH', -1), ({PROP_ID}, 'PUBLISH', -1), ({INV_ID}, 'PUBLISH', -1);

-- Inverse count: exactly one live entity must refer to each T.
INSERT INTO entities_view VALUES
    ('urn:ok', 'T', 0), ('urn:bad', 'T', 0), ('urn:del', 'T', 1),
    ('urn:ref:1', 'R', 0);
INSERT INTO attributes_view VALUES
    ('urn:ref:1', '{INV_PATH}', '{RELATIONSHIP}', 'urn:ok', NULL, 0);
"""


def _replayed_raises():
    """What the previous job left on the topic: a raise for every key."""
    rows = []
    for resource in ('urn:ok', 'urn:bad', 'urn:del'):
        for event, cid in ((REL_EVENT, REL_ID), (PROP_EVENT, PROP_ID), (INV_EVENT, INV_ID)):
            rows.append((resource, event, cid, 1, 'warning',
                         f'Replayed: found 10 instead of [1, 1] for {resource}'))
    return rows


def _run(replay=True):
    conn = sqlite3.connect(':memory:')
    conn.executescript(DDL)
    conn.executescript(MODEL)
    if replay:
        conn.executemany('INSERT INTO constraint_trigger_table VALUES (?, ?, ?, ?, ?, ?, NULL)',
                         _replayed_raises())

    for template, a1 in ((props.sql_check_relationship_property_count, 'rel_a1'),
                         (props.sql_check_property_count, 'prop_a1')):
        head = f'INSERT OR REPLACE INTO constraint_trigger_table\nWITH A1 AS (SELECT * FROM {a1})\n'
        sql = head + Template(template).render(sqlite=True) + ';'
        conn.executescript(utils.process_sql_dialect(sql, True))
    inverse = Template(props.sql_check_inverse_relationship_count).render(
        sqlite=True, alerts_bulk_table='constraint_trigger_table',
        constraint_table='constraint_table', target_class='entities',
        inverse_marker=props.INVERSE_RELATIONSHIP_TYPE)
    conn.executescript(utils.process_sql_dialect(inverse, True))
    conn.executescript(Template(props.sql_insert_constraint_in_alerts).render(
        alerts_bulk_table='alerts_bulk', sqlite=True))

    alerts = {(r, e): (s, t) for r, e, s, t in conn.execute(
        'SELECT resource, event, severity, text FROM alerts_bulk')}
    triggers = {(r, e): (bool(tr), s, t) for r, e, tr, s, t in conn.execute(
        'SELECT resource, event, triggered, severity, text FROM constraint_trigger_table')}
    conn.close()
    return alerts, triggers


EVENTS = (REL_EVENT, PROP_EVENT, INV_EVENT)


def test_a_replayed_raise_closes_once_the_count_is_satisfied():
    """Acceptance criterion 1 of #977, for relationship, property and inverse counts."""
    alerts, _ = _run()
    for event in EVENTS:
        assert ('urn:ok', event) not in alerts, \
            f'the replayed raise for {event} survived a satisfied count: {alerts[("urn:ok", event)]}'


def test_a_replayed_raise_stays_open_while_still_violated():
    """Acceptance criterion 2 of #977: open, and now carrying the job's own verdict."""
    alerts, _ = _run()
    for event in EVENTS:
        assert ('urn:bad', event) in alerts, f'a violated {event} was closed'
        severity, text = alerts[('urn:bad', event)]
        assert severity == 'warning'
        assert not text.startswith('Replayed'), \
            f'{event} still carries the replayed text, so the check wrote nothing: {text}'
    assert 'Found 0 relationships instead of [1, 1]!' in alerts[('urn:bad', REL_EVENT)][1]
    assert 'Found 2 properties instead of [1, 1]!' in alerts[('urn:bad', PROP_EVENT)][1]
    assert 'Found 0 referring entities instead of [1, 1]!' in alerts[('urn:bad', INV_EVENT)][1]


def test_a_replayed_raise_of_a_deleted_entity_closes():
    """A deleted entity is not validated (#886): its replayed raise must not stay either."""
    alerts, _ = _run()
    for event in EVENTS:
        assert ('urn:del', event) not in alerts, f'{event} kept a deleted entity alerting'


def test_a_satisfied_count_writes_an_ok_verdict():
    """The ok row has the form the circuit levels write: triggered false, 'ok', 'All ok'."""
    _, triggers = _run(replay=False)
    for resource in ('urn:ok', 'urn:del'):
        for event in EVENTS:
            assert triggers.get((resource, event)) == (False, 'ok', 'All ok'), \
                f'{resource}/{event}: no ok verdict, got {triggers.get((resource, event))}'


def test_without_a_replay_only_the_violations_are_published():
    """Writing ok verdicts must not change which alerts a fresh job raises."""
    alerts, _ = _run(replay=False)
    assert set(alerts) == {('urn:bad', event) for event in EVENTS}


def test_an_ok_verdict_does_not_lower_the_severity_of_an_alert_sharing_its_event():
    """
    Alerts are keyed by (resource, event), and two constraints can share both --
    the same count on a class and on its superclass. An ok row of one of them
    must not be aggregated into the published alert of the other: 'ok' sorts
    above 'critical', 'major' and 'minor', so MAX(severity) would publish it.
    """
    conn = sqlite3.connect(':memory:')
    conn.executescript(DDL)
    conn.executescript(f"""
        INSERT INTO constraint_table VALUES
            (7, 'T', '{PROP_PATH}', '{PROPERTY}', 1, 1, 'critical', NULL),
            (8, 'S', '{PROP_PATH}', '{PROPERTY}', 1, 1, 'critical', 'A shape message');
        INSERT INTO constraint_combination_table VALUES (7, 'PUBLISH', -1), (8, 'PUBLISH', -1);
        INSERT INTO constraint_trigger_table VALUES
            ('urn:x', '{PROP_EVENT}', 7, 1, 'critical', 'Found 0 properties', NULL),
            ('urn:x', '{PROP_EVENT}', 8, 0, 'ok', 'All ok', NULL);
    """)
    conn.executescript(Template(props.sql_insert_constraint_in_alerts).render(
        alerts_bulk_table='alerts_bulk', sqlite=True))
    rows = conn.execute('SELECT severity, text FROM alerts_bulk').fetchall()
    conn.close()
    assert rows == [('critical', 'Found 0 properties')]


def _generated_count_statements():
    """Every count statement as generated for Flink, one UNION ALL member each."""
    _, relationship = props.create_relationship_sql()
    _, prop = props.create_property_sql()
    _, inverse = props.create_inverse_relationship_sql()
    members = re.split(r'\bUNION\s+ALL\b', relationship + prop + inverse, flags=re.IGNORECASE)
    return [m for m in members if 'CountConstraintComponent' in m]


def test_no_count_statement_filters_its_verdicts():
    """A HAVING would drop the ok verdicts again; the verdict is a column instead."""
    statements = _generated_count_statements()
    assert len(statements) == 3
    for statement in statements:
        assert not re.search(r'\bHAVING\b', statement, re.IGNORECASE), statement[:200]
        assert "ELSE 'ok'" in statement and "ELSE 'All ok'" in statement
