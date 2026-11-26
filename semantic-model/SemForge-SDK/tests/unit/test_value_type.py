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

"""What type a value of an example is: said on its page, and made another on
purpose without knowing JSON-LD."""

import json
import os
import re
import shutil
import subprocess

import pytest

import headless_chromium
from semforge.cooked.casepage import build_case_page
from semforge.cooked.examples import set_value, set_value_type, value_type
from semforge.editor import edits
from semforge.errors import PackageError
from semforge.package import load

from test_tree_clicks import _drive, _opened
from test_value_prefix import _package, _value

XSD = 'http://www.w3.org/2001/XMLSchema#'
DOUBLE = {'@value': 50.0, '@type': XSD + 'double'}
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'vscode', 'src')


def _write(made, key, value):
    """The value, as someone wrote it into the file."""
    with open(made['file']) as handle:
        scene = json.load(handle)
    next(d for d in scene if d.get('id') == made['resource'])[key]['value'] = value
    with open(made['file'], 'w') as handle:
        json.dump(scene, handle, indent=2)


def _fired(root, made):
    """The components that fire on the case's entities and attributes."""
    page = build_case_page(load(root), made['case'])
    return [str(v['component']).rsplit('#', 1)[-1].rsplit('/', 1)[-1] for f in page['files']
            for c in f['cards'] for v in c['violations'] + [v for a in c['attributes'] for v in a['violations']]]


def _said(root, made):
    return next(a['valueType'] for f in build_case_page(load(root), made['case'])['files']
                for c in f['cards'] for a in c['attributes'] if a['name'] == 'hasMode')


def _make(root, made, key, wanted):
    set_value_type(load(root), made['resource'], [key, 'value'], wanted, made['file'])
    return _value(made, key)


# --- said ----------------------------------------------------------------------------------

@pytest.mark.parametrize('value, said', [
    (50, 'integer'), (50.0, 'integer'), (50.5, 'double'), ('50', 'text'), (True, 'boolean'),
    (DOUBLE, 'double'), ({'@value': '50', '@type': XSD + 'decimal'}, 'decimal'),
    ({'@value': 1, '@type': 'xsd:string'}, 'text'), ({'@value': 50.0}, 'integer'),
    ({'@value': 'rot', '@language': 'de'}, 'text'), ({'@id': 'x:y'}, 'term'),
    (1e21, 'double'), (10 ** 21, 'double'), (10 ** 21 - 1, 'integer'), ([1], ''), ({'a': 1}, ''), (None, '')])
def test_what_a_value_is(value, said):
    assert value_type(value) == said


def test_one_spelling_four_types(tmp_path):
    root, made, key = _package(tmp_path, 'xsd:double')
    for value, said in ((50, 'integer'), (50.0, 'integer'), ('50', 'text'), (DOUBLE, 'double'),
                        ({'@value': '50', '@type': XSD + 'decimal'}, 'decimal')):
        _write(made, key, value)
        assert _said(root, made) == said
        # What is said is what the validation judges.
        assert (_fired(root, made) == []) == (said == 'double'), value


# --- another type, on purpose --------------------------------------------------------------

@pytest.mark.parametrize('wanted, written', [
    ('double', DOUBLE), ('integer', 50), ('decimal', {'@value': '50.0', '@type': XSD + 'decimal'}),
    ('text', '50.0')])
def test_a_value_is_made_another_type_and_says_the_same(tmp_path, wanted, written):
    root, made, key = _package(tmp_path, 'xsd:double')
    set_value(load(root), made['resource'], [key, 'value'], '50.0', made['file'])
    now = _make(root, made, key, wanted)
    assert now == written and type(now) is type(written)
    assert _said(root, made) == wanted
    assert _fired(root, made) == ([] if wanted == 'double' else ['Datatype'])
    assert _make(root, made, key, 'shape') == DOUBLE and _fired(root, made) == []


def test_a_double_where_the_shape_asks_for_an_integer(tmp_path):
    root, made, key = _package(tmp_path, 'xsd:integer')
    _write(made, key, 50)
    assert _make(root, made, key, 'double') == DOUBLE and _fired(root, made) != []
    assert _make(root, made, key, 'shape') == 50 and _fired(root, made) == []


