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

"""A value that is more than one set of conditions: read, said, edited.

One plain value stays one plain value -- the picker edits it, and nothing here
is offered unless asked for. A value that already is an expression is read as
a tree; every edit is one rewrite of the value layer, read back before kept.
"""

import shutil

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import SH

from semforge.cooked.expression import (Leaf, Op, describe, edit, normalize, normalize_root,
                                        read_layer)
from semforge.errors import PackageError

FILTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/FilterShape'
STRENGTH = ['iffBaseEntities:hasStrength']
EXTRA = '''
<https://example.org/ExprShape> a sh:NodeShape ;
    sh:targetClass iffBaseEntities:Filter ;
    sh:property [ sh:path iffBaseEntities:hasNoteX ; sh:minCount 0 ; sh:maxCount 1 ;
                  sh:property [ sh:path ngsild:hasValue ; sh:minCount 1 ; sh:maxCount 1 ;
                                sh:datatype xsd:string ] ] ,
                [ sh:path iffBaseEntities:hasNodeX ; sh:minCount 0 ; sh:maxCount 1 ;
                  sh:property [ sh:path ngsild:hasValue ;
                                sh:or ( [ sh:node <https://example.org/Other> ]
                                        [ sh:datatype xsd:string ] ) ] ] ,
                [ sh:path iffBaseEntities:hasCommentX ; sh:minCount 0 ; sh:maxCount 1 ;
                  sh:property [ sh:path ngsild:hasValue ;
                                sh:or ( [ sh:datatype xsd:string ]   # text
                                        [ sh:datatype xsd:integer ] ) ] ] .
'''
EXPR = 'https://example.org/ExprShape'
KNOWLEDGE = ''.join(
    f'\n<https://industryfusion.github.io/contexts/example/v0/base_entities/{name}> '
    f'a <http://www.w3.org/2002/07/owl#ObjectProperty> ; '
    f'<http://www.w3.org/2000/01/rdf-schema#domain> '
    f'<https://industryfusion.github.io/contexts/example/v0/base_entities/Filter> .\n'
    for name in ('hasNoteX', 'hasNodeX', 'hasCommentX'))


@pytest.fixture
def root(tmp_path, corpus):
    root = tmp_path / 'pkg'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    shapes = root / 'shacl.ttl'
    shapes.write_text(shapes.read_text() + EXTRA)
    knowledge = root / 'knowledge.ttl'
    knowledge.write_text(knowledge.read_text() + KNOWLEDGE)
    return root


def _layer(root, shape=FILTER, chain=STRENGTH):
    from semforge.package import load

    return read_layer(load(str(root)), (root / 'shacl.ttl').read_text(), shape, chain)


def _edit(root, action, shape=FILTER, chain=STRENGTH):
    from semforge.package import load

    return edit(load(str(root)), shape, chain, action)


def _row(root, label):
    from semforge.cooked.typepage import PENDING, build_type_page
    from semforge.package import load

    page = build_type_page(load(str(root)), 'iffBaseEntities:Filter', PENDING)
    return next(r for r in page['attributes'] if r['label'] == label)


# --- the shape of a tree -----------------------------------------------------------------

def test_an_empty_set_is_anything_and_only_an_all_of_may_drop_it():
    text = Leaf((('sh:datatype', 'xsd:string'),))
    assert normalize(Op('and', (Leaf(), text))) == text
    assert normalize(Op('or', (Leaf(), text))) == Op('or', (Leaf(), text))
    assert normalize(Op('or', (text,))) == text
    assert normalize(Op('not', (text,))) == Op('not', (text,))


def test_top_level_conditions_join_the_layers_own_unless_they_clash():
    double = Leaf((('sh:datatype', 'xsd:double'),))
    bounded = Leaf((('sh:maxInclusive', '100'),))
    integer = Leaf((('sh:datatype', 'xsd:integer'),))
    root = normalize_root(Op('and', (double, bounded, integer)))
    assert root.children[0] == Leaf((('sh:datatype', 'xsd:double'), ('sh:maxInclusive', '100')))
    assert root.children[1:] == (integer,)


# --- reading ---------------------------------------------------------------------------------

def test_the_kms_number_is_read_as_an_expression(root):
    layer = _layer(root)
    assert layer.complex and layer.editable
    assert describe(layer) == '0 – 100 · any of: number (double) | number (integer)'


def test_one_plain_value_is_not_an_expression(root):
    layer = _layer(root, EXPR, ['iffBaseEntities:hasNoteX'])
    assert not layer.complex
    row = _row(root, 'hasNoteX')
    assert row['expression'] is None and row['valueEditable']
    # The kms number keeps its plain words on the page, and is an expression.
    strength = _row(root, 'hasStrength')
    assert strength['expression']
    assert strength['value'] == 'number · 0 – 100'


