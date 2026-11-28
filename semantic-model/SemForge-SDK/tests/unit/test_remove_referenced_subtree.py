#
# Copyright (c) 2026 IndustryFusion Foundation
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

"""Remove with subtree… from a reference row: the entity it points at, its
subtree, and of the parent's references only that one."""

import json
import shutil
from types import SimpleNamespace

import pytest

from semforge.cooked.casepage import build_model_page
from semforge.editor import edits, views
from semforge.package import load

from test_copy_paste import UA, _typed

FILTER = 'iffBaseEntities:hasFilter'
CUTTER = 'urn:plasmacutter:1'


@pytest.fixture
def kms(tmp_path, corpus_path, monkeypatch):
    """The corpus, its cutter pointing at two filters, one datasetId each."""
    monkeypatch.setenv('SEMFORGE_HISTORY', 'off')
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    _typed(str(target), hasFilter=UA + 'HasComponent', hasCartridge=UA + 'HasOrderedComponent')
    model = load(str(target)).sources['model']
    with open(model) as handle:
        documents = json.load(handle)
    cutter = next(d for d in documents if d['id'] == CUTTER)
    cutter[FILTER] = [{'type': 'Relationship', 'object': 'urn:filter:1', 'datasetId': 'urn:ds:a'},
                      {'type': 'Relationship', 'object': 'urn:filter:2', 'datasetId': 'urn:ds:b'}]
    with open(model, 'w') as handle:
        json.dump(documents, handle, indent=2)
    return str(target)


def _rows(node):
    yield node
    for child in node.get('children', []):
        yield from _rows(child)


def _tree(kms):
    payload = views.model(None, {'uri': f'file://{kms}/kms.yaml'})
    return [row for root in payload['roots'] for row in _rows(root)]


def _model(kms):
    with open(load(kms).sources['model']) as handle:
        return {d['id']: d for d in json.load(handle)}


def test_a_reference_row_names_its_entity_and_the_file_s_digest(kms):
    rows = _tree(kms)
    cutter = next(r for r in rows if r['kind'] == 'entity' and r['entity'] == CUTTER and 'position' in r)
    filters = [r for r in rows if r['kind'] == 'dataset' and r['entity'] == CUTTER
               and r['attributePath'][-1:] == [FILTER]]
    assert {r['datasetId']: r['object'] for r in filters} == {'urn:ds:a': 'urn:filter:1',
                                                              'urn:ds:b': 'urn:filter:2'}
    assert {r['digest'] for r in filters} == {cutter['digest']}
    attribute = next(r for r in rows if r['kind'] == 'attribute' and r['entity'] == CUTTER
                     and r['attributePath'][-1:] == [FILTER])
    assert 'object' not in attribute, 'several instances: the attribute names none'


def test_only_a_single_iri_is_a_reference():
    def node(kind, path, value):
        return SimpleNamespace(kind=kind, path=path, value=value)
    assert views._reference(node('instance', ['p', 0, 'object'], '"urn:x:1"')) == 'urn:x:1'
    assert views._reference(node('attribute', ['p', 0, 'object'], '"urn:x:1"')) == 'urn:x:1'
    assert views._reference(node('instance', ['p', 0, 'object'], '["urn:x:1", "urn:x:2"]')) is None
    assert views._reference(node('instance', ['p', 0, 'objectList'], '["urn:x:1"]')) is None
    assert views._reference(node('instance', ['p', 0, 'value'], '"urn:x:1"')) is None
    assert views._reference(node('entity', ['p', 0, 'object'], '"urn:x:1"')) is None
    assert views._reference(node('dataset', ['p', 0, 'object'], 'not json')) is None


def test_the_case_page_row_of_a_relationship_names_its_target(kms):
    """What the case page's Remove with subtree… takes: the row's `target`."""
    page = build_model_page(load(kms))
    cards = [card for f in page['files'] for card in f['cards']]
    rows = [row for card in cards if card['id'] == CUTTER for row in card['attributes']
            if row['term'] == FILTER]
    assert sorted((r['kind'], r['target']) for r in rows) == [('Relationship', 'urn:filter:1'),
                                                              ('Relationship', 'urn:filter:2')]
    assert all(card['digest'] for card in cards if card['id'] == CUTTER)


