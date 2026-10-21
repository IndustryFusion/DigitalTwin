"""Add attribute on an entity that already has it: another instance.

An attribute is (entity, name, datasetId), so adding one the entity already
carries is not a mistake -- it is another instance, and the question is only
under which datasetId. The dialog asks for it every time (empty: the default
instance), and only a datasetId the attribute already has is refused.
"""

import json
import os
import shutil
import subprocess

import pytest

from semforge.cooked.examples import add_attribute
from semforge.errors import PackageError
from semforge.package import load

STRENGTH = 'iffBaseEntities:hasStrength'


@pytest.fixture
def kms(tmp_path, corpus_path):
    from semforge.package.prefixes import add_namespace

    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    add_namespace(str(target), 'sensor', 'urn:sensor:')
    return target


def _strength(kms):
    document = json.load(open(kms / 'model-instance.jsonld'))
    entity = next(e for e in document if e.get('id') == 'urn:filter:1')
    value = entity[STRENGTH]
    return value if isinstance(value, list) else [value]


def test_another_datasetid_adds_an_instance(kms):
    before = _strength(kms)
    path, kind = add_attribute(load(str(kms)), 'urn:filter:1', STRENGTH, value=0.7,
                               datasetId='urn:sensor:second')
    after = _strength(kms)
    assert after[:len(before)] == before, 'the existing instances stay as they were'
    assert after[-1] == {'type': kind, 'value': 0.7, 'datasetId': 'urn:sensor:second'}


def test_the_kind_is_the_one_already_written(kms):
    _, kind = add_attribute(load(str(kms)), 'urn:filter:1', STRENGTH, value=1,
                            kind='Relationship', datasetId='urn:sensor:x')
    assert kind == _strength(kms)[0]['type'] == 'Property'


def test_the_same_datasetid_is_refused_and_nothing_written(kms):
    add_attribute(load(str(kms)), 'urn:filter:1', STRENGTH, value=0.7, datasetId='urn:sensor:b')
    text = open(kms / 'model-instance.jsonld').read()
    with pytest.raises(PackageError, match='with datasetId urn:sensor:b'):
        add_attribute(load(str(kms)), 'urn:filter:1', STRENGTH, value=0.8,
                      datasetId='urn:sensor:b')
    assert open(kms / 'model-instance.jsonld').read() == text


@pytest.mark.parametrize('bad, says', [('left', 'not an IRI'), ('@none', 'default instance')])
def test_a_datasetid_must_be_an_iri(kms, bad, says):
    with pytest.raises(PackageError, match=says):
        add_attribute(load(str(kms)), 'urn:filter:1', STRENGTH, value=1, datasetId=bad)


def test_a_new_attribute_with_a_datasetid_carries_it(kms):
    document = json.load(open(kms / 'model-instance.jsonld'))
    entity = next(e for e in document if e.get('id') == 'urn:filter:1')
    entity.pop(STRENGTH)
    json.dump(document, open(kms / 'model-instance.jsonld', 'w'), indent=2)
    add_attribute(load(str(kms)), 'urn:filter:1', STRENGTH, value=1, datasetId='urn:sensor:a')
    assert _strength(kms) == [{'type': 'Property', 'value': 1, 'datasetId': 'urn:sensor:a'}]


def test_an_empty_datasetid_is_the_default_instance(kms):
    document = json.load(open(kms / 'model-instance.jsonld'))
    entity = next(e for e in document if e.get('id') == 'urn:filter:1')
    entity[STRENGTH] = dict(_strength(kms)[0], datasetId='urn:sensor:only')
    json.dump(document, open(kms / 'model-instance.jsonld', 'w'), indent=2)
    add_attribute(load(str(kms)), 'urn:filter:1', STRENGTH, value=0.5, datasetId='')
    assert 'datasetId' not in _strength(kms)[-1]


# --- the dialog ------------------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
ATTRIBUTES = {'attributes': [{'term': 'e:hasStrength', 'kind': 'Property', 'constrained': True,
                              'domains': ['e:Filter'], 'comment': ''}]}


