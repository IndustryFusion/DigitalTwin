"""Counts other than 0 and 1: "exactly 3", "at least 2", "2 to 4".

sh:minCount / sh:maxCount on the attribute count its instances -- distinct
datasetIds. The Presence cell sets them; Required no longer resets a higher
minimum to 1; and a minimum above the maximum, which no data can ever
satisfy, is refused by every cooked write and reported where a hand edit
left it.
"""

import json
import os
import shutil
import subprocess

import pytest
from rdflib import Literal
from rdflib.namespace import SH

from semforge.cooked import apply_edit
from semforge.cooked.constrain import add_attribute_constraint, edit_attribute
from semforge.cooked.knowledge import add_attribute_term
from semforge.cooked.tree import add_constraint
from semforge.cooked.typepage import build_type_page
from semforge.errors import PackageError
from semforge.package import load
from semforge.package.scaffold import create_package
from semforge.sanity import sanity

PRESSURE = 'myModelEntities:hasPressure'


@pytest.fixture
def machine(tmp_path):
    root = str(tmp_path / 'my-model')
    create_package(root)
    package = load(root)
    cls = next(c for c in package.knowledge.subjects() if str(c).endswith('/Machine'))
    add_attribute_term(package, 'hasPressure', 'Property', str(cls))
    package = load(root)
    shape = next(s for s in package.shapes.subjects() if str(s).endswith('/MachineShape'))
    add_attribute_constraint(package, str(shape), 'hasPressure', required=True,
                             datatype='xsd:double')
    return root, str(cls), str(shape)


def _presence(root, cls):
    page = build_type_page(load(root), cls)
    return next(a for a in page['attributes'] if a['label'] == 'hasPressure')['presence']


def _counts(root):
    package = load(root)
    node = next(n for n in package.shapes.subjects(SH.path, None)
                if str(package.shapes.value(n, SH.path)).endswith('hasPressure'))
    return package.shapes.value(node, SH.minCount), package.shapes.value(node, SH.maxCount)


@pytest.mark.parametrize('counts, said, written', [
    ({'min': 3, 'max': 3}, 'exactly 3', (Literal(3), Literal(3))),
    ({'min': 2, 'max': None}, 'at least 2', (Literal(2), None)),
    ({'min': 2, 'max': 4}, '2 to 4', (Literal(2), Literal(4))),
    ({'min': 0, 'max': None}, 'any number', (Literal(0), None)),
    ({'min': 0, 'max': 5}, 'at most 5', (Literal(0), Literal(5)))])
def test_counts_are_written_and_said(machine, counts, said, written):
    root, cls, shape = machine
    edit_attribute(load(root), shape, [PRESSURE], counts=counts)
    assert _counts(root) == written
    assert _presence(root, cls) == said


def test_required_keeps_a_higher_minimum(machine):
    root, cls, shape = machine
    edit_attribute(load(root), shape, [PRESSURE], counts={'min': 3, 'max': 3})
    edit_attribute(load(root), shape, [PRESSURE], presence='required')
    assert _presence(root, cls) == 'exactly 3'
    edit_attribute(load(root), shape, [PRESSURE], presence='optional')
    edit_attribute(load(root), shape, [PRESSURE], presence='required')
    assert _counts(root)[0] == Literal(1), 'from 0, required is 1'


def test_one_step_from_one_to_five_to_eight(machine):
    root, cls, shape = machine
    edit_attribute(load(root), shape, [PRESSURE], counts={'min': 5, 'max': 8})
    assert _presence(root, cls) == '5 to 8'


@pytest.mark.parametrize('write', [
    lambda root, shape: edit_attribute(load(root), shape, [PRESSURE],
                                       counts={'min': 5, 'max': 3}),
    lambda root, shape: apply_edit(load(root), shape, [PRESSURE], 'sh:minCount', '5'),
    lambda root, shape: add_constraint(load(root), shape, [PRESSURE], 'sh:maxCount', '0',
                                       layer='attribute')])
def test_a_minimum_above_the_maximum_is_refused_everywhere(machine, write):
    root, _, shape = machine
    shapes = load(root).sources['shapes']
    before = open(shapes).read()
    with pytest.raises(PackageError, match='no data can satisfy'):
        write(root, shape)
    assert open(shapes).read() == before


def test_a_count_is_a_whole_number(machine):
    root, _, shape = machine
    with pytest.raises(PackageError, match='whole number'):
        edit_attribute(load(root), shape, [PRESSURE], counts={'min': 'two', 'max': None})
    with pytest.raises(PackageError, match='0 or more'):
        edit_attribute(load(root), shape, [PRESSURE], counts={'min': -1, 'max': None})


def _break_by_hand(root):
    shapes = load(root).sources['shapes']
    text = open(shapes).read()
    at = text.index(f'sh:path {PRESSURE} ;')
    open(shapes, 'w').write(text[:at] + text[at:].replace('sh:minCount 1', 'sh:minCount 4', 1))
    return shapes


