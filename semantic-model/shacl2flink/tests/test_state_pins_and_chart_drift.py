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
    test_attribute_dedup_semantics for the generator side)."""
    text = _chart_text()
    assert 'ORDER BY `eventTime` DESC' in text


def _chart_attributes_table():
    """The `attributes` BeamSqlTable body.

    `name: attributes` appears twice per document -- once under metadata, once
    under spec -- and str.split splits on EVERY occurrence, so [1] is the
    eight-character gap between them. The fields live after the second one.
    An earlier version of this guard read that gap and asserted against it,
    which passed no matter what the chart said.
    """
    return _chart_text().split('name: attributes\n')[2].split('---')[0]


def test_chart_attributes_view_sorts_on_one_column():
    """A second sort column makes Flink 2.1+ declare the dedup INSERT_ONLY and
    silently drop its retractions. The chart is what actually deploys, so it
    needs the guard as much as the generator does."""
    assert '`offset`' not in _chart_attributes_table(), \
        'the attributes table regained the offset tie-break column'
    assert 'COALESCE(`observedAt`, `ts`) DESC,' not in _chart_text(), \
        'the two-column dedup ordering is back'


def test_chart_attributes_table_declares_the_event_time_rowtime():
    attributes = _chart_attributes_table()
    assert "'observedAt': TIMESTAMP(3)" in attributes
    assert "'eventTime': AS COALESCE(`observedAt`, `ts`)" in attributes, \
        'the chart does not declare the eventTime computed column'
    assert 'watermark' in attributes.lower(), \
        'without the watermark the dedup compiles to a general Rank, which ' \
        'keeps the incumbent on a tie and is declared INSERT_ONLY on 2.1+'
