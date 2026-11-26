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

"""A test that should fail: it fails until its reason is asserted.

Asked for on an attribute with sh:in, for which New test… offered nothing:
its list of what can go wrong had no entry for it. A failing test no longer
chooses from a list. It starts valid and reasonless, and fails; its data is
broken and what fires is asserted -- the same for every constraint there is.
"""

import json
import os
import re

import pytest
from rdflib import Literal
from rdflib.namespace import XSD

from semforge.cooked.casepage import assertable, attribute_cases, build_case_page
from semforge.cooked.constrain import add_attribute_constraint
from semforge.cooked.examples import set_value
from semforge.cooked.knowledge import add_attribute_term
from semforge.cooked.remove_use import remove_assert
from semforge.cooked.shapelink import value_choices
from semforge.cooked.tree import add_constraint, build_tree
from semforge.errors import PackageError
from semforge.expect.attributecase import attribute_test_options, new_attribute_test
from semforge.expect.deletecase import delete_cases
from semforge.expect.runner import NO_REASON, evaluate
from semforge.expect.stale import retarget_assert
from semforge.expect.store import Example, add_assert
from semforge.package import load
from semforge.package.scaffold import create_package
from semforge.sanity import known_constraints
from semforge.validate.results import Report, Result

from test_tree_clicks import OPTIONS, PRESSURE, _drive, _opened

IN = 'InConstraintComponent'


def _package(tmp_path, items, datatype):
    root = str(tmp_path / 'my-model')
    create_package(root)
    machine = str(next(c for c in load(root).knowledge.subjects() if str(c).endswith('/Machine')))
    add_attribute_term(load(root), 'hasMode', 'Property', machine, label='Mode')
    package = load(root)
    shape = str(next(s for s in package.shapes.subjects() if str(s).endswith('/MachineShape')))
    add_attribute_constraint(package, shape, 'hasMode', required=False, datatype=datatype)
    path = next(list(a.path_chain) for r in build_tree(load(root)) if r.target_class == machine
                for s in r.children for a in s.children
                if a.kind == 'attribute' and a.label.endswith('hasMode'))
    add_constraint(load(root), shape, path, 'sh:in', items)
    return root, machine, path


def _key(made):
    with open(made['file']) as handle:
        return next(k for d in json.load(handle) for k in d if k.endswith('hasMode'))


@pytest.mark.parametrize('items, datatype', [
    ('"red", "green"', 'xsd:string'), ('1, 2', 'xsd:integer'), ('20.5, 21.5', 'xsd:double'),
    ('"1", "true"', None), ('true', None), ('grün, with \\ and "x"', None),
    ('😀', None), ('1, 2', 'xsd:string'), ('20.5, 2.50', 'xsd:decimal')])
def test_a_list_is_proven_both_ways(tmp_path, items, datatype):
    root, machine, path = _package(tmp_path, items, datatype)
    purposes = [o['purpose'] for o in attribute_test_options(load(root), machine, path)['options']]
    assert purposes == ['valid', 'invalid']

    good = new_attribute_test(load(root), machine, path, 'valid', 'mode-valid')
    assert good['passes'], good['failures']

    # Valid data, no reason: it fails, whatever the list is made of.
    bad = new_attribute_test(load(root), machine, path, 'invalid', 'mode-invalid')
    assert not bad['passes']
    assert NO_REASON in bad['failures']

    key = _key(bad)
    offered, _ = value_choices(load(root), 'Machine', key)
    assert len(offered) == len(items.split(','))
    assert all('\\u' not in o['label'] for o in offered)
    for choice in offered:
        set_value(load(root), bad['resource'], [key, 'value'], choice['value'], bad['file'])
        assert build_case_page(load(root), bad['case'])['summary']['violations'] == 0, choice

    # Broken, but still without a reason: it still fails.
    set_value(load(root), bad['resource'], [key, 'value'], 'not in it', bad['file'])
    page = build_case_page(load(root), bad['case'])
    assert page['failures'] == [NO_REASON]
    firing = next(u for u in page['unasserted'] if u['constraint'].endswith(f'hasMode/{IN}'))
    offered = assertable(load(root), bad['case'])
    assert offered[0]['fires'] and firing['constraint'] in [o['constraint'] for o in offered]

    add_assert(load(root), bad['case'], firing['constraint'], firing['resource'])
    page = build_case_page(load(root), bad['case'])
    assert page['passed'], page['failures']
    assert firing['constraint'] not in [o['constraint'] for o in assertable(load(root), bad['case'])]

    # And taken out again: back to failing.
    claim = page['claims'][0]
    remove_assert(page['expectations'], claim['entry'], claim['index'])
    assert build_case_page(load(root), bad['case'])['failures'] == [NO_REASON]


