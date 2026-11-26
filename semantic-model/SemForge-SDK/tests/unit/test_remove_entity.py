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

"""Remove an entity from its file: the one that was meant, whole, and what that
touches is said first (openspec gh-1118-remove-entity)."""

import html
import json
import os
import re
import shutil
import subprocess

import pytest

from semforge.cooked import removeentity
from semforge.cooked.casepage import build_case_page, build_model_page
from semforge.cooked.examples import add_entity, build_suite
from semforge.cooked.removeentity import digest_of, remove_entity
from semforge.editor import edits
from semforge.editor.views import _serialise_example
from semforge.errors import PackageError
from semforge.package import load

from test_tree_clicks import PACKAGE_JSON, SRC, _drive

BAD = os.path.join('examples', 'test_FilterShape', 'bad', 'without-cartridge.jsonld')
SHARED = os.path.join('examples', 'subobjects', 'cartridge-fresh.jsonld')


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False, ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _read(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


def _write(path, documents):
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(documents, handle, indent=2)
        handle.write('\n')


def _ids(path):
    return [d['id'] for d in json.loads(_read(path))]


def _case(kms, *documents):
    """The filter's case, with more documents of the same context after its own."""
    path = os.path.join(kms, BAD)
    scene = json.loads(_read(path))
    _write(path, scene + [dict({'@context': scene[0]['@context']}, **d) for d in documents])
    return path


def _rows(kms, path):
    """The entity rows of a file, as the tree has them."""
    found, pending = [], [_serialise_example(n) for n in build_suite(load(kms))]
    while pending:
        node = pending.pop(0)
        if node['kind'] == 'entity' and os.path.realpath(node['file']) == os.path.realpath(path):
            found.append(node)
        pending += node['children']
    return found


def _rel(target):
    return {'type': 'Relationship', 'object': target}


# --- what is removed ---------------------------------------------------------------

def test_it_goes_and_the_others_stay(kms):
    path = _case(kms, {'id': 'urn:a', 'type': 'base:Filter'}, {'id': 'urn:b', 'type': 'base:Filter'})
    model = _read(os.path.join(kms, 'model-instance.jsonld'))
    before = json.loads(_read(path))
    plan = remove_entity(load(kms), 'urn:a', file=path, check=True)
    assert json.loads(_read(path)) == before, 'only asked'
    done = remove_entity(load(kms), 'urn:a', file=path, plan=plan['plan'])
    assert done['removed'] == 'urn:a' and done['file'] == path
    assert json.loads(_read(path)) == [before[0], before[2]]
    assert _read(os.path.join(kms, 'model-instance.jsonld')) == model
    with pytest.raises(PackageError, match='any more'):
        remove_entity(load(kms), 'urn:a', file=path)


def test_the_rows_and_cards_say_which_document_they_are(kms):
    path = _case(kms, {'id': 'urn:filter:9', 'type': 'base:Filter'})
    scene = json.loads(_read(path))
    _write(path, [scene[0], 'no entity', scene[1]])    # a card's number is not its place
    read = digest_of(_read(path))
    row_places = [(r['entity'], r['position'], r['digest']) for r in _rows(kms, path)]
    cards = build_case_page(load(kms), path)['files'][0]['cards']
    assert row_places == [(c['id'], c['position'], c['digest']) for c in cards] == \
        [('urn:filter:9', 0, read), ('urn:filter:9', 2, read)]
    assert [c['position'] for c in build_model_page(load(kms))['files'][0]['cards']] == \
        [r['position'] for r in _rows(kms, os.path.join(kms, 'model-instance.jsonld'))]


def test_one_of_two_with_the_same_id(kms):
    path = _case(kms, {'id': 'urn:filter:9', 'type': 'base:Filter'})
    first, second = json.loads(_read(path))
    with pytest.raises(PackageError, match='2 times'):
        remove_entity(load(kms), 'urn:filter:9', file=path)
    row = _rows(kms, path)[1]
    done = remove_entity(load(kms), row['entity'], file=row['file'], position=row['position'], digest=row['digest'])
    assert done['remains'] and json.loads(_read(path)) == [first]
    with pytest.raises(PackageError, match='not where it was'):
        remove_entity(load(kms), 'urn:filter:9', file=path, position=1)


def test_a_file_changed_since_it_was_read(kms):
    path = _case(kms, {'id': 'urn:a', 'type': 'base:Filter'}, {'id': 'urn:a', 'type': 'base:Cartridge'})
    row = _rows(kms, path)[2]
    scene = json.loads(_read(path))
    _write(path, scene + [scene[1]])               # at its place there is still one of its id
    _write(path, [scene[0], scene[2], scene[1]])
    changed = _read(path)
    with pytest.raises(PackageError, match='has changed since it was read'):
        remove_entity(load(kms), 'urn:a', file=path, position=row['position'], digest=row['digest'])
    assert _read(path) == changed


@pytest.mark.parametrize('change', ['file', 'asserts'])
def test_changed_since_the_question(kms, change):
    path = _case(kms, {'id': 'urn:a', 'type': 'base:Filter'})
    plan = remove_entity(load(kms), 'urn:a', file=path, check=True)['plan']
    if change == 'file':
        _write(path, json.loads(_read(path)) + [{'id': 'urn:c', 'type': 'x'}])
    else:
        declared = os.path.join(os.path.dirname(path), 'expectations.yaml')
        text = _read(declared)
        with open(declared, 'w', encoding='utf-8') as handle:
            handle.write(text.replace('urn:filter:9', 'urn:a'))
    with pytest.raises(PackageError, match='changed meanwhile'):
        remove_entity(load(kms), 'urn:a', file=path, plan=plan)
    assert 'urn:a' in _ids(path)


def test_the_last_one_leaves_an_empty_list(kms):
    path = os.path.join(kms, BAD)
    done = remove_entity(load(kms), 'urn:filter:9', file=path)
    assert done['empty'] and json.loads(_read(path)) == [] and _read(path).endswith('\n')
    page = build_case_page(load(kms), path)
    assert page['files'][0]['cards'] == [] and not page['passed']
    add_entity(load(kms), 'urn:new', 'iffBaseEntities:Filter', file=path)
    assert _ids(path) == ['urn:new']


def test_a_file_of_one_object(kms):
    path = os.path.join(kms, BAD)
    _write(path, json.loads(_read(path))[0])
    assert remove_entity(load(kms), 'urn:filter:9', file=path, position=0)['empty']
    assert json.loads(_read(path)) == []


def test_the_whole_main_model_may_go(kms):
    path = os.path.join(kms, 'model-instance.jsonld')
    for identifier in _ids(path):
        done = remove_entity(load(kms), identifier, file=path)
        assert done['model']
    assert done['empty'] and build_model_page(load(kms))['summary']['entities'] == 0


def test_one_without_an_id_is_the_one_at_its_place(kms):
    path = _case(kms, {'type': 'base:Filter'}, {'id': 'urn:a', 'type': 'base:Filter'})
    row = _rows(kms, path)[1]
    done = remove_entity(load(kms), row['entity'], file=path, position=row['position'], digest=row['digest'])
    assert _ids(path) == ['urn:filter:9', 'urn:a'] and not done['pointing'] and not done['asserts']


def test_a_failed_write_leaves_the_file_as_it_was(kms, monkeypatch):
    path = _case(kms, {'id': 'urn:a', 'type': 'base:Filter'})
    before, beside = _read(path), sorted(os.listdir(os.path.dirname(path)))

    def fails(*_):
        raise OSError('disk full')
    monkeypatch.setattr(removeentity.os, 'replace', fails)
    with pytest.raises(OSError):
        remove_entity(load(kms), 'urn:a', file=path)
    assert _read(path) == before and sorted(os.listdir(os.path.dirname(path))) == beside


def test_a_linked_file_stays_a_link(kms, tmp_path):
    path = _case(kms, {'id': 'urn:a', 'type': 'base:Filter'})
    behind = str(tmp_path / 'behind.jsonld')
    shutil.move(path, behind)
    os.symlink(behind, path)
    done = remove_entity(load(kms), 'urn:a', file=path)
    assert os.path.islink(path) and _ids(behind) == ['urn:filter:9']
    assert done['file'] == path and done['real'] == behind


def test_entities_inside_a_graph_are_refused(kms):
    path = os.path.join(kms, BAD)
    scene = json.loads(_read(path))
    _write(path, {'@context': scene[0]['@context'], '@graph': scene})
    before = _read(path)
    with pytest.raises(PackageError, match='@graph'):
        remove_entity(load(kms), '(no id)', file=path, position=0)
    assert _read(path) == before


def test_a_file_that_is_not_json_is_named(kms):
    path = os.path.join(kms, BAD)
    with open(path, 'w') as handle:
        handle.write('[')
    with pytest.raises(PackageError, match='without-cartridge.jsonld is not JSON'):
        remove_entity(load(kms), 'urn:filter:9', file=path)


def test_only_files_of_the_package(kms, tmp_path):
    other = str(tmp_path / 'other.jsonld')
    _write(other, [{'id': 'urn:a', 'type': 'x'}])
    with pytest.raises(PackageError, match='no model file'):
        remove_entity(load(kms), 'urn:a', file=other)
    undeclared = os.path.join(kms, 'context.jsonld')
    with pytest.raises(PackageError, match='no model file'):
        remove_entity(load(kms), '(no id)', file=undeclared)


# --- what that touches --------------------------------------------------------------

def test_what_points_at_it_however_it_is_spelled(kms):
    path = os.path.join(kms, BAD)
    context = [json.loads(_read(path))[0]['@context'], {'p': 'urn:my:'}]
    has = 'iffBaseEntities:hasCartridge'
    _write(path, [
        {'@context': context, 'id': 'p:cut', 'type': 'base:Filter'},
        {'@context': context, 'id': 'urn:whole', 'type': 'base:Filter', has: _rel('urn:my:cut')},
        {'@context': context, 'id': 'p:short', 'type': 'base:Filter', has: _rel('p:cut')},
        {'@context': context, 'id': 'urn:sub', 'type': 'base:Filter', 'iffBaseEntities:hasState': {
            'type': 'Property', 'value': 1, has: [dict(_rel('urn:x'), datasetId='urn:d:1'),
                                                  dict(_rel(['urn:y', 'p:cut']), datasetId='urn:d:2')]}},
        {'@context': context, 'id': 'urn:none', 'type': 'base:Filter', has: _rel('p:other')}])
    plan = remove_entity(load(kms), 'p:cut', file=path, check=True)
    assert plan['pointing'] == ['p:short', 'urn:sub', 'urn:whole'] and not plan['unread'] and not plan['remains']


def test_an_id_written_again_in_another_way_remains(kms):
    path = os.path.join(kms, BAD)
    context = [json.loads(_read(path))[0]['@context'], {'p': 'urn:my:'}]
    _write(path, [{'@context': context, 'id': 'p:a', 'type': 'base:Filter'},
                  {'@context': context, 'id': 'urn:my:a', 'type': 'base:Filter'}])
    done = remove_entity(load(kms), 'p:a', file=path)
    assert done['remains'] and _ids(path) == ['urn:my:a']


def test_the_asserts_are_said_and_stay(kms):
    path = os.path.join(kms, BAD)
    declared = os.path.join(os.path.dirname(path), 'expectations.yaml')
    before = _read(declared)
    done = remove_entity(load(kms), 'urn:filter:9', file=path)
    assert done['asserts'] == ['test_FilterShape/bad/without-cartridge.jsonld']
    assert _read(declared) == before


def test_an_assert_names_the_iri_of_an_id_with_a_prefix(kms):
    path = os.path.join(kms, BAD)
    scene = json.loads(_read(path))
    scene[0]['@context'] = [scene[0]['@context'], {'f': 'urn:filter:'}]
    scene[0]['id'] = 'f:9'
    _write(path, scene)
    assert remove_entity(load(kms), 'f:9', file=path, check=True)['asserts']


def test_who_uses_the_file(kms):
    plan = remove_entity(load(kms), 'urn:cartridge:1', file=os.path.join(kms, SHARED), check=True)
    assert len(plan['cases']) == 3 and not plan['model']
    model = os.path.join(kms, 'model-instance.jsonld')
    plan = remove_entity(load(kms), 'urn:cartridge:1', file=model, check=True)
    assert plan['model'] and plan['cases'] == [] and plan['pointing'] == ['urn:filter:1']


def test_two_cases_of_one_file(kms):
    path = os.path.join(kms, BAD)
    twin = os.path.join(os.path.dirname(path), 'twin.jsonld')
    os.symlink('without-cartridge.jsonld', twin)
    with open(os.path.join(os.path.dirname(path), 'expectations.yaml'), 'a') as handle:
        handle.write('\n  - path: twin.jsonld\n    expect: invalid\n')
    plan = remove_entity(load(kms), 'urn:filter:9', file=twin, check=True)
    assert sorted(os.path.basename(c) for c in plan['cases']) == ['twin.jsonld', 'without-cartridge.jsonld']


def test_a_file_whose_context_is_not_to_be_had(kms):
    path = os.path.join(kms, BAD)
    _write(path, [{'@context': 'missing.jsonld', 'id': 'urn:a', 'type': 'x'}])
    done = remove_entity(load(kms), 'urn:a', file=path)
    assert done['unread'] and json.loads(_read(path)) == []


# --- the server --------------------------------------------------------------------

def test_the_server_removes_it(kms, monkeypatch):
    published = []
    monkeypatch.setattr(edits.validation, 'publish', lambda ls, uri, *a, **k: published.append(uri))
    path = _case(kms, {'id': 'urn:a', 'type': 'base:Filter'})
    row = _rows(kms, path)[1]
    asked = {'uri': f'file://{kms}/shacl.ttl', 'entity': 'urn:a', 'file': path, 'position': row['position'],
             'digest': row['digest']}
    plan = edits.remove_entity_feature(None, dict(asked, check=True))
    assert plan['ok'] and 'urn:a' in _ids(path) and not published
    assert edits.remove_entity_feature(None, dict(asked, plan=plan['plan']))['ok']
    assert _ids(path) == ['urn:filter:9'] and len(published) == 1
    assert 'has changed' in edits.remove_entity_feature(None, asked)['error']
    assert not edits.remove_entity_feature(None, dict(asked, uri='file:///nowhere/x'))['ok']


# --- the extension -----------------------------------------------------------------

PLAN = {'ok': True, 'file': '/pkg/c.jsonld', 'real': '/pkg/c.jsonld', 'removed': 'urn:f', 'model': False,
        'empty': False, 'remains': False, 'pointing': [], 'asserts': [], 'cases': ['a'], 'plan': 'p1', 'unread': ''}
ROW = {'raw': {'kind': 'entity', 'entity': 'urn:f', 'file': '/pkg/c.jsonld', 'position': 1, 'digest': 'd1'},
       'packageUri': 'file:///pkg/shacl.ttl'}


def _command(tmp_path, node=ROW, answer='Remove', **plan):
    seen = _drive(tmp_path, {'command': 'semforge.removeEntity', 'answer': answer, 'node': node, 'replies': {
        'semforge/removeEntity': dict(PLAN, **plan), 'semforge/model': {'roots': []}}})
    return seen, [r['params'] for r in seen['requests'] if r['method'] == 'semforge/removeEntity']


@pytest.mark.parametrize('answer, removed', [('Remove', 1), (None, 0)])
def test_it_is_asked_first(tmp_path, answer, removed):
    seen, asked = _command(tmp_path, answer=answer)
    row = {'uri': 'file:///pkg/shacl.ttl', 'entity': 'urn:f', 'file': '/pkg/c.jsonld', 'position': 1, 'digest': 'd1'}
    assert asked == [dict(row, check=True)] + [dict(row, plan='p1')] * removed
    assert seen['warnings'] == ['Remove urn:f?\nIt goes from c.jsonld, with all its attributes.']


@pytest.mark.parametrize('plan, words', [
    ({'pointing': ['urn:g', 'urn:h']}, 'Still pointing at it in this file:\nurn:g\nurn:h'),
    ({'pointing': [f'urn:{n}' for n in range(10)]}, '… and 2 more'),
    ({'asserts': ['x/bad/a.jsonld']}, 'Asserting something on it, which stays as it is:\nx/bad/a.jsonld'),
    ({'cases': ['a', 'b']}, '2 cases use this file and change:\na\nb'),
    ({'model': True, 'cases': ['a']}, 'A case uses this file and changes:\na'),
    ({'model': True}, 'That is the main model'),
    ({'empty': True}, 'No entity is left in the file'),
    ({'remains': True}, 'that definition stays'),
    ({'unread': 'no context'}, 'What points at it is not known: no context')])
def test_the_question_says_what_it_touches(tmp_path, plan, words):
    seen, _ = _command(tmp_path, answer=None, **plan)
    assert words in seen['warnings'][0]


def test_a_row_that_is_no_entity_asks_nothing(tmp_path):
    for node in ({'raw': {'kind': 'type', 'entity': 'urn:f'}}, None):
        seen, asked = _command(tmp_path, node=node)
        assert not asked and not seen['warnings'] and 'works on an entity' in seen['info'][-1]


def test_a_refusal_is_said(tmp_path):
    seen, asked = _command(tmp_path, ok=False, error='c.jsonld has changed since it was read')
    assert len(asked) == 1 and 'has changed' in seen['errors'][0] and not seen['warnings']


NODE = """
const Module = require('module');
const s = JSON.parse(process.argv[1]);
if (s.platform) { Object.defineProperty(process, 'platform', { value: s.platform }); }
const out = { asked: [], said: [], done: 0 };
const docs = (s.open || []).map((d) => ({ isDirty: d.dirty, uri: { fsPath: d.file } }));
const load = Module._load;
Module._load = (name, ...rest) => name !== 'vscode' ? load(name, ...rest) : {
  window: { showErrorMessage: async (t) => out.said.push(t), setStatusBarMessage: () => undefined,
    showWarningMessage: async () => { docs.forEach((d) => { d.isDirty = true; }); return 'Remove'; } },
  workspace: { textDocuments: docs } };
const { removeEntity } = require(process.argv[2]);
const client = { sendRequest: async (m, p) => {
  out.asked.push(p);
  const reply = s.replies[out.asked.length - 1];
  if (reply && reply.__reject) { throw new Error(reply.__reject); }
  return reply; } };
removeEntity({ client }, s.node, () => { out.done += 1; }).then(() => console.log(JSON.stringify(out)));
"""


def _alone(replies, open=(), platform=None):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    scenario = {'replies': replies, 'node': ROW, 'open': list(open), 'platform': platform}
    run = subprocess.run([node, '-e', NODE, json.dumps(scenario),
                          os.path.join(SRC, 'removeentity.js')], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_unsaved_edits_are_found_behind_links(tmp_path):
    (tmp_path / 'real.jsonld').write_text('[]')
    os.symlink(tmp_path / 'real.jsonld', tmp_path / 'link.jsonld')
    plan = dict(PLAN, file=str(tmp_path / 'link.jsonld'), real=str(tmp_path / 'real.jsonld'))
    for name in ('link.jsonld', 'real.jsonld'):
        out = _alone([plan, plan], [{'file': str(tmp_path / name), 'dirty': True}])
        assert len(out['asked']) == 1 and 'unsaved edits' in out['said'][0] and not out['done']
    out = _alone([plan, plan], [{'file': str(tmp_path / 'other.jsonld'), 'dirty': True}])
    assert len(out['asked']) == 2 and out['done'] == 1


def test_edits_made_while_it_asked_are_not_lost():
    out = _alone([PLAN, PLAN], [{'file': '/pkg/c.jsonld', 'dirty': False}])
    assert len(out['asked']) == 1 and 'unsaved edits' in out['said'][0]


def test_after_a_refusal_the_view_is_shown_anew():
    refused = {'ok': False, 'error': 'changed'}
    assert _alone([refused])['done'] == 1
    out = _alone([PLAN, refused])
    assert out['done'] == 1 and out['said'] == ['SemForge: changed']


def test_the_menu_is_on_entities_and_not_in_the_palette():
    with open(PACKAGE_JSON) as handle:
        menus = json.load(handle)['contributes']['menus']
    rows = [e for e in menus['view/item/context'] if e['command'] == 'semforge.removeEntity']
    assert [e['when'] for e in rows] == ['view == semforgeModel && viewItem == entity']
    assert [e['when'] for e in menus['commandPalette'] if e['command'] == 'semforge.removeEntity'] == ['false']


# --- the page ------------------------------------------------------------------------

def test_a_card_removes_the_one_it_shows(kms, tmp_path):
    path = _case(kms, {'id': 'urn:filter:9', 'type': 'base:Filter'})
    page = build_case_page(load(kms), path)
    card = page['files'][0]['cards'][1]
    shown = {'digest': card['digest'], 'file': path, 'position': 1, 'id': 'urn:filter:9'}
    seen = _drive(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'label': 'x', 'file': page['file'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'removeEntity', 'at': '0.1', 'value': shown},
                            {'command': 'removeEntity', 'at': '0.1', 'value': dict(shown, digest='an older page')},
                            {'command': 'removeEntity', 'at': '0.7', 'value': shown},
                            {'command': 'removeEntity', 'at': '0.1', 'value': dict(shown, position=0)},
                            {'command': 'removeEntity', 'at': '0.1', 'value': dict(shown, id='urn:other')},
                            {'command': 'removeEntity', 'at': '0.1', 'value': dict(shown, file='/elsewhere')},
                            {'command': 'removeEntity', 'at': '0.1', 'value': card['digest']}],
        'replies': {'semforge/casePage': dict(page, ok=True)}})
    ran = [e['args'][0]['raw'] for e in seen['executed'] if e['command'] == 'semforge.removeEntity']
    raw = {'kind': 'entity', 'entity': 'urn:filter:9', 'file': path, 'position': 1}
    assert ran == [dict(raw, digest=card['digest']), dict(raw, digest='an older page')]
    assert len([e for e in seen['errors'] if 'page has changed' in e]) == 4