def test_a_hand_edit_is_reported_on_the_path(machine):
    root, _, _ = machine
    shapes = _break_by_hand(root)
    [finding] = [f for f in sanity(load(root)) if f.code == 'count-impossible']
    assert finding.file == os.path.abspath(shapes) and finding.severity == 'error'
    assert f'sh:path {PRESSURE}' in open(shapes).read().splitlines()[finding.line - 1]
    assert 'at least 4 and at most 1' in finding.message


def test_an_impossible_count_already_there_does_not_block_other_edits(machine):
    root, cls, shape = machine
    _break_by_hand(root)
    edit_attribute(load(root), shape, ['myModelEntities:hasTemperature'], presence='optional')
    edit_attribute(load(root), shape, [PRESSURE], counts={'min': 1, 'max': 2})
    assert _presence(root, cls) == '1 to 2'
    assert not [f for f in sanity(load(root)) if f.code == 'count-impossible']


# --- the Presence cell -----------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')


def _click(tmp_path, page, **scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(dict({
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': page['_cls'],
                         'label': page['label'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'presence', 'row': page['row']}],
        'replies': {'semforge/typePage': page, 'semforge/editAttribute': {'ok': True}}},
        **scenario)))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture
def page(machine):
    root, cls, shape = machine
    edit_attribute(load(root), shape, [PRESSURE], counts={'min': 2, 'max': 3})
    built = dict(build_type_page(load(root), cls), ok=True)
    built['_cls'] = cls
    built['row'] = next(i for i, a in enumerate(built['attributes'])
                        if a['label'] == 'hasPressure')
    return built


def _sent(seen):
    return [r['params'] for r in seen['requests'] if r['method'] == 'semforge/editAttribute']


def test_the_cell_offers_counts_and_says_what_it_is_now(tmp_path, page):
    seen = _click(tmp_path, page, picks=[])
    pick = seen['quickPicks'][0]['items']
    assert [i['label'] for i in pick] == ['Optional', 'Required', 'Exactly one', 'Exactly…',
                                          'At least…', 'Between…', 'Any number']
    assert 'keeps sh:minCount 2' in pick[1]['description']
    assert _sent(seen) == []


@pytest.mark.parametrize('picks, inputs, counts', [
    (['Exactly…'], ['4'], {'min': 4, 'max': 4}),
    (['At least…'], ['3'], {'min': 3, 'max': None}),
    (['Between…'], ['2', '5'], {'min': 2, 'max': 5}),
    (['Any number'], [], {'min': 0, 'max': None}),
    (['Exactly one'], [], {'min': 1, 'max': 1})])
def test_each_choice_sends_its_counts(tmp_path, page, picks, inputs, counts):
    seen = _click(tmp_path, page, picks=picks, inputs=inputs)
    [sent] = _sent(seen)
    assert sent['counts'] == counts and sent['path'] == [PRESSURE]


def test_between_offers_the_current_bounds(tmp_path, page):
    seen = _click(tmp_path, page, picks=['Between…'], inputs=['2', '3'])
    assert [i['value'] for i in seen['inputs']] == ['2', '3']


def test_cancelling_a_number_writes_nothing(tmp_path, page):
    seen = _click(tmp_path, page, picks=['Between…'], inputs=['2'])
    assert _sent(seen) == []


# --- the server, as pygls hands it the request ------------------------------------------

class _Silent:
    def text_document_publish_diagnostics(self, params):
        pass


def _as_pygls(value):
    """A custom method's params as pygls deserialises them: nested objects with
    attributes, and no .get -- the harness's plain dicts never showed that."""
    from types import SimpleNamespace

    if isinstance(value, dict):
        return SimpleNamespace(**{k: _as_pygls(v) for k, v in value.items()})
    return value


@pytest.mark.parametrize('change, said', [
    ({'counts': {'min': 2, 'max': 4}}, '2 to 4'),
    ({'counts': {'min': 3, 'max': None}}, 'at least 3')])
def test_edit_attribute_reads_nested_params_as_pygls_sends_them(machine, change, said):
    from semforge.editor.server import _path_to_uri as path_to_uri, edit_attribute_feature

    root, cls, shape = machine
    params = _as_pygls(dict({'uri': path_to_uri(load(root).sources['shapes']),
                             'shape': shape, 'path': [PRESSURE]}, **change))
    answer = edit_attribute_feature(_Silent(), params)
    assert answer['ok'], answer
    assert _presence(root, cls) == said


def test_a_value_edit_reads_nested_params_too(machine):
    from semforge.editor.server import _path_to_uri as path_to_uri, edit_attribute_feature

    root, cls, shape = machine
    params = _as_pygls({'uri': path_to_uri(load(root).sources['shapes']), 'shape': shape,
                        'path': [PRESSURE], 'value': {'datatype': 'xsd:integer'}})
    answer = edit_attribute_feature(_Silent(), params)
    assert answer['ok'], answer
    from rdflib.namespace import XSD

    assert (None, SH.datatype, XSD.integer) in load(root).shapes