def test_a_reason_may_be_named_before_it_fires(tmp_path):
    root, machine, path = _package(tmp_path, '"red", "green"', None)
    bad = new_attribute_test(load(root), machine, path, 'invalid', 'mode-invalid')
    choice = next(o for o in assertable(load(root), bad['case'])
                  if o['constraint'].endswith(f'hasMode/{IN}'))
    assert not choice['fires'] and choice['resource'] == bad['resource']
    add_assert(load(root), bad['case'], choice['constraint'], choice['resource'])
    assert not build_case_page(load(root), bad['case'])['passed']
    set_value(load(root), bad['resource'], [_key(bad), 'value'], 'blue', bad['file'])
    assert build_case_page(load(root), bad['case'])['passed']


def test_the_tests_about_an_attribute(tmp_path):
    from semforge.editor.verdicts import compute

    root, machine, path = _package(tmp_path, '"red", "green"', None)
    new_attribute_test(load(root), machine, path, 'valid', 'mode-valid')
    bad = new_attribute_test(load(root), machine, path, 'invalid', 'mode-invalid')
    package = load(root)
    shape = next(o['constraint'] for o in assertable(package, bad['case'])
                 if o['constraint'].endswith(f'hasMode/{IN}')).split('/')[0]
    found = attribute_cases(package, shape, 'hasMode', compute(package, 'now'))
    # Only what has the attribute: the scaffold's own cases do not.
    assert {c['case'].split('/')[-1]: c['passed'] for c in found} == {
        'mode-valid.jsonld': True, 'mode-invalid.jsonld': False}
    assert attribute_cases(package, shape, 'hasMode', None) == [], 'nothing known yet'

    set_value(package, bad['resource'], [_key(bad), 'value'], 'blue', bad['file'])
    add_assert(load(root), bad['case'], f'{shape}/hasMode/{IN}', bad['resource'])
    package = load(root)
    first = attribute_cases(package, shape, 'hasMode', compute(package, 'later'))[0]
    assert first['case'] == bad['case'] and first['asserts'] == ['In'] == first['fires']
    assert first['passed']


def test_a_list_of_terms_is_written_as_terms(tmp_path):
    root, machine, path = _package(tmp_path, 'owl:Thing, owl:Nothing', None)
    made = new_attribute_test(load(root), machine, path, 'valid', 'mode-valid')
    assert made['passes'], made['failures']
    offered, _ = value_choices(load(root), 'Machine', _key(made), search='NOTH')
    assert [o['label'] for o in offered] == ['Nothing']
    assert '@id' in json.loads(offered[0]['value'])


def test_a_list_written_by_hand_in_any_quotes(tmp_path):
    root, machine, path = _package(tmp_path, '"red"', None)
    shapes = next(p for p in load(root).files('shapes') if 'sh:in' in open(p).read())
    before = re.search(r'sh:in \(.*?\)', open(shapes).read()).group(0)
    for written, words in (("( 'red' \'\'\'a \"b\" c\'\'\' )", ['red', 'a "b" c']),
                           ('( "a\\"b" "gr\\u00fcn"@de )', ['a"b', 'grün']),
                           ('( "x"^^xsd:string "\\ud83d\\ude00" "z"^^<http://x/a(b),c> )',
                            ['x', '😀', 'z']),
                           ('( # colours, (two)\n "red" # the first\n "x" )', ['red', 'x']),
                           ('( 1# the first\n 2 )', ['1', '2']),
                           ('( "INF"^^xsd:double )', ['inf']),
                           ('( 1 "abc"^^xsd:integer )', ['1', 'abc'])):
        text = open(shapes).read()
        with open(shapes, 'w') as handle:
            handle.write(text.replace(before, f'sh:in {written}'))
        before = f'sh:in {written}'
        made = new_attribute_test(load(root), machine, path, 'valid', f'mode {words[0]}')
        assert made['passes'], (written, made['failures'])
        offered, _ = value_choices(load(root), 'Machine', _key(made))
        assert [o['label'] for o in offered] == words
        for choice in offered:
            set_value(load(root), made['resource'], [_key(made), 'value'], choice['value'], made['file'])
            assert build_case_page(load(root), made['case'])['passed'], (written, choice)
        delete_cases(load(root), made['case'])       # or the next starts from it


