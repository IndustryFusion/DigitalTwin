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

"""Reveal in graph view: the graph shows only the path to one entity.

The page's own script runs in headless Chromium; the ways in, through the
extension's wiring with the Node harness.
"""

import copy
import html as entities
import json
import os
import re
import shutil
import subprocess
import time

import pytest

import test_entity_graph
from test_entity_graph import PAGE, SRC, _card, _chrome, _node, _render, _row
from test_tree_clicks import PACKAGE_JSON, _drive, _opened

from semforge.cooked.casepage import build_model_page, page_of_file
from semforge.errors import PackageError
from semforge.package import load

CORPUS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'corpus'))


def _scene(cards, *more):
    page = copy.deepcopy(PAGE)
    page['ok'] = True
    page['files'][0]['cards'] = cards
    for other in more:
        page['files'].append(dict(page['files'][0], role='include', cards=other))
    return page


def _rel(name, target):
    return _row(name, 'Relationship', target)


# A plant points at two pumps, both at one motor (two ways to it), and a pump
# through a sub-attribute at a drive; two entities point at each other, at
# nothing else; motors have more attributes than the path takes.
SCENE = _scene([
    _card('urn:plant', 'ex:Plant', [_row('hasName'), _rel('hasPump', 'urn:p1'), _rel('hasSpare', 'urn:p2')]),
    _card('urn:p1', 'ex:Pump', [_row('hasSpeed'), _rel('hasMotor', 'urn:m'),
                                _row('hasState', children=[_rel('hasDriver', 'urn:d'), _row('hasSince')])]),
    _card('urn:p2', 'ex:Pump', [_rel('hasMotor', 'urn:m')]),
    _card('urn:m', 'ex:Motor', [_row('hasPower'), _row('hasMaker'), _rel('hasDrive', 'urn:d')]),
    _card('urn:d', 'ex:Drive', [_row('hasTorque')]),
    _card('urn:x', 'ex:Loop', [_rel('hasOther', 'urn:y')]),
    _card('urn:y', 'ex:Loop', [_rel('hasOther', 'urn:x')])])

# What the graph shows: the cards, outermost first, and each card's rows.
SAY = '''
function say() {
  var out = { bar: (document.querySelector('.way') || {}).textContent || '', cards: [], rows: {} };
  document.querySelectorAll('#graph details.tcard').forEach(function (d) {
    out.cards.push(d.dataset.id);
    out.rows[d.dataset.id] = Array.from(d.querySelectorAll(':scope > .card .attr'))
      .filter(function (r) { return r.closest('.tcard') === d && r.offsetParent !== null; })
      .map(function (r) { return r.dataset.name; });
  });
  out.end = (document.querySelector('.wayend') || { dataset: {} }).dataset.id || '';
  out.graph = !document.getElementById('graph').hidden;
  out.filter = document.getElementById('fid').value;
  var f = document.activeElement;
  out.focus = f.tagName + ':' + JSON.stringify(Object.assign({}, f.dataset));
  out.focusCard = (f.closest('.tcard') || { dataset: {} }).dataset.id || '';
  out.scroll = Math.round(window.scrollY);
  document.documentElement.dataset.said = JSON.stringify(out);
}
setTimeout(function () { %s
  setTimeout(say, 60);
}, 50);
'''


def _attribute(dom, name):
    found = re.search(r'<html[^>]* data-%s="([^"]*)"' % name, dom)
    return json.loads(entities.unescape(found.group(1))) if found else None


def _page(tmp_path, monkeypatch, after='', scene=SCENE, state=None, **options):
    """What the page shows once it is up and `after` ran; with what it posted
    and remembers."""
    page = dict(scene, __options=options)
    if state:
        page['__state'] = state
    monkeypatch.setattr(test_entity_graph, 'PAGE', page)
    out = _render(tmp_path, SAY % after)
    dom = subprocess.run([_chrome(), '--headless=new', '--no-sandbox', '--disable-gpu',
                          '--virtual-time-budget=4000', '--dump-dom', 'file://' + str(out)],
                         capture_output=True, text=True, timeout=120).stdout
    said = _attribute(dom, 'said')
    assert said, dom[-600:]
    said['posted'] = _attribute(dom, 'posted') or []
    said['state'] = _attribute(dom, 'state')
    said['sync'] = entities.unescape(re.search(r'<html[^>]* data-sync="([^"]*)"', dom).group(1)) \
        if 'data-sync=' in dom else None
    return said


def _click(selector):
    return "document.querySelector('%s').click();" % selector


# --- the path ----------------------------------------------------------------------------

def test_only_the_path_is_shown(tmp_path, monkeypatch):
    said = _page(tmp_path, monkeypatch, reveal='urn:m')
    assert said['graph'] and said['end'] == 'urn:m'
    assert said['cards'] == ['urn:plant', 'urn:p1', 'urn:m'], 'no other root, no other branch'
    assert said['rows'] == {'urn:plant': ['hasPump'], 'urn:p1': ['hasMotor'],
                            'urn:m': ['hasPower', 'hasMaker', 'hasDrive']}, 'the entity itself is whole'
    assert 'Path to urn:m' in said['bar'] and '1 of 2' in said['bar'] and 'or more' not in said['bar']
    landed = [m for m in said['posted'] if m['command'] == 'landed']
    assert landed[0]['path'] == said['cards'] and landed[0]['inView']


def test_a_relationship_inside_a_sub_attribute(tmp_path, monkeypatch):
    said = _page(tmp_path, monkeypatch, reveal='urn:d')
    assert said['cards'] == ['urn:plant', 'urn:p1', 'urn:d'], 'the shortest first'
    assert said['rows']['urn:p1'] == ['hasState', 'hasDriver'], 'what the row is in stays'


def test_two_sub_attributes_of_one_name_are_two_paths(tmp_path, monkeypatch):
    scene = _scene([_card('urn:a', 'ex:A', [_row('hasLeft', children=[_rel('hasX', 'urn:b')]),
                                            _row('hasRight', children=[_rel('hasX', 'urn:b')])]),
                    _card('urn:b', 'ex:B', [_row('hasN')])])
    assert _page(tmp_path, monkeypatch, scene=scene, reveal='urn:b')['rows']['urn:a'] == ['hasLeft', 'hasX']
    said = _page(tmp_path, monkeypatch, _click('[data-way="1"]'), scene=scene, reveal='urn:b')
    assert said['rows']['urn:a'] == ['hasRight', 'hasX']


