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

"""Editing on the entity type page: each click, and what it writes.

Every write is checked as text -- the file must read as if a person had made
the change: one line for a one-line change, no blank lines left behind -- and
as meaning, through the graph. Then the clicks are driven through the Node
harness, the way the page's script posts them.
"""

import json
import os
import shutil
import subprocess

import pytest
from rdflib import URIRef
from rdflib.namespace import SH, XSD

from semforge.cooked.constrain import edit_attribute, remove_property_group
from semforge.cooked.tree import override_constraint
from semforge.cooked.typepage import build_type_page
from semforge.errors import PackageError
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/'
FILTER = BASE + 'base_shacl/FilterShape'
MACHINE = BASE + 'base_shacl/MachineShape'
NGSILD = 'https://uri.etsi.org/ngsi-ld/'
HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.dirname(os.path.dirname(HERE))
DRIVE = os.path.join(SDK, 'tests', 'harness', 'drive.js')
SRC = os.path.join(SDK, 'vscode', 'src')


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _text(root):
    with open(os.path.join(root, 'shacl.ttl'), encoding='utf-8') as handle:
        return handle.read()


def _changed_lines(before, after):
    old, new = before.splitlines(), after.splitlines()
    return [(a, b) for a, b in zip(old, new) if a != b], len(new) - len(old)


def _value_layer(root, shape, attribute):
    """The attribute's value layer -- the nested shape on hasValue/hasObject.

    Not just any nested sh:property: hasState also nests its sub-attribute
    hasXXXWorkpiece, and graph.value() picks one of several arbitrarily.
    """
    graph = load(root).shapes
    for group in graph.objects(URIRef(shape), SH.property):
        if (group, SH.path, URIRef(attribute)) in graph:
            for nested in graph.objects(group, SH.property):
                if str(graph.value(nested, SH.path)).startswith(NGSILD):
                    return graph, nested
    raise AssertionError(f'{attribute} not on {shape}')


# --- presence ---------------------------------------------------------------------

def test_presence_is_one_line_and_round_trips(kms):
    original = _text(kms)
    edit_attribute(load(kms), FILTER, ['iffBaseEntities:hasStrength'], presence='optional')
    changed, grown = _changed_lines(original, _text(kms))
    assert grown == 0 and len(changed) == 1
    assert changed[0][1].strip() == 'sh:minCount 0 ;'
    edit_attribute(load(kms), FILTER, ['iffBaseEntities:hasStrength'], presence='required')
    assert _text(kms) == original


# --- the value ----------------------------------------------------------------------

def test_a_class_for_a_class_rewrites_one_value(kms):
    original = _text(kms)
    edit_attribute(load(kms), FILTER, ['iffBaseEntities:hasCartridge'],
                   value={'valueClass': 'iffBaseEntities:Consumable'})
    changed, grown = _changed_lines(original, _text(kms))
    assert grown == 0 and len(changed) == 1
    assert 'iffBaseEntities:Consumable' in changed[0][1]


def test_a_class_for_a_datatype_leaves_no_blank_line(kms):
    def blank_lines(text):
        block = text.split('iffBaseShacl:MachineShape a sh:NodeShape')[1].split(' .\n')[0]
        return [line for line in block.splitlines() if line.strip() == '']

    before = blank_lines(_text(kms))           # the file has one of its own
    edit_attribute(load(kms), MACHINE, ['iffBaseEntities:hasState'],
                   value={'datatype': 'xsd:string'})
    assert blank_lines(_text(kms)) == before, 'the edit left a blank line'
    graph, value = _value_layer(kms, MACHINE, BASE + 'base_entities/hasState')
    assert (value, SH.datatype, XSD.string) in graph
    assert (value, SH['class'], None) not in graph
    assert (value, SH.nodeKind, None) not in graph
    assert (value, SH.minCount, None) in graph, 'the counts stay'
    block = _text(kms).split('iffBaseShacl:MachineShape a sh:NodeShape')[1].split(' .\n')[0]
    assert 'sh:property [ \n' not in block and 'sh:property [\n' not in block


def test_any_value_drops_the_class_and_keeps_the_rest(kms):
    edit_attribute(load(kms), FILTER, ['iffBaseEntities:hasCartridge'], value={'kind': 'any'})
    graph, value = _value_layer(kms, FILTER, BASE + 'base_entities/hasCartridge')
    assert (value, SH['class'], None) not in graph
    assert (value, SH.path, URIRef(NGSILD + 'hasObject')) in graph


