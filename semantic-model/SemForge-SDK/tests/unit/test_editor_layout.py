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

"""The editor layout (openspec gh-950-semforge-two-columns): the scenarios of
semforge-sdk/editor-layout that no other test file covers.

How the views are split over the two containers, the ⓘ of each view and the
details toggle are in test_package_page.py and test_extension_activates.py;
jumps and counts with the graph open in test_violation_navigation.py.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

from test_violation_navigation import PAGE, _render

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')


def _manifest():
    with open(os.path.join(SDK, 'vscode', 'package.json')) as handle:
        return json.load(handle)


def _drive(tmp_path, scenario, target):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, target), str(path)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# --- Menus name actions without the extension's prefix -----------------------

def test_every_command_is_in_the_category_and_no_title_carries_a_prefix():
    commands = _manifest()['contributes']['commands']
    assert [c['command'] for c in commands if c.get('category') != 'SemForge'] == []
    assert [c['title'] for c in commands if c['title'].startswith('SemForge:')] == []
    assert [c['title'] for c in commands if c['title'].startswith('+')] == []


def test_adding_to_an_item_says_add():
    titles = {c['command']: c['title'] for c in _manifest()['contributes']['commands']}
    # Right-click an entity, an entity type, a shape: the same verb.
    assert titles['semforge.addAttribute'] == 'Add attribute'
    assert titles['semforge.addTypeAttribute'] == 'Add attribute…'
    assert titles['semforge.addAttributeConstraint'] == 'Add attribute to shape'
    assert titles['semforge.addSparqlConstraint'] == 'Add SPARQL constraint…'


# --- Title bars hold what creates ---------------------------------------------

def _bar(view):
    contributes = _manifest()['contributes']
    titles = {c['command']: c['title'] for c in contributes['commands']}
    titles.update({s['id']: s['id'] for s in contributes['submenus']})
    buttons, overflow = [], []
    for entry in contributes['menus']['view/title']:
        if f'view == {view}' not in entry['when']:
            continue
        name = titles[entry.get('command') or entry.get('submenu')]
        (buttons if entry.get('group', '').startswith('navigation') else overflow).append(name)
    return buttons, overflow


def test_the_package_views_title_bar():
    buttons, overflow = _bar('semforgeProject')
    assert sorted(buttons) == sorted([
        'Select package', 'Show details', 'semforge.project',
        next(c['title'] for c in _manifest()['contributes']['commands']
             if c['command'] == 'semforge.about.project')])
    assert sorted(overflow) == ['Open package health', 'Open package settings',
                                'Refresh package']


def test_no_title_bar_shows_refresh_as_a_button():
    for view in ('semforgeProject', 'semforgeModel', 'semforgeConstraints',
                 'semforgeShapes', 'semforgeKnowledge'):
        buttons, overflow = _bar(view)
        assert not [b for b in buttons if b.startswith('Refresh')], view
        assert [o for o in overflow if o.startswith('Refresh')], view


# --- The Package view stays short --------------------------------------------

def test_only_the_package_view_explains_what_a_package_is():
    welcome = {w['view']: w['contents'] for w in _manifest()['contributes']['viewsWelcome']}
    assert 'A package is knowledge' in welcome['semforgeProject']
    assert 'command:semforge.newProject' in welcome['semforgeProject']
    for view, contents in welcome.items():
        assert 'command:semforge.initPackage' in contents and 'command:semforge.doctor' in contents
        if view != 'semforgeProject':
            assert 'A package is knowledge' not in contents, view
            assert len(contents.splitlines()) == 3, view


def test_the_settings_start_folded(tmp_path):
    roots = [{'kind': 'project', 'label': 'Project', 'children': [
                 {'kind': 'setting', 'label': 'name', 'value': 'example', 'editable': True}]},
             {'kind': 'group', 'label': 'Settings', 'children': [
                 {'kind': 'setting', 'label': 'version', 'value': '1.0.0', 'editable': True}]},
             {'kind': 'group', 'label': 'Contents', 'children': [
                 {'kind': 'fact', 'label': 'shapes', 'value': 'shacl.ttl'}]}]
    seen = _drive(tmp_path, {
        'mode': 'tree', 'provider': 'ProjectTreeProvider', 'uri': 'file:///pkg/shacl.ttl',
        'states': True,
        'replies': {'semforge/project': {'roots': roots}, 'semforge/health': {'ok': False}}},
        'project.js')
    states = {s['label']: s['collapsibleState'] for s in seen['tree']['states']}
    collapsed, expanded = 1, 2
    assert states['Settings'] == collapsed
    assert states['Contents'] == expanded and states['Project'] == expanded
    assert not seen['tree'].get('message'), 'no heading above the rows'


# --- A view says what it is in a hover: the message is for what is wrong ------

def test_without_a_language_server_the_view_says_so(tmp_path):
    seen = _drive(tmp_path, {
        'mode': 'tree', 'provider': 'ProjectTreeProvider', 'uri': 'file:///pkg/shacl.ttl',
        'noClient': True, 'replies': {}}, 'project.js')
    assert seen['tree']['roots'] == []
    assert seen['tree']['message'].startswith('The language server is not running')
    assert 'Doctor' in seen['tree']['message']


# --- The Main model page explains its violations in a hover -------------------

def test_the_violation_list_explains_itself_in_a_hover(tmp_path):
    html = _render(tmp_path).read_text()
    found = re.search(r'<h2 id="violations">.*?</h2>\s*<p class="dim">(.*?)</p>', html, re.S)
    assert found, 'the line under the heading'
    line = found.group(1)
    assert re.match(r'<span class="info" tabindex="0" title="Click one to go to it\. Each is '
                    r'also listed in VS Code’s Problems panel[^"]*F8 steps from one to the next\.">'
                    r'ⓘ</span> <a tabindex="0" role="link" data-problems="1">Open the Problems '
                    r'panel</a>$', line), line


# --- Pages open their entities as a graph ---------------------------------------

def test_the_entity_bar_is_graph_then_all_and_opens_on_the_graph(tmp_path):
    html = _render(tmp_path, dict(PAGE)).read_text()
    bar = re.search(r'<span class="views">(.*?)</span>', html).group(1)
    assert re.findall(r'data-view="(\w+)"[^>]*>(\w+)</button>', bar) == [
        ('graph', 'Graph'), ('cards', 'All')]
    assert 'class="mini on" data-view="graph"' in bar
    assert '<div id="cardview" hidden>' in html
    assert '<div class="graph" id="graph"></div>' in html