def test_deeper_sub_attributes_keep_what_they_are_in(tmp_path, monkeypatch):
    row = _rel('hasLast', 'urn:b')
    for name in ('hasE', 'hasD', 'hasC', 'hasB', 'hasA'):
        row = _row(name, children=[_row('hasOther'), row])
    scene = _scene([_card('urn:a', 'ex:A', [row]), _card('urn:b', 'ex:B', [_row('hasN')])])
    said = _page(tmp_path, monkeypatch, scene=scene, reveal='urn:b')
    assert said['rows']['urn:a'] == ['hasA', 'hasB', 'hasC', 'hasD', 'hasE', 'hasLast']


def test_inside_an_earlier_observation(tmp_path, monkeypatch):
    old = dict(_row('hasState', children=[_rel('hasX', 'urn:b')]), superseded=True)
    scene = _scene([_card('urn:a', 'ex:A', [old, _row('hasState')]), _card('urn:b', 'ex:B', [_row('hasN')])])
    said = _page(tmp_path, monkeypatch, scene=scene, reveal='urn:b')
    assert said['end'] == 'urn:b' and 'hasX' in said['rows']['urn:a']


def test_the_next_path_and_around_again(tmp_path, monkeypatch):
    said = _page(tmp_path, monkeypatch, _click('[data-way="1"]'), reveal='urn:m')
    assert said['cards'] == ['urn:plant', 'urn:p2', 'urn:m'] and '2 of 2' in said['bar']
    assert said['focus'] == 'BUTTON:{"way":"1"}', 'a step is one key again'
    said = _page(tmp_path, monkeypatch, _click('[data-way="-1"]'), reveal='urn:m')
    assert '2 of 2' in said['bar']


def test_the_other_attributes_and_the_whole_graph_are_one_click_away(tmp_path, monkeypatch):
    said = _page(tmp_path, monkeypatch, _click('[data-waymore]'), reveal='urn:m')
    assert said['rows']['urn:plant'] == ['hasName', 'hasPump', 'hasSpare']
    assert said['focusCard'] == 'urn:plant'
    monkeypatch.setattr(test_entity_graph, 'PAGE', dict(SCENE, __options={'reveal': 'urn:m'}))
    dom = subprocess.run([_chrome(), '--headless=new', '--no-sandbox', '--disable-gpu', '--virtual-time-budget=3000',
                          '--dump-dom', 'file://' + str(_render(tmp_path))], capture_output=True, text=True,
                         timeout=120).stdout
    shown = re.findall(r'data-waymore="[^"]*"[^>]*>([^<]*)<', dom)
    assert shown and all(text == '… show the rest of this card' for text in shown), shown
    said = _page(tmp_path, monkeypatch, _click('[data-wholegraph]'), reveal='urn:m')
    assert not said['bar'] and said['end'] == ''
    assert {'urn:plant', 'urn:x'} <= set(said['cards']) and 'urn:m' not in said['cards']
    assert said['focus'] == 'BUTTON:{"view":"graph"}'


def test_what_was_open_in_the_graph_comes_back(tmp_path, monkeypatch):
    said = _page(tmp_path, monkeypatch, _click('[data-rel="urn:p2"] [data-reltoggle]') +
                 _click('summary [data-reveal="urn:x"]') + _click('[data-wholegraph]'))
    assert 'urn:p2' in said['cards']


def test_a_root_is_its_own_path_and_a_circle_ends(tmp_path, monkeypatch):
    assert _page(tmp_path, monkeypatch, reveal='urn:plant')['cards'] == ['urn:plant']
    said = _page(tmp_path, monkeypatch, reveal='urn:y')
    assert said['cards'] == ['urn:x', 'urn:y']
    said = _page(tmp_path, monkeypatch, reveal='urn:x')
    assert said['cards'] == ['urn:x'] and said['end'] == 'urn:x', 'where its circle is entered'


def test_an_entity_that_only_points_at_itself(tmp_path, monkeypatch):
    scene = _scene([_card('urn:s', 'ex:S', [_rel('hasSelf', 'urn:s')]), _card('urn:t', 'ex:T', [_row('hasN')])])
    said = _page(tmp_path, monkeypatch, scene=scene, reveal='urn:s')
    assert said['cards'] == ['urn:s'] and said['end'] == 'urn:s'


def test_an_entity_of_two_files_is_reached_by_either(tmp_path, monkeypatch):
    """The case's definition has no relationship, the included one has: the
    path goes by the card that has it."""
    scene = _scene([_card('urn:a', 'ex:A', [_rel('hasB', 'urn:b')]), _card('urn:b', 'ex:B', [_row('hasN')])],
                   [_card('urn:a', 'ex:A', [_row('hasName')])])
    said = _page(tmp_path, monkeypatch, scene=scene, reveal='urn:b')
    assert said['cards'] == ['urn:a', 'urn:b'] and said['end'] == 'urn:b'


HOSTILE = 'urn:"><img src=x onerror="document.title=1">\'&amp;</script>[x](command:y)'


@pytest.mark.parametrize('odd', [HOSTILE, 'sn1234c3Z1PXVybg==', 'a relative/id?x=1#2', 'ex:pump 1'])
def test_ids_of_any_spelling(tmp_path, monkeypatch, odd):
    scene = _scene([_card('urn:a', 'ex:A', [dict(_rel('hasB', odd.split(':')[-1]), target=odd)]),
                    _card(odd, 'ex:B', [_row('hasN')])])
    said = _page(tmp_path, monkeypatch, _click('#cardview [data-card="0.1"] [data-reveal]'), scene=scene)
    assert said['cards'] == ['urn:a', odd] and said['end'] == odd
    assert 'Path to ' + odd in said['bar']
    monkeypatch.setattr(test_entity_graph, 'PAGE', scene)
    html = _render(tmp_path).read_text()
    assert '<img' not in html.split('<script')[0] and '<img' not in html.split('id="cardview"')[1]
    contexts = [json.loads(entities.unescape(c)) for c in re.findall(r'data-vscode-context="([^"]*)"', html)]
    assert {'webviewSection': 'semforgeEntity', 'entity': odd} in contexts


# --- many ---------------------------------------------------------------------------------

