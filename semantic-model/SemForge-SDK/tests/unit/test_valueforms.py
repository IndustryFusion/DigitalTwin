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

"""What an attribute's value may be: its forms, each with its own conditions.

"A single boolean, or a list of numbers"; "a Property or a JsonProperty".
The forms need not share their conditions, and any NGSI-LD kind may be one.
"""

import glob
import html as entities
import json
import os
import re
import shutil
import subprocess

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import SH

from semforge.cooked.valueforms import edit_value, read_value, say, to_payload
from semforge.errors import PackageError

FILTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/FilterShape'
CUTTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/CutterShape'
STRENGTH = ['iffBaseEntities:hasStrength']
LIST = ['iffBaseEntities:hasList']
SDK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


@pytest.fixture
def root(tmp_path, corpus):
    root = tmp_path / 'pkg'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    return root


def _value(root, shape=FILTER, chain=STRENGTH):
    from semforge.package import load

    return read_value(load(str(root)), (root / 'shacl.ttl').read_text(), shape, chain)


def _edit(root, action, shape=FILTER, chain=STRENGTH):
    from semforge.package import load

    return edit_value(load(str(root)), shape, chain, action)


# --- reading and writing ----------------------------------------------------------------

def test_one_value_layer_is_one_form_edited_where_it_stands(root):
    value = _value(root)
    assert value.where == 'slot' and [f.kind for f in value.forms] == ['Property']
    # As the type page says it: double or integer is "a number".
    assert say(value) == 'number · 0 – 100'
    before = (root / 'shacl.ttl').read_text()
    _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:maxInclusive',
                 'value': '50'})
    after = (root / 'shacl.ttl').read_text()
    # In place: the value layer keeps its lines, one parameter changed.
    assert len(after.splitlines()) == len(before.splitlines())
    assert say(_value(root)) == 'number · 0 – 50'


def test_forms_are_added_given_their_own_conditions_and_removed(root):
    _edit(root, {'op': 'addform', 'kind': 'ListProperty'})
    _edit(root, {'op': 'set', 'form': 1, 'node': [0], 'parameter': 'sh:datatype',
                 'value': 'xsd:integer'})
    _edit(root, {'op': 'addform', 'kind': 'JsonProperty'})
    value = _value(root)
    assert value.where == 'attribute'
    assert [f.kind for f in value.forms] == ['Property', 'ListProperty', 'JsonProperty']
    assert say(value) == ('one value: number · 0 – 100, or a list of values (may be empty): '
                          'number, or JSON: any value')
    _edit(root, {'op': 'removeform', 'form': 2})
    _edit(root, {'op': 'removeform', 'form': 1})
    value = _value(root)
    assert value.where == 'slot' and [f.kind for f in value.forms] == ['Property']


def test_one_boolean_or_a_list_of_numbers(root):
    """The forms need not share their conditions."""
    _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:datatype',
                 'value': 'xsd:boolean'}, CUTTER, LIST)
    assert say(_value(root, CUTTER, LIST)) == \
        'true / false, or a list of: number (possibly empty)'

    import pyshacl

    from semforge.package import load
    from semforge.validate.shapes import subgraph_for

    shapes = subgraph_for(load(str(root)).shapes, [URIRef(CUTTER)])

    def fails(payload):
        data = Graph().parse(data=f'''
            @prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
            @prefix e: <https://industryfusion.github.io/contexts/example/v0/base_entities/> .
            <urn:c:1> a e:Cutter ; e:hasList [ {payload} ] .''', format='turtle')
        _, report, _ = pyshacl.validate(data, shacl_graph=shapes + Graph())  # pyshacl writes into it
        return any('hasList' in str(report.value(r, SH.resultPath))
                   for r in report.objects(None, SH.result))

    assert not fails('ngsild:hasValue true')
    assert not fails('ngsild:hasValueList ( 1 2 3 )')
    assert not fails('ngsild:hasValueList ()')
    assert fails('ngsild:hasValue 5')
    assert fails('ngsild:hasValueList ( 1 true )')


def test_a_form_changes_kind_and_a_list_may_stop_being_empty(root):
    _edit(root, {'op': 'empty', 'form': 1, 'value': False}, CUTTER, LIST)
    assert not _value(root, CUTTER, LIST).forms[1].may_be_empty
    _edit(root, {'op': 'formkind', 'form': 1, 'kind': 'JsonProperty'}, CUTTER, LIST)
    assert [f.kind for f in _value(root, CUTTER, LIST).forms] == ['Property', 'JsonProperty']


def test_a_kind_is_one_form_once(root):
    with pytest.raises(PackageError, match='each form once'):
        _edit(root, {'op': 'addform', 'kind': 'Property'})


def test_the_type_page_says_each_form_with_its_own_conditions(root):
    from semforge.cooked.typepage import PENDING, build_type_page
    from semforge.package import load

    _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:datatype',
                 'value': 'xsd:boolean'}, CUTTER, LIST)
    page = build_type_page(load(str(root)), 'iffBaseEntities:Cutter', PENDING)
    row = next(r for r in page['attributes'] if r['label'] == 'hasList')
    assert row['value'] == 'true / false, or a list of: number (possibly empty)'
    assert row['kinds'] == ['Property', 'ListProperty']


# --- the panel ----------------------------------------------------------------------------

