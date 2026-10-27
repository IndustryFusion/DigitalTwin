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

"""A violation is something to go to, not only a count.

The Problems panel said "2 violation(s) here" on the SHAPE, a click on it
opened shacl.ttl; the tree said "· 1 violation(s)" at the end of a grey
line; the Main page drew a red border, and nothing led from one to the next.
Now each violation of the model is a problem on its own row in the data
(F8 steps through them), the Main and case pages list them -- a click goes
there -- and filter to what violates, and the tree says it first.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

SDK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(SDK, 'vscode', 'src')
RENDER = os.path.join(SDK, 'tests', 'harness', 'render_casepage.js')
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')


# --- the Problems panel -----------------------------------------------------------------

def test_each_violation_of_the_model_is_a_problem_on_its_row(corpus):
    """The kms' Main has entities without the required hasXXXWorkpiece."""
    from semforge.editor.analysis import analyse

    found, package = analyse(corpus.path, package=corpus)
    model = os.path.abspath(package.sources['model'])
    violations = [f for f in found.get(model, []) if f.kind == 'violation']
    assert violations, 'the corpus model violates something'
    cutter = next(f for f in violations if f.subject == 'urn:cutter:1')
    assert cutter.message == 'urn:cutter:1: hasXXXWorkpiece is required but missing (MachineShape)'
    assert cutter.code == 'model-violation' and cutter.data['entity'] == 'urn:cutter:1'
    with open(model, encoding='utf-8') as handle:
        lines = handle.read().split('\n')
    near = '\n'.join(lines[cutter.line - 1:cutter.line + 2])
    assert 'urn:cutter:1' in near, f'line {cutter.line} is not the entity: {near}'
    assert cutter.severity == 'error', 'a violation is the error the panel leads with'
    # Nothing about it on the shapes: a click there would open the .ttl.
    shapes = os.path.abspath(package.sources['shapes'])
    assert not [f for f in found.get(shapes, []) if 'hasXXXWorkpiece' in f.message]


def test_its_quick_fix_shows_it_on_the_main_page():
    from lsprotocol import types

    from semforge.editor.documents import _fixes_for

    diagnostic = types.Diagnostic(
        range=types.Range(types.Position(1, 0), types.Position(1, 200)), message='x',
        data={'code': 'model-violation', 'subject': 'urn:w:1', 'entity': 'urn:w:1',
              'attribute': 'hasWidth'})
    [action] = _fixes_for(diagnostic, 'file:///pkg/model-instance.jsonld')
    assert action.title == 'Show it on the Main page'
    assert action.command.command == 'semforge.openModelPage'
    assert action.command.arguments == [{'packageUri': 'file:///pkg/model-instance.jsonld',
                                         'focus': 'urn:w:1', 'attribute': 'hasWidth'}]


# --- the Main page ----------------------------------------------------------------------

def _row(name, violations=(), kind='Property', value='1'):
    return {'name': name, 'term': 'ex:' + name, 'kind': kind, 'value': value, 'dataset': '',
            'unitCode': '', 'observedAt': '', 'stamp': {}, 'latestAt': '', 'superseded': False,
            'instances': 1, 'line': 1, 'violations': list(violations), 'children': [],
            'display': name}


def _card(id_, rows, violations=()):
    return {'id': id_, 'type': 'ex:T', 'file': '/pkg/model.jsonld', 'line': 1,
            'violations': list(violations), 'attributes': rows}


WIDE = {'text': 'hasWidth is above its maximum', 'shape': 'WorkpieceShape', 'detail': ''}
MISSING = {'text': 'hasPort is required but missing', 'shape': 'PumpShape', 'detail': ''}
PAGE = {
    'kind': 'model', 'name': 'Main', 'case': '', 'expect': '', 'group': '', 'suite': '',
    'description': '', 'passed': True, 'failures': [], 'claims': [], 'unasserted': [],
    'residuePinned': False, 'file': '/pkg/model.jsonld', 'expectations': '',
    'verdicts': {'state': 'ready'}, 'summary': {'entities': 3, 'violations': 2, 'includes': 0},
    'files': [{'role': 'model', 'path': '/pkg/model.jsonld', 'relative': 'model.jsonld',
               'sharedBy': [], 'cards': [
                   _card('urn:a', [_row('hasSpeed')]),
                   _card('urn:b', [_row('hasHeight'), _row('hasWidth', [WIDE])]),
                   _card('urn:c', [_row('hasSpeed')], [MISSING])]}],
}