@pytest.mark.parametrize('middles, bar', [(19, '1 of 19 '), (20, '1 of 20 '), (21, '1 of 20 or more')])
def test_or_more_only_when_there_is_more(tmp_path, monkeypatch, middles, bar):
    """Twenty ways to it and a loop beside them that leads nowhere else: the
    search ends with the loop still to look at, and there is no more."""
    cards = [_card('urn:root', 'ex:R', [_rel('hasM', 'urn:m%d' % i) for i in range(middles)] +
                   [_rel('hasOther', 'urn:other')]),
             _card('urn:other', 'ex:O', [_rel('hasDeep', 'urn:deep')]), _card('urn:deep', 'ex:O', [_row('hasN')])]
    cards += [_card('urn:m%d' % i, 'ex:M', [_rel('hasEnd', 'urn:end')]) for i in range(middles)]
    cards.append(_card('urn:end', 'ex:E', [_row('hasN'), _rel('hasY', 'urn:y')]))
    cards += [_card('urn:y', 'ex:Y', [_rel('hasEnd', 'urn:end'), _rel('hasW', 'urn:w')]),
              _card('urn:w', 'ex:W', [_rel('hasY', 'urn:y')])]
    said = _page(tmp_path, monkeypatch, scene=_scene(cards), reveal='urn:end')
    assert bar in said['bar'] + ' ' and ('or more' in bar) == ('or more' in said['bar']), said['bar']


ALIASED = _scene([dict(_card('ex:plant', 'ex:Plant', [_rel('hasPump', 'pump-1')]), iri='http://ex/plant'),
                  dict(_card('pump-1', 'ex:Pump', [_row('hasN')]), iri='pump-1')])


@pytest.mark.parametrize('asked, end', [('http://ex/plant', 'ex:plant'), ('ex:plant', 'ex:plant'),
                                        ('pump-1', 'pump-1')])
def test_an_id_the_graph_spells_out_finds_its_card(tmp_path, monkeypatch, asked, end):
    """A type or shape page, and Knowledge, name an entity as the graph has it:
    a prefixed id spelled out."""
    said = _page(tmp_path, monkeypatch, scene=ALIASED, reveal=asked)
    assert said['end'] == end
    assert not [m for m in said['posted'] if m['command'] == 'noReveal']


def test_very_many_paths_are_bounded_and_the_shortest_is_there(tmp_path, monkeypatch):
    """Six layers of twelve, each pointing at all of the next: a quarter of a
    million paths, and one short cut."""
    cards = [_card('urn:root', 'ex:R', [_rel('hasL', 'urn:0.%d' % j) for j in range(12)] +
                   [_rel('hasCut', 'urn:end')])]
    for layer in range(6):
        below = ['urn:%d.%d' % (layer + 1, j) for j in range(12)] if layer < 5 else ['urn:end']
        cards += [_card('urn:%d.%d' % (layer, i), 'ex:L', [_rel('hasL', t) for t in below]) for i in range(12)]
    cards.append(_card('urn:end', 'ex:E', [_row('hasN')]))
    started = time.time()
    said = _page(tmp_path, monkeypatch, scene=_scene(cards), reveal='urn:end')
    assert time.time() - started < 30
    assert said['cards'] == ['urn:root', 'urn:end'], 'the shortest'
    assert '1 of 1 or more' in said['bar'], 'the bound stops the search: said'
    # Without the short cut there is none within the bound: one is found still.
    cards[0]['attributes'].pop()
    said = _page(tmp_path, monkeypatch, scene=_scene(cards), reveal='urn:end')
    assert len(said['cards']) == 8 and '1 of 1 or more' in said['bar']


def test_every_entity_of_a_package_of_hundreds_has_its_path(tmp_path, monkeypatch):
    """The OPC UA pump slice, its model twenty times over (400 entities, ids
    without a scheme): each path starts at a pump, goes on by what the card
    before it points at, and ends at the entity."""
    page = build_model_page(load(os.path.join(CORPUS, 'opcua-pumps')))
    cards = page['files'][0]['cards']
    ids = {card['id'] for card in cards}

    def renamed(rows, n):
        return [dict(r, target=r['target'] + '-%d' % n, value=r['target'] + '-%d' % n)
                if r.get('target') in ids and r['kind'] == 'Relationship'
                else dict(r, children=renamed(r.get('children') or [], n)) for r in rows]

    many = [dict(c, id=c['id'] + '-%d' % n, attributes=renamed(c['attributes'], n))
            for n in range(20) for c in cards]
    page['files'][0]['cards'] = many
    page['verdicts'] = {'state': 'ready'}
    assert len(many) == 400
    owner = {}
    for card in many:
        for row in card['attributes']:
            if row['kind'] == 'Relationship':
                owner[row['target']] = card['id']
    after = '''
var ways = {};
var t = performance.now();
ENTITIES.forEach(function (e) {
  reveal(e.id);
  var shown = Array.from(document.querySelectorAll('#graph .tcard'));
  ways[e.id] = { cards: shown.map(function (c) { return c.dataset.id; }),
                 end: document.querySelector('.wayend').dataset.id };
});
var took = performance.now() - t;
var node = document.createElement('pre'); node.id = 'ways';
node.textContent = JSON.stringify({ ways: ways, took: took }); document.body.append(node);
'''
    monkeypatch.setattr(test_entity_graph, 'PAGE', page)
    dom = subprocess.run([_chrome(), '--headless=new', '--no-sandbox', '--disable-gpu',
                          '--virtual-time-budget=9000', '--dump-dom', 'file://' + str(_render(tmp_path, after))],
                         capture_output=True, text=True, timeout=180).stdout
    got = json.loads(entities.unescape(re.search(r'<pre id="ways">(.*?)</pre>', dom, re.S).group(1)))
    for card in many:
        path = [card['id']]
        while path[0] in owner:
            path.insert(0, owner[path[0]])
        assert got['ways'][card['id']] == {'cards': path, 'end': card['id']}
        assert path[0].startswith(cards[-1]['id']), 'a pump is the root'
    assert got['took'] / 400 < 500, 'milliseconds an entity'


# --- it stays, and it goes ----------------------------------------------------------------

def _post(message):
    return 'window.postMessage(%s);' % json.dumps(message)


def test_a_tab_shown_again_does_not_bring_an_older_path_back(tmp_path, monkeypatch):
    """The tab re-runs the page with what it was drawn with: request 1, the
    motor. Since, the page was asked (2) for the drive, or left the path."""
    first = _page(tmp_path, monkeypatch, _post({'command': 'reveal', 'entity': 'urn:d', 'asked': '2'}),
                  reveal='urn:m', asked='1')
    again = _page(tmp_path, monkeypatch, state=first['state'], reveal='urn:m', asked='1')
    assert again['end'] == 'urn:d', 'the newer path, not the older one'
    left = _page(tmp_path, monkeypatch, _post({'command': 'reveal', 'entity': 'urn:d', 'asked': '2'}) +
                 'setTimeout(function () { ' + _click('[data-wholegraph]') + ' }, 10);', reveal='urn:m', asked='1')
    again = _page(tmp_path, monkeypatch, state=left['state'], reveal='urn:m', asked='1')
    assert again['end'] == '' and not again['bar'], 'left, it stays left'