def test_a_long_list_is_offered_whole(tmp_path):
    root, machine, path = _package(tmp_path, ', '.join(f'"c{n}"' for n in range(250)), None)
    made = new_attribute_test(load(root), machine, path, 'valid', 'm')
    assert len(value_choices(load(root), 'Machine', _key(made), limit=200)[0]) == 250


def test_a_list_inside_a_connective_is_offered_too(tmp_path):
    root, machine, path = _package(tmp_path, '"red"', None)
    shapes = next(p for p in load(root).files('shapes') if 'sh:in' in open(p).read())
    text = open(shapes).read()
    with open(shapes, 'w') as handle:
        handle.write(re.sub(r'sh:in \(.*?\)', 'sh:and ( [ sh:in ( "a" "b" ) ] [ sh:minLength 1 ] )', text, count=1))
    made = new_attribute_test(load(root), machine, path, 'valid', 'm')
    assert made['passes'], made['failures']
    for said in (_key(made), 'hasMode', 'other:hasMode'):
        for kind in ('Machine', 'my:Machine'):
            assert [o['label'] for o in value_choices(load(root), kind, said)[0]] == ['a', 'b'], (said, kind)


@pytest.mark.parametrize('said, component', [
    ('sh:closed true', 'Closed'),
    ('sh:expression [ sh:path PREFIX:hasOther ]', 'Expression'),
    ('sh:property [ sh:path PREFIX:hasMode ; sh:qualifiedValueShape [ sh:nodeKind sh:IRI ] ; '
     'sh:qualifiedMinCount 1 ]', 'QualifiedMinCount'),
    ('sh:property [ sh:path PREFIX:hasMode ; sh:disjoint PREFIX:hasMode ]', 'Disjoint'),
    ('sh:property [ sh:path PREFIX:hasMode ; sh:equals PREFIX:hasOther ]', 'Equals'),
    ('sh:property [ sh:path PREFIX:hasMode ; sh:sparql [ a sh:SPARQLConstraint ; '
     'sh:select "SELECT $this ?value WHERE { $this $PATH ?value }" ] ]', 'SPARQL')])
def test_what_fires_can_be_asserted_whatever_it_is(tmp_path, said, component):
    root, machine, path = _package(tmp_path, '"red"', None)
    bad = new_attribute_test(load(root), machine, path, 'invalid', 'mode-invalid')
    listed = set(known_constraints(load(root)))
    shapes = next(p for p in load(root).files('shapes') if 'sh:in' in open(p).read())
    text = open(shapes).read()
    prefix = re.search(r'sh:path (\w+):hasMode', text).group(1)
    with open(shapes, 'w') as handle:
        handle.write(re.sub(r'(sh:targetClass [^;]*;)', lambda m: m.group(1) + ' ' +
                            said.replace('PREFIX', prefix) + ' ;', text, count=1))
    page = build_case_page(load(root), bad['case'])
    firing = next(u for u in page['unasserted'] if u['constraint'].endswith(f'/{component}ConstraintComponent'))
    assert firing['constraint'] in [o['constraint'] for o in assertable(load(root), bad['case'])]
    for unasserted in page['unasserted']:
        add_assert(load(root), bad['case'], unasserted['constraint'], unasserted['resource'])
    page = build_case_page(load(root), bad['case'])
    assert page['passed'] and not any(c.get('stale') for c in page['claims']), page['failures']
    # What coverage counts is the same; a name nobody declares is still none.
    known = known_constraints(load(root))
    assert listed <= set(known) and f'{firing["constraint"].split("/")[0]}/x/UniqueLangConstraintComponent' not in known