def test_remove_with_subtree_from_a_reference_row_end_to_end(kms):
    """"From a reference row", through the server: the row's entity, its
    file and digest, as the extension sends them -- asked first, then done."""
    row = next(r for r in _tree(kms) if r['kind'] == 'dataset' and r.get('object') == 'urn:filter:2')
    uri = f'file://{kms}/kms.yaml'
    params = {'uri': uri, 'entity': row['object'], 'file': row['file'], 'digest': row['digest'],
              'subtree': True}
    plan = edits.remove_entity_feature(None, dict(params, check=True))
    assert plan['ok'], plan
    assert plan['removed'] == ['urn:filter:2', 'urn:cartridge:2']
    assert [(d['entity'], d['datasetId']) for d in plan['dropped'] if d['entity'] == CUTTER] == \
        [(CUTTER, 'urn:ds:b')]
    done = edits.remove_entity_feature(None, dict(params, plan=plan['plan']))
    assert done['ok'], done
    after = _model(kms)
    assert 'urn:filter:2' not in after and 'urn:cartridge:2' not in after
    assert 'urn:filter:1' in after and 'urn:cartridge:1' in after, 'the other child and its subtree stay'
    left = after[CUTTER][FILTER]
    left = left if isinstance(left, list) else [left]
    assert [(i['object'], i['datasetId']) for i in left] == [('urn:filter:1', 'urn:ds:a')]


def test_a_file_changed_since_the_row_was_shown_is_refused(kms):
    row = next(r for r in _tree(kms) if r['kind'] == 'dataset' and r.get('object') == 'urn:filter:2')
    with open(row['file'], 'a') as handle:
        handle.write('\n')
    answer = edits.remove_entity_feature(None, {
        'uri': f'file://{kms}/kms.yaml', 'entity': row['object'], 'file': row['file'],
        'digest': row['digest'], 'subtree': True, 'check': True})
    assert not answer['ok'] and 'changed' in answer['error']


# --- the extension -----------------------------------------------------------------

PLAN = {'ok': True, 'file': '/pkg/c.jsonld', 'real': '/pkg/c.jsonld', 'removed': ['urn:f', 'urn:c'],
        'elsewhere': [], 'shared': [], 'assumed': [], 'missing': [], 'model': False, 'empty': False,
        'dropped': [{'entity': 'urn:p', 'path': ['https://x/base/hasChild'], 'datasetId': 'urn:ds:f',
                     'object': 'urn:f'}],
        'pointing': ['urn:p'], 'asserts': [], 'cases': ['a'], 'plan': 'p1', 'unread': ''}
REFERENCE = {'kind': 'dataset', 'entity': 'urn:p', 'object': 'urn:f', 'datasetId': 'urn:ds:f',
             'attributePath': ['https://x/base/hasChild'], 'path': ['https://x/base/hasChild', 0, 'object'],
             'value': '"urn:f"', 'file': '/pkg/c.jsonld', 'digest': 'd1', 'children': []}


def _drive(tmp_path, scenario):
    from test_tree_clicks import _drive as drive

    return drive(tmp_path, dict({'replies': {'semforge/removeEntity': PLAN, 'semforge/model': {'roots': []}}},
                                **scenario))


def test_remove_with_subtree_on_a_reference_row_takes_the_entity_it_points_at(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.removeSubtree', 'answer': 'Remove',
                             'node': {'raw': REFERENCE, 'packageUri': 'file:///pkg/shacl.ttl'}})
    asked = [r['params'] for r in seen['requests'] if r['method'] == 'semforge/removeEntity']
    row = {'uri': 'file:///pkg/shacl.ttl', 'entity': 'urn:f', 'file': '/pkg/c.jsonld', 'digest': 'd1',
           'subtree': True}
    assert asked == [dict(row, check=True), dict(row, plan='p1')]
    assert seen['warnings'][0].startswith('Remove urn:f with its subtree (2 entities)?')
    assert 'urn:p · hasChild (urn:ds:f)' in seen['warnings'][0], 'only that reference goes'


def test_a_row_that_points_at_nothing_is_refused(tmp_path):
    raw = {k: v for k, v in REFERENCE.items() if k != 'object'}
    seen = _drive(tmp_path, {'command': 'semforge.removeSubtree', 'answer': 'Remove',
                             'node': {'raw': raw, 'packageUri': 'file:///pkg/shacl.ttl'}})
    assert not [r for r in seen['requests'] if r['method'] == 'semforge/removeEntity']
    assert any('reference to one' in m for m in seen['info'])


def _row_at(page, entity, target):
    for f, file in enumerate(page['files']):
        for c, card in enumerate(file['cards']):
            for r, row in enumerate(card['attributes']):
                if card['id'] == entity and row['target'] == target:
                    return f'{f}.{c}.{r}', card, row
    raise AssertionError(f'no row of {entity} pointing at {target}')


