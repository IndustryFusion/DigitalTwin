"""Remove… an attribute -- or one instance, observation or metadata key -- from
an entity in a test case or the model.

The row says what it stands for, and that is what goes: the whole attribute,
the instances of one datasetId, one observation of a series, one metadata
key. An attribute left with nothing goes entirely. A required attribute
removed from a valid case makes it violate -- the way a bad case is made.
"""

import json
import os
import shutil
import subprocess
import sys
from unittest import mock

import pytest

from semforge.cooked.examples import add_observation, remove_value
from semforge.errors import PackageError
from semforge.package import load

CASE = 'test_WorkpieceShape/good/at-the-limits.jsonld'
WP = 'urn:workpiece:1'
H = 'iffBaseEntities:hasHeight'
SEMFORGE = os.path.join(os.path.dirname(sys.executable), 'semforge')


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return target


def _entity(kms, entity=WP, case=CASE):
    with open(kms / 'examples' / case, encoding='utf-8') as handle:
        return next(e for e in json.load(handle) if e['id'] == entity)


def test_a_whole_attribute_goes(kms):
    done = remove_value(load(str(kms)), WP, [H], CASE)
    assert done['removed'] == 'hasHeight'
    assert H not in _entity(kms) and 'iffBaseEntities:hasWidth' in _entity(kms)


def test_removing_a_required_attribute_makes_the_case_violate(kms):
    remove_value(load(str(kms)), WP, [H], CASE)
    run = subprocess.run([SEMFORGE, 'test', str(kms)], capture_output=True, text=True)
    assert f'FAIL  {CASE}' in run.stdout, 'hasHeight is required on a Workpiece'


def test_one_observation_of_a_series(kms):
    add_observation(load(str(kms)), WP, [H], value='6.0', observed_at='2026-01-02T00:00:00Z',
                    file=CASE)
    assert len(_entity(kms)[H]) == 2
    done = remove_value(load(str(kms)), WP, [H, 0, 'value'], CASE)
    assert done['removed'] == 'an observation of hasHeight'
    assert _entity(kms)[H] == [{'type': 'Property', 'value': 6.0,
                                'observedAt': '2026-01-02T00:00:00.000Z'}]  # the kms form


def test_the_only_observation_takes_the_attribute(kms):
    remove_value(load(str(kms)), WP, [H, 0, 'value'], CASE)
    assert H not in _entity(kms)


def test_one_dataset_s_instances(kms):
    add_observation(load(str(kms)), WP, [H], dataset_id='urn:ds:laser', value='7.0', file=CASE)
    done = remove_value(load(str(kms)), WP, [H], CASE, dataset='urn:ds:laser')
    assert done['removed'] == 'hasHeight (urn:ds:laser)'
    assert _entity(kms)[H] == [{'type': 'Property', 'value': 5.0}], 'the default instance stays'


def test_a_metadata_key(kms):
    add_observation(load(str(kms)), WP, [H], value='6.0', observed_at='2026-01-02T00:00:00Z',
                    file=CASE)
    done = remove_value(load(str(kms)), WP, [H, 1, 'observedAt'], CASE)
    assert done['removed'] == 'observedAt'
    assert 'observedAt' not in _entity(kms)[H][1]


def test_a_sub_attribute(kms):
    model = kms / 'model-instance.jsonld'
    with open(model, encoding='utf-8') as handle:
        document = json.load(handle)
    holder = next(e for e in document if 'iffBaseEntities:hasFilter' in e and
                  'iffBaseEntities:hasTrust' in json.dumps(e['iffBaseEntities:hasFilter']))
    path = ['iffBaseEntities:hasFilter', 0, 'iffBaseEntities:hasTrust']
    done = remove_value(load(str(kms)), holder['id'], path)
    assert done['removed'] == 'hasTrust'
    with open(model, encoding='utf-8') as handle:
        after = next(e for e in json.load(handle) if e['id'] == holder['id'])
    assert 'iffBaseEntities:hasTrust' not in json.dumps(after['iffBaseEntities:hasFilter'])
    assert 'iffBaseEntities:hasFilter' in after, 'the parent stays'