def test_a_property_shape_with_a_target_of_its_own(tmp_path):
    root, machine, path = _package(tmp_path, '"red"', None)
    bad = new_attribute_test(load(root), machine, path, 'invalid', 'mode-invalid')
    shapes = next(p for p in load(root).files('shapes') if 'sh:in' in open(p).read())
    prefix = re.search(r'sh:path (\w+):hasMode', open(shapes).read()).group(1)
    with open(shapes, 'a') as handle:
        handle.write(f'\n{prefix}:P a sh:PropertyShape ; sh:targetClass <{machine}> ; '
                     f'sh:path {prefix}:hasOther ; sh:minCount 1 .\n')
    page = build_case_page(load(root), bad['case'])
    firing = next(u for u in page['unasserted'] if 'hasOther/MinCount' in u['constraint'])
    add_assert(load(root), bad['case'], firing['constraint'], firing['resource'])
    page = build_case_page(load(root), bad['case'])
    assert page['passed'] and not page['claims'][0].get('stale')
    assert firing['constraint'] in known_constraints(load(root))


def test_the_list_of_a_relationship_is_offered_as_iris(tmp_path):
    root = str(tmp_path / 'my-model')
    create_package(root)
    machine = str(next(c for c in load(root).knowledge.subjects() if str(c).endswith('/Machine')))
    add_attribute_term(load(root), 'hasPeer', 'Relationship', machine, label='Peer')
    package = load(root)
    shape = str(next(s for s in package.shapes.subjects() if str(s).endswith('/MachineShape')))
    add_attribute_constraint(package, shape, 'hasPeer', required=False)
    shapes = next(p for p in load(root).files('shapes') if 'hasPeer' in open(p).read())
    text = open(shapes).read()
    at = text.index('hasPeer')
    with open(shapes, 'w') as handle:
        handle.write(text[:at] + re.sub(
            r'sh:path (\S+hasObject)', r'sh:path \1 ; sh:or ( [ sh:in ( <urn:a:1> <urn:a:2> ) ] )',
            text[at:], count=1))
    assert [o['value'] for o in value_choices(load(root), 'Machine', 'hasPeer')[0]] == ['urn:a:1', 'urn:a:2']


def test_a_case_declared_with_a_dotted_path_loses_its_assert_too(tmp_path):
    root, machine, path = _package(tmp_path, '"red"', None)
    bad = new_attribute_test(load(root), machine, path, 'invalid', 'mode-invalid')
    choice = assertable(load(root), bad['case'])[0]
    add_assert(load(root), bad['case'], choice['constraint'], choice['resource'])
    page = build_case_page(load(root), bad['case'])
    text = open(page['expectations']).read()
    with open(page['expectations'], 'w') as handle:
        handle.write(text.replace('path: mode-invalid', 'path: ./mode-invalid'))
    page = build_case_page(load(root), bad['case'])
    claim = page['claims'][0]
    retarget_assert(page['expectations'], claim['entry'], claim['index'], choice['constraint'] + 'x')
    remove_assert(page['expectations'], claim['entry'], claim['index'])
    assert build_case_page(load(root), bad['case'])['claims'] == []


def test_the_next_test_gets_the_next_name(tmp_path):
    root, machine, path = _package(tmp_path, '"red"', None)
    names = []
    for _ in range(3):
        name = attribute_test_options(load(root), machine, path)['options'][1]['name']
        new_attribute_test(load(root), machine, path, 'invalid', name)
        names.append(name)
    assert names == ['mode-invalid', 'mode-invalid-2', 'mode-invalid-3']


def test_a_name_is_free_as_the_file_it_becomes(tmp_path):
    from semforge.expect.attributecase import _directory, _row, _suggested

    root, machine, path = _package(tmp_path, '"red"', None)
    package = load(root)
    row = dict(_row(package, machine, path)[1], label='hasTürMode')
    name = _suggested(package, row, 'invalid')
    os.makedirs(_directory(package, row, 'invalid'), exist_ok=True)
    open(os.path.join(_directory(package, row, 'invalid'), f'{name}.jsonld'), 'w').close()
    assert _suggested(package, row, 'invalid') == f'{name}-2' and name.isascii()


