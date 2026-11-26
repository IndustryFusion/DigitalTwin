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

"""Pins name things, and say when the thing is gone."""

import json
import os
import shutil
import subprocess

import pytest
from semforge.editor import views
from semforge.editor.search import pins_exist

from test_tree_clicks import PACKAGE_JSON, SRC, _drive

ENT = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'
SHACL = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'


def test_a_pin_is_there_or_gone(corpus):
    case = os.path.join(corpus.examples_dir, 'test_FilterShape', 'bad', 'without-cartridge.jsonld')
    vocabulary = next(str(s) for s in corpus.knowledge.subjects() if str(s).endswith('MachineState'))
    for kind, name, extra in (('type', ENT + 'Filter', {}), ('attribute', ENT + 'Filter', {'names': ['hasStrength']}),
                              ('shape', SHACL + 'FilterShape', {}), ('query', SHACL + 'StateOnFilterShape', {}),
                              ('case', case, {}), ('entity', 'urn:filter:1', {}),
                              ('entity', 'urn:filter:9', {'file': case}), ('vocabulary', vocabulary, {}),
                              ('model', 'main', {})):
        pin = dict({'kind': kind, 'id': name, 'names': [], 'file': ''}, **extra)
        assert pins_exist(corpus, [pin]) == [True], pin
        if kind != 'model':
            gone = dict(pin, id=name + 'x')
            assert pins_exist(corpus, [gone]) == [False], gone
    assert pins_exist(corpus, [{'kind': 'attribute', 'id': ENT + 'Filter', 'names': ['hasNo'], 'file': ''}]) == [False]


def test_the_server_answers_in_order_and_says_when_the_package_is_gone(corpus):
    uri = f'file://{corpus.path}/shacl.ttl'
    said = views.pins_exist_feature(None, {'uri': uri, 'pins': [
        {'kind': 'type', 'id': 'no'}, {'kind': 'model', 'id': 'main'}]})
    assert said == {'ok': True, 'exist': [False, True]}
    assert views.pins_exist_feature(None, {'uri': 'file:///nowhere/x.ttl', 'pins': []})['gone']


# --- in the editor ----------------------------------------------------------------------

NODE = {'raw': {'kind': 'type', 'label': 'Filter', 'targetClass': ENT + 'Filter', 'children': []},
        'packageUri': 'file:///pkg/shacl.ttl'}


def test_the_star_and_the_key_are_there():
    import json

    with open(PACKAGE_JSON) as handle:
        contributes = json.load(handle)['contributes']
    title = {e['command']: e['when'] for e in contributes['menus']['editor/title'] if 'command' in e}
    assert 'pagePinned' in title['semforge.pinPage'] and 'pagePinned' in title['semforge.unpinPage']
    key = next(k for k in contributes['keybindings'] if k['command'] == 'semforge.bookmarks')
    # Ctrl+Alt+B / ⌥⌘B toggles VS Code's secondary side bar: only SemForge's own places.
    assert 'focusedView' in key['when'] and 'activeWebviewPanelId' in key['when']
    rows = ' '.join(e['when'] for e in contributes['menus']['view/item/context'] if e['command'] == 'semforge.pin')
    for view in ('semforgeModel', 'semforgeConstraints', 'semforgeShapes', 'semforgeKnowledge'):
        assert view in rows
    constraints = next(e['when'] for e in contributes['menus']['view/item/context']
                       if e['command'] == 'semforge.pin' and 'semforgeConstraints' in e['when'])
    assert 'inherited' in constraints and 'shape' in constraints, 'inherited rows and shapes too'
    assert any(e['command'] == 'semforge.pin' and 'semforgeEntity' in e['when']
               for e in contributes['menus']['webview/context'])


def test_nothing_pinned_says_how(tmp_path):
    seen = _drive(tmp_path, {'command': 'semforge.bookmarks', 'replies': {}})
    assert any('nothing is pinned yet' in text for text in seen['info'])


def test_a_row_is_pinned_and_nothing_else_is(tmp_path):
    assert _drive(tmp_path, {'command': 'semforge.pin', 'node': NODE, 'replies': {}})['errors'] == []
    seen = _drive(tmp_path, {'command': 'semforge.pin', 'node': {'raw': {'kind': 'group', 'label': 'Tests'}},
                             'replies': {}})
    assert any('right-click a row or an id' in text for text in seen['info'])


# --- what a rename takes along ----------------------------------------------------------

