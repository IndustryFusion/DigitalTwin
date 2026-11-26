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

"""sh:in (and sh:hasValue) edited in plain words, one value per row.

The editor used to show a list as Turtle, `( "Executing" )`, and take what was
typed into it as one text, so adding a value quoted the whole list. Nobody has
to know Turtle: what is shown and what is typed is the value itself.
"""

import json
import re

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import SH, XSD

from semforge.cooked.valueforms import to_payload
from semforge.errors import PackageError

from test_valueforms import FILTER, STRENGTH, _edit, _panel, _posted, _state, _value, root  # noqa: F401


def _condition(root, parameter='sh:in'):  # noqa: F811
    own = to_payload(_value(root))['forms'][0]['expression']['children'][0]
    return next(c for c in own['conditions'] if c['parameter'] == parameter)


def _set(root, rows, parameter='sh:in', datatype=None):  # noqa: F811
    _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': parameter, 'value': rows,
                 'datatype': datatype})
    return (root / 'shacl.ttl').read_text()


def _texts(*said):
    return [{'kind': 'text', 'text': text} for text in said]


def _kept(*said):
    """Rows the editor sends back as they were read: kept, not checked again."""
    return [{'kind': 'text', 'text': text, 'kept': True} for text in said]


def _written(root, turtle):  # noqa: F811
    """The value's sh:in as written by hand: `turtle` in place of a first list."""
    shapes = _set(root, _texts('placeholder'))
    (root / 'shacl.ttl').write_text(shapes.replace('( "placeholder" )', turtle))


def _terms(root):  # noqa: F811
    """The RDF terms of every sh:in in the shapes file."""
    graph = Graph().parse(root / 'shacl.ttl', format='turtle')
    return [list(Collection(graph, o)) for o in graph.objects(None, SH['in'])]


# --- Values are shown as they read -------------------------------------------------------

def test_a_list_of_texts_is_shown_in_words(root):  # noqa: F811
    """Scenario "A list of texts"."""
    _written(root, '( "Executing" "NONE" )')
    shown = _condition(root)
    assert shown['value'] == 'Executing · NONE'
    assert shown['items'] == _texts('Executing', 'NONE')


def test_typed_tagged_and_escaped_items_are_shown_as_they_read(root):  # noqa: F811
    """Scenario "Typed, tagged and escaped items"; a term by its local name, single
    quotes and an escape the way #1087 reads them."""
    _written(root, '( "2026-01-01"^^xsd:date "rot"@de "say \\"hi\\"" \'single\' '
             '"tab\\there" iffBaseEntities:Filter )')
    assert _condition(root)['value'] == '2026-01-01 · rot · say "hi" · single · tab\there · Filter'
    assert _condition(root)['items'][:2] == [
        {'kind': 'typed', 'text': '2026-01-01', 'datatype': 'xsd:date'},
        {'kind': 'typed', 'text': 'rot', 'lang': 'de'}]


def test_exactly_and_the_words_of_the_value_are_plain(root):  # noqa: F811
    _set(root, _texts('say "hi"'), 'sh:hasValue')
    own = to_payload(_value(root))['forms'][0]['expression']['children'][0]
    assert 'exactly say "hi"' in own['words']
    assert _condition(root, 'sh:hasValue')['value'] == 'say "hi"'


def test_a_pattern_is_shown_without_its_quotes(root):  # noqa: F811
    _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:pattern',
                 'value': '^\\d+$'})
    assert _condition(root, 'sh:pattern')['value'] == '^\\d+$'


def test_the_type_page_says_the_list_in_words():
    from semforge.cooked.typepage import _in_list, value_text

    listed = '( "say \\"hi\\"" "rot"@de x:state_ON )'
    assert value_text('Property', {'sh:in': listed}, []) == 'one of: say "hi" · rot · state_ON'
    slot = type('Slot', (), {'path_chain': ('x:a', 'ngsild:hasValue')})()
    assert _in_list([('sh:in', listed)], {}, slot)['words'] == ['say "hi"', 'rot', 'state_ON']


# --- One value per row -------------------------------------------------------------------

def test_a_second_value_is_a_second_value_not_one_quoted_text(root):  # noqa: F811
    """Scenario "A second value": it was shown as ( "Executing" ), and what was
    typed in that form came back as one text, quotes and brackets and all."""
    _written(root, '( "Executing" )')
    assert 'sh:in ( "Executing" "NONE" )' in _set(root, _condition(root)['items'] + _texts('NONE'))
    assert _condition(root)['items'] == _texts('Executing', 'NONE')


def test_a_value_taken_out(root):  # noqa: F811
    """Scenario "A value taken out"."""
    _written(root, '( "Executing" "NONE" )')
    assert 'sh:in ( "NONE" )' in _set(root, _condition(root)['items'][1:])


def test_empty_and_repeated_rows(root):  # noqa: F811
    """Scenario "Empty and repeated rows"; the same RDF term written otherwise
    is repeated too, the text 1 and the number 1 are two values."""
    assert 'sh:in ( "NONE" )' in _set(root, _texts('NONE', '', ' ', 'NONE'))
    assert 'sh:in ( 2.5 1 "1" )' in _set(root, [
        {'kind': 'number', 'text': '2.5', 'datatype': 'xsd:decimal'},
        {'kind': 'number', 'text': '2.5', 'datatype': '<http://www.w3.org/2001/XMLSchema#decimal>'},
        {'kind': 'number', 'text': '1'}, {'kind': 'text', 'text': '1'}])


