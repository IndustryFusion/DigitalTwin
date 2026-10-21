"""A shape is not tied to an entity type.

SHACL selects focus nodes by class, by named node, by the subjects or objects
of a predicate, by a SPARQL query, or implicitly when the shape is itself a
class; a shape may also have no target and be reached through sh:node. The
kms uses only sh:targetClass, and the validator had come to run only those:
a shape written with sh:targetNode was never checked at all.

tests/corpus/targets has one shape per kind and three violations.
"""

from collections import Counter

import pytest

from semforge.validate import validate_package
from semforge.validate.applicable import focus_nodes
from semforge.validate.shapes import every_node_shape, node_shapes, targeted_shapes

EX = 'https://example.org/targets/'


def _local(shapes):
    return {str(s).rsplit('/', 1)[-1] for s in shapes}


def test_every_target_kind_is_a_shape_that_runs(targets):
    assert _local(targeted_shapes(targets.shapes)) == {
        'PumpShape', 'ValveNodeShape', 'HasValveShape', 'PointedAtShape',
        'HighPressureShape', 'Gauge'}
    # node_shapes keeps meaning "belongs to an entity type" -- by sh:targetClass,
    # or by being the class itself (Gauge).
    assert _local(node_shapes(targets.shapes)) == {'PumpShape', 'Gauge'}


def test_a_shape_that_is_its_class_is_that_type_s_own(targets):
    """ex:Gauge is a class and a node shape: it targets Gauges implicitly, so
    it is Gauge's own shape -- in the Types tree, edited on the type page, and
    where + Attribute writes. Not a shape that applies "under a condition"."""
    from semforge.cooked.constrain import own_shape
    from semforge.cooked.tree import build_tree
    from semforge.cooked.typepage import build_type_page
    from semforge.validate.shapes import class_targets

    assert [str(c) for c in class_targets(targets.shapes, EX + 'Gauge')] == [EX + 'Gauge']
    assert own_shape(targets, EX + 'Gauge') == EX + 'Gauge'
    root = next(r for r in build_tree(targets) if r.target_class == EX + 'Gauge')
    assert [s.label for s in root.children] == ['ex:Gauge']
    page = build_type_page(targets, EX + 'Gauge')
    assert page['ownShape'] == EX + 'Gauge'
    rows = page['attributes']
    assert [r['label'] for r in rows] == ['hasReading'] and not rows[0].get('via')
    assert 'ex:Gauge' not in [a['shapeName'] for a in page['alsoCheckedBy']]


def test_a_shape_reached_only_through_sh_node_is_still_a_shape(targets):
    assert _local(every_node_shape(targets.shapes)) == \
        _local(targeted_shapes(targets.shapes)) | {'PositionShape'}


@pytest.fixture(scope='module')
def report(targets):
    return validate_package(targets, strict=False)


def test_every_target_kind_is_validated(report):
    found = {(str(v.resource), v.shape_curie) for v in report.violations}
    assert found == {('urn:gauge:1', 'ex:Gauge'),
                     ('urn:pump:2', 'ex:HighPressureShape'),
                     ('urn:valve:2', 'ex:PointedAtShape')}


def test_the_conforming_ones_are_reported_as_evaluated(report):
    """Conformance is the absence of a result; the enumerator has to have
    expected each pair, or a shape that never ran reads as satisfied."""
    statuses = Counter((r.shape_curie, r.status.name) for r in report.results)
    for shape in ('ex:PumpShape', 'ex:HasValveShape', 'ex:ValveNodeShape',
                  'ex:PointedAtShape'):
        assert statuses[(shape, 'CONFORMANT')], shape
    assert not report.diagnostics, [d.message for d in report.diagnostics]


@pytest.mark.parametrize('shape, nodes', [
    ('PumpShape', {'urn:pump:1', 'urn:pump:2', 'urn:pump:3'}),
    ('ValveNodeShape', {'urn:valve:1'}),
    ('HasValveShape', {'urn:pump:1', 'urn:pump:3'}),
    ('PointedAtShape', {'urn:valve:1', 'urn:valve:2'}),
    ('HighPressureShape', {'urn:pump:2'}),
    ('Gauge', {'urn:gauge:1'}),
    ('PositionShape', set()),
])
def test_focus_nodes_follow_each_target_kind(targets, shape, nodes):
    from rdflib import URIRef

    found = focus_nodes(URIRef(EX + shape), targets.shapes, targets.model,
                        targets.knowledge)
    assert {str(n) for n in found} == nodes