@pytest.mark.parametrize('entity, path, dataset, said', [
    ('urn:nothing:1', [H], None, 'no entity'),
    (WP, ['iffBaseEntities:hasNothing'], None, 'has no hasNothing'),
    (WP, [H], 'urn:ds:none', 'no instance with datasetId'),
    (WP, ['type'], None, 'makes it an entity'),
])
def test_what_is_not_there_is_not_removed(kms, entity, path, dataset, said):
    before = (kms / 'examples' / CASE).read_text()
    with pytest.raises(PackageError, match=said):
        remove_value(load(str(kms)), entity, path, CASE, dataset)
    assert (kms / 'examples' / CASE).read_text() == before


def test_the_server_removes_and_republishes(kms):
    from semforge.editor import server

    with mock.patch.object(server, '_publish') as published:
        done = server.remove_case_value_feature(mock.MagicMock(), {
            'uri': f'file://{kms}/shacl.ttl', 'entity': WP, 'path': [H], 'file': CASE})
    assert done['ok'] and done['removed'] == 'hasHeight', done
    published.assert_called()


# --- the extension ----------------------------------------------------------------------

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


def _remove(tmp_path, raw, answer='Remove'):
    return _drive(tmp_path, {
        'command': 'semforge.removeCaseValue',
        'node': {'raw': dict({'entity': WP, 'file': '/pkg/examples/' + CASE, 'label': 'x'}, **raw),
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'answer': answer,
        'replies': {'semforge/removeCaseValue': {'ok': True, 'file': '/f', 'removed': 'hasHeight'},
                    'semforge/model': {'roots': []}}})


def _asked(seen):
    return [r['params'] for r in seen['requests'] if r['method'] == 'semforge/removeCaseValue']


@pytest.mark.parametrize('raw, path, dataset, what', [
    ({'kind': 'attribute', 'attributePath': [H], 'path': [H, 0, 'value']}, [H], None,
     'hasHeight'),
    ({'kind': 'dataset', 'attributePath': [H], 'datasetId': 'urn:ds:laser'}, [H], 'urn:ds:laser',
     'hasHeight (urn:ds:laser)'),
    ({'kind': 'instance', 'path': [H, 1, 'value']}, [H, 1, 'value'], None,
     'this observation of hasHeight'),
    ({'kind': 'meta', 'label': 'observedAt', 'path': [H, 1, 'observedAt']},
     [H, 1, 'observedAt'], None, 'observedAt of hasHeight'),
])
def test_each_row_removes_what_it_stands_for(tmp_path, raw, path, dataset, what):
    seen = _remove(tmp_path, raw)
    assert seen['warnings'][0].startswith(f'Remove {what} from {WP}?')
    expected = {'uri': 'file:///pkg/shacl.ttl', 'entity': WP, 'path': path,
                'file': '/pkg/examples/' + CASE}
    if dataset is not None:                        # undefined is not sent at all
        expected['dataset'] = dataset
    assert _asked(seen) == [expected]


def test_a_shared_file_says_who_else_changes(tmp_path):
    seen = _remove(tmp_path, {'kind': 'attribute', 'attributePath': [H],
                              'sharedBy': ['test_A/good/a.jsonld', 'test_B/bad/b.jsonld']}, None)
    assert 'This file is included by 2 cases — all of them change' in seen['warnings'][0]
    assert _asked(seen) == [], 'dismissed: nothing removed'


def test_the_tree_offers_remove_on_attribute_rows():
    with open(os.path.join(SRC, '..', 'package.json')) as handle:
        menus = json.load(handle)['contributes']['menus']['view/item/context']
    entry = next(e for e in menus if e['command'] == 'semforge.removeCaseValue')
    for context in ('exampleEditable', 'exampleDataset', 'exampleSeries', 'attributeReadOnly'):
        assert context in entry['when'], context