def test_a_failed_reveal_and_a_jump_are_not_repeated_by_a_redraw(tmp_path, monkeypatch):
    first = _page(tmp_path, monkeypatch, _post({'command': 'reveal', 'entity': 'urn:gone', 'asked': '2'}), asked='1')
    assert {'command': 'noReveal', 'entity': 'urn:gone'} in first['posted']
    again = _page(tmp_path, monkeypatch, state=first['state'], reveal='urn:gone', asked='2')
    assert not [m for m in again['posted'] if m['command'] == 'noReveal'], 'said once'
    first = _page(tmp_path, monkeypatch, _post({'command': 'land', 'asked': '2'}), focus='urn:p1', asked='1')
    assert [m['from'] for m in first['posted'] if m['command'] == 'landed'] == ['open', 'open']
    again = _page(tmp_path, monkeypatch, state=first['state'], focus='urn:p1', asked='2')
    assert not [m for m in again['posted'] if m['command'] == 'landed'], 'no jump on a redraw'
    assert not again['graph'], 'the cards it showed'


# What the page keeps when it is drawn again: (what is done, then what it shows).
KEPT = {
    'the view': (_click('[data-view=cards]'), lambda s: not s['graph']),
    'a filter': ("var i = document.getElementById('fid'); i.value = 'urn:p'; i.dispatchEvent(new Event('input'));",
                 lambda s: s['filter'] == 'urn:p' and set(s['cards']) == {'urn:plant', 'urn:p1', 'urn:p2'}),
    'an open card': (_click('[data-rel="urn:p2"] [data-reltoggle]'), lambda s: 'urn:p2' in s['cards']),
    'the path': ('reveal("urn:m");', lambda s: s['end'] == 'urn:m' and '1 of 2' in s['bar']),
    'the next path': ('reveal("urn:m"); ' + _click('[data-way="1"]'), lambda s: '2 of 2' in s['bar']),
    'the rest of a card': ('reveal("urn:m"); ' + _click('[data-waymore]'),
                           lambda s: s['rows']['urn:plant'] == ['hasName', 'hasPump', 'hasSpare']),
    'a filter set on a path': ('reveal("urn:m"); var i = document.getElementById("fid"); i.value = "urn:p"; '
                               'i.dispatchEvent(new Event("input"));',
                               lambda s: s['filter'] == 'urn:p' and not s['bar']),
    'the path left': ('reveal("urn:m"); ' + _click('[data-wholegraph]'), lambda s: not s['bar'] and s['graph']),
}


def test_a_filter_set_on_a_path_is_remembered_at_once(tmp_path, monkeypatch):
    """Remembered at once, not by the next scroll: a redraw in between kept the
    path and dropped the filter."""
    said = _page(tmp_path, monkeypatch, "var i = document.getElementById('fid'); i.value = 'urn:p'; "
                 "i.dispatchEvent(new Event('input')); document.documentElement.dataset.sync = "
                 "document.documentElement.dataset.state;", reveal='urn:m')
    monkeypatch.setattr(test_entity_graph, 'PAGE', SCENE)
    remembered = json.loads(said['sync'])['/pkg/model.jsonld']
    assert remembered['id'] == 'urn:p' and 'way' not in remembered


@pytest.mark.parametrize('kept', sorted(KEPT))
@pytest.mark.parametrize('asked', ['1', 'older'])
def test_what_the_page_keeps_when_it_is_drawn_again(tmp_path, monkeypatch, kept, asked):
    """Drawn again for the same request (a validation, an edit), or with an
    older one (its tab shown again after it was asked for more)."""
    done, shows = KEPT[kept]
    first = _page(tmp_path, monkeypatch, done, asked='2')
    assert shows(first), first
    again = _page(tmp_path, monkeypatch, state=first['state'], asked='2' if asked == '1' else '1')
    assert shows(again), again


def test_the_path_stays_when_the_page_is_drawn_again(tmp_path, monkeypatch):
    first = _page(tmp_path, monkeypatch, _click('[data-way="1"]') + _click('[data-waymore]') +
                  "document.querySelector('.wayend [data-rel=\"urn:d\"] [data-reltoggle]').click();",
                  reveal='urn:m', asked='1')
    again = _page(tmp_path, monkeypatch, state=first['state'], reveal='urn:m', asked='1')
    assert '2 of 2' in again['bar'] and again['end'] == 'urn:m', 'the same one of the paths'
    assert again['cards'] == first['cards'] == ['urn:plant', 'urn:p2', 'urn:m', 'urn:d']
    assert again['rows'] == first['rows'], 'and what was shown of its cards'


def test_drawn_again_it_takes_neither_the_focus_nor_the_scroll(tmp_path, monkeypatch):
    scene = _scene([_card('urn:a', 'ex:A', [_rel('hasB', 'urn:b')]),
                    _card('urn:b', 'ex:B', [_row('hasN%d' % i) for i in range(300)])])
    first = _page(tmp_path, monkeypatch, scene=scene, reveal='urn:b', asked='1')
    key = list(first['state'])[0]
    # Seen, a second after it was shown, and scrolled down since.
    first['state'][key]['way'].update(land=False, scroll=900)
    again = _page(tmp_path, monkeypatch, scene=scene, state=first['state'], reveal='urn:b', asked='1')
    assert again['scroll'] == 900 and again['focus'].startswith('BODY')
    assert again['posted'][-1]['from'] == 'kept'


def test_drawn_again_before_it_was_seen_it_is_gone_to(tmp_path, monkeypatch):
    scene = _scene([_card('urn:t%d' % i, 'ex:T', [_rel('hasNext', 'urn:t%d' % (i + 1))] if i < 60 else [_row('hasN')])
                    for i in range(61)])
    first = _page(tmp_path, monkeypatch, scene=scene, reveal='urn:t60', asked='1')
    key = list(first['state'])[0]
    first['state'][key]['way'].update(land=True, scroll=0)
    again = _page(tmp_path, monkeypatch, scene=scene, state=first['state'], reveal='urn:t60', asked='1')
    assert again['posted'][-1]['inView'] and again['posted'][-1]['from'] == 'reveal'


def test_left_it_does_not_come_back_when_the_page_is_drawn_again(tmp_path, monkeypatch):
    """A tab shown again runs the same page again, with what it was asked."""
    first = _page(tmp_path, monkeypatch, _click('[data-wholegraph]'), reveal='urn:m', asked='1')
    again = _page(tmp_path, monkeypatch, state=first['state'], reveal='urn:m', asked='1')
    assert not again['bar'] and again['end'] == ''
    asked = _page(tmp_path, monkeypatch, state=first['state'], reveal='urn:m', asked='2')
    assert asked['end'] == 'urn:m', 'asked for again, it does'