def test_a_list_without_a_value_is_not_written(root):  # noqa: F811
    _written(root, '( "Executing" )')
    before = (root / 'shacl.ttl').read_text()
    with pytest.raises(PackageError, match='remove "one of" instead'):
        _set(root, _texts('', ' '))
    assert (root / 'shacl.ttl').read_text() == before


def test_exactly_is_one_value(root):  # noqa: F811
    """Scenario "Exactly"; a second value is refused, an empty row is none."""
    assert 'sh:hasValue "Executing"' in _set(root, _texts('Executing', ''), 'sh:hasValue')
    before = (root / 'shacl.ttl').read_text()
    with pytest.raises(PackageError, match='for several, use "one of"'):
        _set(root, _texts('a', 'b'), 'sh:hasValue')
    with pytest.raises(PackageError, match='needs a value'):
        _set(root, _texts(''), 'sh:hasValue')
    assert (root / 'shacl.ttl').read_text() == before


# --- A text is what was typed ------------------------------------------------------------

SAID = ['with, comma', '( "odd" )', 'say "hi"', 'a:b', '12', 'true', 'back\\slash', 'Grün',
        '\U0001F600', 'two\nlines', "it's"]


def test_characters_turtle_uses(root):  # noqa: F811
    """Scenario "Characters Turtle uses": each one text, shown as typed."""
    _set(root, _texts(*SAID))
    assert _condition(root)['items'] == _texts(*SAID)
    assert [Literal(t) for t in SAID] in _terms(root)


# --- The kind of a value -----------------------------------------------------------------

def test_a_number_where_the_shape_asks_for_a_double(root):  # noqa: F811
    """Scenario "A number where the shape asks for a double"."""
    _set(root, [{'kind': 'number', 'text': '1'}, {'kind': 'number', 'text': '20.5'}],
         datatype='xsd:double')
    assert [Literal('1', datatype=XSD.double), Literal('20.5', datatype=XSD.double)] in _terms(root)


def test_a_new_number_without_a_datatype_is_as_json_brings_it(root):  # noqa: F811
    _set(root, [{'kind': 'number', 'text': t} for t in ('3', '20.5', '1e3')])
    assert [Literal('3', datatype=XSD.integer), Literal('20.5', datatype=XSD.double),
            Literal('1e3', datatype=XSD.double)] in _terms(root)


def test_a_number_where_the_shape_asks_for_a_text(root):  # noqa: F811
    """Scenario "A number where the shape asks for a text", on the server: the
    row the page sends for it is the text 5."""
    assert 'sh:in ( "5" )' in _set(root, _texts('5'), datatype='xsd:string')


def test_a_term_offered(root):  # noqa: F811
    """Scenario "A term offered", on the server."""
    _set(root, [{'kind': 'term', 'text': 'iffBaseEntities:Filter'}])
    assert [URIRef('https://industryfusion.github.io/contexts/example/v0/base_entities/Filter')] \
        in _terms(root)
    assert _condition(root)['items'] == [{'kind': 'term', 'text': 'iffBaseEntities:Filter'}]


def test_a_date_typed_where_the_shape_asks_for_one(root):  # noqa: F811
    _set(root, _texts('2026-01-01'), datatype='xsd:date')
    assert [Literal('2026-01-01', datatype=XSD.date)] in _terms(root)


# --- A value that was not touched stays the same -----------------------------------------

EVERY_KIND = ('( 1 2.5 1.0e3 true iffBaseEntities:Filter "12" "rot"@de "2026-01-01"^^xsd:date '
              '"x"^^xsd:string "1.50"^^xsd:decimal "7"^^xsd:double '
              '"say \\"hi\\"" )')


def test_items_of_every_kind(root):  # noqa: F811
    """Scenario "Items of every kind": the same terms in the same order, and the text."""
    _written(root, EVERY_KIND)
    before = next(t for t in _terms(root) if len(t) == 12)
    _set(root, _condition(root)['items'] + _texts('added'))
    after = next(t for t in _terms(root) if len(t) == 13)
    assert after == before + [Literal('added')]
    # rdflib tells the plain text and the xsd:string apart, so does the list.
    assert Literal('x', datatype=XSD.string) in after and Literal('x') not in after


def test_a_changed_number_keeps_its_datatype(root):  # noqa: F811
    _written(root, '( 2.5 )')
    item = dict(_condition(root)['items'][0], text='3')
    _set(root, [item])
    assert [Literal('3', datatype=XSD.decimal)] in _terms(root)


# --- A value that is not of its kind is refused ------------------------------------------

@pytest.mark.parametrize('row, said', [
    ({'kind': 'number', 'text': 'many'}, 'many is not a number'),
    ({'kind': 'boolean', 'text': 'yes'}, 'neither true nor false'),
    ({'kind': 'term', 'text': 'Executing'}, 'choose Text if it is a text'),
    ({'kind': 'term', 'text': 'nope:x'}, 'not declared'),
    ({'kind': 'colour', 'text': 'red'}, 'no kind of value')])