def test_the_button_in_the_page_itself(kms, tmp_path):
    from headless_chromium import chrome

    browser = chrome()
    for page in (build_case_page(load(kms), os.path.join(kms, BAD)), build_model_page(load(kms))):
        (tmp_path / 'page.json').write_text(json.dumps(page))
        (tmp_path / 'after.js').write_text('document.querySelector("[data-removeentity]").click();')
        out = tmp_path / 'page.html'
        harness = os.path.join(SRC, '..', '..', 'tests', 'harness', 'render_casepage.js')
        subprocess.run(['node', harness, SRC, str(tmp_path / 'page.json'), str(out), str(tmp_path / 'after.js')],
                       check=True, timeout=60)
        dom = subprocess.run([browser, '--headless=new', '--no-sandbox', '--disable-gpu',
                              '--virtual-time-budget=2000', '--dump-dom', f'file://{out}'],
                             capture_output=True, text=True, timeout=120).stdout
        first = page['files'][0]['cards'][0]
        posted = json.loads(html.unescape(re.search('data-posted="([^"]*)"', dom).group(1)))
        assert [m for m in posted if m['command'] == 'removeEntity'] == [
            {'command': 'removeEntity', 'at': '0.0', 'value': {
                'digest': first['digest'], 'file': first['file'], 'position': first['position'], 'id': first['id']}}]