def test_a_path_from_a_page_opened_at_an_entity_stays(tmp_path, monkeypatch):
    """Opened at urn:p1, then a path revealed on it: a redraw jumped back to
    the card it had been opened at."""
    first = _page(tmp_path, monkeypatch, _click('#cardview .card[data-id="urn:m"] [data-reveal]'),
                  focus='urn:p1', only=True, asked='1')
    assert first['end'] == 'urn:m'
    again = _page(tmp_path, monkeypatch, state=first['state'], focus='urn:p1', only=True, asked='1')
    assert again['end'] == 'urn:m' and again['graph']
    other = _page(tmp_path, monkeypatch, state=first['state'], focus='urn:p2', asked='2')
    assert not other['graph'], 'opened at another entity, it goes there'


def test_an_entity_gone_when_the_page_is_drawn_again(tmp_path, monkeypatch):
    first = _page(tmp_path, monkeypatch, reveal='urn:m', asked='1')
    scene = _scene([c for c in SCENE['files'][0]['cards'] if c['id'] != 'urn:m'])
    again = _page(tmp_path, monkeypatch, scene=scene, state=first['state'], reveal='urn:m', asked='1')
    assert again['graph'] and not again['bar'] and 'urn:plant' in again['cards'], 'the whole graph'
    assert 'way' not in again['state'][list(again['state'])[0]]


def test_an_entity_not_on_the_page_is_said(tmp_path, monkeypatch):
    said = _page(tmp_path, monkeypatch, reveal='urn:gone')
    assert said['end'] == '' and 'urn:plant' in said['cards'], 'the page as it was'
    assert {'command': 'noReveal', 'entity': 'urn:gone'} in said['posted']


def test_the_path_is_left_for_the_cards_a_filter_and_a_violation(tmp_path, monkeypatch):
    said = _page(tmp_path, monkeypatch, _click('[data-view=cards]') + _click('[data-view=graph]'), reveal='urn:m')
    assert not said['bar'] and said['end'] == ''
    said = _page(tmp_path, monkeypatch, "var i = document.getElementById('fid'); i.value = 'urn:p'; "
                 "i.dispatchEvent(new Event('input'));", reveal='urn:m')
    assert not said['bar'] and set(said['cards']) == {'urn:plant', 'urn:p1', 'urn:p2'}
    scene = copy.deepcopy(SCENE)
    scene['files'][0]['cards'][3]['violations'] = [{'text': 'wrong', 'shape': 'S', 'detail': '', 'causes': []}]
    said = _page(tmp_path, monkeypatch, _click('[data-jump] a'), scene=scene, reveal='urn:m')
    assert not said['graph'] and said['posted'][-1]['from'] == 'list'


def test_a_filter_does_not_hide_the_path(tmp_path, monkeypatch):
    state = {'/pkg/model.jsonld': {'id': 'urn:x', 'view': 'cards'}}
    said = _page(tmp_path, monkeypatch, state=state, reveal='urn:m')
    assert said['end'] == 'urn:m' and said['filter'] == ''


# --- the ways in -------------------------------------------------------------------------

def test_from_an_id_on_the_page_and_in_the_graph(tmp_path, monkeypatch):
    said = _page(tmp_path, monkeypatch, _click('[data-view=cards]') +
                 _click('#cardview .card[data-id="urn:m"] [data-reveal]'))
    assert said['graph'] and said['end'] == 'urn:m'
    assert said['focus'].startswith('SUMMARY') and said['focusCard'] == 'urn:m', 'the keyboard goes along'
    said = _page(tmp_path, monkeypatch, _click('#graph [data-rel="urn:p2"] [data-reveal]'))
    assert said['end'] == 'urn:p2', 'what a relationship points at'
    said = _page(tmp_path, monkeypatch, "window.postMessage({ command: 'reveal', entity: 'urn:d', asked: '7' });"
                 "window.postMessage({ command: 'other' });")
    assert said['end'] == 'urn:d' and said['state']['/pkg/model.jsonld']['asked'] == '7'


def test_every_place_an_id_stands_has_its_button(tmp_path, monkeypatch):
    scene = copy.deepcopy(SCENE)
    scene.update(kind='case', expect='invalid', claims=[
        {'constraint': 'S/a/X', 'resource': 'urn:m', 'holds': True, 'explained': None}])
    scene['files'][0]['cards'][4]['violations'] = [{'text': 'wrong', 'shape': 'S', 'detail': '', 'causes': []}]
    scene['files'][0]['cards'].append(_card('', 'ex:None', [_row('hasN')]))
    monkeypatch.setattr(test_entity_graph, 'PAGE', scene)
    html = _render(tmp_path).read_text()
    body = html.split('<script nonce')[0]
    for before, entity in (('class="claims"', 'urn:m'), ('class="vlist"', 'urn:d'), ('class="title"', 'urn:m')):
        place = body[body.index(before):]
        assert f'<button type="button" class="reveal" data-reveal="{entity}" title="Reveal in graph view" ' \
            f'aria-label="Reveal {entity} in graph view">' in place
    assert 'data-reveal=""' not in body, 'an entity without an id has none'
    assert 'button.reveal:focus-visible' in html and 'color: var(--vscode-textLink-foreground)' in html


def test_the_menus(tmp_path):
    with open(PACKAGE_JSON) as handle:
        menus = json.load(handle)['contributes']['menus']
    assert {e['command'] for e in menus['webview/context']
            if e['when'] == "webviewSection == 'semforgeEntity'"} == {
        'semforge.revealInGraph', 'semforge.copyEntity', 'semforge.copySubtree', 'semforge.pin'}
    assert [e for e in menus['webview/context'] if e['command'] == 'semforge.revealInGraph'] == [
        {'command': 'semforge.revealInGraph', 'when': "webviewSection == 'semforgeEntity'", 'group': '1_reveal@1'}]
    rows = [e['when'] for e in menus['view/item/context'] if e['command'] == 'semforge.revealRowInGraph']
    assert rows == ['view == semforgeModel && viewItem =~ /^(entity|violation)$/',
                    'view == semforgeKnowledge && viewItem =~ /^(usage|instance)$/']


CASE = '/pkg/examples/c.jsonld'


@pytest.mark.parametrize('node, said, asks', [
    ({'case': CASE}, None, ['semforge/casePage']),
    ({}, None, ['semforge/modelPage']),
    ({'file': '/pkg/examples/sub.jsonld'}, {'ok': True, 'case': CASE},
     ['semforge/pageOfFile', 'semforge/casePage']),
    ({'file': '/pkg/model.jsonld'}, {'ok': True, 'case': ''}, ['semforge/pageOfFile', 'semforge/modelPage'])])
