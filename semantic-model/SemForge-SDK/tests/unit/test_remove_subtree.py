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

"""Remove with subtree…: the subtree Copy with subtree copies, from one file."""

import json
import os
import shutil

import pytest

from semforge.cooked.examples import copy_entities
from semforge.cooked.removeentity import remove_subtree
from semforge.editor import edits
from semforge.errors import PackageError
from semforge.expect.store import load_expectations
from semforge.package import load

from test_copy_paste import UA, _typed


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _model_ids(kms):
    package = load(kms)
    with open(package.sources['model']) as handle:
        return [d['id'] for d in json.load(handle)]


def _children(kms):
    _typed(kms, hasFilter=UA + 'HasComponent', hasCartridge=UA + 'HasOrderedComponent')


def test_the_plan_is_the_copied_subtree_and_writes_nothing(kms):
    _children(kms)
    before = _model_ids(kms)
    plan = remove_subtree(load(kms), 'urn:plasmacutter:1', check=True)
    assert plan['removed'] == copy_entities(load(kms), 'urn:plasmacutter:1', subtree=True)['copied']
    assert plan['removed'] == ['urn:plasmacutter:1', 'urn:filter:1', 'urn:cartridge:1']
    assert plan['elsewhere'] == [] and not set(plan['pointing']) & set(plan['removed'])
    assert _model_ids(kms) == before


def test_removed_with_its_subtree_and_nothing_else(kms):
    _children(kms)
    before = _model_ids(kms)
    done = remove_subtree(load(kms), 'urn:plasmacutter:1')
    after = _model_ids(kms)
    assert not set(done['removed']) & set(after)
    assert after == [i for i in before if i not in done['removed']], 'the rest stays, in order'


def test_without_children_it_is_the_entity_alone(kms):
    plan = remove_subtree(load(kms), 'urn:plasmacutter:1', check=True)
    assert plan['removed'] == ['urn:plasmacutter:1']


def _model(kms):
    with open(load(kms).sources['model']) as handle:
        return {d['id']: d for d in json.load(handle)}


def _store_model(kms, docs):
    with open(load(kms).sources['model'], 'w') as handle:
        json.dump(list(docs.values()), handle)


def _filter_key(entity):
    return next(k for k in entity if k.endswith('hasFilter'))


def test_the_parent_s_reference_goes_with_it(kms):
    _children(kms)
    plan = remove_subtree(load(kms), 'urn:filter:1', check=True)
    assert plan['removed'] == ['urn:filter:1', 'urn:cartridge:1']
    assert plan['pointing'] == ['urn:plasmacutter:1'] and len(plan['dropped']) == 1
    key = _filter_key(_model(kms)['urn:plasmacutter:1'])
    assert plan['dropped'][0]['path'] == [key] and plan['dropped'][0]['object'] == 'urn:filter:1'
    assert key in _model(kms)['urn:plasmacutter:1'], 'a plan writes nothing'
    remove_subtree(load(kms), 'urn:filter:1')
    assert key not in _model(kms)['urn:plasmacutter:1'], 'its only instance gone, the attribute too'


def test_only_the_instance_pointing_at_it_goes(kms):
    """A parent keeps its other children: one instance per child, by datasetId."""
    _children(kms)
    docs = _model(kms)
    cutter = docs['urn:plasmacutter:1']
    key = _filter_key(cutter)
    one = cutter[key][0] if isinstance(cutter[key], list) else cutter[key]
    other = dict(one, object='urn:filter:2', datasetId='urn:ds:2')
    cutter[key] = [dict(one, datasetId='urn:ds:1'), other]
    docs['urn:filter:2'] = dict(docs['urn:filter:1'], id='urn:filter:2')
    _store_model(kms, docs)
    done = remove_subtree(load(kms), 'urn:filter:1')
    assert [d['datasetId'] for d in done['dropped']] == ['urn:ds:1']
    assert _model(kms)['urn:plasmacutter:1'][key] == [other], 'the other instance stays'
    # The copied filter has the same cartridge: shared, so it stays for filter 2.
    assert done['removed'] == ['urn:filter:1'] and done['shared'] == ['urn:cartridge:1']
    assert {'urn:filter:2', 'urn:cartridge:1'} <= set(_model(kms))


