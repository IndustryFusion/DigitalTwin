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

"""Search…: the views show only what fits; a file leads back to its page."""

import json
import os
import shutil
import subprocess

import pytest

from semforge.editor import views
from semforge.editor.search import page_at, prune
from semforge.package import load

from test_tree_clicks import PACKAGE_JSON, SRC, _drive, _opened

ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
SHACL = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'


@pytest.fixture
def root(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _rows(nodes):
    for node in nodes:
        yield node
        yield from _rows(node.get('children') or [])


def _search(root, feature, text, detail='summary'):
    return getattr(views, feature)(None, {'uri': f'file://{root}/shacl.ttl', 'detail': detail,
                                          'search': text})


# --- the views --------------------------------------------------------------------------

def test_only_what_fits_and_what_it_is_under():
    tree = [{'kind': 'type', 'label': 'Machine', 'children': [
        {'kind': 'attribute', 'label': 'hasState', 'detail': 'state_ON', 'children': []},
        {'kind': 'attribute', 'label': 'hasPower', 'detail': 'number', 'children': []}]},
        {'kind': 'type', 'label': 'Filter', 'detail': 'a hasState count', 'children': []}]
    kept, count = prune(tree, 'STATE has')
    assert count == 1 and len(kept) == 1, 'a count ("3 attribute(s)") is nothing a row says'
    assert kept[0]['expand'] and [c['label'] for c in kept[0]['children']] == ['hasState']
    assert kept[0]['children'][0]['hit'] and 'hit' not in kept[0]
    # A fitting row without fitting rows keeps its own, closed.
    kept, _ = prune(tree, 'machine')
    assert len(kept[0]['children']) == 2 and not kept[0].get('expand')
    assert prune(tree, '  ') == (tree, 0)
    assert prune(tree, 'no such') == ([], 0)


def test_a_count_is_nothing_a_row_says():
    tree = [{'kind': 'type', 'label': 'Machine', 'detail': '3 attribute(s)', 'children': []},
            {'kind': 'carrier', 'label': 'Slots', 'detail': '3 attribute(s)', 'children': []},
            {'kind': 'example', 'label': 'Main', 'detail': '12 entities · 2 violation(s)', 'children': []},
            {'kind': 'attribute', 'label': 'hasState', 'detail': '1 violation(s)', 'children': []}]
    for text in ('attribute(s)', 'attribute', 'entities', 'violation'):
        assert prune(tree, text) == ([], 0), text
    # What a description says beside a count still fits.
    tree[2]['detail'] = '12 entities · from main.jsonld'
    assert prune(tree, 'main.jsonld')[1] == 1


def test_hidden_rows_are_still_named_for_the_edits():
    state = {'kind': 'attribute', 'label': 'hasState', 'shape': 'x:S', 'attributePath': ['x:hasState'],
             'datasetId': '@none', 'datasets': ['@none'], 'value': 'ON', 'children': [{'kind': 'meta', 'label': 'x'}]}
    tree = [{'kind': 'entity', 'label': 'urn:m:1', 'children': [
        state, {'kind': 'attribute', 'label': 'hasPower', 'file': 'm.jsonld', 'children': []}]}]
    [kept], _ = prune(tree, 'hasPower')
    assert [c['label'] for c in kept['children']] == ['hasPower']
    assert kept['all'] == [{key: state[key] for key in (
        'kind', 'label', 'shape', 'attributePath', 'datasetId', 'datasets')},
        {'kind': 'attribute', 'label': 'hasPower', 'file': 'm.jsonld'}]
    for text in ('has', 'urn:m:1'):
        assert 'all' not in prune(tree, text)[0][0], 'nothing is hidden'


@pytest.mark.parametrize('detail', ['summary', 'full'])
def test_an_attribute_is_found_in_all_four_areas(root, detail):
    for feature in ('cooked_tree', 'model', 'shapes_feature', 'knowledge'):
        found = _search(root, feature, 'hasStrength', detail)
        assert found.get('error') is None and found['matches'], (feature, found)
        assert any(n.get('hit') for n in _rows(found['roots'])), feature
    shapes = _search(root, 'shapes_feature', 'hasStrength', detail)['roots']
    assert {n['shape'] for n in shapes} >= {SHACL + 'FilterShape'}
    assert all('hasStrength' in n['detail'] for n in shapes), 'the row says why it is here'


def test_a_listed_value_finds_the_shape_that_lists_it(root):
    from semforge.cooked.valueforms import edit_value

    edit_value(load(root), SHACL + 'FilterShape', ['iffBaseEntities:hasStrength'], {
        'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:in',
        'value': [{'kind': 'text', 'text': 'Executing'}]})
    assert [n['shape'] for n in _search(root, 'shapes_feature', 'executing')['roots']] == \
        [SHACL + 'FilterShape']
    hits = [n for n in _rows(_search(root, 'cooked_tree', 'executing')['roots']) if n.get('hit')]
    assert [n['label'] for n in hits] == ['hasStrength']
    assert _search(root, 'knowledge', 'executing')['matches'] == 0


def test_in_full_form_a_value_fits_the_rows_of_its_own_attribute(root):
    from semforge.cooked.valueforms import edit_value

    edit_value(load(root), SHACL + 'FilterShape', ['iffBaseEntities:hasStrength'], {
        'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:in',
        'value': [{'kind': 'text', 'text': 'Executing'}]})
    for feature in ('cooked_tree', 'shapes_feature'):
        hits = [n for n in _rows(_search(root, feature, 'executing', 'full')['roots']) if n.get('hit')]
        assert hits and all('hasStrength' in json.dumps(n.get('path')) or n.get('kind') == 'shape'
                            for n in hits), (feature, [(n['kind'], n['label']) for n in hits])
        # Before, every parameter row of every attribute of the shape fitted.
        rows = [n for n in _rows(_search(root, feature, 'FilterShape', 'full')['roots'])
                if n.get('shape') == SHACL + 'FilterShape']
        assert feature == 'shapes_feature' or len(hits) < len(rows), feature


def test_an_expectations_file_through_a_link_names_cases_where_it_is(root, tmp_path):
    case = os.path.join(root, 'examples', 'test_FilterShape', 'bad')
    declared = os.path.join(case, 'expectations.yaml')
    elsewhere = tmp_path / 'elsewhere.yaml'
    shutil.move(declared, elsewhere)
    os.symlink(elsewhere, declared)
    found = page_at(load(root), declared, _line(declared, 'without-cartridge') + 1)
    assert found['file'] == os.path.join(case, 'without-cartridge.jsonld')


def test_a_case_is_found_by_what_it_asserts(root):
    found = _search(root, 'model', 'hasCartridge MinCount')
    assert 'without-cartridge.jsonld' in [n['label'] for n in _rows(found['roots']) if n.get('hit')]


def test_an_entity_is_of_its_type_its_attributes_are_not(root):
    hits = [n for n in _rows(_search(root, 'model', 'FilterCartridge')['roots']) if n.get('hit')]
    assert any(n['kind'] == 'entity' for n in hits)
    assert not any(n['kind'] == 'attribute' and n['label'] == 'isUsedFrom' for n in hits)


def test_without_a_search_nothing_changes(root):
    found = _search(root, 'shapes_feature', '')
    assert 'search' not in found and len(found['roots']) > 2


# --- back from a file ---------------------------------------------------------------------

def _line(path, text):
    with open(path, encoding='utf-8') as handle:
        return next(i for i, said in enumerate(handle, 1) if text in said)


def test_a_line_of_the_shapes_is_its_shapes_page(root):
    path = os.path.join(root, 'shacl.ttl')
    at = _line(path, 'iffBaseEntities:hasStrength')
    assert page_at(load(root), path, at) == {'page': 'shape', 'shape': SHACL + 'FilterShape'}


def test_a_line_of_the_knowledge_is_the_page_of_its_term(root):
    path = os.path.join(root, 'knowledge.ttl')
    package = load(root)
    index = package.index('knowledge')

    def found(iri):
        return page_at(package, path, index.block_for(iri)[1].start_line)
    assert found(ENT + 'Filter') == {'page': 'type', 'targetClass': ENT + 'Filter'}
    strength = found(ENT + 'hasStrength')
    assert strength == {'page': 'type', 'targetClass': ENT + 'Filter', 'focusNames': ['hasStrength']}
    state = next(str(s) for s in package.knowledge.subjects() if str(s).endswith('state_ON'))
    individual = found(state)
    assert individual['page'] == 'vocabulary' and individual['focus'] == state
    assert individual['cls'].endswith('MachineState')
    assert found(individual['cls']) == {'page': 'vocabulary', 'cls': individual['cls']}


def test_a_line_of_the_data_is_its_entity(root):
    model = os.path.join(root, 'model-instance.jsonld')
    assert page_at(load(root), model, _line(model, '"id": "urn:filter:1"')) == {
        'page': 'model', 'focus': 'urn:filter:1'}
    case = os.path.join(root, 'examples', 'test_FilterShape', 'bad', 'without-cartridge.jsonld')
    assert page_at(load(root), case, _line(case, '"id": "urn:filter:9"')) == {
        'page': 'case', 'file': case, 'focus': 'urn:filter:9'}
    declared = os.path.join(os.path.dirname(case), 'expectations.yaml')
    assert page_at(load(root), declared, _line(declared, 'without-cartridge') + 1)['file'] == case
    shared = os.path.join(root, 'examples', 'subobjects', 'cartridge-fresh.jsonld')
    assert page_at(load(root), shared, 3)['page'] == 'case', 'a file cases include: the first of them'


def test_an_unsaved_line_is_one_of_the_text_shown(root):
    path = os.path.join(root, 'shacl.ttl')
    at = _line(path, 'iffBaseEntities:hasStrength')
    with open(path, encoding='utf-8') as handle:
        text = '# one more\n' * 500 + handle.read()
    expected = {'page': 'shape', 'shape': SHACL + 'FilterShape'}
    assert page_at(load(root), path, at + 500, text=text) == expected
    assert page_at(load(root), path, at + 500) != expected
    said = views.page_at_feature(None, {'uri': f'file://{path}', 'line': at + 500, 'text': text})
    assert said == dict(expected, ok=True)
    model = os.path.join(root, 'model-instance.jsonld')
    with open(model, encoding='utf-8') as handle:
        text = '\n' * 100 + handle.read()
    found = page_at(load(root), model, _line(model, '"id": "urn:filter:1"') + 100, text=text)
    assert found == {'page': 'model', 'focus': 'urn:filter:1'}
    declared = os.path.join(root, 'examples', 'test_FilterShape', 'bad', 'expectations.yaml')
    assert page_at(load(root), declared, 2, 'word', text='examples: [') == {'page': 'search', 'text': 'word'}
    # Half-typed JSON: the page, at no entity.
    assert page_at(load(root), model, 1, text='[{') == {'page': 'model', 'focus': None}


def test_a_line_about_nothing_with_a_page_is_searched_for(root):
    path = os.path.join(root, 'shacl.ttl')
    assert page_at(load(root), path, 1, 'iffBaseEntities:hasState') == {
        'page': 'search', 'text': 'hasState'}
    assert page_at(load(root), path, 1, 'iffBaseEntities:hasState.')['text'] == 'hasState'
    answer = views.page_at_feature(None, {'uri': 'file:///nowhere/x.ttl', 'line': 1})
    assert not answer['ok']
    assert views.page_at_feature(None, {'uri': f'file://{path}', 'line': 1})['ok']


# --- in the editor -------------------------------------------------------------------------

def test_every_view_offers_the_search_and_every_file_the_way_back():
    with open(PACKAGE_JSON) as handle:
        contributes = json.load(handle)['contributes']
    menus = contributes['menus']
    for view in ('semforgeModel', 'semforgeConstraints', 'semforgeShapes', 'semforgeKnowledge'):
        for command in ('semforge.search', 'semforge.clearSearch'):
            assert any(e.get('command') == command and view in e['when'] for e in menus['view/title'])
    for menu in ('editor/title', 'editor/context'):
        entry = next(e for e in menus[menu] if e.get('command') == 'semforge.openHere')
        assert '.ttl' in entry['when'] and '.jsonld' in entry['when']
    key = next(k for k in contributes['keybindings'] if k['command'] == 'semforge.search')
    assert key['when'] == '!editorTextFocus', "outside an editor: Cmd+Alt+F is VS Code's Replace on a Mac"


def test_open_in_semforge_needs_a_file(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.openHere', 'replies': {}})
    assert seen['warnings'] and _opened(seen, 'semforge.openShapePage') == []


def test_an_attribute_whose_row_is_hidden_is_still_taken(tmp_path):
    """Adding an attribute the entity has, with that row hidden by the search,
    wrote a second default instance without a time."""
    strength = ENT + 'hasStrength'
    node = {'packageUri': 'file:///pkg/shacl.ttl', 'raw': {
        'kind': 'entity', 'label': 'urn:m:1', 'entity': 'urn:m:1', 'entityType': ENT + 'Filter',
        'file': 'case.jsonld', 'children': [],
        'all': [{'kind': 'attribute', 'attributePath': [strength], 'datasetId': '@none'}]}}
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute', 'node': node, 'picks': [strength, 'Default instance'],
        'replies': {'semforge/attributes': {'attributes': [{'term': strength, 'kind': 'Property'}]},
                    'semforge/vocabularyNamespaces': {'namespaces': []}}})
    default = next(i for i in seen['quickPicks'][1]['items'] if i['label'] == 'Default instance')
    assert 'another observation' in default['description']
    assert '$(clock) Now' in [i['label'] for i in seen['quickPicks'][2]['items']], 'asked for its time'