def test_the_page_that_holds_it_opens_on_its_path(tmp_path, node, said, asks):
    seen = _drive(tmp_path, {
        'command': 'semforge.revealInGraph',
        'node': dict(node, entity='urn:m', packageUri='file:///other/shacl.ttl'),
        'replies': {'semforge/pageOfFile': said, 'semforge/casePage': SCENE, 'semforge/modelPage': SCENE}})
    assert seen['errors'] == [], seen['errors']
    asked = [r for r in seen['requests'] if r['method'] in
             ('semforge/pageOfFile', 'semforge/casePage', 'semforge/modelPage')]
    assert [r['method'] for r in asked] == asks
    assert all(r['params']['uri'] == 'file:///other/shacl.ttl' for r in asked), 'in its own package'
    html = seen['webviews'][0]['html'][-1]
    assert 'data-openreveal="urn:m" data-asked="1"' in html


def test_a_file_no_page_shows_is_said(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.revealInGraph',
        'node': {'entity': 'urn:m', 'file': '/pkg/loose.jsonld', 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {'semforge/pageOfFile': {'ok': False, 'error': 'no page has its graph'}}})
    assert seen['webviews'] == [] and 'no page has its graph' in str(seen['warnings'])


@pytest.mark.parametrize('node', [{}, {'entity': ''}, {'entity': {'x': 1}}])
def test_without_an_id_there_is_nothing_to_reveal(tmp_path, node):
    seen = _drive(tmp_path, {'command': 'semforge.revealInGraph', 'node': node, 'replies': {}})
    assert seen['warnings'] and seen['webviews'] == []


def test_a_row_of_knowledge_names_its_file(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.revealRowInGraph',
        'node': {'key': 'k', 'raw': {'kind': 'usage', 'entity': 'urn:m', 'file': '/pkg/x.jsonld'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'replies': {}})
    told = _opened(seen, 'semforge.revealInGraph')[0][0]
    assert (told['entity'], told['file'], told['packageUri']) == ('urn:m', '/pkg/x.jsonld', 'file:///pkg/shacl.ttl')


def test_from_the_type_page(tmp_path):
    page = {'ok': True, 'iri': 'https://x/Motor', 'label': 'Motor', 'crumbs': [], 'summary': {},
            'rules': [], 'exercisedBy': [], 'subtypes': [], 'attributes': [],
            'instances': [{'id': 'urn:m', 'type': 'Motor', 'violations': []},
                          {'id': 'urn:n', 'type': 'Motor', 'violations': None}]}
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'label': 'Motor', 'targetClass': 'https://x/Motor',
                         'children': []}, 'packageUri': 'file:///other/shacl.ttl'},
        'webviewMessages': [{'command': 'revealGraph', 'entity': 'urn:m'}],
        'replies': {'semforge/typePage': page}})
    html = seen['webviews'][0]['html'][0]
    assert 'data-reveal="urn:m"' in html and 'data-reveal="urn:n"' in html
    assert '<body data-vscode-context="{&quot;packageUri&quot;:&quot;file:///other/shacl.ttl&quot;}">' in html
    told = _opened(seen, 'semforge.revealInGraph')[0][0]
    assert (told['entity'], told['packageUri']) == ('urn:m', 'file:///other/shacl.ttl')


def test_from_the_shape_page(tmp_path):
    page = {'ok': True, 'shape': 'https://x/S', 'name': 'ex:S', 'label': 'S', 'summary': {}, 'attributes': [],
            'checks': [], 'targets': [], 'usedBy': [], 'types': [],
            'reach': {'nodes': [{'id': 'urn:a', 'violations': []}, {'id': 'urn:b', 'violations': None}], 'more': 0},
            'exercisedBy': [{'case': 's/bad/c.jsonld', 'file': CASE, 'fired': 1, 'firedOn': ['urn:m'],
                             'held': False, 'passed': True, 'description': ''}]}
    seen = _drive(tmp_path, {
        'command': 'semforge.openShapePage',
        'node': {'raw': {'shape': 'https://x/S'}, 'packageUri': 'file:///other/shacl.ttl'},
        'webviewMessages': [{'command': 'revealGraph', 'entity': 'urn:m', 'case': CASE}],
        'replies': {'semforge/shapePage': page}})
    html = seen['webviews'][0]['html'][0]
    assert f'data-reveal="urn:m" data-revealcase="{CASE}"' in html
    assert all(f'data-reveal="{id_}" title' in html for id_ in ('urn:a', 'urn:b'))
    told = _opened(seen, 'semforge.revealInGraph')[0][0]
    assert (told['entity'], told['case'], told['packageUri']) == ('urn:m', CASE, 'file:///other/shacl.ttl')


@pytest.mark.parametrize('name', ['typepage', 'shapepage'])
def test_the_button_is_what_these_pages_post(tmp_path, name):
    """The click handler of the page itself, in the browser."""
    with open(os.path.join(SRC, name + '.js')) as handle:
        source = handle.read()
    assert "command: 'revealGraph', entity: target.dataset.reveal, case: target.dataset.revealcase" in source
    assert re.search(r"closest\('\[data-reveal\],", source)


SHOW = '''
const Module = require('module');
const load = Module._load;
const posted = [];
const panel = { visible: true, webview: { html: '', onDidReceiveMessage() {}, postMessage: (m) => posted.push(m) },
  onDidDispose() {}, onDidChangeViewState() {}, reveal() {} };
const said = [];
Module._load = (name, ...rest) => name === 'vscode' ? { ViewColumn: { Active: 1 }, window: {
  createWebviewPanel: () => panel, showInformationMessage: (text) => said.push(text) } } : load(name, ...rest);
const { CasePages } = require(process.argv[2] + '/casepage.js');
let page = JSON.parse(process.argv[3]);
let requests = 0;
const pages = new CasePages({ client: { sendRequest: async () => { requests += 1; return page; } } });
(async () => {
  const out = [];
  const step = async (act) => { posted.length = 0; requests = 0; await act();
    out.push({ posted: posted.slice(), requests, asked: (/data-asked="([0-9]+)"/.exec(panel.webview.html) || [])[1],
      reveal: (/data-openreveal="([^"]*)"/.exec(panel.webview.html) || [])[1] }); };
  const show = (focus, reveal) => pages.show('file:///p/shacl.ttl', '@model', focus, false, reveal ? { reveal } : {});
  await step(() => show('urn:p1'));
  await step(() => show('urn:p1'));                 // the same again: land
  await step(() => show(undefined, 'urn:m'));       // in sight: the page does it
  await step(() => pages.render());                 // drawn again
  panel.visible = false;
  await step(() => show(undefined, 'urn:d'));       // not in sight: drawn with it
  panel.visible = true;
  page = { ok: false, error: 'broken' };
  await step(() => pages.render());
  page = JSON.parse(process.argv[3]);
  await step(() => show(undefined, 'urn:m'));       // nothing there to do it
  await pages.receive({ command: 'noReveal', entity: 'urn:gone' });
  pages.asked = 10;
  await show('urn:p1');
  page = JSON.parse(process.argv[3]);
  await show(undefined, 'urn:m');                   // on the page in sight: it keeps what it was opened at
  const kept = pages.current;
  console.log(JSON.stringify({ out, said, kept }));
})();
'''