def test_a_child_in_an_included_file_stays_there(kms):
    _typed(kms, hasCartridge=UA + 'HasComponent')
    case = next(e for e in load_expectations(kms).examples if any('cartridge-fresh' in i for i in e.include))
    source = os.path.join(kms, 'examples', case.path)
    with open(source) as handle:
        entity = json.load(handle)[0]['id']
    included = [os.path.join(kms, 'examples', i) for i in case.include]
    kept = {p: open(p).read() for p in included}
    plan = remove_subtree(load(kms), entity, file=source, check=True)
    assert 'urn:cartridge:1' in plan['elsewhere'] and 'urn:cartridge:1' not in plan['removed']
    assert case.path in plan['cases']
    remove_subtree(load(kms), entity, file=source)
    assert {p: open(p).read() for p in included} == kept, 'an included file is never written'


def test_an_entity_not_in_the_file_is_refused(kms):
    with pytest.raises(PackageError, match='no entity urn:none'):
        remove_subtree(load(kms), 'urn:none')


def test_the_server_removes_with_subtree(kms, monkeypatch):
    monkeypatch.setattr(edits.validation, 'publish', lambda *a, **k: None)
    _children(kms)
    asked = {'uri': f'file://{kms}/shacl.ttl', 'entity': 'urn:filter:1', 'subtree': True}
    plan = edits.remove_entity_feature(None, dict(asked, check=True))
    assert plan['ok'] and plan['removed'] == ['urn:filter:1', 'urn:cartridge:1']
    assert 'urn:filter:1' in _model_ids(kms)
    assert edits.remove_entity_feature(None, asked)['ok']
    assert not {'urn:filter:1', 'urn:cartridge:1'} & set(_model_ids(kms))
    one = edits.remove_entity_feature(None, {'uri': asked['uri'], 'entity': 'urn:plasmacutter:1',
                                             'check': True})
    assert one['ok'] and one['removed'] == 'urn:plasmacutter:1', 'without subtree: the entity alone'


# --- references, however they are written ------------------------------------------

BAD = os.path.join('examples', 'test_FilterShape', 'bad', 'without-cartridge.jsonld')


def _rel(target):
    return {'type': 'Relationship', 'object': target}


def _scene(kms, documents):
    path = os.path.join(kms, BAD)
    with open(path) as handle:
        context = [json.load(handle)[0]['@context'], {'p': 'urn:my:'}]
    with open(path, 'w') as handle:
        json.dump([dict({'@context': context}, **d) for d in documents], handle)
    return path


def _docs(path):
    with open(path) as handle:
        return {d['id']: d for d in json.load(handle)}


def test_a_reference_goes_however_it_is_written(kms):
    has = 'iffBaseEntities:hasCartridge'
    path = _scene(kms, [
        {'id': 'p:cut', 'type': 'base:Filter'},
        {'id': 'urn:whole', 'type': 'base:Filter', has: _rel('urn:my:cut')},
        {'id': 'p:short', 'type': 'base:Filter', has: _rel('p:cut')},
        {'id': 'urn:sub', 'type': 'base:Filter', 'iffBaseEntities:hasState': {
            'type': 'Property', 'value': 1, has: [dict(_rel('urn:x'), datasetId='urn:d:1'),
                                                  dict(_rel(['urn:y', 'p:cut']), datasetId='urn:d:2')]}},
        {'id': 'urn:none', 'type': 'base:Filter', has: _rel('p:other')}])
    plan = remove_subtree(load(kms), 'p:cut', file=path, check=True)
    assert plan['removed'] == ['p:cut'] and not plan['unread']
    assert plan['pointing'] == ['p:short', 'urn:sub', 'urn:whole']
    assert _docs(path)['urn:whole'][has], 'a plan writes nothing'
    remove_subtree(load(kms), 'p:cut', file=path, plan=plan['plan'])
    after = _docs(path)
    assert 'p:cut' not in after and has not in after['urn:whole'] and has not in after['p:short']
    sub = after['urn:sub']['iffBaseEntities:hasState'][has]
    assert sub == [dict(_rel('urn:x'), datasetId='urn:d:1'), dict(_rel(['urn:y']), datasetId='urn:d:2')], \
        'of several objects only the removed one goes'
    assert after['urn:none'][has] == _rel('p:other')


def test_an_object_list_loses_the_removed_entry(kms):
    has = 'iffBaseEntities:hasCartridge'
    path = _scene(kms, [
        {'id': 'urn:gone', 'type': 'base:Filter'},
        {'id': 'urn:keeps', 'type': 'base:Filter',
         has: {'type': 'Relationship', 'objectList': [{'object': 'urn:gone'}, {'object': 'urn:other'}]}}])
    done = remove_subtree(load(kms), 'urn:gone', file=path)
    assert [d['object'] for d in done['dropped']] == ['urn:gone']
    assert _docs(path)['urn:keeps'][has]['objectList'] == [{'object': 'urn:other'}]