def _node():
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    return node


def _render(tmp_path, page=PAGE, after=None):
    path = tmp_path / 'page.json'
    path.write_text(json.dumps(page))
    out = tmp_path / 'page.html'
    args = [_node(), RENDER, SRC, str(path), str(out)]
    if after:
        (tmp_path / 'after.js').write_text(after)
        args.append(str(tmp_path / 'after.js'))
    run = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[-1500:]
    return out


def _dom(tmp_path, after, page=PAGE):
    from test_entity_graph import _chrome

    out = _render(tmp_path, page, after)
    return subprocess.run([_chrome(), '--headless=new', '--no-sandbox', '--disable-gpu',
                           '--virtual-time-budget=3000', '--dump-dom', 'file://' + str(out)],
                          capture_output=True, text=True, timeout=120).stdout


def test_the_page_lists_each_violation_with_the_way_to_it(tmp_path):
    html = _render(tmp_path).read_text()
    assert '<h2 id="violations">Violations <span class="dim">· 2</span></h2>' in html
    # What the Problems panel is, and the way to it: nothing said either.
    assert 'data-problems="1">Open the Problems panel</a>' in html
    # The count at the top leads to the list.
    assert re.search(r'data-jumplist="1"[^>]*><span class="chip warn"[^>]*>2 violation', html)
    # The whole line goes there, not only its link: the message is most of it.
    assert re.search(r'<li data-jump="0\.1\.1"[^>]*><a tabindex="0" role="link">urn:b · hasWidth</a> '
                     r'hasWidth is above its maximum', html)
    assert re.search(r'<li data-jump="0\.2"[^>]*><a tabindex="0" role="link">urn:c</a> hasPort is required', html)
    assert 'class="attr violates" data-at="0.1.1" data-name="hasWidth"' in html
    assert '<input id="fbad" type="checkbox"> only what violates' in html


def test_a_page_without_violations_lists_none(tmp_path):
    clean = json.loads(json.dumps(PAGE))
    for card in clean['files'][0]['cards']:
        card['violations'] = []
        for row in card['attributes']:
            row['violations'] = []
    assert '<h2>Violations' not in _render(tmp_path, clean).read_text()


def test_only_what_violates_hides_the_rest(tmp_path):
    dom = _dom(tmp_path, '''
document.getElementById('fbad').click();
''')
    shown = re.findall(r'<div class="card([^"]*)"[^>]* data-id="([^"]+)"([^>]*)>', dom)
    visible = sorted(i for cls, i, rest in shown if 'hidden' not in rest)
    assert visible == ['urn:b', 'urn:c'], shown
    assert re.search(r'id="fcount"[^>]*>2 of 3 shown<', dom)


def test_a_violation_in_the_list_goes_to_its_row(tmp_path):
    """Even when the filter hid its card: the jump clears it."""
    dom = _dom(tmp_path, '''
document.getElementById('fid').value = 'urn:a';
document.getElementById('fid').dispatchEvent(new Event('input'));
// The message part of the line -- clicking it did nothing when only the
// entity and attribute were the link.
document.querySelector('li[data-jump="0.1.1"] .dim').click();
var row = document.querySelector('.attr[data-at="0.1.1"]');
document.documentElement.dataset.flashed = String(row.classList.contains('flash'));
document.documentElement.dataset.shown = String(!row.closest('.card').hidden);
''')
    assert re.search(r'<html[^>]* data-flashed="true"', dom)
    assert re.search(r'<html[^>]* data-shown="true"', dom)


def test_opened_at_an_attribute_marks_its_row(tmp_path):
    page = dict(PAGE, __options={'focus': 'urn:b', 'attribute': 'hasWidth'})
    dom = _dom(tmp_path, '''
var row = document.querySelector('.attr[data-name="hasWidth"]');
document.documentElement.dataset.flashed = String(row.classList.contains('flash'));
''', page)
    assert re.search(r'<html[^>]* data-flashed="true"', dom)


LANDED = """
setTimeout(function () {
  var row = document.querySelector('.attr[data-name="hasWidth"]');
  var box = row.getBoundingClientRect();
  var d = document.documentElement.dataset;
  d.inview = String(box.height > 0 && box.top >= 0 && box.bottom <= window.innerHeight);
  d.flashed = String(row.classList.contains('flash'));
  d.cards = String(!document.getElementById('cardview').hidden);
}, WAIT);
"""