def _entity(children):
    return {'raw': {'kind': 'entity', 'entity': 'urn:filter:1', 'entityType': 'e:Filter',
                    'file': 'case.jsonld', 'label': 'urn:filter:1', 'children': children},
            'packageUri': 'file:///pkg/shacl.ttl'}


SPACES = {'namespaces': [
    {'prefix': 'base', 'namespace': 'https://x/base/', 'terms': 3, 'default': True},
    {'prefix': 'sensors', 'namespace': 'https://x/sensors/', 'terms': 0, 'default': False}]}


def _drive(tmp_path, node, picks, inputs, replies=None):
    executable = shutil.which('node')
    if executable is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps({
        'command': 'semforge.addAttribute', 'node': node,
        'picks': ['e:hasStrength'] + picks, 'inputs': inputs,
        'replies': dict({'semforge/attributes': ATTRIBUTES,
                         'semforge/valueChoices': {'choices': []},
                         'semforge/vocabularyNamespaces': SPACES,
                         'semforge/addAttribute': {'ok': True, 'kind': 'Property'}},
                        **(replies or {}))}))
    out = subprocess.run([executable, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _sent(seen):
    return [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addAttribute']


PRESENT = {'kind': 'attribute', 'attributePath': ['e:hasStrength'], 'datasetId': '@none',
           'datasets': ['@none']}


def test_the_default_instance_comes_first_then_the_namespaces(tmp_path):
    seen = _drive(tmp_path, _entity([]), ['Default instance'], ['0.5'])
    items = seen['quickPicks'][1]['items']
    labels = [i['label'] for i in items if i['label']]
    assert labels == ['Default instance', 'In a namespace of this package',
                      'base:hasStrength-2', 'sensors:hasStrength-2',
                      '$(add) New namespace…']
    assert _sent(seen)[0]['datasetId'] is None


def test_a_namespace_and_a_local_part_make_the_full_iri(tmp_path):
    seen = _drive(tmp_path, _entity([]), ['sensors:hasStrength-2'], ['left', '0.5'])
    assert seen['inputs'][0]['value'] == 'hasStrength-2'
    assert _sent(seen)[0]['datasetId'] == 'https://x/sensors/left', \
        'written whole: a prefix from semforge.yaml is not in the case\'s @context'


def test_a_new_namespace_is_defined_on_the_spot(tmp_path):
    seen = _drive(tmp_path, _entity([]), ['$(add) New namespace…'],
                  ['plant', 'https://example.org/plant/', 'inlet', '0.5'],
                  replies={'semforge/addNamespace': {
                      'ok': True, 'prefix': 'plant', 'namespace': 'https://example.org/plant/',
                      'file': 'semforge.yaml', 'line': 3}})
    defined = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/addNamespace']
    assert defined == [{'uri': 'file:///pkg/shacl.ttl', 'prefix': 'plant',
                        'namespace': 'https://example.org/plant/'}]
    assert _sent(seen)[0]['datasetId'] == 'https://example.org/plant/inlet'


def test_with_a_default_instance_there_another_one_is_an_observation_at_a_time(tmp_path):
    """Same datasetId, another time: allowed -- it asks when it was observed."""
    seen = _drive(tmp_path, _entity([PRESENT]),
                  ['Default instance', '$(calendar) A time of your own…'],
                  ['2024-02-28T14:52:35+01:00', '0.5'])
    item = next(i for i in seen['quickPicks'][1]['items'] if i['label'] == 'Default instance')
    assert item['description'] == 'another observation of it — at another time'
    assert 'Has default' in seen['quickPicks'][1]['placeHolder']
    sent = _sent(seen)[0]
    assert (sent['datasetId'], sent['observedAt']) == (None, '2024-02-28T13:52:35.000Z')


def test_a_new_datasetid_asks_no_time(tmp_path):
    seen = _drive(tmp_path, _entity([PRESENT]), ['sensors:hasStrength-2'], ['left', '0.5'])
    assert _sent(seen)[0]['observedAt'] is None


def test_cancelling_the_datasetid_adds_nothing(tmp_path):
    seen = _drive(tmp_path, _entity([]), [], [])
    assert _sent(seen) == [] and seen['inputs'] == []