# --- what is read once, and checked before it is written ---------------------------

def test_a_file_changed_while_it_is_written_is_left_as_it_was(kms, monkeypatch):
    from semforge.cooked import examples

    path = _case(kms, {'id': 'urn:a', 'type': 'base:Filter'})
    meanwhile = '[]\n'
    write = examples._write

    def and_someone_else(partial, document, text):
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(meanwhile)
        return write(partial, document, text)
    monkeypatch.setattr(examples, '_write', and_someone_else)
    with pytest.raises(PackageError, match='changed while'):
        remove_entity(load(kms), 'urn:a', file=path)
    assert _read(path) == meanwhile
    assert not [n for n in os.listdir(os.path.dirname(path)) if n.endswith('.partial')]


def test_the_file_is_read_once(kms, monkeypatch):
    from semforge.package import context

    def again(*_):
        raise AssertionError('read a second time')
    monkeypatch.setattr(context, 'resolve_model_document', again)
    plan = remove_entity(load(kms), 'urn:cartridge:1', file=os.path.join(kms, 'model-instance.jsonld'), check=True)
    assert plan['unread'] == '' and plan['pointing'] == ['urn:filter:1']


def test_what_is_no_entity_does_not_count_as_one(kms):
    path = os.path.join(kms, BAD)
    _write(path, json.loads(_read(path)) + ['no entity', 7])
    assert remove_entity(load(kms), 'urn:filter:9', file=path, check=True)['empty']