MESSAGE = """
const Module = require('module');
const real = Module._load;
const runs = {};
Module._load = (name, ...rest) => name === 'vscode' ? {
  commands: { executeCommand: async () => {}, registerCommand: (id, fn) => { runs[id] = fn; } },
  TreeItemCollapsibleState: { None: 0, Collapsed: 1, Expanded: 2 } } : real(name, ...rest);
const search = require(process.argv[1]);
(async () => {
  const before = search.message('shapes', { roots: [] }, 'own');
  let drawn = 0;
  search.register({ subscriptions: [] }, {}, () => { drawn += 1; });
  await search.set(' Filter ');
  await search.set('Filter');
  const said = [search.message('shapes', { search: 'Filter', matches: 2 }, 'own'),
    search.message('shapes', { search: 'Filter' }), search.message('shapes', { search: 'Fil', matches: 9 })];
  const item = (raw, state) => search.decorate({ collapsibleState: state }, raw);
  const rows = [item({ searchId: '0', expand: true }, 1), item({ searchId: '1' }, 2), item({ searchId: '2' }, 0)];
  said.push(search.message('shapes', { roots: [] }));
  const asked = search.params({ uri: 'u' });
  await runs['semforge.clearSearch']();
  console.log(JSON.stringify({ before, said, rows, asked, drawn, after: search.params({ uri: 'u' }),
    plain: item({ searchId: '0' }, 1) }));
})();
"""