def test_a_branch_it_cannot_say_is_kept_and_the_rest_edited(root):
    chain = ['iffBaseEntities:hasNodeX']
    layer = _layer(root, EXPR, chain)
    assert layer.editable
    branches = layer.root.children[1].children
    assert branches[0].text == '[ sh:node <https://example.org/Other> ]'
    _edit(root, {'op': 'add', 'node': [1], 'parameter': 'sh:datatype', 'value': 'xsd:integer'},
          EXPR, chain)
    after = _layer(root, EXPR, chain).root.children[1].children
    assert after[0] == branches[0] and len(after) == 3


def test_a_comment_inside_keeps_it_read_only(root):
    layer = _layer(root, EXPR, ['iffBaseEntities:hasCommentX'])
    assert layer.complex and not layer.editable and 'comment' in layer.reason
    assert _row(root, 'hasCommentX')['valueEditable'] is False
    with pytest.raises(PackageError, match='comment'):
        _edit(root, {'op': 'remove', 'node': [1, 0]}, EXPR, ['iffBaseEntities:hasCommentX'])


# --- editing ---------------------------------------------------------------------------------

def test_branches_are_added_and_removed_and_one_left_is_a_plain_value_again(root):
    _edit(root, {'op': 'add', 'node': [1], 'parameter': 'sh:datatype', 'value': 'xsd:decimal'})
    assert describe(_layer(root)).endswith('| number (decimal)')
    _edit(root, {'op': 'remove', 'node': [1, 2]})
    _edit(root, {'op': 'remove', 'node': [1, 1]})
    layer = _layer(root)
    assert not layer.complex
    assert describe(layer) == 'number (double) · 0 – 100'
    assert _row(root, 'hasStrength')['expression'] is None


def test_combine_turns_one_value_into_any_of(root):
    chain = ['iffBaseEntities:hasNoteX']
    _edit(root, {'op': 'combine', 'connective': 'or', 'parameter': 'sh:datatype',
                 'value': 'xsd:integer'}, EXPR, chain)
    layer = _layer(root, EXPR, chain)
    assert describe(layer) == 'any of: text | number (integer)'
    row = _row(root, 'hasNoteX')
    assert row['expression']


def test_combine_needs_a_value_to_combine_with(root, tmp_path):
    from semforge.package import load

    shapes = root / 'shacl.ttl'
    shapes.write_text(shapes.read_text().replace(
        'sh:maxCount 1 ;\n                                sh:datatype xsd:string ] ] ,',
        'sh:maxCount 1 ] ] ,'))
    with pytest.raises(PackageError, match='any value so far'):
        edit(load(str(root)), EXPR, ['iffBaseEntities:hasNoteX'],
             {'op': 'combine', 'connective': 'or', 'parameter': 'sh:datatype',
              'value': 'xsd:integer'})


def test_wrap_retype_and_unwrap(root):
    _edit(root, {'op': 'retype', 'node': [1], 'connective': 'xone'})
    assert 'exactly one of' in describe(_layer(root))
    _edit(root, {'op': 'wrap', 'node': [1, 0], 'connective': 'not'})
    assert 'not (number (double))' in describe(_layer(root))
    _edit(root, {'op': 'unwrap', 'node': [1, 0]})
    assert describe(_layer(root)) == '0 – 100 · exactly one of: number (double) | number (integer)'


def test_set_and_unset_a_condition_of_a_branch(root):
    _edit(root, {'op': 'set', 'node': [1, 1], 'parameter': 'sh:maxInclusive', 'value': '10'})
    assert 'number (integer) · ≤ 10' in describe(_layer(root))
    _edit(root, {'op': 'unset', 'node': [1, 1], 'parameter': 'sh:maxInclusive'})
    assert describe(_layer(root)) == '0 – 100 · any of: number (double) | number (integer)'


def test_what_is_written_validates_as_meant(root):
    """'n/a', or a number from 0 to 100: both pass; 150 and "other" do not."""
    import pyshacl

    from semforge.package import load
    from semforge.validate.shapes import subgraph_for

    _edit(root, {'op': 'combine', 'connective': 'or', 'parameter': 'sh:hasValue',
                 'value': '"n/a"'})
    shapes = subgraph_for(load(str(root)).shapes, [URIRef(FILTER)])

    def fails(value):
        data = Graph().parse(data=f'''
            @prefix ngsild: <https://uri.etsi.org/ngsi-ld/> .
            @prefix e: <https://industryfusion.github.io/contexts/example/v0/base_entities/> .
            <urn:f:1> a e:Filter ; e:hasStrength [ ngsild:hasValue {value} ] .''', format='turtle')
        _, report, _ = pyshacl.validate(data, shacl_graph=shapes + Graph())  # pyshacl writes into it
        return any('hasStrength' in str(report.value(r, SH.resultPath)) or
                   'hasValue' in str(report.value(r, SH.resultPath))
                   for r in report.objects(None, SH.result)
                   if str(report.value(r, SH.focusNode)) != 'urn:f:1' or
                   'hasStrength' in str(report.value(r, SH.resultPath)))

    assert not fails('"50"^^<http://www.w3.org/2001/XMLSchema#double>')
    assert not fails('"n/a"')
    assert fails('"150"^^<http://www.w3.org/2001/XMLSchema#double>')
    assert fails('"other"')