def test_a_value_that_is_not_its_kind_is_refused(root, row, said):  # noqa: F811
    """Scenarios "A word as a number" and "A word as a term": refused, the file unchanged."""
    _written(root, '( "Executing" )')
    before = (root / 'shacl.ttl').read_text()
    with pytest.raises(PackageError, match=said):
        _set(root, _texts('fine') + [row])
    assert (root / 'shacl.ttl').read_text() == before


# --- A Turtle list typed is a list --------------------------------------------------

def test_turtle_typed():
    """Scenario "Turtle typed": a Turtle list in a text field is that list."""
    from semforge.cooked.tree import _list_value

    assert _list_value(None, '', '( "Executing" "NONE" )') == '( "Executing" "NONE" )'
    assert _list_value(None, '', ' ( "a, b" \'c\' ) ') == '( "a, b" \'c\' )'


def test_the_rows_reach_the_file_through_the_server(root, monkeypatch):  # noqa: F811
    """The language server request takes rows: a custom request arrives as
    objects, not dicts."""
    from types import SimpleNamespace

    from semforge.editor import edits

    assert edits._items([SimpleNamespace(kind='text', text='a')]) == [
        {'kind': 'text', 'text': 'a', 'datatype': None, 'lang': None, 'kept': None}]
    assert edits._items('5') == '5'
    assert json.dumps(edits._items(None)) == 'null'

    from semforge.package import load

    monkeypatch.setattr(edits.session, 'package_for', lambda r: load(str(root)))
    monkeypatch.setattr(edits.session, 'forget', lambda r: None)
    monkeypatch.setattr(edits.validation, 'publish', lambda ls, uri: None)
    answer = edits.edit_value_forms_feature(None, SimpleNamespace(
        uri=(root / 'shacl.ttl').as_uri(), shape=FILTER, path=STRENGTH,
        action=SimpleNamespace(op='set', form=0, node=[0], parameter='sh:in', datatype=None,
                               value=[SimpleNamespace(kind='text', text='with, comma'),
                                      SimpleNamespace(kind='typed', text='rot', lang='de')])))
    assert answer.get('ok'), answer
    assert 'sh:in ( "with, comma" "rot"@de )' in (root / 'shacl.ttl').read_text()


# --- the panel ------------------------------------------------------------------------------

def test_the_list_is_edited_one_value_per_row(root, tmp_path):  # noqa: F811
    """Scenario "A second value" in the editor: Enter in the last row adds one."""
    _set(root, _texts('Executing'))
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
var rows = function () { return document.querySelectorAll('form [data-field=item]'); };
document.documentElement.dataset.shown = rows()[0].value;
rows()[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
rows()[1].value = 'NONE';
rows()[1].dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""")
    assert re.search(r'<html[^>]* data-shown="Executing"', dom)
    assert [(m['action']['op'], m['action']['parameter'], m['action']['value'])
            for m in _posted(dom)] == [('set', 'sh:in', _kept('Executing') + _texts('NONE'))]


def test_a_number_typed_is_a_number_and_a_value_can_be_taken_out(root, tmp_path):  # noqa: F811
    """Scenarios "A number typed" and "A value taken out" in the editor; + Value adds a row."""
    _set(root, _texts('Executing', 'NONE'))
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=remove]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form [data-field=item]')).pop();
last.value = '5';
last.dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""")
    assert _posted(dom)[0]['action']['value'] == _kept('NONE') + [{'kind': 'number', 'text': '5'}]


def test_a_kind_chosen_stays_what_is_typed_afterwards(root, tmp_path):  # noqa: F811
    _set(root, _texts('Executing'))
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form .item')).pop();
var kind = last.querySelector('[data-field=itemkind]');
kind.value = 'text';
kind.dispatchEvent(new Event('change', { bubbles: true }));
last.querySelector('[data-field=item]').value = '5';
last.querySelector('[data-field=item]').dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""")
    assert _posted(dom)[0]['action']['value'] == _kept('Executing') + _texts('5')


def test_an_untouched_item_goes_back_with_its_datatype_or_language(root, tmp_path):  # noqa: F811
    _written(root, '( "rot"@de 2.5 )')
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form').requestSubmit();
""")
    assert _posted(dom)[0]['action']['value'] == [
        {'kind': 'typed', 'text': 'rot', 'lang': 'de', 'kept': True},
        {'kind': 'number', 'text': '2.5', 'datatype': 'xsd:decimal', 'kept': True}]


def test_rows_without_a_value_are_sent_for_the_server_to_refuse(root, tmp_path):  # noqa: F811
    _set(root, _texts('Executing'))
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=remove]').click();
document.querySelector('form').requestSubmit();
""")
    assert _posted(dom)[0]['action']['value'] == []


def test_exactly_has_one_row(root, tmp_path):  # noqa: F811
    _set(root, _texts('Executing'), 'sh:hasValue')
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:hasValue"] [data-act=change]').click();
var form = document.querySelector('form');
document.documentElement.dataset.rows = form.querySelectorAll('[data-field=item]').length;
document.documentElement.dataset.more = form.querySelectorAll('[data-item]').length;
form.requestSubmit();
""")
    assert re.search(r'<html[^>]* data-rows="1"', dom) and re.search(r'data-more="0"', dom)
    assert _posted(dom)[0]['action']['value'] == _kept('Executing')