@pytest.mark.parametrize('path, value, says', [
    (['iffBaseEntities:hasStrength'], {'datatype': 'xsd:string'}, 'sh:or'),
    (['iffBaseEntities:hasCartridge'], {'datatype': 'xsd:string'}, 'no datatype'),
    (['iffBaseEntities:hasCartridge'], {'valueClass': 'base:MachineState'},
     'not an entity type'),
])
def test_a_refused_value_writes_nothing(kms, path, value, says):
    original = _text(kms)
    with pytest.raises(PackageError, match=says):
        edit_attribute(load(kms), FILTER, path, value=value)
    assert _text(kms) == original


# --- removing and overriding --------------------------------------------------------

def test_removing_a_sub_attribute_leaves_its_parent(kms):
    remove_property_group(load(kms), MACHINE,
                          ['iffBaseEntities:hasState', 'iffBaseEntities:hasXXXWorkpiece'])
    graph = load(kms).shapes
    assert (None, SH.path, URIRef(BASE + 'base_entities/hasXXXWorkpiece')) not in graph
    graph, value = _value_layer(kms, MACHINE, BASE + 'base_entities/hasState')
    assert (value, SH['class'], URIRef(BASE + 'base_knowledge/MachineState')) in graph


def test_overriding_a_value_constraint_nests_it_in_a_value_layer(kms):
    override_constraint(load(kms), FILTER,
                        ['iffBaseEntities:hasState', 'ngsild:hasValue'],
                        'sh:class', 'base:MachineState')
    graph, value = _value_layer(kms, FILTER, BASE + 'base_entities/hasState')
    assert (value, SH.path, URIRef(NGSILD + 'hasValue')) in graph
    assert (value, SH['class'], URIRef(BASE + 'base_knowledge/MachineState')) in graph


# --- the payload carries the edit addresses -------------------------------------------

def test_rows_carry_what_an_edit_needs(corpus):
    page = build_type_page(corpus, 'iffBaseEntities:Filter')
    rows = {row['label']: row for row in page['attributes']}
    assert page['ownShape'] == FILTER
    # hasStrength's value is an expression (sh:or of number types): editable
    # in the expression editor, which a plain value never opens.
    assert rows['hasStrength']['valueEditable'] and rows['hasStrength']['expression']
    assert rows['hasCartridge']['valueEditable'] and rows['hasCartridge']['expression'] is None
    assert rows['hasXXXWorkpiece']['path'] == ['iffBaseEntities:hasState',
                                               'iffBaseEntities:hasXXXWorkpiece']
    value_class = next(p for p in rows['hasCartridge']['parameters']
                       if p['parameter'] == 'sh:class')
    assert value_class['path'] == ['iffBaseEntities:hasCartridge', 'ngsild:hasObject']


# --- the clicks, through the extension -------------------------------------------------

@pytest.fixture(scope='module')
def page(corpus):
    return dict(build_type_page(corpus, 'iffBaseEntities:Filter'), ok=True)