def test_a_group_is_added_with_its_branches(root):
    chain = ['iffBaseEntities:hasNoteX']
    _edit(root, {'op': 'addgroup', 'node': [], 'connective': 'or',
                 'conditions': [{'parameter': 'sh:maxLength', 'value': '5'},
                                {'parameter': 'sh:hasValue', 'value': '"n/a"'}]}, EXPR, chain)
    assert describe(_layer(root, EXPR, chain)) == \
        'text · any of: at most 5 characters | exactly "n/a"'
    with pytest.raises(PackageError, match='two or more'):
        _edit(root, {'op': 'addgroup', 'node': [], 'connective': 'or',
                     'conditions': [{'parameter': 'sh:maxLength', 'value': '5'}]}, EXPR, chain)


def test_a_scalar_or_list_value_takes_an_expression_on_every_form(tmp_path, corpus):
    """The kms hasList: an integer or a list of them. The expression holds for
    the one value and for each item alike."""
    from semforge.cooked.valueforms import read_value, say
    from semforge.package import load

    root = tmp_path / 'pkg'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    cutter = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/CutterShape'
    chain = ['iffBaseEntities:hasList']
    edit(load(str(root)), cutter, chain, {'op': 'combine', 'connective': 'or',
                                          'parameter': 'sh:hasValue', 'value': '"n/a"'})
    value = read_value(load(str(root)), (root / 'shacl.ttl').read_text(), cutter, chain)
    scalar, listed = value.forms
    assert normalize_root(scalar.root) == normalize_root(listed.root)
    assert say(value) == \
        'any of: number (integer) | exactly "n/a", or a list of them (possibly empty)'


# --- a value that may be one or a list: its forms, shown -------------------------------------

CUTTER = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/CutterShape'
LIST = ['iffBaseEntities:hasList']


def _cutter(tmp_path, corpus):
    root = tmp_path / 'cut'
    shutil.copytree(corpus.path, root, ignore=shutil.ignore_patterns('.semforge'))
    return root


def test_the_forms_are_said_and_the_encoding_is_not_a_condition(tmp_path, corpus):
    """The kms hasList is written as the OPC UA tools write hasAmbientHumidity:
    an integer, or a list of integers that may be empty. The editor showed the
    integer and sh:nodeKind sh:Literal -- and nothing of the list."""
    from semforge.cooked.valueforms import read_value, to_payload
    from semforge.package import load

    root = _cutter(tmp_path, corpus)
    value = read_value(load(str(root)), (root / 'shacl.ttl').read_text(), CUTTER, LIST)
    forms = to_payload(value)['forms']
    assert [(f['kind'], f['payload'], f['mayBeEmpty']) for f in forms] == [
        ('Property', 'ngsi-ld:hasValue', False), ('ListProperty', 'ngsi-ld:hasValueList', True)]
    assert forms[0]['expression']['children'][0]['conditions'] == \
        [{'parameter': 'sh:datatype', 'value': 'xsd:integer'}]


def test_the_one_values_encoding_follows_what_it_must_be(tmp_path, corpus):
    from semforge.cooked.constrain import _group_in
    from semforge.cooked.payloads import alternatives, prefixes_of
    from semforge.package import load

    root = _cutter(tmp_path, corpus)

    def encodings():
        """sh:nodeKind of the one value and of each item, as written."""
        package = load(str(root))
        text = (root / 'shacl.ttl').read_text()
        written = _group_in(text, CUTTER, LIST).parameter('sh:or')[2]
        scalar, listed = alternatives(written, prefixes_of(package))
        return dict(scalar.member).get('sh:nodeKind'), dict(listed.member).get('sh:nodeKind')

    edit(load(str(root)), CUTTER, LIST, {'op': 'set', 'node': [0], 'parameter': 'sh:datatype',
                                         'value': 'xsd:double'})
    assert encodings() == ('sh:Literal', None)
    edit(load(str(root)), CUTTER, LIST, {'op': 'combine', 'connective': 'or',
                                         'parameter': 'sh:hasValue', 'value': '"n/a"'})
    # A choice of a number and a text: both literals, so still sh:Literal.
    assert encodings() == ('sh:Literal', None)
    edit(load(str(root)), CUTTER, LIST, {'op': 'add', 'node': [1], 'parameter': 'sh:class',
                                         'value': 'iffBaseEntities:Filter'})
    # A literal or an IRI: no one encoding holds for every branch.
    assert encodings() == (None, None)