def test_the_datatype_decides_what_a_value_is(root, tmp_path):  # noqa: F811
    """Scenario "A number where the shape asks for a text" in the editor."""
    _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:datatype',
                 'value': 'xsd:string'})
    _set(root, _texts('Executing'))
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form [data-field=item]')).pop();
last.value = '5';
last.dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""")
    action = _posted(dom)[0]['action']
    assert action['value'] == _kept('Executing') + _texts('5') and action['datatype'] == 'xsd:string'
    assert 'sh:in ( "Executing" "5" )' in _set(root, action['value'], datatype='xsd:string')


def test_a_term_offered_in_the_editor(root, tmp_path):  # noqa: F811
    """Scenario "A term offered": the vocabulary's values are offered, and one
    picked is a term."""
    _set(root, _texts('Executing'))
    state = dict(_state(root, FILTER, STRENGTH),
                 terms=[{'value': 'iffBaseEntities:Filter', 'label': 'Filter'}])
    _, dom = _panel(tmp_path, state, """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form [data-field=item]')).pop();
last.value = 'iffBaseEntities:Filter';
last.dispatchEvent(new Event('input', { bubbles: true }));
document.documentElement.dataset.list = last.getAttribute('list');
document.querySelector('form').requestSubmit();
""")
    assert re.search(r'<html[^>]* data-list="terms"', dom)
    assert _posted(dom)[0]['action']['value'][-1] == {'kind': 'term', 'text': 'iffBaseEntities:Filter'}


# --- what a review found ----------------------------------------------------------------

def test_a_pattern_comes_back_as_it_was_shown(root):  # noqa: F811
    """The editor shows a pattern in words; Apply without a change keeps it,
    quotes inside it included."""
    for pattern in ('"[^"]*"', '"abc"', '^\\d+$'):
        _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:pattern',
                     'value': pattern})
        shown = _condition(root, 'sh:pattern')['value']
        assert shown == pattern
        _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:pattern',
                     'value': shown})
        assert _condition(root, 'sh:pattern')['value'] == pattern
        graph = Graph().parse(root / 'shacl.ttl', format='turtle')
        assert Literal(pattern) in set(graph.objects(None, SH.pattern))


@pytest.mark.parametrize('typed, written', [
    ("'tis fine", '( "\'tis fine" )'), ('(none)', '( "(none)" )'),
    ('"a", \'b\'', '( "a" \'b\' )'), ("'a, b', NONE", '( \'a, b\' "NONE" )'),
    ('( <urn:a> "b" 1 )', '( <urn:a> "b" 1 )')])
def test_a_text_field_quotes_what_is_no_turtle(typed, written):
    from semforge.cooked.tree import _list_value

    assert _list_value(None, '', typed) == written


@pytest.mark.parametrize('turtle, changed, said', [
    ('( 2.5 )', '1e3', 'not an xsd:decimal'), ('( "5"^^xsd:int )', '2.5', 'not an xsd:int')])
def test_a_changed_number_must_suit_its_datatype(root, turtle, changed, said):  # noqa: F811
    _written(root, turtle)
    before = (root / 'shacl.ttl').read_text()
    with pytest.raises(PackageError, match=said):
        _set(root, [dict(_condition(root)['items'][0], text=changed)])
    assert (root / 'shacl.ttl').read_text() == before


@pytest.mark.parametrize('datatype, expected', [
    ('xsd:gYear', Literal('2020', datatype=XSD.gYear)), ('xsd:token', Literal('2020', datatype=XSD.token)),
    ('xsd:string', Literal('2020'))])
def test_a_new_text_has_the_datatype_the_shape_names(root, datatype, expected):  # noqa: F811
    _set(root, _texts('2020'), datatype=datatype)
    assert [expected] in _terms(root)


def test_the_row_s_parameters_say_exactly_in_words():
    from semforge.cooked.typepage import _parameter_words

    assert _parameter_words('sh:hasValue', '"say \\"hi\\""') == {'words': 'say "hi"'}
    assert _parameter_words('sh:pattern', '"^a"') == {'words': '^a'}
    assert _parameter_words('sh:minCount', '1') == {}


def _with_datatype(state, datatype):
    """The panel's state with every sh:datatype said as `datatype`."""
    def walk(node):
        for c in node.get('conditions', []):
            if c['parameter'] == 'sh:datatype':
                c['value'] = datatype
        for child in node.get('children', []):
            walk(child)
    for form in state['forms']:
        walk(form['expression'])
    return state


def test_a_numeric_datatype_written_as_an_iri_makes_a_number(root, tmp_path):  # noqa: F811
    _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:datatype',
                 'value': 'xsd:double'})
    _set(root, _texts('Executing'))
    state = _with_datatype(_state(root, FILTER, STRENGTH), '<http://www.w3.org/2001/XMLSchema#double>')
    _, dom = _panel(tmp_path, state, """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form [data-field=item]')).pop();
last.value = '5';
last.dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""")
    assert _posted(dom)[0]['action']['value'][-1] == {'kind': 'number', 'text': '5'}


