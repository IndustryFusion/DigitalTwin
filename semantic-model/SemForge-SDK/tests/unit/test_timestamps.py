"""Timestamps (observedAt): only the latest observation of a datasetId is
validated, as on the platform.

The attribute view keeps, per (entity, attribute, datasetId), the greatest
COALESCE(observedAt, ts) -- and the bridge stamps an instance without
observedAt with the time it arrives. So an unstamped instance counts as NOW;
timestamps are points in time, not text; instances tied on time are kept
together, so a duplicate still counts. Timestamps are never asked by
default; when one is wanted it is picked, and what would make the platform and
the tests disagree is reported.
"""

import json
import os
import shutil
import subprocess

import pytest
from rdflib import BNode, Graph, Literal, URIRef

from semforge.cooked.casepage import build_case_page
from semforge.cooked.constrain import edit_attribute
from semforge.cooked.examples import (add_attribute, add_observation, set_observed_at,
                                      sort_observations)
from semforge.errors import PackageError
from semforge.ngsild import timestamps
from semforge.ngsild.views import collapse_updates
from semforge.package import load
from semforge.package.scaffold import create_package
from semforge.sanity import sanity
from semforge.validate.orchestrator import validate_package

NGSILD = 'https://uri.etsi.org/ngsi-ld/'
TEMPERATURE = 'myModelEntities:hasTemperature'
MACHINE_ID = 'urn:myModel:machine:1'


# --- reading a timestamp ---------------------------------------------------------------

@pytest.mark.parametrize('text, written', [
    ('2024-02-28T13:52:35.000Z', '2024-02-28T13:52:35.000Z'),
    ('2024-02-28T13:52:35Z', '2024-02-28T13:52:35.000Z'),
    ('2024-02-28T14:52:35.5+01:00', '2024-02-28T13:52:35.500Z'),
    ('2024-02-28T13:52:35', None), ('2024-02-28', None), ('yesterday', None)])
def test_a_timestamp_is_read_as_a_point_in_time_and_written_one_way(text, written):
    assert timestamps.normalised(text) == written


# --- what validation sees --------------------------------------------------------------

def _graph(*instances):
    """One entity's hasX: each instance (value, observedAt or None, datasetId)."""
    graph = Graph()
    entity, attribute = URIRef('urn:e:1'), URIRef('urn:attr:hasX')
    for value, stamp, dataset in instances:
        node = BNode()
        graph.add((entity, attribute, node))
        graph.add((node, URIRef(NGSILD + 'hasValue'), Literal(value)))
        if stamp:
            graph.add((node, URIRef(NGSILD + 'observedAt'), Literal(stamp)))
        if dataset:
            graph.add((node, URIRef(NGSILD + 'datasetId'), URIRef(dataset)))
    return graph


def _values(graph):
    return sorted(int(v) for v in graph.objects(None, URIRef(NGSILD + 'hasValue')))


def test_the_latest_is_a_point_in_time_not_text():
    # 14:00+02:00 is 12:00 UTC: earlier than 13:00Z, though later as text.
    graph = _graph((1, '2024-02-28T14:00:00.000+02:00', None), (2, '2024-02-28T13:00:00.000Z', None))
    assert collapse_updates(graph) == 1 and _values(graph) == [2]


def test_an_unstamped_instance_counts_as_now_and_supersedes():
    graph = _graph((1, '2999-01-01T00:00:00.000Z', None), (2, None, None))
    collapse_updates(graph)
    assert _values(graph) == [2]


def test_ties_are_kept_so_a_duplicate_still_counts():
    same = '2024-02-28T13:00:00.000Z'
    assert collapse_updates(_graph((1, same, None), (2, same, None))) == 0
    assert collapse_updates(_graph((1, None, None), (2, None, None))) == 0


def test_datasetids_are_never_collapsed_across():
    graph = _graph((1, '2024-01-01T00:00:00.000Z', 'urn:d:a'),
                   (2, '2024-02-01T00:00:00.000Z', 'urn:d:b'))
    assert collapse_updates(graph) == 0


# --- a package: validation, the writes, the checks -------------------------------------