def test_the_assert_removed_is_the_one_meant(tmp_path):
    root, machine, path = _package(tmp_path, '"red"', None)
    bad = new_attribute_test(load(root), machine, path, 'invalid', 'mode-invalid')
    first, second = assertable(load(root), bad['case'])[:2]
    for choice in (first, second):
        add_assert(load(root), bad['case'], choice['constraint'], choice['resource'])
    page = build_case_page(load(root), bad['case'])
    claim = page['claims'][0]
    meant = (claim['constraint'], claim['resource'])
    remove_assert(page['expectations'], claim['entry'], 0, meant)
    with pytest.raises(PackageError, match='changed'):
        remove_assert(page['expectations'], claim['entry'], 0, meant)
    with pytest.raises(PackageError, match='changed'):
        retarget_assert(page['expectations'], claim['entry'], 0, 'x:S/y/z', meant)
    assert len(build_case_page(load(root), bad['case'])['claims']) == 1


def test_the_server_answers_both(tmp_path):
    from semforge.editor import views

    root, machine, path = _package(tmp_path, '"red", "green"', None)
    bad = new_attribute_test(load(root), machine, path, 'invalid', 'mode-invalid')
    uri = f'file://{root}/kms.yaml'
    said = views.assertable_feature(None, {'uri': uri, 'case': bad['case']})
    assert said['ok'] and said['choices']
    assert not views.assertable_feature(None, {'uri': uri, 'case': 'no/such.jsonld'})['ok']
    assert views.attribute_cases_feature(None, {'uri': uri, 'shape': 'x:S', 'attribute': 'y'})['ok']
    for feature in (views.assertable_feature, views.attribute_cases_feature):
        assert not feature(None, {'uri': 'file:///nowhere/x.ttl'})['ok']


def test_a_violation_is_not_a_reason():
    report = Report(results=[Result('urn:a', 'hasX', IN, 'https://x/S', 'violation')])
    assert evaluate(Example(path='c', expect='invalid'), report).failures == [NO_REASON]
    assert evaluate(Example(path='c', expect='valid'), Report()).passed


# --- the pages -------------------------------------------------------------------------

CASE = '/pkg/examples/test_S/bad/mode.jsonld'
PAGE = {'ok': True, 'kind': 'case', 'name': 'mode.jsonld', 'case': 'test_S/bad/mode.jsonld',
        'expect': 'invalid', 'passed': False, 'failures': [NO_REASON], 'claims': [],
        'unasserted': [], 'file': CASE, 'expectations': '/pkg/examples/test_S/bad/expectations.yaml',
        'files': [], 'summary': {'entities': 1, 'violations': 0}}
CLAIM = {'constraint': f'x:S/hasMode/{IN}', 'resource': 'urn:m:1', 'holds': True,
         'explained': None, 'entry': 'mode.jsonld', 'index': 0}


def _case_page(tmp_path, page, messages, replies=None, **scenario):
    return _drive(tmp_path, dict({
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'file': CASE}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': messages,
        'replies': dict({'semforge/casePage': page}, **(replies or {}))}, **scenario))


