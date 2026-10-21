"""Arrays (datasetId), timestamps (observedAt) and units (unitCode) together:
the cases each feature's own tests leave out, and the ones where they meet.

An NGSI-LD attribute is a dictionary of instances keyed by datasetId; each
instance is a series of observations of which only the latest is validated
(an unstamped one counting as now); each instance says its unit. So a count
counts datasetIds, not observations; a wrong unit on a superseded observation
does not fire, on the latest it does; and every one of these holds one level
down, on a sub-attribute, too.
"""

import json
import os
import shutil
import subprocess

import pytest
from rdflib import BNode, Graph, Literal, URIRef

from semforge.cooked.casepage import build_case_page
from semforge.cooked.constrain import edit_attribute
from semforge.cooked.examples import _current_index, set_observed_at
from semforge.cooked.typepage import build_type_page
from semforge.cooked.units import set_unit_code, set_units
from semforge.errors import PackageError
from semforge.ngsild.views import collapse_updates
from semforge.package import load
from semforge.package.scaffold import create_package
from semforge.sanity import sanity
from semforge.validate.orchestrator import validate_package

NGSILD = 'https://uri.etsi.org/ngsi-ld/'
TEMPERATURE = 'myModelEntities:hasTemperature'
MACHINE_ID = 'urn:myModel:machine:1'
OLD, NEW = '2025-01-01T00:00:00.000Z', '2026-06-01T00:00:00.000Z'


@pytest.fixture
def pkg(tmp_path):
    from semforge.package.prefixes import add_namespace

    root = str(tmp_path / 'my-model')
    create_package(root)
    add_namespace(root, 'sensor', 'urn:sensor:')
    return root


def _shape(root):
    return str(next(s for s in load(root).shapes.subjects() if str(s).endswith('/MachineShape')))


def _machine(root):
    return str(next(c for c in load(root).knowledge.subjects() if str(c).endswith('/Machine')))


def _first(root):
    entity = next(e for e in json.load(open(load(root).sources['model'])) if e.get('id') == MACHINE_ID)
    value = entity[TEMPERATURE]
    return dict(value[0] if isinstance(value, list) else value)


def _set(root, instances):
    path = load(root).sources['model']
    document = json.load(open(path))
    next(e for e in document if e.get('id') == MACHINE_ID)[TEMPERATURE] = instances
    json.dump(document, open(path, 'w'), indent=2)


def _violations(root):
    return sorted((r.attribute, r.component) for r in
                  validate_package(load(root), strict=False).violations)


# --- arrays x timestamps ---------------------------------------------------------------

@pytest.mark.parametrize('most, fires', [(1, True), (2, False)])
def test_a_count_counts_datasetids_not_observations(pkg, most, fires):
    """Two datasetIds, each a series of two observations: two instances."""
    edit_attribute(load(pkg), _shape(pkg), [TEMPERATURE], counts={'min': 1, 'max': most})
    first = _first(pkg)
    _set(pkg, [dict(first, observedAt=OLD), dict(first, observedAt=NEW),
               dict(first, observedAt=OLD, datasetId='urn:sensor:b'),
               dict(first, observedAt=NEW, datasetId='urn:sensor:b')])
    found = ('hasTemperature', 'MaxCountConstraintComponent') in _violations(pkg)
    assert found is fires


def test_a_stamp_is_unique_per_datasetid_not_per_attribute(pkg):
    first = _first(pkg)
    _set(pkg, [dict(first, observedAt=OLD), dict(first, observedAt=NEW),
               dict(first, observedAt=OLD, datasetId='urn:sensor:b')])
    with pytest.raises(PackageError, match='the same update written twice'):
        set_observed_at(load(pkg), MACHINE_ID, [TEMPERATURE], 1, OLD)
    set_observed_at(load(pkg), MACHINE_ID, [TEMPERATURE], 2, NEW)   # another datasetId: fine


def test_an_unparseable_time_counts_as_now_in_validation():
    graph = Graph()
    entity, attribute = URIRef('urn:e:1'), URIRef('urn:attr:hasX')
    for value, stamp in ((1, '2999-01-01T00:00:00.000Z'), (2, 'soon')):
        node = BNode()
        graph.add((entity, attribute, node))
        graph.add((node, URIRef(NGSILD + 'hasValue'), Literal(value)))
        graph.add((node, URIRef(NGSILD + 'observedAt'), Literal(stamp)))
    collapse_updates(graph)
    assert [int(v) for v in graph.objects(None, URIRef(NGSILD + 'hasValue'))] == [2]


def test_the_tree_marks_the_instance_validation_reads():
    stamped = {'value': 1, 'observedAt': NEW}
    assert _current_index([(0, {'value': 0}), (1, stamped)]) == 0, 'unstamped is now'
    assert _current_index([(0, stamped), (1, dict(stamped, value=2))]) == 1, 'a tie: the last'
    assert _current_index([(0, dict(stamped, observedAt='2026-06-01T03:00:00+02:00')),
                           (1, stamped)]) == 0, 'a point in time, not text'