@pytest.fixture
def pkg(tmp_path):
    root = str(tmp_path / 'my-model')
    create_package(root)
    package = load(root)
    shape = next(s for s in package.shapes.subjects() if str(s).endswith('/MachineShape'))
    edit_attribute(package, str(shape), [TEMPERATURE], counts={'min': 1, 'max': 1})
    return root


def _model(root):
    return load(root).sources['model']


def _temperature(root):
    entity = next(e for e in json.load(open(_model(root))) if e.get('id') == MACHINE_ID)
    value = entity[TEMPERATURE]
    return value if isinstance(value, list) else [value]


def _set(root, instances):
    path = _model(root)
    document = json.load(open(path))
    next(e for e in document if e.get('id') == MACHINE_ID)[TEMPERATURE] = instances
    json.dump(document, open(path, 'w'), indent=2)


def _violations(root):
    return sorted((r.attribute, r.component) for r in
                  validate_package(load(root), strict=False).violations)


def test_only_the_latest_observation_is_validated(pkg):
    first = _temperature(pkg)[0]
    _set(pkg, [dict(first, value=500.0, observedAt='2025-01-01T00:00:00.000Z'), first])
    assert _violations(pkg) == [], 'the old, out-of-range value is filtered out'
    _set(pkg, [first, dict(first, value=500.0, observedAt='2027-01-01T00:00:00.000Z')])
    assert ('hasTemperature', 'MaxInclusiveConstraintComponent') in _violations(pkg)
    assert ('hasTemperature', 'MaxCountConstraintComponent') not in _violations(pkg)


def test_an_unstamped_one_is_validated_over_the_stamped(pkg):
    first = _temperature(pkg)[0]
    bare = {k: v for k, v in first.items() if k != 'observedAt'}
    _set(pkg, [first, dict(bare, value=500.0)])
    assert _violations(pkg) == [('hasTemperature', 'MaxInclusiveConstraintComponent')]


def test_a_second_observation_needs_a_time_none_has(pkg):
    first = _temperature(pkg)[0]
    with pytest.raises(PackageError, match='a timestamp none of its instances has'):
        add_attribute(load(pkg), MACHINE_ID, TEMPERATURE, value=22.0)
    with pytest.raises(PackageError, match='the same update written twice'):
        add_attribute(load(pkg), MACHINE_ID, TEMPERATURE, value=22.0,
                      observedAt=first['observedAt'])
    add_attribute(load(pkg), MACHINE_ID, TEMPERATURE, value=22.0,
                  observedAt='2026-01-02T01:00:00+01:00')
    assert _temperature(pkg)[-1]['observedAt'] == '2026-01-02T00:00:00.000Z'
    assert _violations(pkg) == []


def test_add_observation_checks_its_time(pkg):
    with pytest.raises(PackageError, match='not a timestamp'):
        add_observation(load(pkg), MACHINE_ID, [TEMPERATURE], value='1', observed_at='today')
    add_observation(load(pkg), MACHINE_ID, [TEMPERATURE], value='1',
                    observed_at='2026-01-03T00:00:00Z')
    assert _temperature(pkg)[-1]['observedAt'] == '2026-01-03T00:00:00.000Z'


def test_set_and_remove_one_instance_s_time(pkg):
    set_observed_at(load(pkg), MACHINE_ID, [TEMPERATURE], 0, '2026-02-01T10:00:00+02:00')
    assert _temperature(pkg)[0]['observedAt'] == '2026-02-01T08:00:00.000Z'
    set_observed_at(load(pkg), MACHINE_ID, [TEMPERATURE], 0, '')
    assert 'observedAt' not in _temperature(pkg)[0]


def test_sorting_puts_the_latest_last(pkg):
    first = _temperature(pkg)[0]
    _set(pkg, [dict(first, value=2.0, observedAt='2026-03-01T00:00:00.000Z'), first])
    sort_observations(load(pkg), MACHINE_ID, [TEMPERATURE])
    assert [i['value'] for i in _temperature(pkg)] == [first['value'], 2.0]


def _found(root, code):
    return [f for f in sanity(load(root)) if f.code == code]