def test_the_kms_runs_exactly_what_it_ran_before(corpus):
    """Every kms shape has a class target, so nothing changes there."""
    assert targeted_shapes(corpus.shapes) == node_shapes(corpus.shapes)


# --- navigation: the Shapes view, the shape page, the type page ------------------

def test_the_shapes_view_says_each_target_in_words(targets):
    from semforge.cooked.shapes import build_shapes

    said = {row['label'].split(':')[-1]: row['detail'] for row in build_shapes(targets)}
    assert said['PumpShape'].startswith('targets Pump')
    assert said['ValveNodeShape'] == 'targets urn:valve:1'
    assert said['HasValveShape'].startswith('targets subjects of hasValve')
    assert said['PointedAtShape'].startswith('targets objects of hasObject')
    assert said['HighPressureShape'].startswith('SPARQL target')
    assert said['Gauge'].startswith('targets Gauge (implicitly)')
    assert said['PositionShape'].startswith('no target · used by ValveNodeShape')
    assert '1 violation(s)' in said['PointedAtShape']


def test_a_shape_without_a_target_reaches_what_its_user_reaches(targets):
    from semforge.cooked.shapepage import build_shape_page

    page = build_shape_page(targets, 'ex:PositionShape')
    assert page['targets'] == [] and page['usedBy'][0]['name'] == 'ex:ValveNodeShape'
    assert [n['id'] for n in page['reach']['nodes']] == ['urn:valve:1']
    assert [t['label'] for t in page['types']] == ['Valve']
    assert [a['label'] for a in page['attributes']] == ['hasPosition']


def test_a_shape_page_names_what_it_violates(targets):
    from semforge.cooked.shapepage import build_shape_page

    page = build_shape_page(targets, EX + 'PointedAtShape')
    assert page['targets'][0]['text'] == 'every entity a Relationship points at'
    assert page['summary']['reached'] == 2 and page['summary']['violations'] == 1
    bad = {n['id']: n['violations'] for n in page['reach']['nodes']}
    assert bad['urn:valve:2'] and not bad['urn:valve:1']


def test_a_shape_page_edits_its_own_shape(corpus, targets):
    """Every row action on the shape page writes into the shape itself."""
    page = build_shape_page_for(corpus, 'iffBaseShacl:FilterShape')
    assert page['ownShape'].endswith('/FilterShape')
    assert page['testType'].endswith('/Filter') and page['subject'] == 'Filter'
    loose = build_shape_page_for(targets, 'ex:PositionShape')
    assert loose['testType'] == '' and loose['subject'] == 'focus node of PositionShape'


def test_an_attribute_is_added_to_a_shape_without_a_class_target(tmp_path):
    """+ Attribute on the shape page of a shape reached only through sh:node."""
    import shutil

    from semforge.cooked.constrain import add_attribute_constraint, attribute_options
    from semforge.package import load
    from conftest import TARGETS

    root = tmp_path / 'targets'
    shutil.copytree(TARGETS, root, ignore=shutil.ignore_patterns('.semforge'))
    shape = EX + 'PositionShape'
    offered = {o['label']: o['status'] for o in attribute_options(load(str(root)), shape)}
    assert offered['hasPosition'] == 'here' and offered['hasReading'] == 'free'
    add_attribute_constraint(load(str(root)), shape, 'hasReading', required=True,
                             datatype='xsd:double')
    page = build_shape_page_for(load(str(root)), shape)
    assert [a['label'] for a in page['attributes']] == ['hasPosition', 'hasReading']


def build_shape_page_for(package, shape):
    from semforge.cooked.shapepage import build_shape_page

    return build_shape_page(package, shape)


def test_a_sparql_target_shows_its_query(targets):
    from semforge.cooked.shapepage import build_shape_page

    target = build_shape_page(targets, 'ex:HighPressureShape')['targets'][0]
    assert target['kind'] == 'sparql' and 'FILTER(?p > 5)' in target['value']


def test_the_type_page_lists_shapes_that_reach_it_by_other_targets(targets):
    from semforge.cooked.typepage import build_type_page

    pump = build_type_page(targets, EX + 'Pump')
    assert {a['shapeName'] for a in pump['alsoCheckedBy']} == {
        'ex:HasValveShape', 'ex:HighPressureShape'}
    valve = build_type_page(targets, EX + 'Valve')
    assert {a['shapeName'] for a in valve['alsoCheckedBy']} == {
        'ex:PointedAtShape', 'ex:ValveNodeShape', 'ex:PositionShape'}