# --- one level down: a sub-attribute ----------------------------------------------------

def test_a_sub_attribute_s_series_collapses_on_its_own():
    graph = Graph()
    entity, attribute, sub = URIRef('urn:e:1'), URIRef('urn:attr:hasX'), URIRef('urn:attr:hasY')
    outer = BNode()
    graph.add((entity, attribute, outer))
    graph.add((outer, URIRef(NGSILD + 'hasValue'), Literal(0)))
    for value, stamp in ((1, OLD), (2, NEW)):
        node = BNode()
        graph.add((outer, sub, node))
        graph.add((node, URIRef(NGSILD + 'hasValue'), Literal(value)))
        graph.add((node, URIRef(NGSILD + 'observedAt'), Literal(stamp)))
    assert collapse_updates(graph) == 1
    inner = [int(graph.value(n, URIRef(NGSILD + 'hasValue'))) for n in graph.objects(outer, sub)]
    assert inner == [2]


def test_a_sub_attribute_s_datasetid_and_time_are_checked_where_written(pkg):
    first = _first(pkg)
    first['myModelEntities:hasState'] = [
        {'type': 'Property', 'value': 'x', 'datasetId': 'left', 'observedAt': NEW},
        {'type': 'Property', 'value': 'y', 'observedAt': '2026-06-01T03:00:00+02:00'}]
    _set(pkg, first)
    found = {f.code: f for f in sanity(load(pkg))
             if f.code in ('dataset-not-iri', 'observed-at-format')}
    assert set(found) == {'dataset-not-iri', 'observed-at-format'}
    assert found['dataset-not-iri'].fix['attributePath'] == [TEMPERATURE, 0,
                                                             'myModelEntities:hasState']


# --- units x timestamps x arrays --------------------------------------------------------

def test_a_wrong_unit_on_a_superseded_observation_does_not_fire(pkg):
    set_units(load(pkg), _shape(pkg), [TEMPERATURE], ['CEL'], required=True)
    first = _first(pkg)
    old, new = dict(first, observedAt=OLD), dict(first, observedAt=NEW)
    _set(pkg, [dict(old, unitCode='FAH'), dict(new, unitCode='CEL')])
    assert _violations(pkg) == []
    _set(pkg, [dict(old, unitCode='CEL'), dict(new, unitCode='FAH')])
    assert _violations(pkg) == [('hasTemperature.unitCode', 'InConstraintComponent')]


def test_each_datasetid_says_its_own_unit(pkg):
    set_units(load(pkg), _shape(pkg), [TEMPERATURE], ['CEL'])
    first = _first(pkg)
    _set(pkg, [dict(first, unitCode='CEL'), dict(first, unitCode='FAH', datasetId='urn:sensor:b')])
    assert ('hasTemperature.unitCode', 'InConstraintComponent') in _violations(pkg)
    set_unit_code(load(pkg), MACHINE_ID, [TEMPERATURE], 'urn:sensor:b', 'CEL')
    assert ('hasTemperature.unitCode', 'InConstraintComponent') not in _violations(pkg)


def test_a_relationship_has_no_unit(pkg):
    first = _first(pkg)
    _set(pkg, {'type': 'Relationship', 'object': 'urn:x:1', 'observedAt': first['observedAt']})
    with pytest.raises(PackageError, match='Relationship'):
        set_unit_code(load(pkg), MACHINE_ID, [TEMPERATURE], '', 'CEL')


def test_the_type_page_row_carries_its_unit_s_violations(pkg):
    set_units(load(pkg), _shape(pkg), [TEMPERATURE], ['CEL'], required=True)
    row = next(a for a in build_type_page(load(pkg), _machine(pkg))['attributes']
               if a['label'] == 'hasTemperature')
    assert row['violations'], 'the main-model entity says no unit'


def _case(pkg):
    from semforge.cooked.tree import build_tree
    from semforge.expect.attributecase import new_attribute_test

    node = next(a for r in build_tree(load(pkg)) if r.target_class == _machine(pkg)
                for s in r.children for a in s.children
                if a.kind == 'attribute' and a.label.endswith('hasTemperature'))
    return new_attribute_test(load(pkg), _machine(pkg), list(node.path_chain), 'valid', 'units')


def test_the_case_page_says_the_unit_by_its_symbol(pkg):
    set_units(load(pkg), _shape(pkg), [TEMPERATURE], ['CEL'])
    made = _case(pkg)
    page = build_case_page(load(pkg), made['case'])
    row = next(r for f in page['files'] for c in f['cards'] if c['id'] == made['resource']
               for r in c['attributes'] if r['name'] == 'hasTemperature')
    assert (row['unitCode'], row['unitText']) == ('CEL', '°C')


