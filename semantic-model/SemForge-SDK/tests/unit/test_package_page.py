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

"""The package page, and views named for what they show.

A setting was the last row whose click opened a file: kms.yaml, the
comment above the key as the only explanation. The page shows each setting
with what it decides and Edit… beside it; the file is its Open button.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')


def _node(tmp_path, scenario, target):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, target), str(path)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope='module')
def payload(corpus):
    from semforge.cooked.project import build_project
    from semforge.editor.views import _serialise_project

    return {'root': corpus.path,
            'roots': [_serialise_project(n) for n in build_project(corpus)]}


def _render(tmp_path, payload, focus=None):
    page = dict(payload, manifest=os.path.join(payload['root'], 'kms.yaml'))
    return _node(tmp_path, {'mode': 'render', 'function': 'renderPackagePage', 'payload': page,
                            'options': {'nonce': 'n', 'focus': focus}}, 'packagepage.js')['html']


def _rows(payload):
    out = []

    def walk(row):
        out.append(row)
        for child in row['children']:
            walk(child)
    for root in payload['roots']:
        walk(root)
    return out


def test_each_setting_says_what_it_decides_with_edit_beside_it(tmp_path, payload):
    import html as markup

    html = _render(tmp_path, payload)
    text = markup.unescape(html)
    settings = [r for r in _rows(payload) if r['kind'] == 'setting']
    assert settings
    for row in settings:
        assert row['label'] in text
        assert (row['detail'] or row['doc']) in text, row['label']
    editable = [r for r in settings if r['editable']]
    assert html.count('data-act="edit"') == len(editable)
    assert '+ Namespace</button>' in html


def test_the_file_is_a_button_and_nothing_else_opens_it(tmp_path, payload):
    html = _render(tmp_path, payload)
    opens = re.findall(r'<button[^>]*data-open="[^"]*"[^>]*>([^<]*)</button>', html)
    assert opens == ['Open kms.yaml']
    assert html.count('data-open=') == 1


def test_a_setting_clicked_in_the_view_is_marked(tmp_path, payload):
    html = _render(tmp_path, payload, focus={'key': 'context.published'})
    assert html.count('id="focus"') == 1
    row = html.split('id="focus"', 1)[1].split('</tr>', 1)[0]
    assert 'published context' in row


def test_a_click_in_the_package_view_opens_the_page(tmp_path):
    seen = _node(tmp_path, {
        'mode': 'select', 'view': 'semforgeProject', 'config': {},
        'node': {'key': 'root/0', 'raw': {'kind': 'setting', 'label': 'published context',
                                          'key': 'context.published', 'children': [],
                                          'definedAt': '/pkg/kms.yaml:11'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/project': {'roots': []}, 'semforge/health': {'ok': False}}},
        'extension.js')
    opened = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openPackagePage']
    assert opened and opened[0][0]['raw']['key'] == 'context.published'
    assert seen['shown'] == []


def test_edit_on_the_page_runs_the_view_s_own_command(tmp_path, payload):
    rows = _rows(payload)
    index = next(i for i, r in enumerate(rows) if r.get('key') == 'context.published')
    seen = _node(tmp_path, {
        'command': 'semforge.openPackagePage', 'node': {'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'edit', 'row': index}],
        'replies': {'semforge/project': payload}}, 'extension.js')
    assert seen['errors'] == [], seen['errors']
    edited = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.editSetting']
    assert edited[0][0]['raw']['key'] == 'context.published'
    assert len([r for r in seen['requests'] if r['method'] == 'semforge/project']) == 2, \
        'the page shows what was written'


def test_the_views_are_named_for_what_they_show():
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        views = json.load(handle)['contributes']['views']
    assert {v['id']: v['name'] for group in views.values() for v in group} == {
        'semforgeProject': 'Package',
        'semforgeConstraints': 'Constraints by Type',
        'semforgeShapes': 'SHACL Shapes as Written',
        'semforgeModel': 'Entities & Test Cases',
        'semforgeKnowledge': 'Knowledge (Ontology)',
    }


def test_the_details_stay_away_until_asked_for():
    """The main column is the package and its data. The constraints, shapes
    and knowledge are a second container shown under one context key, which
    "Show details" sets and "Hide details" clears."""
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        contributes = json.load(handle)['contributes']
    details = contributes['views']['semforgeDetails']
    assert {v.get('when') for v in details} == {'semforge.details'}
    assert 'semforgeDetails' in {c['id'] for c in contributes['viewsContainers']['activitybar']}
    shown = [e for e in contributes['menus']['view/title']
             if e.get('command') == 'semforge.showDetails']
    assert [e['when'] for e in shown] == ['view == semforgeProject && !semforge.details']
    hidden = {e['when'] for e in contributes['menus']['view/title']
              if e.get('command') == 'semforge.hideDetails'}
    assert hidden == {f'view == {v["id"]}' for v in details}


def test_what_a_view_is_is_a_hover_not_a_paragraph(tmp_path):
    """Each view said what it is in a paragraph at its top, always, in a column
    with little room. It is the hover of an ⓘ in its title bar now -- the
    command's title -- and the message is left for what is wrong."""
    seen = _node(tmp_path, {
        'mode': 'select', 'view': 'semforgeProject', 'config': {},
        'node': {'key': 'root/0', 'raw': {'kind': 'health', 'label': 'Health', 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/project': {'roots': []}, 'semforge/health': {'ok': False}}},
        'extension.js')
    said = {view: (seen['views'].get(view) or {}).get('message') for view in (
        'semforgeProject', 'semforgeConstraints', 'semforgeShapes', 'semforgeModel',
        'semforgeKnowledge')}
    assert not any(said.values()), said

    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    stub = tmp_path / 'node_modules' / 'vscode'
    stub.mkdir(parents=True)
    (stub / 'index.js').write_text('module.exports = {};')
    out = subprocess.run(
        [node, '-e', 'const s = require(process.argv[1]); console.log(JSON.stringify('
         'Object.entries(s.ABOUT).map(([v, t]) => [s.aboutCommand(v), v, t])))',
         os.path.join(SRC, 'sidebar.js')],
        capture_output=True, text=True, timeout=60,
        env=dict(os.environ, NODE_PATH=str(tmp_path / 'node_modules')))
    assert out.returncode == 0, out.stderr[-1500:]
    about = json.loads(out.stdout)
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        contributes = json.load(handle)['contributes']
    titles = {c['command']: c['title'] for c in contributes['commands']}
    bars = {(e.get('command'), e.get('when')) for e in contributes['menus']['view/title']}
    assert {v for _, v, _ in about} == {v['id'] for group in contributes['views'].values()
                                        for v in group}
    for command, view, text in about:
        assert titles.get(command) == text, command
        assert (command, f'view == {view}') in bars, command
    assert dict((v, t) for _, v, t in about)['semforgeProject'].startswith('This package:')