def _click(tmp_path, page, messages, **scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    replies = {'semforge/typePage': page, 'semforge/editAttribute': {'ok': True},
               'semforge/removeProperty': {'ok': True}, 'semforge/override': {'ok': True},
               'semforge/setConstraint': {'ok': True}}
    replies.update(scenario.pop('replies', {}))
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(dict({
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': page['iri'], 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': messages, 'replies': replies}, **scenario)))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _sent(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


def _row(page, label):
    return next(i for i, r in enumerate(page['attributes']) if r['label'] == label)


def test_clicking_presence_writes_it_and_refreshes(tmp_path, page):
    seen = _click(tmp_path, page, [{'command': 'presence', 'row': _row(page, 'hasCartridge')}],
                  pick='Optional')
    assert seen['errors'] == [], seen['errors']
    assert _sent(seen, 'semforge/editAttribute') == [{
        'uri': 'file:///pkg/shacl.ttl', 'shape': FILTER,
        'path': ['iffBaseEntities:hasCartridge'], 'presence': 'optional'}]
    assert len(_sent(seen, 'semforge/typePage')) == 2, 'the page re-renders'
    assert {'semforge.refreshTree', 'semforge.refreshModel'} <= \
        {e['command'] for e in seen['executed']}


FORMS = {'ok': True, 'editable': True, 'said': 'a Consumable', 'forms': [],
         'kinds': ['Relationship'], 'lists': 'single'}


def test_clicking_a_row_opens_the_attribute_editor_beside(tmp_path, page):
    """A row is a summary; a click on it opens the one place it is changed."""
    row = _row(page, 'hasCartridge')
    seen = _click(tmp_path, page, [{'command': 'attribute', 'row': row}],
                  replies={'semforge/valueForms': FORMS})
    assert seen['errors'] == [], seen['errors']
    assert _sent(seen, 'semforge/valueForms') == [{
        'uri': 'file:///pkg/shacl.ttl', 'shape': FILTER,
        'path': ['iffBaseEntities:hasCartridge']}]
    editor = seen['webviews'][-1]
    assert editor['viewType'] == 'semforgeAttribute'
    assert editor['title'] == 'Attribute: hasCartridge'
    html = editor['html'][-1]
    for asks in ('data-cmd="presence"', 'data-cmd="severity"', 'data-cmd="test"',
                 'data-cmd="open"', 'data-cmd="params"'):
        assert asks in html, asks
    assert 'data-act="lists-on"' in html, 'one value: a list may be allowed'
    assert not _sent(seen, 'semforge/editAttribute'), 'opening writes nothing'


def test_an_edit_in_the_editor_writes_and_redraws_both(tmp_path, page):
    action = {'op': 'set', 'form': 0, 'parameter': 'sh:class',
              'value': 'iffBaseEntities:Consumable'}
    seen = _click(tmp_path, page, [{'command': 'attribute', 'row': _row(page, 'hasCartridge')},
                                   {'command': 'edit', 'action': action}],
                  replies={'semforge/valueForms': FORMS,
                           'semforge/editValueForms': {'ok': True}})
    assert [e['action'] for e in _sent(seen, 'semforge/editValueForms')] == [action]
    assert len(_sent(seen, 'semforge/typePage')) == 2, 'the page re-renders'
    assert len(_sent(seen, 'semforge/valueForms')) == 2, 'and so does the editor'


def test_the_editor_s_buttons_run_the_page_s_own_flows(tmp_path, page):
    """Presence in the editor is the page's presence picker, on the page's row."""
    seen = _click(tmp_path, page, [{'command': 'attribute', 'row': _row(page, 'hasCartridge')},
                                   {'command': 'row', 'name': 'presence'}],
                  pick='Optional', replies={'semforge/valueForms': FORMS})
    assert _sent(seen, 'semforge/editAttribute') == [{
        'uri': 'file:///pkg/shacl.ttl', 'shape': FILTER,
        'path': ['iffBaseEntities:hasCartridge'], 'presence': 'optional'}]


def test_a_locked_value_says_why_and_offers_no_edit(tmp_path, page):
    locked = dict(FORMS, editable=False,
                  reason='a comment inside it would be lost')
    seen = _click(tmp_path, page, [{'command': 'attribute', 'row': _row(page, 'hasStrength')}],
                  replies={'semforge/valueForms': locked})
    html = seen['webviews'][-1]['html'][-1]
    assert 'Edited in the .ttl: a comment inside it would be lost' in html
    assert 'data-act="addform"' not in html and 'data-act="lists-on"' not in html


def test_override_declares_on_the_types_own_shape(tmp_path, page):
    seen = _click(tmp_path, page, [{'command': 'override', 'row': _row(page, 'hasState')}],
                  picks=['sh:class base:MachineState'], inputs=['base:MachineState'])
    sent = _sent(seen, 'semforge/override')
    assert sent and sent[0]['targetShape'] == FILTER
    assert sent[0]['path'] == ['iffBaseEntities:hasState', 'ngsild:hasValue']
    assert sent[0]['parameter'] == 'sh:class'


def test_the_row_menu_hands_sub_attributes_to_the_existing_flow(tmp_path, page):
    seen = _click(tmp_path, page, [{'command': 'menu', 'row': _row(page, 'hasCartridge')}],
                  pick='$(add) Add a sub-attribute…')
    handed = [e for e in seen['executed'] if e['command'] == 'semforge.addAttributeConstraint']
    assert handed and handed[0]['args'][0]['raw']['path'] == ['iffBaseEntities:hasCartridge']
    assert handed[0]['args'][0]['raw']['kind'] == 'attribute'


def test_removing_from_the_shape_asks_first(tmp_path, page):
    row = _row(page, 'hasCartridge')
    declined = _click(tmp_path, page, [{'command': 'menu', 'row': row}],
                      pick='$(remove) Remove from FilterShape…', answer=None)
    assert not _sent(declined, 'semforge/removeProperty')
    agreed = _click(tmp_path, page, [{'command': 'menu', 'row': row}],
                    pick='$(remove) Remove from FilterShape…', answer='Remove')
    assert _sent(agreed, 'semforge/removeProperty')[0]['path'] == ['iffBaseEntities:hasCartridge']


def test_the_header_button_adds_to_the_types_own_shape(tmp_path, page):
    seen = _click(tmp_path, page, [{'command': 'addAttribute', 'row': -1}])
    handed = [e for e in seen['executed'] if e['command'] == 'semforge.addAttributeConstraint']
    assert handed[0]['args'][0]['raw'] == {'kind': 'shape', 'shape': FILTER,
                                           'label': 'iffBaseShacl:FilterShape',
                                           'inheritedFrom': ''}


def test_the_rendered_page_offers_the_right_action_per_row(tmp_path, page):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    scenario = tmp_path / 'render.json'
    scenario.write_text(json.dumps({'mode': 'render', 'function': 'renderTypePage',
                                    'payload': page, 'options': {'nonce': 'n'}}))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'typepage.js'),
                          str(scenario)], capture_output=True, text=True, timeout=60)
    html = json.loads(out.stdout.strip().splitlines()[-1])['html']
    assert html.count('data-action="override"') == 2, 'the two inherited rows'
    assert html.count('data-action="menu"') == 2, 'the two own rows'
    assert 'class="primary" data-action="addAttribute"' in html
    assert 'data-action="pageMenu"' in html, 'New subtype… waits behind the ⋯'
    assert '<button data-action="override"' not in html, 'override is a quiet link'
    # Every row opens the attribute editor; its cells are text, not links.
    for label in ('hasStrength', 'hasCartridge'):
        assert f'data-action="attribute" data-row="{_row(page, label)}"' in html, label
    assert 'data-action="value"' not in html and 'data-action="presence"' not in html
    # The expression, as a tree under the value.
    assert '<div class="verbatim expr"><div>always: 0 – 100</div><div>any of:</div>' in html