# --- the dialogs -----------------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
UNITS = {'ok': True, 'quantities': ['Temperature'], 'allowed': [], 'required': False,
         'units': [{'code': 'CEL', 'name': 'degree Celsius', 'symbol': '°C',
                    'quantity': 'Temperature', 'quantityLabel': 'temperature',
                    'builtin': True, 'iri': '', 'term': ''}]}
ATTRIBUTES = {'attributes': [{'term': 'e:hasTemperature', 'kind': 'Property',
                              'constrained': True, 'domains': ['e:Machine'], 'comment': ''}]}


def _drive(tmp_path, scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _asked(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


def _entity(children):
    return {'raw': {'kind': 'entity', 'entity': MACHINE_ID, 'entityType': 'e:Machine',
                    'file': 'case.jsonld', 'label': MACHINE_ID, 'children': children},
            'packageUri': 'file:///pkg/shacl.ttl'}


def test_add_attribute_on_an_existing_datasetid_asks_its_time(tmp_path):
    present = {'kind': 'attribute', 'attributePath': ['e:hasTemperature'],
               'datasets': ['@none', 'urn:sensor:b']}
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': _entity([present]),
        'picks': ['e:hasTemperature', 'urn:sensor:b', '$(calendar) A time of your own…'],
        'inputs': ['2026-06-01T02:00:00+02:00', '21.5'],
        'replies': {'semforge/attributes': ATTRIBUTES, 'semforge/valueChoices': {'choices': []},
                    'semforge/units': UNITS, 'semforge/vocabularyNamespaces': {'namespaces': []},
                    'semforge/addAttribute': {'ok': True, 'kind': 'Property'}}})
    [sent] = _asked(seen, 'semforge/addAttribute')
    assert (sent['datasetId'], sent['observedAt'], sent['unitCode']) == (
        'urn:sensor:b', '2026-06-01T00:00:00.000Z', None), 'no units named: none asked'


@pytest.mark.parametrize('picks, inputs, stamp', [
    (['$(calendar) A time of your own…'], ['22.0', '2026-06-01T02:00:00+02:00'],
     '2026-06-01T00:00:00.000Z'),
    ([], ['22.0'], None)])
def test_add_observation_picks_its_time(tmp_path, picks, inputs, stamp):
    seen = _drive(tmp_path, {
        'command': 'semforge.addObservation',
        'node': {'raw': {'kind': 'dataset', 'entity': MACHINE_ID, 'label': 'hasTemperature',
                         'attributePath': [TEMPERATURE], 'datasetId': '@none', 'value': '21.5',
                         'file': 'case.jsonld'}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': picks, 'inputs': inputs,
        'replies': {'semforge/addObservation': {'ok': True, 'count': 2}}})
    sent = _asked(seen, 'semforge/addObservation')
    if stamp is None:
        assert sent == [], 'a cancelled time writes nothing'
    else:
        assert sent[0]['observedAt'] == stamp and sent[0]['value'] == '22.0'
    labels = [i['label'] for i in seen['quickPicks'][0]['items']] if seen['quickPicks'] else []
    assert '$(circle-slash) No timestamp' not in labels, 'an observation needs its time'


def test_unit_with_nothing_ticked_removes_the_constraint(tmp_path, pkg):
    page = dict(build_type_page(load(pkg), _machine(pkg)), ok=True)
    row = next(i for i, a in enumerate(page['attributes']) if a['label'] == 'hasTemperature')
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': _machine(pkg), 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'menu', 'row': row}],
        'picks': ['$(symbol-ruler) Unit…', []],
        'replies': {'semforge/typePage': page, 'semforge/units': dict(UNITS, allowed=['CEL']),
                    'semforge/setUnits': {'ok': True}}})
    [sent] = _asked(seen, 'semforge/setUnits')
    assert (sent['codes'], sent['required']) == ([], False)


def test_find_unit_searches_and_hands_the_code_over(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.findUnit', 'node': {'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['CEL'], 'replies': {'semforge/units': UNITS}})
    pick = seen['quickPicks'][0]
    assert 'Search by code, name or quantity' in pick['placeHolder']
    assert [i['description'] for i in pick['items'] if i['label'] == 'CEL'] == [
        'degree Celsius · °C']
    assert 'SemForge: CEL copied' in seen['messages'], seen['messages']


def test_the_timestamp_check_of_the_dialog():
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    script = ("const Module = require('module'); const load = Module._load;"
              "Module._load = function (r, ...a) { return r === 'vscode' ? {} : load.call(this, r, ...a); };"
              f"const t = require({json.dumps(os.path.join(SRC, 'timestamps.js'))});"
              "console.log(JSON.stringify(['2024-02-28T13:52:35.000Z', '2024-02-28T14:52:35+01:00',"
              "'2024-02-28T13:52', '2024-02-28T13:52:35', 'today'].map((v) => !t.problem(v))));")
    out = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=60)
    assert json.loads(out.stdout) == [True, True, False, False, False], out.stderr