RENAMES = """
const Module = require('module');
const real = Module._load;
const said = [];
Module._load = (name, ...rest) => name === 'vscode' ? {
  commands: { executeCommand: async () => {}, registerCommand: () => ({}) },
  window: { setStatusBarMessage: (text) => said.push(text) } } : real(name, ...rest);
const pins = require(process.argv[1]);
const [pkg] = process.argv.slice(2);
const uri = `file://${pkg}/shacl.ttl`;
const suite = `${pkg}/examples/test_A`;
const at = (name) => `${suite}/bad/${name}.jsonld`;
(async () => {
  pins.register({ subscriptions: [] }, {}, { uri }, {});
  const pin = (fields) => pins.toggle(Object.assign({ packageUri: uri }, fields));
  await pin({ kind: 'shape', id: 'x:AShape', label: 'AShape' });
  await pin({ kind: 'query', id: 'x:AShape', label: 'the state is ON' });
  await pin({ kind: 'case', id: at('one'), label: 'one' });
  await pin({ kind: 'entity', id: 'urn:e:1', label: 'urn:e:1', file: at('one'), where: 'one' });
  await pin({ kind: 'entity', id: 'urn:e:2', label: 'urn:e:2', file: at('two'), where: 'two' });
  await pin({ kind: 'shape', id: 'x:AShape', label: 'AShape', packageUri: 'file:///elsewhere/shacl.ttl' });
  const twice = await pin({ kind: 'shape', id: 'x:AShape', label: 'again' });
  await pin({ kind: 'shape', id: 'x:AShape', label: 'AShape' });
  await pins.renamed(uri, 'x:BShape', 'x:CShape', 'CShape');
  await pins.renamed(uri, 'x:AShape', 'x:BShape', 'BShape');
  await pins.renamed(uri, at('one'), at('uno'), 'uno');
  await pins.renamed(uri, suite, `${pkg}/examples/test_B`);
  console.log(JSON.stringify({ twice, pins: pins.read(pins.PINS) }));
})();
"""