def test_the_terms_stay_offered_while_one_is_typed(root, tmp_path):  # noqa: F811
    _set(root, _texts('Executing'))
    state = dict(_state(root, FILTER, STRENGTH),
                 terms=[{'value': 'iffBaseEntities:Filter', 'label': 'Filter'}])
    _, dom = _panel(tmp_path, state, """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form .item')).pop();
var input = last.querySelector('[data-field=item]');
input.value = 'Fil';
input.dispatchEvent(new Event('input', { bubbles: true }));
document.documentElement.dataset.list = input.getAttribute('list') + ':' +
  last.querySelector('[data-field=itemkind]').value;
""")
    assert re.search(r'<html[^>]* data-list="terms:term"', dom)


def test_a_string_parameter_is_read_as_its_own_term():
    """The block reader took the term AFTER a string: replacing a pattern
    wrote the new one beside the old."""
    from semforge.rdfio.blocks import _read_token

    text = 'sh:pattern # why\n  "a\\"b" ; sh:flags "i"'
    assert _read_token(text, len('sh:pattern'), len(text))[0] == '"a\\"b"'
    assert _read_token(' "i" ;', 0, 6)[0] == '"i"'


@pytest.mark.parametrize('written', ['"rot"@de', '"2026-01-01"^^xsd:date',
                                     '"x"^^<http://www.w3.org/2001/XMLSchema#token>'])
def test_a_tagged_or_typed_value_is_removed_and_replaced_whole(written):
    from semforge.rdfio.blocks import _scan_group, remove_parameter, set_parameter

    text = f'[ sh:path ex:a ; sh:hasValue {written} ; sh:minCount 1 ]'
    block = _scan_group(text, 0, len(text), 0)
    assert block.parameter('sh:hasValue')[2] == written
    assert remove_parameter(text, block, 'sh:hasValue') == '[ sh:path ex:a ;  sh:minCount 1 ]'
    assert set_parameter(text, block, 'sh:hasValue', '5') == \
        '[ sh:path ex:a ; sh:hasValue 5 ; sh:minCount 1 ]'


@pytest.mark.parametrize('said, datatype, refused', [
    ('20.5', 'xsd:long', 'not an xsd:long, as the value must be'),
    ('1e3', 'xsd:decimal', 'not an xsd:decimal, as the value must be'),
    ('2.5', 'xsd:unsignedInt', 'not an xsd:unsignedInt')])
def test_a_new_number_must_suit_the_shape_s_datatype(root, said, datatype, refused):  # noqa: F811
    before = (root / 'shacl.ttl').read_text()
    with pytest.raises(PackageError, match=refused):
        _set(root, [{'kind': 'number', 'text': said}], datatype=datatype)
    assert (root / 'shacl.ttl').read_text() == before


def test_a_whole_number_fits_an_integer_datatype(root):  # noqa: F811
    _set(root, [{'kind': 'number', 'text': '7'}], datatype='xsd:unsignedInt')
    assert [Literal('7', datatype=XSD.unsignedInt)] in _terms(root)


def test_a_text_on_a_boolean_value_is_no_ill_typed_boolean(root):  # noqa: F811
    _set(root, _texts('yes'), datatype='xsd:boolean')
    assert [Literal('yes')] in _terms(root)


def test_the_editor_and_the_server_know_the_same_number_types():
    from semforge.cooked.tree import NUMERIC_TYPES

    import os
    source = open(os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src',
                               'attributepanel.js'), encoding='utf-8').read()
    listed = re.search(r'const NUMBER_TYPES = \[([^\]]*)\]', source).group(1)
    assert set(re.findall(r"'(\w+)'", listed)) == set(NUMERIC_TYPES)


def test_an_unsigned_int_value_takes_numbers(root, tmp_path):  # noqa: F811
    _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:datatype',
                 'value': 'xsd:double'})
    _set(root, _texts('Executing'))
    state = _with_datatype(_state(root, FILTER, STRENGTH), 'xsd:unsignedInt')
    _, dom = _panel(tmp_path, state, """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form [data-field=item]')).pop();
last.value = '5';
last.dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""")
    action = _posted(dom)[0]['action']
    assert action['value'][-1] == {'kind': 'number', 'text': '5'} and action['datatype'] == 'xsd:unsignedInt'


@pytest.mark.parametrize('typed, sent', [
    ('Filter', {'kind': 'term', 'text': 'iffBaseEntities:Filter'}),
    ('iffBaseEntities:Filter', {'kind': 'term', 'text': 'iffBaseEntities:Filter'}),
    ('Fi', {'kind': 'text', 'text': 'Fi'})])
def test_a_guessed_term_is_sent_as_the_term_it_matched(root, tmp_path, typed, sent):  # noqa: F811
    _set(root, _texts('Executing'))
    state = dict(_state(root, FILTER, STRENGTH),
                 terms=[{'value': 'iffBaseEntities:Filter', 'label': 'Filter'}])
    _, dom = _panel(tmp_path, state, """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form [data-field=item]')).pop();
last.value = %s;
last.dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""" % json.dumps(typed))
    assert _posted(dom)[0]['action']['value'][-1] == sent