def test_a_member_written_twice_is_refused(kms):
    path = _scene(kms, [{'id': 'urn:twice', 'type': 'base:Filter'},
                        {'id': 'urn:other', 'type': 'base:Filter'},
                        {'id': 'urn:twice', 'type': 'base:Filter'}])
    with open(path) as handle:
        before = handle.read()
    with pytest.raises(PackageError, match='written 2 times'):
        remove_subtree(load(kms), 'urn:twice', file=path)
    with open(path) as handle:
        assert handle.read() == before


def test_an_iri_still_defined_keeps_its_references(kms):
    """`p:cut` goes, `urn:my:cut` -- the same IRI -- stays: what points at it is no dangling reference."""
    has = 'iffBaseEntities:hasCartridge'
    path = _scene(kms, [{'id': 'p:cut', 'type': 'base:Filter'},
                        {'id': 'urn:my:cut', 'type': 'base:Filter'},
                        {'id': 'urn:holder', 'type': 'base:Filter', has: _rel('p:cut')}])
    done = remove_subtree(load(kms), 'p:cut', file=path)
    assert done['removed'] == ['p:cut'] and done['dropped'] == []
    assert _docs(path)['urn:holder'][has] == _rel('p:cut')


@pytest.mark.parametrize('relationship', [
    {'@type': 'Relationship', 'object': 'urn:gone'},
    {'type': 'ngsi-ld:Relationship', 'object': 'urn:gone'},
    {'type': 'https://uri.etsi.org/ngsi-ld/Relationship', 'object': 'urn:gone'},
    {'type': 'Relationship', 'https://uri.etsi.org/ngsi-ld/hasObject': {'@id': 'urn:gone'}},
    {'type': 'Relationship', 'ngsi-ld:hasObject': [{'@id': 'urn:gone'}]}])
def test_a_relationship_however_it_is_written(kms, relationship):
    has = 'iffBaseEntities:hasCartridge'
    path = _scene(kms, [{'id': 'urn:gone', 'type': 'base:Filter'},
                        {'id': 'urn:holder', 'type': 'base:Filter', has: relationship}])
    done = remove_subtree(load(kms), 'urn:gone', file=path)
    assert [d['object'] for d in done['dropped']] == ['urn:gone']
    assert has not in _docs(path)['urn:holder']


def test_a_context_is_read_once(kms, monkeypatch):
    """Not once per id and object: once per distinct context."""
    from semforge.cooked import removeentity

    calls = []
    real = removeentity._own_contexts
    monkeypatch.setattr(removeentity, '_own_contexts', lambda p, d: calls.append(1) or real(p, d))
    _children(kms)
    remove_subtree(load(kms), 'urn:plasmacutter:1', check=True)
    with open(load(kms).sources['model']) as handle:
        contexts = {json.dumps(d.get('@context'), sort_keys=True) for d in json.load(handle)}
    assert len(calls) == len(contexts)


def test_what_changed_meanwhile_is_refused(kms):
    _children(kms)
    model = load(kms).sources['model']
    plan = remove_subtree(load(kms), 'urn:filter:1', check=True)
    with open(model) as handle:
        text = handle.read()
    with open(model, 'w') as handle:
        handle.write(text.replace('urn:workpiece:1', 'urn:workpiece:1 '))     # another content
    with pytest.raises(PackageError, match='changed meanwhile'):
        remove_subtree(load(kms), 'urn:filter:1', plan=plan['plan'])
    with pytest.raises(PackageError, match='changed since it was read'):
        remove_subtree(load(kms), 'urn:filter:1', digest='0' * 16)
    assert 'urn:filter:1' in _model_ids(kms)


def test_a_file_of_no_package_is_refused(kms, tmp_path):
    """"Another file": refused, and the file is as it was."""
    other = tmp_path / 'elsewhere.jsonld'
    other.write_text(json.dumps([{'id': 'urn:a', 'type': 'base:Filter'}]))
    before = other.read_text()
    with pytest.raises(PackageError, match='no model file'):
        remove_subtree(load(kms), 'urn:a', file=str(other))
    assert other.read_text() == before


# --- the extension -----------------------------------------------------------------

PLAN = {'ok': True, 'file': '/pkg/c.jsonld', 'real': '/pkg/c.jsonld', 'removed': ['urn:f', 'urn:c'],
        'elsewhere': [], 'shared': [], 'assumed': [], 'missing': [], 'model': False, 'empty': False,
        'dropped': [{'entity': 'urn:p', 'path': ['https://x/base/hasChild'], 'datasetId': 'urn:ds:f',
                     'object': 'urn:f'}],
        'pointing': ['urn:p'], 'asserts': [], 'cases': ['a'], 'plan': 'p1', 'unread': ''}
