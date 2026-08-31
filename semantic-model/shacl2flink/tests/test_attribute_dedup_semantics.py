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
The attributes dedup must be a rowtime Deduplicate over ONE sort column.

`attributes_view` is what turns a stream of attribute rows into a changelog:
one row per live attribute, ordered by event time. Two properties of the
operator behind it are load-bearing, and both depend on the ORDER BY being a
single ROWTIME column.

Ties. Same-instant records are real -- the bridge stamps records lacking an
observedAt with its receive time, and a snapshot re-emission repeats its
record's timestamp exactly. Flink's Deduplicate (keep-last-row) takes the later
ARRIVAL on a tie; a general Rank keeps the INCUMBENT and replaces only on a
strictly greater key. Measured on urn:filter:1 hasStrength: the view latched a
deleted=true row, four later re-emissions of the live value tied and lost, and
the count constraint reported "Found 0 properties instead of [1, 1]" against an
attribute that plainly existed. A Kafka `offset` column used to restore
tie-by-arrival explicitly; the rowtime gives it for free, so that column is gone.

Soundness. From Flink 2.1, a top-1 ROW_NUMBER whose ORDER BY is not a single
time attribute is wrongly declared INSERT_ONLY and its retractions are silently
dropped -- alerts raise and never clear, with a healthy job and no error. The
two-column key hit exactly that. This is why a tie-break column must NOT come
back. See bug-reports/flink-2.1-topn-lost-retraction/README.md.

A NOTE ON LATENESS, because an earlier version of this file asserted the
opposite. Declaring the rowtime does NOT make old records "late" and discarded.
Only time-based operators -- windows, interval and temporal joins, windowed
TopN, CEP -- consume a watermark, and nothing here windows.
`RowTimeDeduplicateFunctionHelper.deduplicateOnRowTime` calls only
`shouldKeepCurrentRow(...)`, a pure rowtime comparison with no watermark check.
Verified at runtime on Flink 2.3.0: a row stamped BEHIND the watermark but
NEWER than the incumbent won the dedup and cleared the verdict. The regression
once blamed on lateness had a different cause -- observedAt lived in the Kafka
record timestamp, so retention.ms, a wall-clock STORAGE policy, deleted records
on contact (logStart == logEnd). That is why event time now travels in the
payload and `ts` is the write time.
"""

import pathlib

import ruamel.yaml

import create_core_tables
import create_ngsild_tables


def _tables(document):
    """{table spec name: [field dicts]} from a generated table document.

    Parsed leniently: these files end with Helm template directives, which are
    not YAML, so the loader raises once it reaches them. Everything before that
    point is what we came for.
    """
    tables = {}
    try:
        for section in ruamel.yaml.YAML(typ='safe').load_all(document):
            if not section or 'spec' not in section:
                continue
            spec = section['spec']
            if 'fields' in spec:
                tables[spec.get('name')] = spec['fields']
    except ruamel.yaml.YAMLError:
        pass
    return tables


def _core_tables():
    """create_core_tables.py writes to its own output folder, not a given one."""
    create_core_tables.main()
    return _tables(pathlib.Path('output/core.yaml').read_text())


def _field_names(fields):
    return {name.strip('`') for field in fields for name in field}


def _field_value(fields, wanted):
    for field in fields:
        for name, value in field.items():
            if name.strip('`').lower() == wanted:
                return value
    return None


def test_attributes_declares_a_rowtime_on_the_event_time():
    """Without the WATERMARK the dedup is a general Rank, not a Deduplicate."""
    tables = _core_tables()
    assert 'attributes' in tables, 'create_core_tables.py emitted no attributes table'
    watermark = _field_value(tables['attributes'], 'watermark')
    assert watermark is not None, 'attributes declares no watermark'
    assert 'eventTime' in watermark, \
        f'the rowtime must be the event time, got {watermark!r}'


def test_the_event_time_falls_back_to_the_write_time():
    """A writer that sets no observedAt -- the `synced` writeback, for one --
    would otherwise order by NULL, lose every comparison and never win."""
    tables = _core_tables()
    event_time = _field_value(tables['attributes'], 'eventtime')
    assert event_time is not None, 'attributes carries no eventTime column'
    assert 'COALESCE' in event_time and 'observedAt' in event_time and 'ts' in event_time, \
        f'eventTime must be COALESCE(observedAt, ts), got {event_time!r}'


def test_both_timestamp_columns_are_still_there():
    """observedAt is the event time (data); ts is the write time (transport)."""
    names = _field_names(_core_tables()['attributes'])
    assert 'observedAt' in names
    assert 'ts' in names


def test_the_kafka_offset_tie_break_is_gone():
    """A rowtime Deduplicate breaks ties by arrival without it, and a second
    sort column is exactly what trips the Flink 2.1+ insert-only bug."""
    assert 'offset' not in _field_names(_core_tables()['attributes'])


def test_entities_declares_a_rowtime_too(tmp_path):
    """Without it entities_view is a general Rank, which keeps the incumbent
    on a tie -- the same latent defect that made a deleted attribute go on
    being counted, and entity deletes had it too."""
    create_ngsild_tables.main(output_folder=str(tmp_path))
    tables = _tables((tmp_path / 'ngsild.yaml').read_text())
    entities = [name for name in tables if name and 'entities' in name]
    assert entities, 'create_ngsild_tables.py emitted no entities table'
    for name in entities:
        assert 'watermark' in _field_names(tables[name]), \
            f'{name} lost its rowtime; ties would go to the incumbent again'


def test_alerts_bulk_keeps_its_watermark():
    """The alerting path genuinely windows, and is untouched by this."""
    tables = _core_tables()
    assert 'watermark' in _field_names(tables['alerts_bulk'])


def _view_statements(document):
    """{view spec name: sqlstatement} from a generated table document."""
    views = {}
    try:
        for section in ruamel.yaml.YAML(typ='safe').load_all(document):
            if not section or 'spec' not in section:
                continue
            spec = section['spec']
            if 'sqlstatement' in spec:
                views[spec.get('name')] = spec['sqlstatement']
    except ruamel.yaml.YAMLError:
        pass
    return views


def _attributes_view():
    create_core_tables.main()
    return _view_statements(pathlib.Path('output/core.yaml').read_text())['attributes_view']


def test_the_view_orders_by_the_event_time_rowtime():
    statement = _attributes_view()
    assert 'ORDER BY `eventTime` DESC' in statement, \
        'the dedup no longer orders on the event-time rowtime'


def test_the_order_by_has_exactly_one_sort_column():
    """THE Flink 2.1+ guard. A second sort column makes the planner declare
    this dedup INSERT_ONLY and silently drop every retraction."""
    statement = _attributes_view()
    order_by = statement.split('ORDER BY')[1].split(')')[0]
    assert ',' not in order_by, \
        f'the dedup must sort on ONE column, got ORDER BY{order_by}'


def test_a_view_without_an_event_time_still_orders_by_ts_alone(tmp_path):
    """entities has no event time, so it orders by its single ts column."""
    create_ngsild_tables.main(output_folder=str(tmp_path))
    views = _view_statements((tmp_path / 'ngsild.yaml').read_text())
    entities = [s for name, s in views.items() if name and 'entities' in name]
    assert entities, 'no entities view generated'
    for statement in entities:
        assert '`offset`' not in statement
        assert 'ORDER BY ts DESC' in statement


def test_the_event_time_is_not_exposed_by_the_view():
    """It is the ordering key, not part of the view's schema: projecting it
    would carry a time attribute into the downstream joins."""
    header = _attributes_view().split('FROM (')[0]
    assert '`eventTime`' not in header
    assert '`offset`' not in header