def test_plain_tokens_reach_the_file_through_the_server(root):  # noqa: F811
    from semforge.editor.edits import _items

    assert _items(['iffBaseEntities:Filter', '"x"']) == ['iffBaseEntities:Filter', '"x"']
    assert 'sh:in ( iffBaseEntities:Filter "x" )' in _set(root, _items(['iffBaseEntities:Filter', '"x"']))


def test_an_untouched_number_of_another_type_does_not_block_the_list(root):  # noqa: F811
    _written(root, '( 1 2.5 )')
    _set(root, _condition(root)['items'] + [{'kind': 'number', 'text': '3'}], datatype='xsd:integer')
    assert [Literal('1', datatype=XSD.integer), Literal('2.5', datatype=XSD.decimal),
            Literal('3', datatype=XSD.integer)] in _terms(root)


def test_an_untouched_whole_number_stays_an_integer(root):  # noqa: F811
    _written(root, '( 1 2.5 )')
    _set(root, _condition(root)['items'] + [{'kind': 'number', 'text': '3'}], datatype='xsd:double')
    assert [Literal('1', datatype=XSD.integer), Literal('2.5', datatype=XSD.decimal),
            Literal('3', datatype=XSD.double)] in _terms(root)


@pytest.mark.parametrize('said, datatype', [
    ('-1', 'xsd:nonNegativeInteger'), ('300', 'xsd:unsignedByte'), ('0', 'xsd:positiveInteger'),
    ('40000', 'xsd:short'), ('-5', 'xsd:unsignedInt')])
def test_a_number_outside_its_datatype_is_refused(root, said, datatype):  # noqa: F811
    before = (root / 'shacl.ttl').read_text()
    with pytest.raises(PackageError, match=f'not an {datatype}'):
        _set(root, [{'kind': 'number', 'text': said}], datatype=datatype)
    assert (root / 'shacl.ttl').read_text() == before


def test_a_typed_or_escaped_pattern_is_the_regex_it_says():
    from semforge.cooked.listcheck import list_conflicts
    from semforge.cooked.typepage import value_text

    for written in ('"^[A-Z]+"^^xsd:string', '"^\\\\d+$"'):
        regex = '^[A-Z]+' if 'A-Z' in written else '^\\d+$'
        assert value_text('Property', {'sh:pattern': written}, []) == f'matching {regex}'
    assert list_conflicts(None, {'sh:pattern': '"^[A-Z]+"^^xsd:string'}, ['"ABC"']) == []
    assert list_conflicts(None, {'sh:pattern': '"^\\\\d+$"'}, ['"12"']) == []
    assert list_conflicts(None, {'sh:pattern': '"^\\\\d+$"'}, ['"ab"']) == ['"ab" does not match ^\\d+$']


def test_a_json_boolean_in_plain_tokens_is_a_boolean(root):  # noqa: F811
    from semforge.editor.edits import _items

    assert _items([True, False, 5, 'x']) == ['true', 'false', 5, 'x']
    assert 'sh:in ( true 5 "x" )' in _set(root, _items([True, 5, 'x']))


def test_a_local_name_of_two_terms_stays_a_term_for_the_server_to_ask(root, tmp_path):  # noqa: F811
    _set(root, _texts('Executing'))
    state = dict(_state(root, FILTER, STRENGTH), terms=[
        {'value': 'iffBaseEntities:Filter', 'label': 'Filter'},
        {'value': 'iffFilterEntities:Filter', 'label': 'Filter'}])
    _, dom = _panel(tmp_path, state, """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form [data-field=item]')).pop();
last.value = 'Filter';
last.dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""")
    row = _posted(dom)[0]['action']['value'][-1]
    assert row == {'kind': 'term', 'text': 'Filter'}
    with pytest.raises(PackageError, match='more than one'):
        _set(root, [row])


def test_a_text_field_keeps_a_literal_s_language_and_datatype():
    from semforge.cooked.tree import _list_value

    assert _list_value(None, '', '"rot"@de, b') == '( "rot"@de "b" )'
    assert _list_value(None, '', '"x"^^<urn:t>, "y"') == '( "x"^^<urn:t> "y" )'


RACE = r"""
const Module = require('module');
const path = require('path');
const original = Module._load;
const written = [];
const panel = { visible: true, webview: { set html(h) { written.push(h); }, onDidReceiveMessage() {} },
  onDidChangeViewState() {}, onDidDispose() {}, reveal() {} };
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return { window: { createWebviewPanel: () => panel }, ViewColumn: { Beside: 2 } };
  }
  return original(request, parent, isMain);
};
const { openAttribute, current } = require(path.resolve(process.argv[2], 'attributepanel.js'));
let forms = 0;
let values = [];
const sendRequest = (method) => new Promise((done) => {
  // The first drawing's read is slow and says what was before; the next one is fast.
  const first = method === 'semforge/valueForms' && forms++ === 0;
  const answer = method === 'semforge/valueForms' ? { ok: false, error: first ? 'zzbeforezz' : 'zzafterzz' }
    : method === 'semforge/vocabularyPage' ? { ok: true, values } : { ok: true, cases: [] };
  setTimeout(() => done(answer), first ? 300 : 0);
});
const row = { term: 'x:a', path: ['x:a'], label: 'a', shape: 's', shapeName: 's', kind: 'Property' };
const pages = { current: { packageUri: 'file:///p' }, clientHolder: { client: { sendRequest } },
  page: { attributes: [row] } };
(async () => {
  await openAttribute(pages, row, 0, undefined);
  const editor = current();
  forms = 0;
  const count = written.length;
  const before = editor.render();
  await editor.render();
  await before;
  values = [{ term: 'ON', iri: 'urn:x#ON', name: 'ON' }, { term: 'x:OFF', iri: 'urn:x#OFF', name: 'OFF' }];
  const terms = await editor.terms({ ok: true, forms: [{ expression: {
    conditions: [{ parameter: 'sh:class', value: 'x:C' }] } }] });
  console.log(JSON.stringify({ drawn: written.slice(count).map((h) => h.includes('zzafterzz')),
    terms: terms.map((t) => t.value) }));
})();
"""