def test_an_open_page_is_asked_and_one_that_cannot_answer_is_drawn(tmp_path):
    script = tmp_path / 'show.js'
    script.write_text(SHOW)
    done = subprocess.run([_node(), str(script), SRC, json.dumps(SCENE)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-1500:]
    told = json.loads(done.stdout)
    out = told['out']
    assert out[0]['requests'] == 1 and out[0]['asked'] == '1'
    assert out[1]['posted'] == [{'asked': '2', 'command': 'land'}] and out[1]['requests'] == 0
    assert out[2]['posted'] == [{'asked': '3', 'command': 'reveal', 'entity': 'urn:m'}] and out[2]['requests'] == 0
    assert (out[3]['asked'], out[3]['reveal']) == ('3', 'urn:m'), 'lost on the way, it is in the next drawing'
    assert out[4]['requests'] == 1 and (out[4]['asked'], out[4]['reveal']) == ('4', 'urn:d')
    assert out[5].get('reveal') is None
    assert out[6]['requests'] == 1 and out[6].get('reveal') == 'urn:m'
    assert 'urn:gone is not on this page' in told['said'][0]
    assert (told['kept']['focus'], told['kept']['reveal'], told['kept']['asked']) == ('urn:p1', 'urn:m', '12')


# --- the server ---------------------------------------------------------------------------

@pytest.fixture
def kms(tmp_path):
    target = tmp_path / 'kms'
    shutil.copytree(os.path.join(CORPUS, 'kms'), target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return load(str(target))


def test_which_page_shows_a_file(kms, tmp_path):
    from semforge.expect.store import examples_root, load_expectations

    root = examples_root(kms.path)
    examples = load_expectations(kms.path).examples
    for example in examples:
        assert page_of_file(kms, os.path.join(root, example.path)) == \
            os.path.abspath(os.path.join(root, example.path))
    cases = {os.path.realpath(os.path.join(root, e.path)) for e in examples}
    including = [(e, i) for e in examples for i in e.include
                 if os.path.realpath(os.path.join(root, i)) not in cases]
    assert including
    for example, included in including:
        path = os.path.join(root, included)
        if os.path.exists(path):
            shown = page_of_file(kms, path)
            holder = next(e for e in examples if os.path.abspath(os.path.join(root, e.path)) == shown)
            assert included in holder.include
    for path in kms.files('model'):
        assert page_of_file(kms, path) == ''
    link = tmp_path / 'link.jsonld'
    link.symlink_to(kms.files('model')[0])
    assert page_of_file(kms, str(link)) == '', 'a link is the file it is to'
    assert page_of_file(kms, 'model-instance.jsonld') == '', 'relative to the package'
    loose = tmp_path / 'loose.jsonld'
    loose.write_text('[]')
    with pytest.raises(PackageError, match='loose.jsonld'):
        page_of_file(kms, str(loose))


def _prefixed_case(kms):
    """urn:filter:9 of a case, written as iffBaseEntities:filter9."""
    from semforge.expect.store import examples_root

    path = os.path.join(examples_root(kms.path), 'test_FilterShape', 'bad', 'without-cartridge.jsonld')
    with open(path) as handle:
        text = handle.read()
    with open(path, 'w') as handle:
        handle.write(text.replace('"urn:filter:9"', '"iffBaseEntities:filter9"'))
    return load(kms.path), path


def test_a_use_in_knowledge_names_the_entity_as_written_and_its_file(kms):
    from semforge.cooked.knowledge import build_knowledge

    package, path = _prefixed_case(kms)
    found = []

    def walk(node):
        if node.kind in ('usage', 'instance') and 'filter9' in node.entity:
            found.append((node.kind, node.entity, node.file))
        for child in node.children:
            walk(child)

    for root in build_knowledge(package):
        walk(root)
    assert found and all(entity == 'iffBaseEntities:filter9' and os.path.realpath(file) == os.path.realpath(path)
                         for _, entity, file in found), found
    assert {kind for kind, _, _ in found} == {'usage', 'instance'}
    assert page_of_file(package, found[0][2]) == os.path.abspath(path)


def test_a_card_says_its_id_spelled_out(kms):
    from semforge.cooked.casepage import build_case_page

    package, path = _prefixed_case(kms)
    page = build_case_page(package, path)
    card = next(c for f in page['files'] for c in f['cards'] if c['id'] == 'iffBaseEntities:filter9')
    assert card['iri'] == 'https://industryfusion.github.io/contexts/example/v0/base_entities/filter9'
    model = build_model_page(load(os.path.join(CORPUS, 'opcua-pumps')))
    assert all(c['iri'] == c['id'] for c in model['files'][0]['cards']), 'a relative id is as written'


def test_a_row_says_what_it_points_at_as_written(kms):
    page = build_model_page(kms)
    rows = [r for c in page['files'][0]['cards'] for r in c['attributes']]
    assert any(r['kind'] == 'Relationship' and r['target'] == r['value'] for r in rows)
    with open(kms.files('model')[0]) as handle:
        document = json.load(handle)
    document.append({'id': 'urn:here:1', 'type': document[0]['type'], '@context': document[0].get('@context'),
                     'hasIt': {'type': 'Relationship', 'object': 'ex:other'}})
    with open(kms.files('model')[0], 'w') as handle:
        json.dump(document, handle)
    page = build_model_page(load(kms.path))
    row = next(c for c in page['files'][0]['cards'] if c['id'] == 'urn:here:1')['attributes'][0]
    assert (row['value'], row['target']) == ('other', 'ex:other')


# --- spellings, lists of objects, includes, rows of the view ------------------------------

def test_a_use_keeps_the_places_of_every_spelling(tmp_path):
    """One entity, written in full in one file and with a prefix in another:
    each keeps its own file."""
    from rdflib import Graph, Literal, URIRef

    from semforge.cooked.knowledge import _usages

    full = 'https://industryfusion.github.io/contexts/example/v0/base_entities/f9'
    graph = Graph()
    graph.add((URIRef(full), URIRef('https://x/hasState'), URIRef('https://x/ON')))
    graph.add((URIRef(full), URIRef('https://x/hasName'), Literal('n')))
    package = load(os.path.join(CORPUS, 'kms'))
    expected = [(full, 'hasState', '/a.jsonld:3'), ('iffBaseEntities:f9', 'hasState', '/b.jsonld:7')]
    for places in ({(full, 'hasState'): ['/a.jsonld:3'], ('iffBaseEntities:f9', 'hasState'): ['/b.jsonld:7']},
                   {('iffBaseEntities:f9', 'hasState'): ['/b.jsonld:7'], (full, 'hasState'): ['/a.jsonld:3']}):
        assert sorted(_usages(graph, places, package)['https://x/ON']) == expected


def test_a_page_drawn_for_another_case_is_not_the_one_in_sight(tmp_path):
    script = tmp_path / 'other.js'
    script.write_text(SHOW.split('(async () => {')[0] + '''
(async () => {
  const first = JSON.parse(process.argv[3]);
  let release;
  const slow = new Promise((resolve) => { release = resolve; });
  let calls = 0;
  pages.clientHolder.client.sendRequest = async () => { calls += 1; if (calls === 2) { await slow; } return first; };
  await pages.show('file:///p/shacl.ttl', '@model', undefined, false, {});
  const other = pages.show('file:///p/shacl.ttl', '/p/examples/b.jsonld', undefined, false, {});
  posted.length = 0;
  const asked = pages.show('file:///p/shacl.ttl', '/p/examples/b.jsonld', undefined, false, { reveal: 'urn:m' });
  release();
  await other; await asked;
  console.log(JSON.stringify({ posted, calls, html: /data-openreveal="([^"]*)"/.exec(panel.webview.html) }));
})();
''')
    done = subprocess.run([_node(), str(script), SRC, json.dumps(SCENE)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-1500:]
    told = json.loads(done.stdout)
    assert told['posted'] == [], 'not posted to the page of another case'
    assert told['calls'] == 3 and told['html'][1] == 'urn:m', 'drawn with it'


def test_a_prefixed_relationship_keeps_its_type_and_short_id_in_the_graph(tmp_path, monkeypatch):
    scene = _scene([_card('urn:a', 'ex:A', [dict(_rel('hasB', 'b'), target='ex:b')]),
                    _card('ex:b', 'ex:B', [_row('hasN')])])
    monkeypatch.setattr(test_entity_graph, 'PAGE', scene)
    graph = test_entity_graph._graph(test_entity_graph._dom(tmp_path, ''))
    assert 'data-rel="ex:b"' in graph
    assert '<a class="dim" tabindex="0" role="link" title="Open the ex:B page" data-type="ex:B">ex:B</a> ' \
        '<span title="ex:b">ex:b</span>' in graph


@pytest.mark.parametrize('target, offered', [('urn:b', 'urn:b'), ('', None)])
def test_reveal_only_on_a_relationship_to_one_entity(tmp_path, monkeypatch, target, offered):
    """A list of objects is no edge of the graph, and offers nothing."""
    row = dict(_rel('hasB', 'urn:b' if target else '[urn:b, urn:c]'), target=target)
    monkeypatch.setattr(test_entity_graph, 'PAGE', _scene([_card('urn:a', 'ex:A', [row]),
                                                           _card('urn:b', 'ex:B', [_row('hasN')])]))
    html = _render(tmp_path).read_text().split('id="cardview"')[1].split('<script')[0]
    attr = html.split('data-name="hasB"')[0].rsplit('<div', 1)[1]
    if offered:
        assert 'data-rel="urn:b"' in attr and 'data-reveal="urn:b"' in html
    else:
        assert 'data-rel=' not in attr and 'data-reveal="[' not in html and '&quot;[urn:b' not in html


def test_a_relationship_to_an_object_says_its_id(kms):
    with open(kms.files('model')[0]) as handle:
        document = json.load(handle)
    document.append({'id': 'urn:here:2', 'type': document[0]['type'], '@context': document[0].get('@context'),
                     'hasOne': {'type': 'Relationship', 'object': {'@id': 'urn:filter:1'}},
                     'hasMany': {'type': 'Relationship', 'object': ['urn:filter:1', 'urn:filter:2']}})
    with open(kms.files('model')[0], 'w') as handle:
        json.dump(document, handle)
    rows = {r['name']: r for r in next(c for c in build_model_page(load(kms.path))['files'][0]['cards']
                                       if c['id'] == 'urn:here:2')['attributes']}
    assert rows['hasOne']['target'] == 'urn:filter:1'
    assert rows['hasMany']['target'] == ''


def test_a_row_of_the_view_is_known_by_its_key(tmp_path):
    """The view hands a menu the row it drew; after a refresh that is another
    object with the same key."""
    entity = {'kind': 'entity', 'label': 'urn:m', 'entity': 'urn:m', 'file': '/pkg/model.jsonld', 'children': []}
    seen = _drive(tmp_path, {
        'replies': {'semforge/model': {'roots': [entity]}, 'semforge/modelPage': SCENE},
        'drawTrees': ['semforgeModel'],
        'command': 'semforge.revealRowInGraph',
        'node': {'key': '/0:entity:urn:m:', 'raw': entity, 'packageUri': 'file:///pkg/shacl.ttl'}})
    told = _opened(seen, 'semforge.revealInGraph')[0][0]
    assert told.get('file') is None, 'a row of this view, not of Knowledge'


def test_an_include_is_where_a_case_reads_it(kms, monkeypatch):
    """Both examples/shared.jsonld and shared.jsonld beside the package exist: the
    case reads the first, so only the first is the case's."""
    from types import SimpleNamespace

    import semforge.expect.store as store

    root = store.examples_root(kms.path)
    for path in (os.path.join(root, 'shared.jsonld'), os.path.join(kms.path, 'shared.jsonld')):
        with open(path, 'w') as handle:
            handle.write('[]')
    case = SimpleNamespace(path='s/c.jsonld', include=['shared.jsonld'])
    monkeypatch.setattr(store, 'load_expectations', lambda path: SimpleNamespace(examples=[case]))
    assert page_of_file(kms, os.path.join(root, 'shared.jsonld')) == os.path.join(root, 's', 'c.jsonld')
    with pytest.raises(PackageError):
        page_of_file(kms, os.path.join(kms.path, 'shared.jsonld'))
    os.remove(os.path.join(root, 'shared.jsonld'))
    assert page_of_file(kms, os.path.join(kms.path, 'shared.jsonld')) == os.path.join(root, 's', 'c.jsonld')