@pytest.mark.parametrize('choose', ['subtree', 'reference'])
def test_the_case_page_row_menu_of_a_reference(tmp_path, kms, choose):
    """"From the case page" and "Only this reference"."""
    from test_casepage import _edit, _ran

    page = build_model_page(load(kms))
    at, card, row = _row_at(page, CUTTER, 'urn:filter:2')
    seen = _edit(tmp_path, page, [{'command': 'rowMenu', 'at': at}])
    items = seen['quickPicks'][0]['items']
    labels = [item['label'] for item in items]
    subtree = next(i for i, label in enumerate(labels) if 'with its subtree' in label)
    only = next(i for i, item in enumerate(items)
                if item.get('description') == 'only this reference; the entity stays')
    everything = next(i for i, label in enumerate(labels) if label == f'$(trash) Remove {row["name"]}…')
    assert subtree < only < everything, labels
    assert items[everything]['description'] == f'ALL {row["instances"]} instances, from this entity'
    seen = _edit(tmp_path, page, [{'command': 'rowMenu', 'at': at}],
                 pick=subtree if choose == 'subtree' else only)
    if choose == 'subtree':
        assert _ran(seen, 'semforge.removeSubtree') == [{'raw': {
            'kind': 'entity', 'entity': 'urn:filter:2', 'file': card['file'], 'digest': card['digest']},
            'packageUri': 'file:///pkg/shacl.ttl'}]
    else:
        assert [r['raw'] for r in _ran(seen, 'semforge.removeCaseValue')] == [row['node']]


def test_removing_an_attribute_says_how_many_instances_go(tmp_path):
    """"Several instances"."""
    raw = {'kind': 'attribute', 'entity': 'urn:p', 'attributePath': ['https://x/base/hasChild'],
           'path': ['https://x/base/hasChild'], 'file': '/pkg/c.jsonld', 'editable': False,
           'children': [dict(REFERENCE, datasetId=f'urn:ds:{i}') for i in range(15)]}
    seen = _drive(tmp_path, {'command': 'semforge.removeCaseValue', 'answer': None,
                             'node': {'raw': raw, 'packageUri': 'file:///pkg/shacl.ttl'}})
    assert seen['warnings'][0].startswith('Remove all 15 instances of hasChild from urn:p?')
    assert not [r for r in seen['requests'] if r['method'] == 'semforge/removeCaseValue']


def test_the_case_page_s_attribute_row_counts_its_instances_without_children(tmp_path):
    """"Several instances" from the case page: its rows come without children,
    their datasets name the instances."""
    raw = {'kind': 'attribute', 'entity': 'urn:p', 'attributePath': ['https://x/base/hasChild'],
           'path': ['https://x/base/hasChild'], 'file': '/pkg/c.jsonld', 'editable': False,
           'datasets': [f'urn:ds:{i}' for i in range(15)]}
    seen = _drive(tmp_path, {'command': 'semforge.removeCaseValue', 'answer': None,
                             'node': {'raw': raw, 'packageUri': 'file:///pkg/shacl.ttl'}})
    assert seen['warnings'][0].startswith('Remove all 15 instances of hasChild from urn:p?')


def test_a_reference_written_with_a_prefix_removes_the_entity_of_that_iri(kms):
    """The object as the relationship writes it -- with a prefix of the
    context -- names the document of that IRI, however that one is written."""
    model = load(kms).sources['model']
    with open(model) as handle:
        documents = json.load(handle)
    cutter = next(d for d in documents if d['id'] == CUTTER)
    cutter['@context'] = [cutter['@context'], {'flt': 'urn:filter:'}]
    cutter[FILTER][1]['object'] = 'flt:2'
    with open(model, 'w') as handle:
        json.dump(documents, handle, indent=2)
    row = next(r for r in _tree(kms) if r['kind'] == 'dataset' and r.get('object') == 'flt:2')
    params = {'uri': f'file://{kms}/kms.yaml', 'entity': row['object'], 'file': row['file'],
              'digest': row['digest'], 'subtree': True}
    plan = edits.remove_entity_feature(None, dict(params, check=True))
    assert plan['ok'], plan
    assert plan['removed'] == ['urn:filter:2', 'urn:cartridge:2']
    done = edits.remove_entity_feature(None, dict(params, plan=plan['plan']))
    assert done['ok'], done
    after = _model(kms)
    assert 'urn:filter:2' not in after and 'urn:filter:1' in after
    left = after[CUTTER][FILTER]
    left = left if isinstance(left, list) else [left]
    assert [i['object'] for i in left] == ['urn:filter:1']


def test_an_entity_written_in_another_file_is_refused_saying_so(kms):
    row = next(r for r in _tree(kms) if r['kind'] == 'dataset' and r.get('object') == 'urn:filter:2')
    answer = edits.remove_entity_feature(None, {
        'uri': f'file://{kms}/kms.yaml', 'entity': 'urn:filter:elsewhere', 'file': row['file'],
        'digest': row['digest'], 'subtree': True, 'check': True})
    assert not answer['ok'] and 'another file' in answer['error'], answer