def test_written_inside_another_is_no_definition_that_remains(kms):
    path = os.path.join(kms, BAD)
    context = json.loads(_read(path))[0]['@context']
    has = 'iffBaseEntities:hasCartridge'
    _write(path, [{'@context': context, 'id': 'urn:a', 'type': 'base:Filter'},
                  {'@context': context, 'id': 'urn:b', 'type': 'base:Filter',
                   has: {'type': 'Relationship', 'object': {'@id': 'urn:a', '@type': 'base:Filter'}}}])
    plan = remove_entity(load(kms), 'urn:a', file=path, check=True)
    assert not plan['remains'] and plan['pointing'] == ['urn:b']


def test_without_a_context_a_second_definition_still_remains(kms):
    path = os.path.join(kms, BAD)
    _write(path, [{'@context': 'missing.jsonld', 'id': 'urn:a', 'type': 'x'},
                  {'@context': 'missing.jsonld', 'id': 'urn:a', 'type': 'y'},
                  {'@context': 'missing.jsonld', 'id': 'urn:b', 'type': 'y'}])
    plan = remove_entity(load(kms), 'urn:b', file=path, check=True)
    assert plan['unread'] and not plan['remains']
    plan = remove_entity(load(kms), 'urn:a', file=path, position=0, check=True)
    assert plan['unread'] and plan['remains']