def _long_page(**more):
    page = json.loads(json.dumps(PAGE))
    page['files'][0]['cards'][:0] = [_card(f'urn:f{i}', [_row('hasSpeed')]) for i in range(40)]
    page['__options'] = {'focus': 'urn:b', 'attribute': 'hasWidth'}
    page.update(more)
    return page


REMEMBERED = [
    {'bad': True, 'open': True},          # hid the cards above AFTER the jump
    {'view': 'graph'},                    # the card was in the hidden list
    {'id': 'urn:a'},                      # the filter hid the card itself
]


@pytest.mark.parametrize('remembered', REMEMBERED)
def test_opened_at_a_violation_it_is_in_sight_whatever_the_page_remembered(
        tmp_path, remembered):
    """The jump comes last: a remembered filter or view used to move it away."""
    page = _long_page(__state={'/pkg/model.jsonld': remembered})
    dom = _dom(tmp_path, LANDED.replace('WAIT', '500'), page)
    assert re.search(r'<html[^>]* data-cards="true"', dom), 'the cards, where the row is'
    assert re.search(r'<html[^>]* data-flashed="true"', dom)
    assert re.search(r'<html[^>]* data-inview="true"', dom), 'scrolled to it'


@pytest.mark.parametrize('remembered', REMEMBERED)
def test_opened_at_an_entity_s_own_violation_its_card_is_in_sight(tmp_path, remembered):
    """A missing attribute has no row: the card is the place."""
    page = _long_page(__state={'/pkg/model.jsonld': remembered})
    page['__options'] = {'focus': 'urn:c', 'attribute': 'hasPort'}
    dom = _dom(tmp_path, LANDED.replace('WAIT', '500').replace(
        """document.querySelector('.attr[data-name="hasWidth"]')""",
        """document.querySelector('.card[data-id="urn:c"]')"""), page)
    assert re.search(r'<html[^>]* data-cards="true"', dom)
    assert re.search(r'<html[^>]* data-inview="true"', dom), 'scrolled to it'


def test_clicked_again_it_jumps_again(tmp_path):
    """The tree sends `land` when the page already shows that violation."""
    dom = _dom(tmp_path, """
setTimeout(function () {
  window.scrollTo(0, 0);
  window.postMessage({ command: 'land' }, '*');
}, 200);
""" + LANDED.replace('WAIT', '700'), _long_page())
    assert re.search(r'<html[^>]* data-inview="true"', dom)


# What VS Code's webview host does on a click of a link (handleInnerClick in its
# pre/index.html), the defaultPrevented of the page's own handler ignored. It
# acts on trusted clicks only, so here it is installed for the synthetic one.
VSCODE_LINKS = """
window.addEventListener('click', function (event) {
  for (const node of event.composedPath()) {
    if (node.tagName && node.tagName.toLowerCase() === 'a' && node.href) {
      if (node.getAttribute('href') === '#') { event.view.scrollTo(0, 0); }
      event.preventDefault();
      return;
    }
  }
});
"""


def test_a_link_in_the_list_is_not_undone_by_vscode(tmp_path):
    """The user's case: the entity link of a line in the list. VS Code
    scrolled the page back to its top after the jump, for every href="#"."""
    page = _long_page(__options={})
    dom = _dom(tmp_path, VSCODE_LINKS + """
setTimeout(function () {
  document.querySelector('li[data-jump="0.41.1"] a').click();
}, 200);
""" + LANDED.replace('WAIT', '900'), page)
    assert re.search(r'<html[^>]* data-flashed="true"', dom)
    assert re.search(r'<html[^>]* data-inview="true"', dom), 'still at the row'


def test_no_page_links_to_hash():
    """Every page: a link to "#" scrolls it to the top in VS Code, whatever
    the page's handler does. Links have no href (role=link, tabindex 0)."""
    found = []
    for name in sorted(os.listdir(SRC)):
        if name.endswith('.js'):
            with open(os.path.join(SRC, name), encoding='utf-8') as handle:
                source = handle.read()
            if re.search(r"""href=\\?["']#|\.href = ["']#""", source):
                found.append(name)
    assert not found, found