def _race(tmp_path):
    import os
    import shutil
    import subprocess

    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    (tmp_path / 'race.js').write_text(RACE)
    src = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
    run = subprocess.run([node, str(tmp_path / 'race.js'), os.path.abspath(src)],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[-1500:]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_a_drawing_begun_earlier_does_not_draw_over_a_newer_one(tmp_path):
    """The editor now reads the vocabularies too, after the value: a drawing
    begun earlier and still reading must not write what was before over what is now."""
    assert _race(tmp_path)['drawn'] == [True]


def test_a_vocabulary_value_without_a_prefix_is_offered_by_its_iri_in_the_editor(tmp_path):
    assert _race(tmp_path)['terms'] == ['<urn:x#ON>', 'x:OFF']


@pytest.mark.parametrize('typed, written', [
    ('"Executing", "say \\"hi\\", twice"', '( "Executing" "say \\"hi\\", twice" )'),
    ("'tis, 'twas", '( "\'tis" "\'twas" )'),
    ('"a" , \'b, c\' ,d', '( "a" \'b, c\' "d" )')])
def test_the_input_box_s_own_join_reads_back(typed, written):
    """The text field is filled with the items joined by ', '; reading that
    back is the same list, and a word is a quoted item only where it ends one."""
    from semforge.cooked.tree import _list_value

    assert _list_value(None, '', typed) == written


def test_a_local_name_in_a_row_set_to_term_is_that_term(root, tmp_path):  # noqa: F811
    _set(root, _texts('Executing'))
    state = dict(_state(root, FILTER, STRENGTH),
                 terms=[{'value': 'iffBaseEntities:Filter', 'label': 'Filter'}])
    _, dom = _panel(tmp_path, state, """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form .item')).pop();
var kind = last.querySelector('[data-field=itemkind]');
kind.value = 'term';
kind.dispatchEvent(new Event('change', { bubbles: true }));
var input = last.querySelector('[data-field=item]');
input.value = 'Filter';
input.dispatchEvent(new Event('input', { bubbles: true }));
var other = Array.from(document.querySelectorAll('form .item'))[0];
other.querySelector('[data-field=itemkind]').value = 'term';
other.querySelector('[data-field=itemkind]').dispatchEvent(new Event('change', { bubbles: true }));
other.querySelector('[data-field=item]').value = 'nothing offered';
document.querySelector('form').requestSubmit();
""")
    assert _posted(dom)[0]['action']['value'] == [
        {'kind': 'term', 'text': 'nothing offered'},          # chosen: the server says why not
        {'kind': 'term', 'text': 'iffBaseEntities:Filter'}]


def test_a_number_changed_in_its_row_is_a_new_number(root, tmp_path):  # noqa: F811
    _written(root, '( 5 "rot"@de )')
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
var rows = document.querySelectorAll('form [data-field=item]');
rows[0].value = '5.5';
rows[1].value = 'rotes';
document.querySelector('form').requestSubmit();
""")
    assert _posted(dom)[0]['action']['value'] == [
        {'kind': 'number', 'text': '5.5'}, {'kind': 'typed', 'text': 'rotes', 'lang': 'de'}]


def test_checking_a_number_leaves_rdflib_s_warnings_on():
    import logging

    from semforge.cooked.tree import _fits

    assert not _fits('abc', 'xsd:integer')
    assert logging.getLogger('rdflib.term').isEnabledFor(logging.WARNING)


FLOW = r"""
const Module = require('module');
const path = require('path');
const original = Module._load;
const written = [];
const panel = { visible: true, webview: { set html(h) { written.push(h); }, onDidReceiveMessage() {} },
  onDidChangeViewState() {}, onDidDispose() {}, reveal() {} };
Module._load = function (request, parent, isMain) {
  if (request === 'vscode') {
    return { window: { createWebviewPanel: () => panel }, ViewColumn: { Beside: 2 } };
  }
  return original(request, parent, isMain);
};
const { openAttribute, current } = require(path.resolve(process.argv[2], 'attributepanel.js'));
let state = 'zzbeforezz';
const sendRequest = (method) => Promise.resolve(method === 'semforge/valueForms'
  ? { ok: true, forms: [], editable: false, reason: state } : { ok: true, cases: [] });
const row = { term: 'x:a', path: ['x:a'], label: 'a', shape: 's', shapeName: 's', kind: 'Property' };
const pages = { current: { packageUri: 'file:///p' }, clientHolder: { client: { sendRequest } },
  page: { attributes: [row] },
  // The page's own flow: while its pickers are open, the panel comes back into
  // view and is drawn; then the flow changes the shapes.
  receive: async () => { await current().render(); state = 'zzafterzz'; } };
(async () => {
  await openAttribute(pages, row, 0, undefined, false);
  await current().receive({ command: 'row', name: 'params' });
  console.log(JSON.stringify(written[written.length - 1].includes('zzafterzz')));
})();
"""


def test_the_panel_is_drawn_after_the_page_s_own_flow(tmp_path):
    import os
    import shutil
    import subprocess

    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    (tmp_path / 'flow.js').write_text(FLOW)
    src = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
    run = subprocess.run([node, str(tmp_path / 'flow.js'), os.path.abspath(src)],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[-1500:]
    assert run.stdout.strip().splitlines()[-1] == 'true'


def test_a_pattern_keeps_its_edge_spaces_through_the_panel(root, tmp_path):  # noqa: F811
    _edit(root, {'op': 'set', 'form': 0, 'node': [0], 'parameter': 'sh:pattern', 'value': ' $'})
    assert _condition(root, 'sh:pattern')['value'] == ' $'
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:pattern"] [data-act=change]').click();
document.querySelector('form').requestSubmit();
""")
    action = _posted(dom)[0]['action']
    assert action['parameter'] == 'sh:pattern' and action['value'] == ' $'