def _panel(tmp_path, state, after=None):
    """(the panel's HTML, its DOM after `after` ran in headless Chromium)."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    (tmp_path / 'state.json').write_text(json.dumps(state))
    args = [node, os.path.join(SDK, 'tests', 'harness', 'attributepanel.js'),
            os.path.join(SDK, 'vscode', 'src'), str(tmp_path / 'state.json'),
            str(tmp_path / 'panel.html')]
    if after:
        (tmp_path / 'after.js').write_text(after)
        args.append(str(tmp_path / 'after.js'))
    run = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[-1500:]
    page = (tmp_path / 'panel.html').read_text()
    if after is None:
        return page, None
    chrome = next((c for c in [os.environ.get('SEMFORGE_CHROME', '')] + sorted(glob.glob(
        os.path.expanduser('~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome')))
        if c and os.path.exists(c)), None)
    if chrome is None:
        pytest.skip('no headless Chromium (set SEMFORGE_CHROME)')
    dom = subprocess.run([chrome, '--headless=new', '--no-sandbox', '--disable-gpu',
                          '--virtual-time-budget=3000', '--dump-dom',
                          'file://' + str(tmp_path / 'panel.html')],
                         capture_output=True, text=True, timeout=120).stdout
    return page, dom


def _posted(dom):
    found = re.search(r'<html[^>]* data-posted="([^"]*)"', dom)
    return json.loads(entities.unescape(found.group(1))) if found else []


def _state(root, shape=CUTTER, chain=LIST):
    return dict(to_payload(_value(root, shape, chain)), label=chain[-1].split(':')[-1],
                datatypes=[{'label': 'number', 'value': 'xsd:double'}], classes=[])


def test_the_panel_draws_each_form_with_its_own_conditions(root, tmp_path):
    page, _ = _panel(tmp_path, _state(root))
    assert 'data-form="0"' in page and 'data-form="1"' in page
    assert '<option value="Property" selected>Property</option>' in page
    assert '<option value="ListProperty" selected>ListProperty</option>' in page
    assert '<input type="checkbox" data-act="empty" checked> may be empty' in page
    assert 'Each item must be' in page and 'It must be' in page
    assert 'data-act="addform"' in page and 'data-act="removeform"' in page
    assert '<option value="xsd:double">number</option>' in page


def test_clicking_may_be_empty_ticks_it_and_sends_it(root, tmp_path):
    """A person CLICKS the box. The panel's click handler took every
    [data-act] and prevented its default -- which for a tick box is the tick:
    it never changed, and no 'change' ever came."""
    _, dom = _panel(tmp_path, _state(root), '''
var box = document.querySelector('[data-form="1"] input[data-act=empty]');
box.click();
document.documentElement.dataset.ticked = String(box.checked);
''')
    assert re.search(r'<html[^>]* data-ticked="false"', dom), 'the click unticked it'
    assert [m['action'] for m in _posted(dom)] == [{'op': 'empty', 'value': False, 'form': 1}]


def test_a_value_read_only_shows_no_tools(root, tmp_path):
    page, _ = _panel(tmp_path, dict(_state(root), editable=False,
                                    reason='a comment inside it would be lost'))
    assert 'Edited in the .ttl: a comment inside it would be lost' in page
    assert 'data-act="set"' not in page and 'data-act="addform"' not in page


def test_what_the_panel_sends(root, tmp_path):
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), '''
function fill(form, values) {
  form.querySelectorAll('.row').forEach(function (row, i) {
    var v = values[i]; if (!v) { return; }
    var pick = row.querySelector('[data-field=parameter]');
    if (pick && !pick.disabled) { pick.value = v[0]; }
    row.querySelector('[data-field=value]').value = v[1];
  });
}
// A new form: a JsonProperty.
document.getElementById('newkind').value = 'JsonProperty';
document.querySelector('[data-act=addform]').click();
// A group of two in form 0, all of.
document.querySelector('[data-form="0"] [data-act=rootgroup]').click();
var form = document.querySelector('form');
form.querySelector('[data-field=connective]').value = 'and';
fill(form, [null, ['sh:minInclusive', '1'], ['sh:maxInclusive', '9']]);
form.querySelector('[type=submit]').click();
// The maximum changed.
document.querySelector('.chip[data-param="sh:maxInclusive"] [data-act=change]').click();
fill(document.querySelector('form'), [['sh:maxInclusive', '50']]);
document.querySelector('form [type=submit]').click();
// any of -> exactly one of.
var select = document.querySelector('select[data-act=retype]');
select.value = 'xone'; select.dispatchEvent(new Event('change', { bubbles: true }));
// The form becomes a Relationship.
var kind = document.querySelector('[data-form="0"] select[data-act=formkind]');
kind.value = 'Relationship'; kind.dispatchEvent(new Event('change', { bubbles: true }));
// Removed.
document.querySelector('[data-form="0"] [data-act=removeform]').click();
''')
    assert [m['action'] for m in _posted(dom)] == [
        {'op': 'addform', 'kind': 'JsonProperty'},
        {'op': 'addgroup', 'node': [], 'connective': 'and', 'form': 0,
         'conditions': [{'parameter': 'sh:minInclusive', 'value': '1'},
                        {'parameter': 'sh:maxInclusive', 'value': '9'}]},
        {'op': 'set', 'node': [0], 'parameter': 'sh:maxInclusive', 'value': '50', 'form': 0},
        {'op': 'retype', 'node': [1], 'connective': 'xone', 'form': 0},
        {'op': 'formkind', 'kind': 'Relationship', 'form': 0},
        {'op': 'removeform', 'form': 0}]