def test_opened_from_a_count_it_shows_only_what_violates(tmp_path):
    page = dict(PAGE, __options={'only': True})
    dom = _dom(tmp_path, 'document.documentElement.dataset.ticked = '
                         'String(document.getElementById("fbad").checked);', page)
    assert re.search(r'<html[^>]* data-ticked="true"', dom)
    assert re.search(r'id="fcount"[^>]*>2 of 3 shown<', dom)


# --- the tree ---------------------------------------------------------------------------

def _tree(tmp_path, roots):
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps({'mode': 'items', 'provider': 'ModelTreeProvider',
                                'uri': 'file:///pkg/shacl.ttl',
                                'replies': {'semforge/model': {'roots': roots}}}))
    out = subprocess.run([_node(), DRIVE, str(tmp_path), os.path.join(SRC, 'model.js'), str(path)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])['rows']


def test_a_violating_row_says_it_first(tmp_path, corpus):
    from semforge.cooked.examples import build_suite
    from semforge.editor.verdicts import compute
    from semforge.editor.views import _serialise_example

    roots = [_serialise_example(n) for n in build_suite(corpus, verdicts=compute(corpus, 'x'))]
    rows = _tree(tmp_path, roots)
    cutter = next(r for r in rows if r['kind'] == 'entity' and r['label'] == 'urn:cutter:1')
    assert cutter['description'].startswith('✗ 1 violation(s)'), cutter['description']
    assert cutter['drawn'] == {'label': 'urn:cutter:1', 'highlights': [[0, 12]]}
    assert cutter['color'] == 'list.errorForeground'
    clean = next(r for r in rows if r['kind'] == 'entity' and r['label'] == 'urn:plasmacutter:1')
    assert not clean['description'].startswith('✗') and clean['drawn'] == 'urn:plasmacutter:1'


def _click(tmp_path, raw, parent=None):
    """A click in the Entities & Test Cases view on `raw` under Main."""
    main = {'kind': 'group', 'label': 'Main', 'severity': 'violation', 'children': []}
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps({
        'mode': 'select', 'view': 'semforgeModel', 'config': {}, 'labelPath':
            ['Main'] + ([parent['label']] if parent else []) + ([raw['label']] if raw else []),
        'replies': {'semforge/model': {'roots': [dict(main, children=[dict(
            parent or raw or {}, children=[raw] if parent else [])] if (parent or raw) else [])]},
                    'semforge/tree': {'roots': []}, 'semforge/shapes': {'roots': []},
                    'semforge/knowledge': {'roots': []}}}))
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    out = subprocess.run([_node(), DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    seen = json.loads(out.stdout.strip().splitlines()[-1])
    assert seen['errors'] == [], seen['errors']
    return [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openModelPage']


def test_main_with_violations_opens_only_what_violates(tmp_path):
    [args] = _click(tmp_path, None)
    assert args[1].get('only') is True


def test_a_violating_attribute_opens_the_page_at_its_row(tmp_path):
    entity = {'kind': 'entity', 'label': 'urn:w:1', 'entity': 'urn:w:1',
              'severity': 'violation', 'children': []}
    attribute = {'kind': 'attribute', 'label': 'hasWidth', 'entity': 'urn:w:1',
                 'attributePath': ['ex:hasWidth'], 'severity': 'violation', 'children': []}
    [args] = _click(tmp_path, attribute, entity)
    assert args[1]['focus'] == 'urn:w:1' and args[1]['attribute'] == 'hasWidth'
    assert 'only' not in args[1]


def test_the_count_at_the_top_leads_to_the_list(tmp_path):
    dom = _dom(tmp_path, """
document.querySelector('[data-jumplist]').click();
document.documentElement.dataset.flashed =
  String(document.getElementById('violations').classList.contains('flash'));
""")
    assert re.search(r'<html[^>]* data-flashed="true"', dom)


# --- the Problems panel, with nothing open --------------------------------------------

def test_without_an_open_file_the_problems_still_come(monkeypatch, corpus_path):
    """The pages are where a package is worked on: waiting for an open .ttl
    left the Problems panel empty while the Main page counted violations."""
    from semforge.editor import validation

    sent = []

    class Workspace:
        text_documents = {}

    class Server:
        workspace = Workspace()

    monkeypatch.setattr(validation, 'server', Server())
    monkeypatch.setattr(validation, 'publish', lambda ls, uri: sent.append(uri))
    validation._republish(corpus_path)
    assert sent == ['file://' + os.path.join(corpus_path, 'shacl.ttl')]