def test_edited_afterwards_the_shape_decides_again(tmp_path):
    root, made, key = _package(tmp_path, 'xsd:double')
    assert _make(root, made, key, 'shape')['@type'] == XSD + 'double'
    _make(root, made, key, 'integer')
    set_value(load(root), made['resource'], [key, 'value'], '51', made['file'])
    assert _value(made, key) == {'@value': 51.0, '@type': XSD + 'double'}


@pytest.mark.parametrize('said, wanted, now', [
    ('true', 'boolean', True), (False, 'text', 'false'),
    ('owl:Thing', 'term', {'@id': 'owl:Thing'}), ('urn:a:b', 'term', {'@id': 'urn:a:b'}),
    ('<https://x/y#z>', 'term', {'@id': 'https://x/y#z'}), ({'@id': 'owl:Thing'}, 'text', 'owl:Thing'),
    ('9007199254740993', 'integer', 9007199254740993), (9007199254740993, 'text', '9007199254740993'),
    (9007199254740993, 'decimal', {'@value': '9007199254740993', '@type': XSD + 'decimal'}),
    (1e-7, 'decimal', {'@value': '0.0000001', '@type': XSD + 'decimal'}),
    (' 50 ', 'integer', 50), ('1e3', 'integer', 1000), (' a ', 'text', ' a '),
    ({'@value': 'rot', '@language': 'de'}, 'text', 'rot'),
    ('1e21', 'integer', {'@value': '1' + '0' * 21, '@type': XSD + 'integer'}),
    ('-' + '9' * 400, 'integer', {'@value': '-' + '9' * 400, '@type': XSD + 'integer'}),
    ('9' * 400, 'decimal', {'@value': '9' * 400, '@type': XSD + 'decimal'}),
    ('9' * 1000, 'text', '9' * 1000), ('1e999', 'integer', {'@value': '1' + '0' * 999, '@type': XSD + 'integer'}),
    ('0e-2000', 'integer', 0), ('0e-1000000000', 'decimal', {'@value': '0', '@type': XSD + 'decimal'}),
    ('1e-999', 'decimal', {'@value': '0.' + '0' * 998 + '1', '@type': XSD + 'decimal'}),
    ('0e-1000000000', 'double', {'@value': 0.0, '@type': XSD + 'double'}),
    ('0.000', 'decimal', {'@value': '0.000', '@type': XSD + 'decimal'}),
    ('-0.0', 'decimal', {'@value': '-0.0', '@type': XSD + 'decimal'})])
def test_what_it_says_is_kept(tmp_path, said, wanted, now):
    root, made, key = _package(tmp_path, None)
    _write(made, key, said)
    assert _make(root, made, key, wanted) == now


@pytest.mark.parametrize('datatype, said, now', [
    ('xsd:string', 50, '50'), ('xsd:string', 'true', 'true'), ('xsd:boolean', 'true', True),
    ('xsd:integer', '50.0', 50), ('xsd:float', '50', {'@value': 50.0, '@type': XSD + 'float'}),
    ('xsd:decimal', 50, {'@value': '50', '@type': XSD + 'decimal'}),
    ('xsd:date', '2026-01-01', {'@value': '2026-01-01', '@type': XSD + 'date'}),
    ('xsd:int', '50', {'@value': 50, '@type': XSD + 'int'}),
    ('xsd:nonNegativeInteger', 50.0, {'@value': 50, '@type': XSD + 'nonNegativeInteger'}),
    ('xsd:nonNegativeInteger', '1e21', {'@value': '1' + '0' * 21, '@type': XSD + 'nonNegativeInteger'}),
    (None, '50', 50), (None, 'true', True), (None, 'NaN', 'NaN'), (None, '[1]', '[1]'),
    (None, 'red', 'red'), (None, DOUBLE, 50.0), (None, {'@id': 'owl:Thing'}, {'@id': 'owl:Thing'})])
def test_as_the_shape_says(tmp_path, datatype, said, now):
    root, made, key = _package(tmp_path, datatype)
    _write(made, key, said)
    assert _make(root, made, key, 'shape') == now
    assert not [c for c in _fired(root, made) if 'Datatype' in c]