def test_the_type_page_collects_every_constraint_that_applies(targets):
    """Pump's own hasPressure, and the ones that apply under a condition:
    HasValveShape's (pumps with a valve) and HighPressureShape's (its SPARQL
    target) -- in the same table, marked."""
    from semforge.cooked.typepage import build_type_page

    rows = build_type_page(targets, EX + 'Pump')['attributes']
    # One row per attribute; the shapes behind it are its contributions.
    assert [r['label'] for r in rows] == ['hasPressure', 'hasValve']
    rows = [c for r in rows for c in r.get('contributions', [r])]
    found = {(r['label'], r.get('via', ''), r.get('condition', '')) for r in rows}
    assert found == {
        ('hasPressure', '', ''),
        ('hasPressure', 'ex:HasValveShape', 'only when it has hasValve'),
        ('hasValve', 'ex:HighPressureShape',
         'only for the entities its SPARQL target selects')}
    assert all(r['inherited'] for r in rows if r.get('via')), 'edited on their shape'


def test_a_conditional_shape_applies_before_any_data_reaches_it(tmp_path):
    """A fresh package: a shape on "whatever has hasTemperature" belongs on
    Machine's page because the knowledge gives hasTemperature to Machine --
    not only once an entity in the data happens to have one."""
    from semforge.cooked.constrain import add_attribute_constraint
    from semforge.cooked.shapes import add_shape
    from semforge.cooked.typepage import build_type_page
    from semforge.package import load
    from semforge.package.scaffold import create_package

    root = str(tmp_path / 'm')
    create_package(root)
    made = add_shape(load(root), 'HotShape', 'subjectsOf', 'hasTemperature')
    add_attribute_constraint(load(root), made['iri'], 'hasState', required=True)
    package = load(root)
    machine = next(str(c) for c in package.knowledge.subjects() if str(c).endswith('/Machine'))
    # No data anywhere: neither the model nor a case has a Machine.
    import shutil
    shutil.rmtree(f'{root}/model/examples')
    with open(f'{root}/model/main.jsonld', 'w') as handle:
        handle.write('[]')
    page = build_type_page(load(root), machine)
    from semforge.cooked.shapes import base_name

    also = {base_name(a['shapeName'].split(':')[-1]): a for a in page['alsoCheckedBy']}
    assert also['HotShape']['condition'] == 'only when it has hasTemperature'
    assert also['HotShape']['reached'] == 0
    state = next(r for r in page['attributes'] if r['label'] == 'hasState')
    assert any(c.get('via', '').endswith(made['iri'].rsplit('/', 1)[-1])
               for c in state['contributions'])
    # Conditional: listed, not merged -- the row still says what always holds.
    assert state['presence'] == 'required · one'


def test_a_kms_rule_shape_page_has_the_review_s_evidence(corpus):
    """StateOnFilterShape: reached in 4 cases, never fired."""
    from semforge.cooked.shapepage import build_shape_page

    page = build_shape_page(corpus, 'iffBaseShacl:StateOnFilterShape')
    assert page['rule'] and page['rules'][0]['tested'] == 'never fired'
    assert page['summary']['cases'] == 4 and page['summary']['neverFired']
    assert [t['label'] for t in page['types']] == ['Filter']


# --- the Types view ----------------------------------------------------------------

def _walk(nodes, depth=0):
    for node in nodes:
        yield depth, node
        yield from _walk(node.get('children', []), depth + 1)


def test_types_is_the_hierarchy_with_own_attributes_and_rules(corpus):
    from semforge.cooked.tree import build_tree
    from semforge.editor.server import _serialise, _type_hierarchy
    from semforge.editor.slim import slim_constraints

    payload = {'types': _type_hierarchy(corpus)}
    roots = slim_constraints([_serialise(n) for n in build_tree(corpus)], payload)
    assert [r['label'] for r in roots] == ['Entity']
    rows = {n['label']: (depth, n) for depth, n in _walk(roots)}
    assert rows['Filter'][0] == 2 and rows['Plasmacutter'][0] == 3
    filter_kids = [c['label'] for c in rows['Filter'][1]['children']]
    assert filter_kids == ['hasStrength', 'hasCartridge', 'Rules']
    rules = rows['Filter'][1]['children'][-1]['children']
    assert {r['label'] for r in rules} == {'FilterStrengthShape', 'StateOnFilterShape'}
    assert all(r['kind'] == 'rule' and r['shape'] for r in rules)
    assert not [n for _, n in _walk(roots) if n['kind'] == 'shape'], \
        'shapes are not a level of the Types view'
