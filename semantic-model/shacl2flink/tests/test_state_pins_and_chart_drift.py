"""Two regression guards born from live debugging.

State pins: every side of a validation join must carry a STATE_TTL '0d'
hint. An expired join is dead for good -- re-publication is folded to a
no-op by the dedup rank and never refreshes downstream state -- so a
missing pin surfaces as rules that silently stop firing about one TTL
after the last full re-sync (measured with per-vertex counters).

Chart drift: helm/charts/sql-core/templates/core-tables.yaml is a
hand-maintained copy of what create_core_tables.py generates. Fixing the
generator does NOT fix a cluster deployed from the chart -- that exact
drift shipped once already -- so the load-bearing lines of the chart are
asserted here against the same expectations the generator tests use.
"""
import pathlib

import lib.shacl_properties_to_sql


def test_property_bases_pin_every_join_side():
    context = lib.shacl_properties_to_sql.attribute_level_context()
    rel = context['relationship_ttl_hint']
    prop = context['property_ttl_hint']
    for alias in ('A', 'D', 'C'):
        assert f"'{alias}' = '0d'" in rel
        assert f"'{alias}' = '0d'" in prop
    # the subclass-closure join of the relationship base
    assert "'G' = '0d'" in rel
    # every attribute join level in use
    assert "'B' = '0d'" in rel and "'B' = '0d'" in prop


def test_base_templates_use_the_generated_pins():
    src = pathlib.Path(lib.shacl_properties_to_sql.__file__).read_text()
    assert '{{ relationship_ttl_hint }}' in src, \
        'the relationship base no longer renders the join pins'
    assert '{{ property_ttl_hint }}' in src, \
        'the property base no longer renders the join pins'


def _chart_text():
    chart = pathlib.Path(__file__).resolve().parents[3] / \
        'helm' / 'charts' / 'sql-core' / 'templates' / 'core-tables.yaml'
    return chart.read_text()


def test_chart_attributes_view_matches_generator_ordering():
    """The dedup ordering is the event-time contract; the chart copy must
    carry the same clause the generator emits (see
    test_no_late_record_dropping for the generator side)."""
    text = _chart_text()
    assert 'ORDER BY COALESCE(`observedAt`, `ts`) DESC, `offset` DESC' in text


def test_chart_attributes_table_carries_event_time_and_offset():
    text = _chart_text()
    assert "'observedAt': TIMESTAMP(3)" in text
    assert "'offset': BIGINT METADATA VIRTUAL" in text
    assert 'WATERMARK' not in text.split('name: attributes\n')[1].split('---')[0], \
        'the attributes table regained a watermark; only windowed operators ' \
        'need one and it changes which dedup operator Flink selects'