@pytest.mark.parametrize('said, why', [('red', 'not a number'), ('50.5', 'whole number')])
def test_an_integer_type_of_the_shape_takes_whole_numbers_only(tmp_path, said, why):
    root, made, key = _package(tmp_path, 'xsd:int')
    _write(made, key, said)
    with pytest.raises(PackageError, match=why):
        _make(root, made, key, 'shape')
    assert _value(made, key) == said


@pytest.mark.parametrize('written', ['<http://www.w3.org/2001/XMLSchema#double>', 'xs:double'])
def test_the_datatype_is_what_its_name_means(tmp_path, written):
    root, made, key = _package(tmp_path, 'xsd:double')
    shapes = next(p for p in load(root).files('shapes') if 'hasMode' in open(p).read())
    with open(shapes) as handle:
        text = handle.read()
    with open(shapes, 'w') as handle:
        handle.write('@prefix xs: <http://www.w3.org/2001/XMLSchema#> .\n' +
                     text.replace('sh:datatype xsd:double', f'sh:datatype {written}'))
    _write(made, key, '50')
    assert _make(root, made, key, 'shape') == DOUBLE


def test_out_of_the_range_of_its_type_it_is_written_as_said(tmp_path):
    root, made, key = _package(tmp_path, 'xsd:unsignedByte')
    _write(made, key, '300')
    assert _make(root, made, key, 'shape') == {'@value': 300, '@type': XSD + 'unsignedByte'}


def test_a_text_with_a_language_keeps_it_where_the_shape_asks_for_one(tmp_path):
    root, made, key = _package(tmp_path, 'xsd:boolean')
    shapes = next(p for p in load(root).files('shapes') if 'hasMode' in open(p).read())
    with open(shapes) as handle:
        text = handle.read()
    with open(shapes, 'w') as handle:
        handle.write('@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n' +
                     text.replace('sh:datatype xsd:boolean', 'sh:datatype rdf:langString'))
    _write(made, key, {'@value': 'rot', '@language': 'de'})
    _make(root, made, key, 'text')
    with pytest.raises(PackageError, match='no language'):
        _make(root, made, key, 'shape')
    _write(made, key, {'@value': 'rot', '@language': 'de'})
    assert _make(root, made, key, 'shape') == {'@value': 'rot', '@language': 'de'}


@pytest.mark.parametrize('said, wanted, why', [
    (50.5, 'integer', 'whole number'), ('red', 'double', 'not a number'), ('NaN', 'double', 'not a number'),
    ('1_000', 'double', 'not a number'), ('1e999', 'double', 'double can hold'),
    ('1e1000', 'decimal', '1000 digits'), ('1e1000', 'integer', '1000 digits'),
    ('1e-1000', 'decimal', '1000 digits'), ('1.' + '1' * 500 + 'e-900', 'decimal', '1000 digits'),
    ('1e-400', 'double', 'double can hold'), ('1e99999999999999999999', 'double', 'written out'),
    ('1e-99999999999999999999', 'decimal', 'written out'), ('', 'integer', 'not a number'),
    ('yes', 'boolean', 'neither true'), (1, 'boolean', 'neither true'),
    ('red', 'term', 'prefix'), ('12:30 a', 'term', 'prefix'), ('red', 'colour', 'no type'),
    ({'a': 1}, 'text', 'a list, an object'), ([1, 2], 'text', 'a list, an object'), (None, 'text', 'null'),
    ({'@value': None}, 'shape', 'null')])
def test_a_value_that_cannot_be_one_is_refused_and_kept(tmp_path, said, wanted, why):
    root, made, key = _package(tmp_path, None)
    _write(made, key, said)
    with open(made['file'], 'rb') as handle:
        before = handle.read()
    with pytest.raises(PackageError, match=why):
        _make(root, made, key, wanted)
    with open(made['file'], 'rb') as handle:
        assert handle.read() == before


def test_only_a_value_has_a_type(tmp_path):
    root, made, key = _package(tmp_path, None)
    for path in ([key, 'type'], [key, 'observedAt'], []):
        with pytest.raises(PackageError, match='value of a Property'):
            set_value_type(load(root), made['resource'], path, 'text', made['file'])


