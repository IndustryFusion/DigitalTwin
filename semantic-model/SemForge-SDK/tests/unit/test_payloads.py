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

"""The forms a value may take: a scalar, a list, or a choice of them.

The OPC UA tools write every Variable as `sh:or ( scalar | list )` -- its
ValueRank decides which an instance may be -- and as `ngsi-ld:`, not `ngsild:`.
The cooked views showed "any value" with the sh:or verbatim, and every
relationship's `ngsi-ld:hasObject` as a sub-attribute named hasObject.
"""

import shutil

import pytest

from semforge.cooked.payloads import alternatives, list_form
from semforge.cooked.valueforms import say, value_of
from semforge.ngsild.kinds import SPELLINGS, payload_of

PREFIXES = [('sh', 'http://www.w3.org/ns/shacl#'), ('xsd', 'http://www.w3.org/2001/XMLSchema#'),
            ('rdf', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'),
            ('ngsi-ld', 'https://uri.etsi.org/ngsi-ld/'), ('ex', 'https://example.org/')]

LIST_OF = ('( [ sh:nodeKind sh:BlankNode ; sh:property [ {member} ; '
           'sh:path ( [ sh:zeroOrMorePath rdf:rest ] rdf:first ) ] ] [ sh:hasValue () ] )')


def scalar_or_list(member, scalar_extra='sh:nodeKind sh:Literal ;'):
    return (f'( [ sh:property [ {member} ; sh:maxCount 1 ; sh:minCount 1 ; {scalar_extra} '
            f'sh:path ngsi-ld:hasValue ] ] '
            f'[ sh:property [ sh:maxCount 1 ; sh:minCount 1 ; '
            f'sh:or {LIST_OF.format(member=member)} ; sh:path ngsi-ld:hasValueList ] ] )')


@pytest.mark.parametrize('text, name', [
    ('ngsild:hasValue', 'hasValue'), ('ngsi-ld:hasObject', 'hasObject'),
    ('<https://uri.etsi.org/ngsi-ld/hasValueList>', 'hasValueList'),
    ('ex:hasValue', ''), ('ngsi-ld:hasCategory', ''), ('', ''),
])
def test_every_spelling_of_a_payload_is_one(text, name):
    assert payload_of(text) == name
    assert (text in SPELLINGS) is bool(name)


@pytest.mark.parametrize('member, said', [
    ('sh:datatype xsd:string', 'text, or a list of them (possibly empty)'),
    ('sh:datatype xsd:double', 'number, or a list of them (possibly empty)'),
    ('sh:class ex:PortDirectionEnum', 'one of PortDirectionEnum, or a list of them (possibly empty)'),
])
def test_a_scalar_or_a_list_is_read_and_said(member, said):
    found = alternatives(scalar_or_list(member), PREFIXES)
    assert [a.kind for a in found] == ['Property', 'ListProperty']
    assert [a.payload for a in found] == ['hasValue', 'hasValueList']
    assert found[1].may_be_empty and not found[0].may_be_empty
    assert say(value_of(found, PREFIXES)) == said


def test_a_list_whose_members_differ_says_both():
    text = ('( [ sh:property [ sh:datatype xsd:string ; sh:path ngsi-ld:hasValue ] ] '
            '[ sh:property [ sh:path ngsi-ld:hasValueList ; sh:nodeKind sh:BlankNode ; '
            'sh:property [ sh:datatype xsd:double ; '
            'sh:path ( [ sh:zeroOrMorePath rdf:rest ] rdf:first ) ] ] ] )')
    found = alternatives(text, PREFIXES)
    assert not found[1].may_be_empty
    assert say(value_of(found, PREFIXES)) == 'text, or a list of: number'


def test_the_value_of_a_list_payload_is_read():
    assert list_form(LIST_OF.format(member='sh:datatype xsd:string'), PREFIXES) == \
        ((('sh:datatype', 'xsd:string'),), True)


@pytest.mark.parametrize('text', [
    # A choice of datatypes, not of value layers: the type page says "number".
    '( [ sh:datatype xsd:double ] [ sh:datatype xsd:integer ] )',
    # Not a payload.
    '( [ sh:property [ sh:path ex:other ; sh:datatype xsd:string ] ] )',
    # Something this does not say in words, on the value.
    '( [ sh:property [ sh:path ngsi-ld:hasValue ; sh:node ex:Shape ] ] )',
    # A value layer with more beside it.
    '( [ sh:property [ sh:path ngsi-ld:hasValue ] ; sh:minCount 1 ] )',
    # A list whose members are reached some other way.
    '( [ sh:property [ sh:path ngsi-ld:hasValueList ; sh:nodeKind sh:BlankNode ; '
    'sh:property [ sh:path rdf:first ; sh:datatype xsd:string ] ] ] )',
    'not turtle at all (',
])
def test_anything_else_is_not_guessed_at(text):
    assert alternatives(text, PREFIXES) is None


SHAPES = '''
<https://example.org/FormsShape> a sh:NodeShape ;
    sh:targetClass iffBaseEntities:Filter ;
    sh:property [ sh:path iffBaseEntities:hasCategoryX ; sh:minCount 0 ; sh:maxCount 1 ;
                  sh:nodeKind sh:BlankNode ; sh:or {forms} ] ,
                [ sh:path iffBaseEntities:hasLinkX ; sh:minCount 0 ; sh:maxCount 1 ;
                  sh:property [ sh:path ngsi-ld:hasObject ; sh:class iffBaseEntities:Filter ] ] ,
                [ sh:path iffBaseEntities:hasListX ;
                  sh:property [ sh:path ngsi-ld:hasValueList ; sh:minCount 1 ; sh:maxCount 1 ;
                                sh:or {listed} ] ] ,
                [ sh:path iffBaseEntities:hasPlainX ; sh:minCount 0 ; sh:maxCount 1 ;
                  sh:property [ sh:path ngsi-ld:hasValue ; sh:minCount 1 ; sh:maxCount 1 ;
                                sh:datatype xsd:string ; sh:maxLength 20 ] ] .
'''

KNOWLEDGE = ''.join(
    f'\n<https://industryfusion.github.io/contexts/example/v0/base_entities/{name}> '
    f'a <http://www.w3.org/2002/07/owl#ObjectProperty> ; '
    f'<http://www.w3.org/2000/01/rdf-schema#domain> '
    f'<https://industryfusion.github.io/contexts/example/v0/base_entities/Filter> .\n'
    for name in ('hasCategoryX', 'hasLinkX', 'hasListX', 'hasPlainX'))
FORMS = 'https://example.org/FormsShape'


def _package(tmp_path, corpus):
    root = tmp_path / 'pkg'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    shapes = root / 'shacl.ttl'
    shapes.write_text('@prefix ngsi-ld: <https://uri.etsi.org/ngsi-ld/> .\n' +
                      shapes.read_text() + SHAPES.format(
                          forms=scalar_or_list('sh:datatype xsd:string'),
                          listed=LIST_OF.format(member='sh:datatype xsd:double')))
    knowledge = root / 'knowledge.ttl'
    knowledge.write_text(knowledge.read_text() + KNOWLEDGE)
    return root


def _rows(root):
    from semforge.cooked.typepage import PENDING, build_type_page
    from semforge.package import load

    page = build_type_page(load(str(root)), 'iffBaseEntities:Filter', PENDING)
    return {r['label']: r for r in page['attributes']}


def test_the_type_page_says_the_forms(tmp_path, corpus):
    from semforge.cooked.tree import build_tree
    from semforge.package import load

    root = _package(tmp_path, corpus)
    package = load(str(root))
    rows = _rows(root)

    category = rows['hasCategoryX']
    assert category['kinds'] == ['Property', 'ListProperty']
    assert category['value'] == 'text, or a list of them (possibly empty)'
    assert not any(v.startswith('sh:or') for v in category['verbatim'])
    assert [a['payload'] for a in category['forms']] == ['hasValue', 'hasValueList']

    # ngsi-ld:hasObject is the relationship's value, not a sub-attribute.
    link = rows['hasLinkX']
    assert link['kind'] == 'Relationship' and link['value'] == '→ Filter'
    assert 'hasObject' not in rows

    listed = rows['hasListX']
    assert listed['kinds'] == ['ListProperty']
    assert listed['value'] == 'a list of: number (possibly empty)'

    # And the constraints tree names the sh:or by what it says.
    def nodes(node):
        yield node
        for child in node.children:
            yield from nodes(child)
    said = [n for top in build_tree(package) for n in nodes(top)
            if n.kind == 'raw' and n.label.startswith('value: ')]
    assert {n.label for n in said} >= {'value: Property or ListProperty', 'value: ListProperty'}
    # The attribute editor offers a list where one value is allowed, and back.
    assert category['valueEditable'] and _switch(root, 'hasCategoryX') == 'allowed'
    assert _switch(root, 'hasPlainX') == 'single'


def _switch(root, attribute):
    """What the attribute editor's list button does (semforge/valueForms)."""
    from semforge.cooked.valueforms import read_value, to_payload
    from semforge.package import load

    text = (root / 'shacl.ttl').read_text()
    value = read_value(load(str(root)), text, FORMS, [f'iffBaseEntities:{attribute}'])
    return to_payload(value)['lists']


# --- editing them --------------------------------------------------------------------

def _edit(root, attribute, value):
    from semforge.cooked.constrain import edit_attribute
    from semforge.package import load

    return edit_attribute(load(str(root)), FORMS, [f'iffBaseEntities:{attribute}'], value=value)


def test_a_new_type_goes_into_every_form(tmp_path, corpus):
    root = _package(tmp_path, corpus)
    before = (root / 'shacl.ttl').read_text()
    _edit(root, 'hasCategoryX', {'datatype': 'xsd:double'})
    after = (root / 'shacl.ttl').read_text()
    rows = _rows(root)
    assert rows['hasCategoryX']['value'] == 'number, or a list of them (possibly empty)'
    assert rows['hasCategoryX']['kinds'] == ['Property', 'ListProperty']
    # Only the sh:or changed: the corpus' own shapes, and the others here, did not.
    head = before[:before.index('<https://example.org/FormsShape>')]
    assert after.startswith(head)
    assert after[after.index('iffBaseEntities:hasLinkX'):] == \
        before[before.index('iffBaseEntities:hasLinkX'):]

    _edit(root, 'hasCategoryX', {'kind': 'any'})
    assert _rows(root)['hasCategoryX']['value'] == 'any value, or a list of them (possibly empty)'


def test_a_list_values_members_are_edited(tmp_path, corpus):
    root = _package(tmp_path, corpus)
    _edit(root, 'hasListX', {'datatype': 'xsd:string'})
    assert _rows(root)['hasListX']['value'] == 'a list of: text (possibly empty)'


def _lists(root, allowed):
    """⋯ → "Allow a list too" / "One value only": the one writer of values."""
    from semforge.cooked.valueforms import edit_value
    from semforge.package import load

    return edit_value(load(str(root)), FORMS, ['iffBaseEntities:hasPlainX'],
                      {'op': 'lists', 'value': allowed})


def test_a_single_value_may_become_a_list_and_back(tmp_path, corpus):
    root = _package(tmp_path, corpus)
    made = _lists(root, True)
    assert made.get('changed', True)
    row = _rows(root)['hasPlainX']
    assert row['kinds'] == ['Property', 'ListProperty'] and _switch(root, 'hasPlainX') == 'allowed'
    assert row['value'] == 'text · at most 20 characters, or a list of them (possibly empty)'
    # Again: nothing to do.
    assert not _lists(root, True)['changed']

    _lists(root, False)
    row = _rows(root)['hasPlainX']
    assert row['kinds'] == ['Property'] and _switch(root, 'hasPlainX') == 'single'
    assert row['value'] == 'text · at most 20 characters'


def test_a_constraint_goes_into_the_value_layer_however_it_is_spelled(tmp_path, corpus):
    """`ngsi-ld:hasValue` is the value layer: a constraint added to the value
    goes into it, not into a second one beside it."""
    from semforge.cooked.tree import add_constraint
    from semforge.package import load

    root = _package(tmp_path, corpus)
    add_constraint(load(str(root)), FORMS, ['iffBaseEntities:hasPlainX'], 'sh:minLength', '2')
    text = (root / 'shacl.ttl').read_text()
    plain = text[text.index('iffBaseEntities:hasPlainX'):]
    assert plain.count('hasValue') == 1
    assert _rows(root)['hasPlainX']['value'] == 'text · 2 – 20 characters'


def test_what_is_written_validates_as_meant(tmp_path, corpus):
    """A list of strings conforms to the rewritten shape; a list holding a
    number, or a value too long, does not."""
    import pyshacl
    from rdflib import Graph, URIRef
    from rdflib.namespace import SH

    from semforge.package import load
    from semforge.validate.shapes import subgraph_for

    root = _package(tmp_path, corpus)
    _lists(root, True)
    shapes = subgraph_for(load(str(root)).shapes, [URIRef(FORMS)])

    def violations(value):
        data = Graph().parse(data=f'''
            @prefix ngsi-ld: <https://uri.etsi.org/ngsi-ld/> .
            @prefix e: <https://industryfusion.github.io/contexts/example/v0/base_entities/> .
            <urn:f:1> a e:Filter ; e:hasPlainX [ {value} ] .''', format='turtle')
        _, report, _ = pyshacl.validate(data, shacl_graph=shapes + Graph())  # pyshacl writes into it
        return [r for r in report.objects(None, SH.result)
                if 'hasPlainX' in str(report.value(r, SH.resultPath))]

    assert violations('ngsi-ld:hasValue "short"') == []
    assert violations('ngsi-ld:hasValueList ( "a" "b" )') == []
    assert violations('ngsi-ld:hasValueList ()') == []
    assert violations('ngsi-ld:hasValueList ( "a" 3 )')
    assert violations('ngsi-ld:hasValue "far too long for twenty characters"')