def test_a_request_that_fails_is_said():
    out = _alone([{'__reject': 'the server went away'}])
    assert out['said'] == ['SemForge: the server went away'] and out['done'] == 1
    out = _alone([PLAN, {'__reject': 'gone'}])
    assert out['said'] == ['SemForge: gone'] and out['done'] == 1


def test_the_published_context_is_the_package_s_own_and_what_is_written_keeps_it(kms, monkeypatch):
    from semforge.package import context

    config = context.context_config(kms)
    documents = [{'@context': config.published, 'id': 'urn:a'}, {'@context': [config.published, {'p': 'urn:p:'}]},
                 {'@context': 'other.jsonld'}, {'id': 'urn:no-context'}, 'no entity']
    own = removeentity._own_contexts(load(kms), documents)
    inline = context.local_context_value(kms, config)
    assert own[0]['@context'] == inline and own[1]['@context'] == [inline, {'p': 'urn:p:'}]
    assert own[2:] == documents[2:] and documents[0]['@context'] == config.published, 'copies'
    monkeypatch.setattr(context, 'local_context_value', lambda *_: None)
    assert removeentity._own_contexts(load(kms), documents) is documents


def test_a_page_marks_the_card_it_removes_from_as_busy(kms, tmp_path):
    from test_casepage import _render

    page = _render(tmp_path, build_case_page(load(kms), os.path.join(kms, BAD)))
    targets = re.search(r"BUSY_TARGETS = ([^;]*);", page).group(1)
    assert '[data-removeentity]' in targets