def test_the_server_changes_the_type(tmp_path, monkeypatch):
    published = []
    monkeypatch.setattr(edits.validation, 'publish', lambda ls, uri: published.append(uri))
    root, made, key = _package(tmp_path, None)
    asked = {'uri': f'file://{root}/kms.yaml', 'entity': made['resource'], 'path': [key, 'value'],
             'file': made['file'], 'valueType': 'text'}
    assert edits.set_value_type_feature(None, asked)['ok'] and len(published) == 1
    refused = edits.set_value_type_feature(None, dict(asked, valueType='colour'))
    assert not refused['ok'] and 'colour' in refused['error'] and len(published) == 1
    assert not edits.set_value_type_feature(None, dict(asked, uri='file:///nowhere/x'))['ok']


# --- on the page ---------------------------------------------------------------------------

def _page(value, kind):
    node = {'label': 'hasMode', 'entity': 'urn:m', 'path': ['x:hasMode', 'value'], 'file': '/pkg/c.jsonld',
            'editable': True, 'kind': 'dataset'}
    return {'ok': True, 'kind': 'case', 'name': 'c.jsonld', 'case': 'c.jsonld', 'expect': 'valid', 'passed': True,
            'failures': [], 'claims': [], 'unasserted': [], 'file': '/pkg/c.jsonld', 'expectations': '',
            'summary': {}, 'files': [{'role': 'case', 'path': '/pkg/c.jsonld', 'relative': 'c.jsonld', 'sharedBy': [],
                                      'cards': [{'id': 'urn:m', 'type': 'M', 'file': '/pkg/c.jsonld', 'line': 1,
                                                 'violations': [], 'attributes': [
                                                     {'name': 'hasMode', 'term': 'x:hasMode', 'kind': 'Property',
                                                      'value': value, 'valueType': kind, 'violations': [],
                                                      'children': [], 'node': node, 'attributeNode': node}]}]}]}


def _scenario(**more):
    return dict({'command': 'semforge.openCasePage',
                 'node': {'raw': {'kind': 'example', 'file': '/pkg/c.jsonld'}, 'packageUri': 'file:///pkg/shacl.ttl'},
                 'webviewMessages': [{'command': 'valueType', 'at': '0.0.0'}],
                 'replies': {'semforge/casePage': _page('50.0', 'integer')}}, **more)


def _choose(tmp_path, node, **more):
    seen = _drive(tmp_path, dict({'command': 'semforge.setValueType', 'node': node,
                                  'replies': {'semforge/setValueType': {'ok': True}}}, **more))
    return seen, [r['params'] for r in seen['requests'] if r['method'] == 'semforge/setValueType']


def test_the_type_is_said_where_it_cannot_be_seen_and_changed_there(tmp_path):
    seen = _drive(tmp_path, _scenario())
    html = seen['webviews'][0]['html'][0]
    assert 'data-valuetype="0.0.0"' in html and '>integer</a>' in html and 'It is an integer' in html
    node = _opened(seen, 'semforge.setValueType')[0][0]
    assert node['raw']['valueType'] == 'integer'
    seen, asked = _choose(tmp_path, node, picks=['Double'])
    offered = seen['quickPicks'][0]['items']
    assert [i['label'] for i in offered] == ['As the shape says', 'Double', 'Integer', 'Decimal', 'Text',
                                             'True / false', 'Vocabulary term']
    assert [i['label'] for i in offered if i.get('detail')] == ['Integer'], 'the present one is marked'
    assert asked == [{'uri': 'file:///pkg/shacl.ttl', 'entity': 'urn:m', 'path': ['x:hasMode', 'value'],
                      'file': '/pkg/c.jsonld', 'valueType': 'double'}]


def test_a_type_none_of_the_choices_is_is_said_and_not_marked(tmp_path):
    """Integer writes an xsd:integer: marking it for an xsd:int would say that
    choosing it changes nothing."""
    node = _opened(_drive(tmp_path, _scenario()), 'semforge.setValueType')[0][0]
    seen, _ = _choose(tmp_path, dict(node, raw=dict(node['raw'], valueType='int')), picks=[])
    assert not [i for i in seen['quickPicks'][0]['items'] if i.get('detail')]
    assert 'It is int now.' in seen['quickPicks'][0]['title']
    seen, _ = _choose(tmp_path, node, picks=[])
    assert 'now.' not in seen['quickPicks'][0]['title'], 'one of the choices is marked, not named'