def test_the_four_checks(pkg):
    first = _temperature(pkg)[0]
    bare = {k: v for k, v in first.items() if k != 'observedAt'}
    _set(pkg, [dict(first, observedAt='2026-03-01T00:00:00+00:00'), dict(first, observedAt='soon'),
               first, bare])
    assert {f.code for f in sanity(load(pkg)) if f.code.startswith('observed-at')} == {
        'observed-at-format', 'observed-at-invalid', 'observed-at-mixed', 'observed-at-order'}
    [format_] = _found(pkg, 'observed-at-format')
    assert format_.fix['observedAt'] == '2026-03-01T00:00:00.000Z' and format_.fix['index'] == 0
    assert _found(pkg, 'observed-at-mixed')[0].fix['index'] == 3


def test_a_clean_series_reports_nothing(pkg):
    first = _temperature(pkg)[0]
    _set(pkg, [first, dict(first, value=2.0, observedAt='2026-03-01T00:00:00.000Z')])
    assert not [f for f in sanity(load(pkg)) if f.code.startswith('observed-at')]


def test_the_kms_corpus_reports_nothing(corpus_path):
    assert not [f for f in sanity(load(corpus_path)) if f.code.startswith('observed-at')]


def test_the_quick_fixes():
    from lsprotocol import types

    from semforge.editor.server import _fixes_for

    def fixes(code, **data):
        diagnostic = types.Diagnostic(
            range=types.Range(types.Position(0, 0), types.Position(0, 1)), message='',
            data=dict(data, code=code, entity=MACHINE_ID, attributePath=[TEMPERATURE], file='f'))
        return [(a.title, a.command.command, a.command.arguments[0])
                for a in _fixes_for(diagnostic, 'file:///pkg/shacl.ttl')]

    [(title, command, argument)] = fixes('observed-at-format', index=0,
                                         observedAt='2026-03-01T00:00:00.000Z')
    assert (title, command) == ('Write it as 2026-03-01T00:00:00.000Z', 'semforge.setObservedAt')
    assert argument['observedAt'] == '2026-03-01T00:00:00.000Z'
    [(title, _, argument)] = fixes('observed-at-mixed', index=3)
    assert title == 'Set its time…' and 'observedAt' not in argument
    [(title, command, _)] = fixes('observed-at-order', datasetId='')
    assert (title, command) == ('Sort them by time', 'semforge.sortObservations')


# --- the case page ---------------------------------------------------------------------

def test_case_rows_say_their_time_and_which_one_is_read(pkg, tmp_path):
    from semforge.expect.attributecase import new_attribute_test
    from semforge.cooked.tree import build_tree

    machine = next(c for c in load(pkg).knowledge.subjects() if str(c).endswith('/Machine'))
    node = next(a for r in build_tree(load(pkg)) if r.target_class == str(machine)
                for s in r.children for a in s.children
                if a.kind == 'attribute' and a.label.endswith('hasTemperature'))
    made = new_attribute_test(load(pkg), str(machine), list(node.path_chain), 'valid', 'series')
    add_observation(load(pkg), made['resource'], [TEMPERATURE], value='30.0',
                    observed_at='2026-06-01T00:00:00.000Z', file=made['file'])
    page = build_case_page(load(pkg), made['case'])
    card = next(c for f in page['files'] for c in f['cards'] if c['id'] == made['resource'])
    rows = [r for r in card['attributes'] if r['name'] == 'hasTemperature']
    assert [(r['observedAt'], r['superseded']) for r in rows] == [
        ('2026-01-01T00:00:00.000Z', True), ('2026-06-01T00:00:00.000Z', False)]
    assert rows[0]['stamp'] == {'attributePath': [TEMPERATURE], 'index': 0}
    assert rows[0]['latestAt'] == '2026-06-01T00:00:00.000Z'


