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

"""The entity views of the model and case pages: the card filter and the graph.

The page script runs in a browser, so the checks that need one run in headless
Chromium when it is there (Playwright's, or SEMFORGE_CHROME) and are skipped
otherwise. What the page is drawn from -- the entities and their
relationships -- is checked everywhere.
"""

import glob
import json
import os
import re
import shutil
import subprocess

import pytest

SDK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(SDK, 'vscode', 'src')
RENDER = os.path.join(SDK, 'tests', 'harness', 'render_casepage.js')


def _row(name, kind='Property', value='1', children=()):
    return {'name': name, 'term': 'ex:' + name, 'kind': kind, 'value': value, 'dataset': '',
            'unitCode': '', 'observedAt': '', 'stamp': {}, 'latestAt': '', 'superseded': False,
            'instances': 1, 'line': 1, 'violations': [], 'children': list(children),
            'display': name}


def _card(id_, type_, rows):
    return {'id': id_, 'type': type_, 'file': '/pkg/model.jsonld', 'line': 1,
            'violations': [], 'attributes': rows}


# A -> B -> A (a cycle), A -> C through a sub-attribute, B -> a target not here.
PAGE = {
    'kind': 'model', 'name': 'Main', 'case': '', 'expect': '', 'group': '', 'suite': '',
    'description': '', 'passed': True, 'failures': [], 'claims': [], 'unasserted': [],
    'residuePinned': False, 'file': '/pkg/model.jsonld', 'expectations': '',
    'verdicts': {'state': 'ready'},
    'summary': {'entities': 3, 'violations': 0, 'includes': 0},
    'files': [{'role': 'model', 'path': '/pkg/model.jsonld', 'relative': 'model.jsonld',
               'sharedBy': [], 'cards': [
                   _card('urn:a', 'ex:Pump', [
                       _row('hasPort', 'Relationship', 'urn:b'),
                       _row('hasState', children=[_row('hasDriver', 'Relationship', 'urn:c')])]),
                   _card('urn:b', 'ex:Port', [
                       _row('hasOwner', 'Relationship', 'urn:a'),
                       _row('hasElsewhere', 'Relationship', 'urn:gone')]),
                   _card('urn:c', 'ex:Drive', [_row('hasSpeed')])]}],
}


def _node():
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    return node


def _render(tmp_path, after=None):
    page = tmp_path / 'page.json'
    page.write_text(json.dumps(PAGE))
    out = tmp_path / 'page.html'
    args = [_node(), RENDER, SRC, str(page), str(out)]
    if after:
        script = tmp_path / 'after.js'
        script.write_text(after)
        args.append(str(script))
    run = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[-1500:]
    return out


def test_the_page_carries_its_entities_and_their_relationships(tmp_path):
    html = _render(tmp_path).read_text()
    data = re.search(r'<script type="application/json" id="entities">(.*?)</script>', html, re.S)
    entities = {e['id']: e for e in json.loads(data.group(1))}
    assert entities['urn:a']['rels'] == [{'name': 'hasPort', 'target': 'urn:b'},
                                         {'name': 'hasState.hasDriver', 'target': 'urn:c'}]
    assert entities['urn:a']['attrs'] == ['hasPort', 'hasState']
    assert 'data-type="ex:Port"' in html and 'data-id="urn:b"' in html
    assert 'data-view="graph"' in html and '<details class="filter" id="filter">' in html


def _chrome():
    candidates = [os.environ.get('SEMFORGE_CHROME', '')] + sorted(glob.glob(os.path.expanduser(
        '~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome')))
    found = next((c for c in candidates if c and os.path.exists(c)), None)
    if found is None:
        pytest.skip('no headless Chromium (set SEMFORGE_CHROME)')
    return found


def _dom(tmp_path, after):
    out = _render(tmp_path, after)
    run = subprocess.run([_chrome(), '--headless=new', '--no-sandbox', '--disable-gpu',
                          '--virtual-time-budget=3000', '--dump-dom', 'file://' + str(out)],
                         capture_output=True, text=True, timeout=120)
    return run.stdout


# Graph; on A open hasPort (-> B) and hasState.hasDriver (-> C); on B open
# hasOwner, which points back at A.
WALK = '''
document.querySelector('[data-view=graph]').click();
function toggleOn(card, rel) {
  card.querySelector('.attr[data-rel="' + rel + '"] [data-reltoggle]').click();
}
setTimeout(function () {
  var a = document.querySelector('#graph details.tcard[data-id="urn:a"]');
  toggleOn(a, 'urn:b');
  toggleOn(a, 'urn:c');
  var b = a.querySelector('details.tcard[data-id="urn:b"]');
  toggleOn(b, 'urn:a');
  REBUILD
}, 30);
'''