def test_a_view_says_how_many_fit_and_opens_down_to_them():
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run([node, '-e', MESSAGE, os.path.join(SRC, 'search.js')],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    seen = json.loads(out.stdout)
    assert seen['before'] == 'own'
    assert seen['said'][:2] == ['Search “Filter”: 2 found. own', 'Search “Filter”: nothing here.']
    assert len(seen['said']) == 4 and seen['said'][2] is None, 'the answer to an earlier text'
    assert 'does not filter' in seen['said'][3], 'an older server says nothing of a search'
    assert [r['collapsibleState'] for r in seen['rows']] == [2, 1, 0]
    assert len({r['id'] for r in seen['rows']}) == 3
    assert seen['asked'] == {'uri': 'u', 'search': 'Filter'} and seen['after'] == {'uri': 'u'}
    assert seen['drawn'] == 2 and 'id' not in seen['plain']


def test_add_attribute_on_a_type_goes_by_its_hidden_shapes_too(tmp_path):
    """A search that leaves only an inherited shape under a type made Add
    attribute… create a new shape although the type has its own."""
    created = {'ok': True, 'iri': 'https://x/New', 'name': 'ex:New'}
    seen = _drive(tmp_path, {
        'command': 'semforge.addTypeAttribute',
        'node': {'raw': {'kind': 'type', 'label': 'Watercutter', 'targetClass': 'https://x/Watercutter',
                         'children': [{'kind': 'shape', 'label': 'ex:CutterShape', 'shape': 'https://x/CutterShape',
                                       'inheritedFrom': 'Cutter', 'children': []}],
                         'all': [{'kind': 'shape', 'label': 'ex:CutterShape', 'shape': 'https://x/CutterShape',
                                  'inheritedFrom': 'Cutter'},
                                 {'kind': 'shape', 'label': 'ex:WatercutterShape',
                                  'shape': 'https://x/WatercutterShape'}]},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'commandResults': {'semforge.newShape': created}, 'replies': {}})
    assert seen['errors'] == [], seen['errors']
    assert _opened(seen, 'semforge.newShape') == []
    assert _opened(seen, 'semforge.addAttributeConstraint')[0][0]['raw']['shape'] == 'https://x/WatercutterShape'