def test_new_subtype_on_the_page_names_the_page_s_type(tmp_path, page):
    seen = _click(tmp_path, page, [{'command': 'newSubtype', 'row': -1}])
    assert seen['errors'] == [], seen['errors']
    asked = [e['args'][0] for e in seen['executed'] if e['command'] == 'semforge.newSubtype']
    assert asked == [{'raw': {'targetClass': page['iri']},
                      'packageUri': 'file:///pkg/shacl.ttl'}]
    assert len(_sent(seen, 'semforge/typePage')) == 1, 'the parent page is unchanged'


# --- the model has a page too: Main ------------------------------------------------------

def test_a_model_entity_and_a_row_s_model_violations_link_to_the_main_page(tmp_path, page):
    """A test case opens its case page from here; the model's entities did not
    open anything -- the Main page is where the model is, entity by entity."""
    flagged = json.loads(json.dumps(page))
    flagged['attributes'][0]['violations'] = ['urn:filter:1: too many']
    seen = _click(tmp_path, flagged, [])
    html = seen['webviews'][0]['html'][-1]
    for instance in page['instances']:
        assert f'data-model="{instance["id"]}"' in html, instance['id']
    assert 'class="violates" data-model=""' in html


@pytest.mark.parametrize('entity, options', [('urn:filter:1', {'focus': 'urn:filter:1'}),
                                             ('', {})])
def test_clicking_one_opens_the_main_page_at_it(tmp_path, page, entity, options):
    # An empty entity (a row's "✗ N") opens the page unscrolled: no focus.
    seen = _click(tmp_path, page, [{'command': 'model', 'entity': entity}])
    opened = [e['args'] for e in seen['executed'] if e['command'] == 'semforge.openModelPage']
    assert opened == [[{'packageUri': 'file:///pkg/shacl.ttl'}, options]]
