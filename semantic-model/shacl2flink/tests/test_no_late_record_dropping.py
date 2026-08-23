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
Entity state must not be discarded for arriving "late".

The bridge stamps attribute and entity records with their observedAt, so the
Kafka record timestamp is an event time taken from the data -- and one that
spans years, because a value observed in 2024 is republished unchanged by every
snapshot. Declaring that column a rowtime with WATERMARK FOR ts AS ts turns the
attributes_view and entities_view dedups into EVENT-TIME Deduplicate operators
with zero lateness tolerance.

The consequence, measured on a cluster: a snapshot republishes all 251
attributes in one burst; the first record carrying a recent observedAt drives
the watermark to now; every remaining record in the burst with an older
observedAt is late and silently dropped. 753 records went into the dedup and 4
came out. Every join downstream was starved, and every constraint over them
reported "Found 0" for attributes that were plainly present in the topic and in
the store. Republishing a single value with a CURRENT timestamp made it visible
within seconds.

Nothing here needs event time. These are entity-state tables, not windowed
analytics: the dedup wants "the newest row per key", which ORDER BY ts DESC
gives just as well over an ordinary column, without a watermark deciding that
older rows may be thrown away. alerts_bulk keeps its watermark, because the
alerting path does use it.

Batch never showed any of this -- SQLite has no watermarks and drops nothing --
which is why the oracle agreed with Flink throughout.
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


def test_attributes_table_has_no_watermark():
    """The regression: 753 rows in, 4 out, and "Found 0" everywhere."""
    tables = _core_tables()
    assert 'attributes' in tables, 'create_core_tables.py emitted no attributes table'
    assert 'watermark' not in _field_names(tables['attributes'])


def test_entities_table_has_no_watermark(tmp_path):
    create_ngsild_tables.main(output_folder=str(tmp_path))
    tables = _tables((tmp_path / 'ngsild.yaml').read_text())
    entities = [name for name in tables if name and 'entities' in name]
    assert entities, 'create_ngsild_tables.py emitted no entities table'
    for name in entities:
        assert 'watermark' not in _field_names(tables[name]), \
            f'{name} declares a watermark again'


def test_the_timestamp_column_is_still_there():
    """Only the rowtime DECLARATION goes; ordering still needs the column.

    attributes_view picks the newest row per key with ORDER BY ts DESC. Dropping
    ts along with the watermark would leave the dedup with nothing to order by.
    """
    tables = _core_tables()
    assert 'ts' in _field_names(tables['attributes'])


def test_alerts_bulk_keeps_its_watermark():
    """The change is targeted, not a blanket removal.

    The alerting path genuinely uses event time; only the entity-state tables
    are wrong to.
    """
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


def test_attributes_table_exposes_the_kafka_offset():
    """The dedup needs an arrival order to break ties on."""
    tables = _core_tables()
    assert 'offset' in _field_names(tables['attributes'])


def test_attributes_view_breaks_ties_by_offset():
    """The regression: a delete that ties on ts must still win.

    debeziumBridge stamps a delete with the timestamp of the value it deletes,
    deliberately the same one, so the two tie. That relied on the tie being
    broken by arrival, which held while this compiled into Flink's Deduplicate.
    Without the watermark it is a general Rank, and Rank keeps the INCUMBENT on
    a tie -- so the delete lost and the attribute stayed live indefinitely.

    Measured: urn:filter:1's hasXXXWorkpiece was deleted in Scorpio, the delete
    published, and the job went on counting it until the same delete was
    republished with a strictly greater timestamp.
    """
    create_core_tables.main()
    statement = _view_statements(pathlib.Path('output/core.yaml').read_text())['attributes_view']
    assert 'ORDER BY COALESCE(`observedAt`, `ts`) DESC, `offset` DESC' in statement


def test_a_view_without_an_offset_column_still_orders_by_ts_alone(tmp_path):
    """entities has no offset metadata, so the tie-break must not be emitted."""
    create_ngsild_tables.main(output_folder=str(tmp_path))
    views = _view_statements((tmp_path / 'ngsild.yaml').read_text())
    entities = [s for name, s in views.items() if name and 'entities' in name]
    assert entities, 'no entities view generated'
    for statement in entities:
        assert '`offset`' not in statement
        assert 'ORDER BY ts DESC' in statement


def test_the_offset_is_not_exposed_by_the_view():
    """It is an ordering key, not part of the view's schema."""
    create_core_tables.main()
    statement = _view_statements(pathlib.Path('output/core.yaml').read_text())['attributes_view']
    header = statement.split('FROM (')[0]
    assert '`offset`' not in header


def test_the_view_orders_by_the_payload_observedAt_not_the_record_stamp():
    """Event time is DATA; the record stamp is transport metadata.

    They used to be the same field: debeziumBridge put observedAt into the Kafka
    record timestamp, so retention.ms -- a wall-clock STORAGE policy -- was being
    applied to an event time. The kms model observes at 2024-02-28, so every
    attribute record was born older than any sane retention and Kafka deleted it
    on contact. Measured on the cluster: three snapshot bursts of 249 records
    each, and iff.ngsild.attributes read back with logStart == logEnd every time.
    The pipeline still looked healthy, because the job consumes records in
    flight -- but there was no replay, no restart recovery and no observability.

    observedAt now travels in the payload and the dedup orders by it, so the
    event-time semantics are unchanged while `ts` reverts to write time.
    """
    create_core_tables.main()
    core = pathlib.Path('output/core.yaml').read_text()
    statement = _view_statements(core)['attributes_view']
    assert 'COALESCE(`observedAt`, `ts`)' in statement, \
        'the dedup no longer orders on the event time'
    assert 'ORDER BY ts' not in statement, \
        'the dedup still orders on the Kafka record timestamp alone'
    assert 'observedAt' in _field_names(_tables(core)['attributes']), \
        'the attributes table does not carry the payload observedAt'
