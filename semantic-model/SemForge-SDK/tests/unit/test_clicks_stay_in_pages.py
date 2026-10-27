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

"""A click stays in SemForge; the file is an option, never the default.

A click shows what was clicked on its page, marked there -- the type page for
an attribute, the vocabulary page for a value. Its lines in the .ttl or the
.jsonld are one deliberate step away: a button or a ⋯ entry that says "Open".
Something just made is shown where it is changed, with the file offered.
The file itself was a dead end: no verdicts, no inherited constraints, no
editor -- an attribute clicked on the Main page landed in it.
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
KNOW = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/'
CUTTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/StateOnCutterShape'


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


def _render(tmp_path, target, function, payload, **options):
    return _node(tmp_path, {'mode': 'render', 'function': function, 'payload': payload,
                            'options': dict({'nonce': 'n'}, **options)}, target)['html']


def _file_links(html):
    """The text of everything a click on which opens a file."""
    return [re.sub(r'<[^>]+>', '', text).strip() for text in re.findall(
        r'<(?:a|button)\b[^>]*\bdata-open="[^"]*"[^>]*>(.*?)</(?:a|button)>', html, re.S)]


def _only_explicit(html):
    for text in _file_links(html):
        assert text.startswith('Open') or text == '.ttl', \
            f'"{text}" opens a file without saying so'


# --- the pages: nothing opens a file but what says "Open" -----------------------------

@pytest.fixture(scope='module')
def pages(corpus):
    from semforge.cooked.casepage import build_case_page, build_model_page
    from semforge.cooked.shapepage import build_shape_page
    from semforge.cooked.typepage import build_type_page
    from semforge.cooked.vocabulary import build_vocabulary_page

    return {
        'case': build_case_page(corpus, 'test_FilterShape/bad/without-cartridge.jsonld'),
        'main': build_model_page(corpus),
        'type': build_type_page(corpus, 'iffBaseEntities:Filter'),
        'shape': build_shape_page(corpus, CUTTER),
        'vocabulary': build_vocabulary_page(corpus, f'{KNOW}MachineState'),
    }


@pytest.mark.parametrize('name, target, function', [
    ('case', 'casepage.js', 'renderCasePage'),
    ('main', 'casepage.js', 'renderCasePage'),
    ('type', 'typepage.js', 'renderTypePage'),
    ('shape', 'shapepage.js', 'renderShapePage'),
    ('vocabulary', 'vocabpage.js', 'renderVocabularyPage'),
])
def test_no_page_opens_a_file_on_a_plain_click(tmp_path, pages, name, target, function):
    _only_explicit(_render(tmp_path, target, function, pages[name]))


def test_an_attribute_on_the_main_page_opens_its_type_page(tmp_path, pages):
    page = pages['main']
    html = _render(tmp_path, 'casepage.js', 'renderCasePage', page)
    card = next(c for f in page['files'] for c in f['cards']
                if any(r['name'] == 'hasState' for r in c['attributes']))
    name = re.search(r'<a tabindex="0" role="link" data-type="([^"]+)" data-names="([^"]+)"[^>]*>hasState</a>',
                     html)
    assert name, 'the attribute name is not a type-page link'
    assert name.group(1) == card['type']
    assert json.loads(name.group(2).replace('&quot;', '"')) == ['hasState']
    # A sub-attribute names its parent too: the type page marks the deeper row.
    assert re.search(r'data-names="\[&quot;hasState&quot;,&quot;hasXXXWorkpiece&quot;\]"', html)
    # The entity's id and the file are text now; the file has its Open button.
    assert f'<span class="mono">{card["id"]}</span>' in html
    assert '>Open .jsonld</button>' in html


def test_the_click_opens_the_type_page_with_the_attribute_marked(tmp_path, pages):
    page = pages['main']
    seen = _node(tmp_path, {
        'command': 'semforge.openModelPage',
        'node': {'raw': {'kind': 'model', 'label': 'Main', 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'type', 'name': 'Cutter',
                             'names': ['hasState', 'hasXXXWorkpiece']}],
        'replies': {'semforge/casePage': dict(page, ok=True)}}, 'extension.js')
    opened = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openTypePage']
    assert opened[0][0]['raw'] == {'targetClass': 'Cutter',
                                   'focusNames': ['hasState', 'hasXXXWorkpiece']}
    assert seen['shown'] == []


def test_every_attribute_row_offers_its_jsonld_in_its_menu(tmp_path, pages):
    page = pages['main']
    html = _render(tmp_path, 'casepage.js', 'renderCasePage', page)
    rows = html.count('<div class="attr')
    assert rows and html.count('data-rowmenu=') == rows


# --- the type page marks an attribute by its names -------------------------------------

def test_the_type_page_marks_an_attribute_by_its_names(tmp_path, pages):
    html = _render(tmp_path, 'typepage.js', 'renderTypePage', pages['type'],
                   focus={'names': ['hasState', 'hasXXXWorkpiece']})
    assert html.count('id="focus"') == 1
    row = html.split('id="focus"', 1)[1].split('</tr>', 1)[0]
    assert 'has<wbr>XXXWorkpiece' in row, 'the deepest row the names reach'


def test_an_attribute_just_added_opens_its_editor(tmp_path, pages):
    page = dict(pages['type'], ok=True)
    seen = _node(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'targetClass': page['iri'], 'focusNames': ['hasCartridge']},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'args': [{'edit': True}],
        'replies': {'semforge/typePage': page,
                    'semforge/valueForms': {'ok': True, 'editable': True, 'forms': [],
                                            'said': 'any value'},
                    'semforge/choices': {'choices': []}}}, 'extension.js')
    editors = [w for w in seen['webviews'] if w['viewType'] == 'semforgeAttribute']
    assert editors and editors[0]['title'] == 'Attribute: hasCartridge'
    assert seen['shown'] == []


# --- the vocabulary page --------------------------------------------------------------

def test_a_value_is_text_and_its_ttl_is_in_its_menu(tmp_path, pages):
    page = pages['vocabulary']
    html = _render(tmp_path, 'vocabpage.js', 'renderVocabularyPage', page)
    value = page['values'][0]
    assert f'>{value["name"]}</span></td>' in html
    assert 'title="Label…, Open in .ttl, Delete…"' in html


# --- a row with no page of its own ----------------------------------------------------

def test_without_a_page_the_ttl_is_still_the_way(tmp_path):
    """A server too old to say the target class: the line, as before."""
    seen = _node(tmp_path, {
        'command': 'semforge.addAttributeConstraint',
        'node': {'raw': {'kind': 'shape', 'shape': 'http://example.com/CartridgeShape',
                         'label': 'CartridgeShape', 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['hasPressure', 'Optional', 'xsd:double'],
        'replies': {
            'semforge/attributeOptions': {'options': [
                {'term': 'ex:hasPressure', 'iri': 'http://example.com/hasPressure',
                 'label': 'hasPressure', 'kind': 'Property', 'comment': '',
                 'domain': 'ex:Cartridge', 'scoped': True, 'status': 'free', 'by': ''}]},
            'semforge/choices': [{'choices': [{'value': 'xsd:double', 'label': 'xsd:double',
                                               'detail': ''}]},
                                 {'choices': []}],
            'semforge/addAttributeConstraint': {'ok': True, 'file': '/pkg/shacl.ttl',
                                                'line': 45}}}, 'extension.js')
    assert seen['shown'] and seen['shown'][0]['line'] == 44


def test_a_knowledge_row_without_a_page_opens_the_page_it_sits_in(tmp_path):
    """A relation under an entity type has no page: the type's opens, not the .ttl."""
    knowledge = {'roots': [{
        'kind': 'class', 'role': 'entityType', 'label': 'Filter', 'iri': 'https://x/Filter',
        'definedAt': '/pkg/knowledge.ttl:3',
        'children': [{'kind': 'relation', 'label': 'isPartOf', 'iri': 'https://x/isPartOf',
                      'definedAt': '/pkg/knowledge.ttl:9', 'children': []}]}]}
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')          # a package the view shows
    scenario = {
        'mode': 'select', 'view': 'semforgeKnowledge', 'label': 'isPartOf', 'config': {},
        'replies': {'semforge/tree': {'roots': []}, 'semforge/model': {'roots': []},
                    'semforge/shapes': {'roots': []}, 'semforge/knowledge': knowledge}}
    seen = _node(tmp_path, scenario, 'extension.js')
    assert seen['errors'] == [], seen['errors']
    opened = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openTypePage']
    assert opened and opened[0][0]['raw']['label'] == 'Filter'
    assert seen['shown'] == []