def test_nothing_picked_changes_nothing(tmp_path):
    node = _opened(_drive(tmp_path, _scenario()), 'semforge.setValueType')[0][0]
    assert _choose(tmp_path, node, picks=[])[1] == []
    raw = dict(node['raw'], path=['x:hasMode', 'type'])
    assert _choose(tmp_path, {'raw': raw, 'packageUri': 'x'}, picks=['Double'])[1] == []


def test_a_superseded_observation_offers_no_type(tmp_path):
    page = _page('50.0', 'integer')
    rows = page['files'][0]['cards'][0]['attributes']
    rows.insert(0, dict(rows[0], value='49.0', superseded=True))     # an earlier observation
    seen = _drive(tmp_path, _scenario(webviewMessages=[], replies={'semforge/casePage': page}))
    html = seen['webviews'][0]['html'][0]
    assert '<span class="vtype">integer</span>' in html, 'the earlier one says its type'
    assert 'data-valuetype="0.0.0"' not in html and 'data-valuetype="0.0.1"' in html, 'only the current one offers it'


def test_the_row_menu_offers_it_for_values_only(tmp_path):
    def menu(value, kind):
        seen = _drive(tmp_path, _scenario(webviewMessages=[{'command': 'rowMenu', 'at': '0.0.0'}],
                                          replies={'semforge/casePage': _page(value, kind)}))
        return [i['label'] for i in seen['quickPicks'][0]['items']]
    assert '$(symbol-numeric) Type of the value…' in menu('50.0', 'integer')
    assert '$(symbol-numeric) Type of the value…' in menu('red', 'text')
    assert '$(symbol-numeric) Type of the value…' not in menu('{"a": 1}', '')


def test_a_shared_file_is_asked_about_and_a_refusal_is_said(tmp_path):
    node = _opened(_drive(tmp_path, _scenario()), 'semforge.setValueType')[0][0]
    shared = dict(node, raw=dict(node['raw'], sharedBy=['a.jsonld', 'b.jsonld']))
    seen, asked = _choose(tmp_path, shared, picks=['Double'])
    assert asked == [] and any('2 cases' in w for w in seen['warnings'])
    seen, asked = _choose(tmp_path, node, picks=['Double'],
                          replies={'semforge/setValueType': {'ok': False, 'error': 'red is not a number'}})
    assert any('red is not a number' in e for e in seen['errors'])


@pytest.mark.parametrize('value, kind, says', [
    ('red', 'text', False), ('1.2.3', 'text', False), ('TRUE', 'text', False), ('1E3', 'double', True),
    ('2026-01-01', 'date', False), ('[1]', '', False),
    ('50', 'text', True), ('-1.5e3', 'double', True), ('true', 'boolean', True)])
def test_it_is_said_of_numbers_and_truths_only(tmp_path, value, kind, says):
    seen = _drive(tmp_path, _scenario(webviewMessages=[], replies={'semforge/casePage': _page(value, kind)}))
    assert ('data-valuetype="' in seen['webviews'][0]['html'][0]) == says


def test_the_click_in_the_page_itself(tmp_path):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    (tmp_path / 'page.json').write_text(json.dumps(_page('50.0', 'integer')))
    (tmp_path / 'after.js').write_text('document.querySelector("[data-valuetype]").click();')
    run = subprocess.run([node, os.path.join(os.path.dirname(SRC), '..', 'tests', 'harness', 'render_casepage.js'),
                          SRC, str(tmp_path / 'page.json'), str(tmp_path / 'page.html'), str(tmp_path / 'after.js')],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[-1500:]
    dom = subprocess.run([headless_chromium.chrome(), '--headless=new', '--no-sandbox', '--disable-gpu',
                          '--virtual-time-budget=2000', '--dump-dom', 'file://' + str(tmp_path / 'page.html')],
                         capture_output=True, text=True, timeout=120).stdout
    posted = re.search(r'data-posted="([^"]*)"', dom)
    assert posted and 'valueType' in posted.group(1) and '0.0.0' in posted.group(1)