def test_unsaved_edits_are_found_by_the_name_the_editor_has(tmp_path):
    (tmp_path / 'real.jsonld').write_text('[]')
    os.symlink(tmp_path / 'real.jsonld', tmp_path / 'link.jsonld')
    # What the server calls the file behind the link need not be what Node does.
    plan = dict(PLAN, file=str(tmp_path / 'link.jsonld'), real='/as/the/server/names/it')
    out = _alone([plan, plan], [{'file': str(tmp_path / 'real.jsonld'), 'dirty': True}])
    assert len(out['asked']) == 1 and 'unsaved edits' in out['said'][0]


def test_on_windows_a_name_is_the_same_in_any_case(tmp_path):
    plan = dict(PLAN, file='C:\\Pkg\\Examples\\c.jsonld', real='C:\\Pkg\\Examples\\c.jsonld')
    open_ = [{'file': 'c:\\pkg\\examples\\C.jsonld', 'dirty': True}]
    out = _alone([plan, plan], open_, platform='win32')
    assert len(out['asked']) == 1 and 'unsaved edits' in out['said'][0]
    assert len(_alone([plan, plan], open_, platform='linux')['asked']) == 2, 'elsewhere case matters'


def test_an_assert_changed_during_the_question(kms):
    path = os.path.join(kms, BAD)
    plan = remove_entity(load(kms), 'urn:filter:9', file=path, check=True)['plan']
    declared = os.path.join(os.path.dirname(path), 'expectations.yaml')
    text = _read(declared)
    with open(declared, 'w', encoding='utf-8') as handle:
        handle.write(text.replace('MinCountConstraintComponent', 'MaxCountConstraintComponent'))
    with pytest.raises(PackageError, match='changed meanwhile'):
        remove_entity(load(kms), 'urn:filter:9', file=path, plan=plan)