def test_a_rename_takes_the_pins_along(tmp_path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    out = subprocess.run([node, '-e', RENAMES, os.path.join(SRC, 'bookmarks.js'), str(tmp_path)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    seen = json.loads(out.stdout)
    assert seen['twice'] is False, 'pinned again is unpinned: one pin per thing'
    moved = str(tmp_path / 'examples' / 'test_B' / 'bad')
    said = [(p['kind'], p['id'], p['label'], p.get('file'), p.get('where'), p['packageUri'].startswith(
        f'file://{tmp_path}')) for p in seen['pins']]
    assert said == [
        ('query', 'x:BShape', 'the state is ON', None, None, True),
        ('case', f'{moved}/uno.jsonld', 'uno', None, None, True),
        ('entity', 'urn:e:1', 'urn:e:1', f'{moved}/uno.jsonld', 'uno', True),
        ('entity', 'urn:e:2', 'urn:e:2', f'{moved}/two.jsonld', 'two', True),
        ('shape', 'x:AShape', 'AShape', None, None, False),
        ('shape', 'x:BShape', 'BShape', None, None, True)]


def test_an_edit_above_leaves_the_pin_on_its_shape(corpus, tmp_path):
    import shutil as copying

    from semforge.package import load

    root = tmp_path / 'kms'
    copying.copytree(corpus.path, root, ignore=copying.ignore_patterns('.semforge'))
    text = (root / 'shacl.ttl').read_text()
    (root / 'shacl.ttl').write_text('# a line\n' * 40 + text)
    assert pins_exist(load(str(root)), [{'kind': 'shape', 'id': SHACL + 'FilterShape', 'names': [],
                                         'file': ''}]) == [True]


LIST = """
const Module = require('module');
const real = Module._load;
const shown = [];
let pick;
Module._load = (name, ...rest) => name === 'vscode' ? {
  commands: { executeCommand: async () => {}, registerCommand: (id, fn) => { commands[id] = fn; return {}; } },
  window: { setStatusBarMessage: () => {}, showInformationMessage: async (text) => shown.push(text),
    createQuickPick: () => { pick = { handlers: {}, items: [], show() {}, hide() { this.handlers.hide(); },
      dispose() {}, onDidTriggerItemButton(fn) { this.handlers.button = fn; },
      onDidAccept(fn) { this.handlers.accept = fn; },
      onDidHide(fn) { this.handlers.hide = fn; } }; return pick; } },
  ThemeIcon: function ThemeIcon(id) { this.id = id; },
  QuickPickItemKind: { Separator: -1 } } : real(name, ...rest);
const commands = {};
const pins = require(process.argv[1]);
const uri = `file://${process.argv[2]}/shacl.ttl`;
const labels = () => pick.items.map((i) => i.label + (i.description ? ` [${i.description}]` : ''));
(async () => {
  const views = { type: { async show() { this.page = { iri: 'x:T', label: 'T' }; }, current: { packageUri: uri } },
    case: { current: { packageUri: uri }, page: { kind: 'case', file: '/p/examples/s/bad/c.jsonld' } } };
  pins.register({ subscriptions: [] }, {}, { uri }, views);
  const onPage = pins.ofNode({ entity: 'urn:e:1', webview: 'semforgeCasePage' });
  await commands['semforge.bookmarks']();
  const empty = shown.slice();
  await views.type.show();                       // visited: a recent place
  await pins.toggle({ kind: 'shape', id: 'x:S', label: 'S', packageUri: uri });
  const listed = commands['semforge.bookmarks']();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const before = labels();
  const recent = pick.items.find((i) => i.pin && i.pin.id === 'x:T');
  await pick.handlers.button({ item: recent, button: recent.buttons[0] });
  const after = labels();
  pick.hide();
  await listed;
  console.log(JSON.stringify({ empty, before, after, onPage }));
})();
"""


def test_the_list_without_a_server_and_a_recent_place_pinned_from_it(tmp_path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    out = subprocess.run([node, '-e', LIST, os.path.join(SRC, 'bookmarks.js'), str(tmp_path)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    seen = json.loads(out.stdout)
    assert 'nothing is pinned yet' in seen['empty'][0]
    # No language server: nothing is said to be gone.
    assert seen['before'] == ['pinned', '$(symbol-interface) S [shape]', 'recent',
                              '$(symbol-class) T [entity type]']
    assert seen['after'] == ['pinned', '$(symbol-interface) S [shape]', '$(symbol-class) T [entity type]'], \
        'pinned from the list, and no empty "recent" under it'
    # An id on a test case's page: that entity, in that case.
    assert {k: seen['onPage'][k] for k in ('kind', 'id', 'file', 'where')} == {
        'kind': 'entity', 'id': 'urn:e:1', 'file': '/p/examples/s/bad/c.jsonld', 'where': 'c'}


NODES = """
const Module = require('module');
const real = Module._load;
const ran = [];
Module._load = (name, ...rest) => name === 'vscode' ? {
  commands: { executeCommand: async (...args) => ran.push(args), registerCommand: (id, fn) => { commands[id] = fn; } },
  window: { setStatusBarMessage: () => {} } } : real(name, ...rest);
const commands = {};
const pins = require(process.argv[1]);
const uri = `file://${process.argv[2]}/shacl.ttl`;
(async () => {
  let shown = 0;
  const views = { type: { current: { packageUri: uri }, page: { iri: 'x:A', label: 'A' },
    async show(fail) { shown += 1; if (!fail) { this.page = { iri: `x:${shown}`, label: String(shown) }; } } } };
  pins.register({ subscriptions: [] }, {}, { uri }, views);
  await views.type.show(true);                   // did not render: still A
  await views.type.show(false);
  const recent = pins.read(pins.RECENT).map((p) => p.id);
  const node = (raw) => pins.ofNode({ raw, packageUri: uri });
  const constraint = node({ kind: 'rule', shape: 'x:S', queryKind: 'constraint', label: 'q' });
  const rule = node({ kind: 'rule', shape: 'x:S', queryKind: 'rule', label: 'r' });
  await pins.toggle(constraint);
  await pins.toggle(rule);
  const both = pins.read(pins.PINS).length;
  const attribute = node({ kind: 'attribute', label: 'hasFilter', path: ['<https://x/hasFilter>'], typeClass: 'x:T' });
  const root = node({ kind: 'example', label: 'model-instance.jsonld' });
  console.log(JSON.stringify({ recent, distinct: pins.keyOf(constraint) !== pins.keyOf(rule), both,
    names: attribute.names, root: [root.kind, root.id] }));
})();
"""


def test_queries_of_one_shape_paths_as_iris_and_model_files(tmp_path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    out = subprocess.run([node, '-e', NODES, os.path.join(SRC, 'bookmarks.js'), str(tmp_path)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    seen = json.loads(out.stdout)
    assert seen['recent'] == ['x:2'], 'a page that did not render is not a place visited'
    assert seen['distinct'] and seen['both'] == 2, 'a constraint and a rule of one shape are two pins'
    assert seen['names'] == ['hasFilter'], 'a path written as <IRI>'
    assert seen['root'] == ['model', 'main'], "a model file's row is the Main page"


def test_an_entity_of_a_deleted_case_is_gone_and_severity_is_there(corpus, tmp_path):
    case = os.path.join(corpus.examples_dir, 'test_FilterShape', 'bad', 'without-cartridge.jsonld')
    gone = str(tmp_path / 'deleted.jsonld')
    assert pins_exist(corpus, [
        {'kind': 'entity', 'id': 'urn:filter:1', 'names': [], 'file': gone},
        {'kind': 'entity', 'id': 'urn:filter:1', 'names': [], 'file': ''},
        {'kind': 'entity', 'id': 'urn:filter:9', 'names': [], 'file': case},
        {'kind': 'vocabulary', 'id': 'http://www.w3.org/ns/shacl#Severity', 'names': [], 'file': ''}]) == [
        False, True, True, True]