def test_the_page_shows_the_latest_and_folds_the_earlier_under_it(pkg, tmp_path):
    """Only the latest observation is shown; "+N earlier" folds the rest out --
    underneath it, not struck through beside it."""
    from semforge.cooked.tree import build_tree
    from semforge.expect.attributecase import new_attribute_test

    machine = next(c for c in load(pkg).knowledge.subjects() if str(c).endswith('/Machine'))
    node = next(a for r in build_tree(load(pkg)) if r.target_class == str(machine)
                for s in r.children for a in s.children
                if a.kind == 'attribute' and a.label.endswith('hasTemperature'))
    made = new_attribute_test(load(pkg), str(machine), list(node.path_chain), 'valid', 'fold')
    for stamp, value in (('2026-06-01T00:00:00.000Z', '30.0'), ('2026-07-01T00:00:00.000Z', '31.0')):
        add_observation(load(pkg), made['resource'], [TEMPERATURE], value=value,
                        observed_at=stamp, file=made['file'])
    page = dict(build_case_page(load(pkg), made['case']), ok=True)
    html = _drive(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'file': page['file'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/casePage': page}})['webviews'][0]['html'][-1]
    shown, _, folded = html.partition('class="older"')
    assert '31.0' in shown and '>+2 earlier</a>' in shown
    assert '30.0' not in shown, 'an earlier observation is not shown until asked'
    assert '30.0' in folded and 'line-through' not in html


DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')


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


def test_timestamp_on_a_tree_row_picks_and_writes(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.setObservedAt',
        'node': {'raw': {'kind': 'instance', 'entity': MACHINE_ID, 'path': [TEMPERATURE, 2],
                         'file': 'case.jsonld', 'label': '21.5'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['$(calendar) A time of your own…'], 'inputs': ['2024-02-28T14:52:35+01:00'],
        'replies': {'semforge/setObservedAt': {'ok': True}}})
    assert _asked(seen, 'semforge/setObservedAt') == [{
        'uri': 'file:///pkg/shacl.ttl', 'observedAt': '2024-02-28T13:52:35.000Z',
        'entity': MACHINE_ID, 'file': 'case.jsonld', 'attributePath': [TEMPERATURE], 'index': 2}]


def test_a_quick_fix_with_its_time_asks_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.setObservedAt',
        'node': {'packageUri': 'file:///pkg/shacl.ttl', 'entity': MACHINE_ID,
                 'attributePath': [TEMPERATURE], 'index': 0, 'file': 'case.jsonld',
                 'observedAt': '2026-03-01T00:00:00.000Z'},
        'replies': {'semforge/setObservedAt': {'ok': True}}})
    assert not seen['quickPicks'] and not seen['inputs']
    assert _asked(seen, 'semforge/setObservedAt')[0]['observedAt'] == '2026-03-01T00:00:00.000Z'


def test_the_case_page_picker_writes_through_the_command(tmp_path, pkg):
    from semforge.cooked.tree import build_tree
    from semforge.expect.attributecase import new_attribute_test

    machine = next(c for c in load(pkg).knowledge.subjects() if str(c).endswith('/Machine'))
    node = next(a for r in build_tree(load(pkg)) if r.target_class == str(machine)
                for s in r.children for a in s.children
                if a.kind == 'attribute' and a.label.endswith('hasTemperature'))
    made = new_attribute_test(load(pkg), str(machine), list(node.path_chain), 'valid', 'one')
    page = dict(build_case_page(load(pkg), made['case']), ok=True)
    card = next(i for i, c in enumerate(page['files'][0]['cards']) if c['id'] == made['resource'])
    row = next(i for i, r in enumerate(page['files'][0]['cards'][card]['attributes'])
               if r['name'] == 'hasTemperature')
    seen = _drive(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'file': page['file'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'stamp', 'at': f'0.{card}.{row}',
                             'value': '2026-05-01T12:00:00.000Z'}],
        'replies': {'semforge/casePage': page, 'semforge/setObservedAt': {'ok': True}}})
    html = seen['webviews'][0]['html'][0]
    assert f'data-stamp="0.{card}.{row}"' in html and 'datetime-local' in html
    [sent] = [e['args'][0] for e in seen['executed'] if e['command'] == 'semforge.setObservedAt']
    assert (sent['entity'], sent['attributePath'], sent['index'], sent['observedAt']) == (
        made['resource'], [TEMPERATURE], 0, '2026-05-01T12:00:00.000Z')