# --- what points at it, what the question is checked by, other drives -------------------

def test_only_relationships_point_at_it(kms):
    path = os.path.join(kms, BAD)
    context = json.loads(_read(path))[0]['@context']
    has, state = 'iffBaseEntities:hasCartridge', 'iffBaseEntities:hasState'
    _write(path, [dict({'@context': context}, **d) for d in [
        {'id': 'urn:t', 'type': 'base:Filter'},
        {'id': 'urn:list', 'type': 'base:Filter',
         has: {'type': 'ListRelationship', 'objectList': [{'object': 'urn:t'}]}},
        {'id': 'urn:ref', 'type': 'base:Filter', has: {'type': 'ListRelationship', 'objectList': [{'@id': 'urn:t'}]}},
        {'id': 'urn:dataset', 'type': 'base:Filter', state: {'type': 'Property', 'value': 1, 'datasetId': 'urn:t'}},
        {'id': 'urn:value', 'type': 'base:Filter', state: {'type': 'Property', 'value': {'@id': 'urn:t'}}},
        {'id': 'urn:typed', 'type': 'urn:t'}]])
    assert remove_entity(load(kms), 'urn:t', file=path, check=True)['pointing'] == ['urn:list', 'urn:ref']


def test_a_graph_that_could_be_built_only_once_does_not_refuse(kms, monkeypatch):
    path = os.path.join(kms, 'model-instance.jsonld')
    left = removeentity._left

    def unread(*_):
        raise OSError('the context is not to be had')
    monkeypatch.setattr(removeentity, '_left', unread)
    plan = remove_entity(load(kms), 'urn:cartridge:1', file=path, check=True)
    assert plan['unread'] and plan['pointing'] == []
    monkeypatch.setattr(removeentity, '_left', left)
    done = remove_entity(load(kms), 'urn:cartridge:1', file=path, plan=plan['plan'])
    assert done['pointing'] == ['urn:filter:1'] and 'urn:cartridge:1' not in _ids(path)


def test_a_file_on_another_drive_is_refused_as_another_file(kms, monkeypatch):
    package = load(kms)

    def drives(paths):
        raise ValueError("Paths don't have the same drive")
    monkeypatch.setattr(removeentity.os.path, 'commonpath', drives)
    with pytest.raises(PackageError, match='no model file'):
        remove_entity(package, 'urn:filter:9', file=os.path.join(kms, BAD))


def test_a_card_click_refused_shows_page_and_view_anew(kms, tmp_path):
    path = os.path.join(kms, BAD)
    page = build_case_page(load(kms), path)
    seen = _drive(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'label': 'x', 'file': page['file'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'removeEntity', 'at': '0.0', 'value': {'id': 'urn:other'}}],
        'replies': {'semforge/casePage': dict(page, ok=True)}})
    refreshed = [e['command'] for e in seen['executed'] if e['command'] == 'semforge.refreshModel']
    assert refreshed == ['semforge.refreshModel']
    assert len([r for r in seen['requests'] if r['method'] == 'semforge/casePage']) == 2