def _asked(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


def test_new_test_offers_two_things_and_asserts_nothing(tmp_path):
    invalid = {'purpose': 'invalid', 'label': 'fails', 'detail': 'x', 'automatic': False,
               'name': 'pressure-invalid'}
    options = dict(OPTIONS, options=OPTIONS['options'][:1] + [invalid])
    seen = _drive(tmp_path, {
        'command': 'semforge.newAttributeTest',
        'node': {'raw': PRESSURE, 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': [1], 'inputs': ['pressure-invalid'],
        'replies': {'semforge/attributeTestOptions': options, 'semforge/newAttributeTest': {
            'ok': True, 'file': CASE, 'case': 'test_S/bad/mode.jsonld', 'purpose': 'invalid',
            'passes': False, 'failures': [NO_REASON]}}})
    assert seen['errors'] == [], seen['errors']
    assert _asked(seen, 'semforge/newAttributeTest')[0]['purpose'] == 'invalid'
    assert any('assert what fires' in text for text in seen['info'])
    assert seen['warnings'] == []


def test_the_case_page_says_what_is_missing_and_offers_everything(tmp_path):
    seen = _case_page(tmp_path, PAGE, [])
    html = seen['webviews'][0]['html'][-1]
    assert 'No reason yet' in html
    for command in ('addAssert', 'clone', 'rename', 'delete'):
        assert f'data-pagecmd="{command}"' in html


def test_an_assert_is_chosen_from_what_judges_the_case(tmp_path):
    choices = [{'constraint': CLAIM['constraint'], 'resource': 'urn:m:1', 'fires': False, 'text': ''}]
    seen = _case_page(tmp_path, PAGE, [{'command': 'addAssert'}], picks=[1], replies={
        'semforge/assertable': {'ok': True, 'choices': choices},
        'semforge/addAssert': {'ok': True, 'file': 'x', 'note': ''}})
    assert seen['errors'] == [], seen['errors']
    assert _asked(seen, 'semforge/addAssert')[0]['constraint'] == CLAIM['constraint']


def test_any_assert_can_be_removed(tmp_path):
    seen = _case_page(tmp_path, dict(PAGE, claims=[CLAIM]), [{'command': 'removeAssert', 'index': 0}],
                      replies={'semforge/removeUse': {'ok': True, 'note': ''}})
    assert 'data-dropassert="0"' in seen['webviews'][0]['html'][0]
    sent = _asked(seen, 'semforge/removeUse')
    assert sent[0]['kind'] == 'assert' and sent[0]['case'] == 'mode.jsonld' and sent[0]['index'] == 0
    assert sent[0]['expected'] == {'constraint': CLAIM['constraint'], 'resource': 'urn:m:1'}


TYPE = {'raw': {'kind': 'type', 'label': 'Machine', 'targetClass': 'https://x/Machine',
                'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'}


def test_the_attribute_editor_lists_its_tests(tmp_path):
    row = {'label': 'hasMode', 'attribute': 'https://x/hasMode', 'path': ['x:hasMode'],
           'term': 'x:hasMode', 'kind': 'Property', 'presence': 'optional', 'value': 'text',
           'verbatim': [], 'shape': 'https://x/S', 'shapeName': 'x:S', 'depth': 0,
           'violations': [], 'tested': 'never fired'}
    page = {'ok': True, 'iri': 'https://x/Machine', 'label': 'Machine', 'crumbs': [], 'summary': {},
            'rules': [], 'instances': [], 'subtypes': [], 'attributes': [row],
            'exercisedBy': [{'case': 'test_S/bad/mode.jsonld', 'file': CASE, 'expect': 'invalid',
                             'passed': False, 'description': ''}]}
    tests = [{'case': 'test_S/bad/mode.jsonld', 'file': CASE, 'expect': 'invalid', 'passed': False,
              'description': '', 'asserts': [], 'fires': ['In']}]
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': TYPE,
        'webviewMessages': [{'command': 'attribute', 'row': 0}],
        'replies': {'semforge/typePage': page, 'semforge/attributeCases': {'ok': True, 'cases': tests},
                    'semforge/valueForms': {'ok': True, 'forms': [], 'editable': True}}})
    htmls = [w['html'][-1] for w in seen['webviews']]
    editor = next(h for h in htmls if 'Attribute: hasMode' in h)
    assert f'data-testopen="{CASE}"' in editor and f'data-testdelete="{CASE}"' in editor
    assert 'fires In' in editor
    assert f'data-delcase="{CASE}"' in next(h for h in htmls if 'Attribute: hasMode' not in h)

    # The list of cases on the type page deletes one, too.
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage', 'node': TYPE,
        'webviewMessages': [{'command': 'deleteCase', 'file': CASE}],
        'replies': {'semforge/typePage': page}})
    assert _opened(seen, 'semforge.deleteTestCase')[0][0]['raw']['file'] == CASE


@pytest.mark.parametrize('lexical, datatype, plain', [
    ('INF', XSD.double, False), ('-INF', XSD.float, False), ('NaN', XSD.double, False),
    ('2.5', XSD.double, True), ('yes', XSD.boolean, True), ('1', XSD.boolean, True)])
def test_an_item_is_written_as_json_that_reads_back_as_itself(lexical, datatype, plain):
    """INF and NaN are no JSON numbers: a double that is none stays text, with
    its datatype. (The graph holds the terms
    as rdflib normalises them, and so do these.)"""
    from semforge.expect.attributecase import json_value

    term = Literal(lexical, datatype=datatype)
    written = json_value(None, term)
    assert json.loads(json.dumps(written, allow_nan=False)) == written
    if plain:
        assert not isinstance(written, dict) or isinstance(written['@value'], float)
    else:
        assert written == {'@value': str(term), '@type': str(datatype)}