@pytest.mark.parametrize('said, datatype', [('tomorrow', 'xsd:date'), ('5', 'xsd:dateTime')])
def test_a_text_its_datatype_cannot_say_is_refused(root, said, datatype):  # noqa: F811
    before = (root / 'shacl.ttl').read_text()
    with pytest.raises(PackageError, match=f'not an {datatype}'):
        _set(root, _texts(said), datatype=datatype)
    assert (root / 'shacl.ttl').read_text() == before


def test_exactly_given_only_blanks_needs_a_value(root):  # noqa: F811
    with pytest.raises(PackageError, match='sh:hasValue needs a value'):
        _set(root, ['  ', ''], 'sh:hasValue')


def test_an_edited_typed_text_must_suit_its_datatype(root):  # noqa: F811
    _written(root, '( "2026-01-01"^^xsd:date )')
    before = (root / 'shacl.ttl').read_text()
    with pytest.raises(PackageError, match='not an xsd:date'):
        _set(root, [dict(_condition(root)['items'][0], text='tomorrow')])
    assert (root / 'shacl.ttl').read_text() == before


def test_a_text_where_a_language_is_needed_is_refused(root):  # noqa: F811
    before = (root / 'shacl.ttl').read_text()
    with pytest.raises(PackageError, match='with a language'):
        _set(root, _texts('rot'), datatype='rdf:langString')
    assert (root / 'shacl.ttl').read_text() == before


def test_a_vocabulary_value_without_a_prefix_is_offered_by_its_iri(root):  # noqa: F811
    assert 'sh:in ( <urn:x#ON> )' in _set(root, [{'kind': 'term', 'text': '<urn:x#ON>'}])


def test_an_untouched_ill_typed_text_does_not_block_the_list(root, tmp_path):  # noqa: F811
    """Only a changed row is checked: what was not touched is written as it was,
    even a literal rdflib does not read as its datatype."""
    _written(root, '( "abc"^^xsd:date "2026-01-01T24:00:00"^^xsd:dateTime "x" )')
    before = next(t for t in _terms(root) if len(t) == 3 and Literal('x') in t)
    _, dom = _panel(tmp_path, _state(root, FILTER, STRENGTH), """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form [data-field=item]')).pop();
last.value = 'y';
last.dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""")
    rows = _posted(dom)[0]['action']['value']
    assert [r.get('kept') for r in rows] == [True, True, True, None]
    _set(root, rows)
    assert before + [Literal('y')] in _terms(root)
    # Changed, the same date is checked.
    with pytest.raises(PackageError, match='not an xsd:date'):
        _set(root, [dict(rows[0], text='abd', kept=None)])


def test_an_edited_date_with_spaces_at_its_ends_is_a_date(root):  # noqa: F811
    _written(root, '( "2026-01-01"^^xsd:date )')
    _set(root, [dict(_condition(root)['items'][0], text=' 2026-01-02 ')])
    assert any(len(t) == 1 and t[0].datatype == XSD.date for t in _terms(root))


def test_a_prefixless_value_is_found_by_its_local_name(root, tmp_path):  # noqa: F811
    _set(root, _texts('Executing'))
    state = dict(_state(root, FILTER, STRENGTH), terms=[{'value': '<urn:x#ON>', 'label': 'ON'}])
    _, dom = _panel(tmp_path, state, """
document.querySelector('.chip[data-param="sh:in"] [data-act=change]').click();
document.querySelector('form [data-item=add]').click();
var last = Array.from(document.querySelectorAll('form [data-field=item]')).pop();
last.value = 'ON';
last.dispatchEvent(new Event('input', { bubbles: true }));
document.querySelector('form').requestSubmit();
""")
    row = _posted(dom)[0]['action']['value'][-1]
    assert row == {'kind': 'term', 'text': '<urn:x#ON>'}
    assert 'sh:in ( "Executing" <urn:x#ON> )' in _set(root, _texts('Executing') + [row])