ROW = {'raw': {'kind': 'entity', 'entity': 'urn:f', 'file': '/pkg/c.jsonld', 'position': 1, 'digest': 'd1'},
       'packageUri': 'file:///pkg/shacl.ttl'}


def _command(tmp_path, answer='Remove', **plan):
    from test_tree_clicks import _drive

    seen = _drive(tmp_path, {'command': 'semforge.removeSubtree', 'answer': answer, 'node': ROW, 'replies': {
        'semforge/removeEntity': dict(PLAN, **plan), 'semforge/model': {'roots': []}}})
    return seen, [r['params'] for r in seen['requests'] if r['method'] == 'semforge/removeEntity']


@pytest.mark.parametrize('answer, removed', [('Remove', 1), (None, 0)])
def test_it_is_asked_first_naming_the_subtree(tmp_path, answer, removed):
    """"Asked first" and "Dismissed"."""
    seen, asked = _command(tmp_path, answer=answer)
    row = {'uri': 'file:///pkg/shacl.ttl', 'entity': 'urn:f', 'file': '/pkg/c.jsonld', 'digest': 'd1',
           'subtree': True}
    assert asked == [dict(row, check=True)] + [dict(row, plan='p1')] * removed
    said = seen['warnings'][0]
    assert said.startswith('Remove urn:f with its subtree (2 entities)?')
    assert 'In its subtree:\nurn:c' in said and 'References to them that go too:\nurn:p · hasChild (urn:ds:f)' in said


@pytest.mark.parametrize('plan, words', [
    ({'elsewhere': ['urn:x']}, 'written in another file, and kept:\nurn:x'),
    ({'shared': ['urn:y']}, 'another entity still points at, and kept:\nurn:y'),
    ({'assumed': ['urn:c']}, 'Children by the data only'),
    ({'removed': ['urn:f']}, 'It has no children in this file.'),
    ({'asserts': ['x/bad/a.jsonld']}, 'Asserting something on them, which stays as it is:\nx/bad/a.jsonld'),
    ({'missing': ['urn:nowhere']}, 'Children written in no file, so not removed:\nurn:nowhere'),
    ({'unread': 'no context'}, 'compared as written: no context'),
    ({'model': True}, 'That is the main model')])
def test_the_question_says_what_stays_and_why(tmp_path, plan, words):
    seen, _ = _command(tmp_path, answer=None, **plan)
    assert words in seen['warnings'][0], seen['warnings']


def _alone(replies, open=()):
    import shutil as which
    import subprocess

    from test_remove_entity import NODE, SRC

    node = which.which('node')
    if node is None:
        pytest.skip('node is not installed')
    script = NODE.replace('const { removeEntity }', 'const { removeSubtree: removeEntity }')
    scenario = {'replies': replies, 'node': ROW, 'open': list(open), 'platform': None}
    run = subprocess.run([node, '-e', script, json.dumps(scenario), os.path.join(SRC, 'removeentity.js')],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_unsaved_edits_are_refused():
    """"Unsaved edits": nothing is asked or removed, a message asks to save or discard."""
    out = _alone([PLAN, PLAN], [{'file': '/pkg/c.jsonld', 'dirty': True}])
    assert len(out['asked']) == 1 and 'unsaved edits' in out['said'][0] and not out['done']
    out = _alone([PLAN, PLAN], [{'file': '/pkg/other.jsonld', 'dirty': True}])
    assert len(out['asked']) == 2 and out['done'] == 1


def test_the_menu_is_on_entities_below_remove_entity_and_not_in_the_palette():
    """"Not an entity"."""
    from test_tree_clicks import PACKAGE_JSON

    with open(PACKAGE_JSON) as handle:
        menus = json.load(handle)['contributes']['menus']
    rows = {e['command']: e for e in menus['view/item/context']
            if e['command'] in ('semforge.removeEntity', 'semforge.removeSubtree')}
    assert rows['semforge.removeSubtree']['when'] == 'view == semforgeModel && viewItem == entity'
    group, order = rows['semforge.removeSubtree']['group'].split('@')
    assert group == rows['semforge.removeEntity']['group'].split('@')[0]
    assert int(order) == int(rows['semforge.removeEntity']['group'].split('@')[1]) + 1, 'right below it'
    assert [e['when'] for e in menus['commandPalette'] if e['command'] == 'semforge.removeSubtree'] == ['false']