def _graph(dom):
    return dom[dom.index('id="graph"'):dom.index('id="cardview"')]


def _cards(graph, entity):
    """How many tree cards show this entity in full (each holds a copy of its card)."""
    return len(re.findall(r'<details class="tcard[^"]*" data-id="' + re.escape(entity) + '"', graph))


def test_a_path_opens_card_by_card_and_a_cycle_ends_in_a_reference(tmp_path):
    graph = _graph(_dom(tmp_path, WALK.replace('REBUILD', '')))
    # urn:a and urn:b point at each other, urn:a at urn:c: everything is pointed
    # at, so the cycle is entered at its first entity -- one root, not three.
    assert '0 root(s): the entities nothing points at · 1 more where a cycle has no way in' \
        in graph
    # Each entity's card, in full, once: B and C under A, A not again under B.
    assert _cards(graph, 'urn:a') == 1
    assert _cards(graph, 'urn:b') == 1 and _cards(graph, 'urn:c') == 1
    assert graph.index('data-id="urn:a"') < graph.index('data-id="urn:b"')
    assert 'data-goto="urn:a"' in graph and 'is open elsewhere on this page' in graph
    # The relationship inside a sub-attribute opened too, named by its row.
    assert 'hasDriver →' in graph
    # A target not on the page cannot be opened, and says why.
    assert 'urn:gone is not on this page' in graph
    # The row names what the card below is: type and id -- the type a link to
    # the TARGET's type page.
    assert '<a class="dim" tabindex="0" role="link" title="Open the ex:Port page" data-type="ex:Port">' \
        'ex:Port</a> <span title="urn:b">urn:b</span>' in graph


def _posted(dom):
    import html as entities

    found = re.search(r'<html[^>]* data-posted="([^"]*)"', dom)
    return json.loads(entities.unescape(found.group(1))) if found else []


def test_a_type_opens_its_own_page_and_a_card_opens_none(tmp_path):
    """Clicking a type -- in a card's head, or on a relationship row naming the
    type it points at -- opens THAT type's page; a click elsewhere on a card
    opens none. The whole card carried its type, and a click anywhere in it
    opened the card's own type page, also from a row pointing at another."""
    dom = _dom(tmp_path, WALK.replace('REBUILD', '''
  a.querySelector(':scope > summary [data-type]').click();
  a.querySelector('.attr[data-rel="urn:b"] .value [data-type]').click();
  a.querySelector('.attr[data-rel="urn:b"] .value [title="urn:b"]').click();
  a.querySelector('.attr[data-rel="urn:b"]').click();
  document.querySelector('#cardview .card[data-id="urn:a"]').click();
'''))
    assert [m for m in _posted(dom) if m.get('command') == 'type'] == [
        {'command': 'type', 'name': 'ex:Pump'}, {'command': 'type', 'name': 'ex:Port'}]


def test_the_open_branches_come_back_when_the_view_is_drawn_again(tmp_path):
    rebuild = ('document.querySelector("[data-view=cards]").click();'
               'document.querySelector("[data-view=graph]").click();')
    graph = _graph(_dom(tmp_path, WALK.replace('REBUILD', rebuild)))
    assert _cards(graph, 'urn:a') == 1
    assert _cards(graph, 'urn:b') == 1 and _cards(graph, 'urn:c') == 1
    assert 'data-goto="urn:a"' in graph


def test_a_filter_hides_the_cards_and_roots_the_graph(tmp_path):
    dom = _dom(tmp_path, '''
var t = document.getElementById('ftype'); t.value = 'ex:Port'; t.dispatchEvent(new Event('change'));
''')
    cards = re.findall(r'<div class="card[^"]*"[^>]*data-id="([^"]+)"[^>]*?( hidden="")?>', dom)
    assert {card for card, hidden in cards if not hidden} == {'urn:b'}
    assert '1 of 3 shown' in dom

    graph = _dom(tmp_path, '''
var t = document.getElementById('ftype'); t.value = 'ex:Port'; t.dispatchEvent(new Event('change'));
document.querySelector('[data-view=graph]').click();
''')
    assert '1 matching entity as roots' in graph
