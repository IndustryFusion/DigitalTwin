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

"""A parameter whose value is a string is located at that string (#1160).

The block reader skipped strings like whitespace, so `sh:pattern "^a"` was
read as the term after the string, and replacing the pattern wrote the new
one beside the old.
"""

import shutil
from types import SimpleNamespace

import pytest
from rdflib import Graph, Literal
from rdflib.compare import isomorphic
from rdflib.namespace import SH

from semforge.package import load
from semforge.rdfio.blocks import _read_token, _scan_group, remove_parameter, set_parameter

FILTER_SHAPE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/FilterShape'
STRENGTH = ['iffBaseEntities:hasStrength']


@pytest.fixture
def kms(tmp_path, corpus_path, monkeypatch):
    """A copy of the corpus, edited through the language server's requests
    as the editor sends them."""
    from semforge.editor import edits

    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    monkeypatch.setattr(edits.session, 'package_for', lambda root: load(str(target)))
    monkeypatch.setattr(edits.session, 'forget', lambda root: None)
    monkeypatch.setattr(edits.validation, 'publish', lambda ls, uri: None)
    return target


# --- the block reader -----------------------------------------------------------------

def test_a_string_is_the_term_after_comments_and_whitespace():
    text = 'sh:pattern # why\n  "a\\"b" ; sh:flags "i"'
    assert _read_token(text, len('sh:pattern'), len(text))[0] == '"a\\"b"'
    assert _read_token(' "i" ;', 0, 6)[0] == '"i"'
    assert _read_token(" '''x\ny''' ]", 0, 12)[0] == "'''x\ny'''"


@pytest.mark.parametrize('token', ['ex:a', '<urn:x>', '( 1 2 )', '[ sh:path ex:b ]', '12'])
def test_other_terms_are_read_as_before(token):
    text = f' {token} ;'
    assert _read_token(text, 0, len(text))[0] == token


@pytest.mark.parametrize('written', ['"^a"', '"rot"@de', '"rot"@de-AT', '"2026-01-01"^^xsd:date',
                                     '"x"^^<http://www.w3.org/2001/XMLSchema#token>'])
def test_a_string_value_is_removed_and_replaced_whole(written):
    text = f'[ sh:path ex:a ; sh:hasValue {written} ; sh:minCount 1 ]'
    block = _scan_group(text, 0, len(text), 0)
    assert block.parameter('sh:hasValue')[2] == written
    assert block.parameter('sh:minCount')[2] == '1'
    assert remove_parameter(text, block, 'sh:hasValue') == '[ sh:path ex:a ;  sh:minCount 1 ]'
    assert set_parameter(text, block, 'sh:hasValue', '5') == \
        '[ sh:path ex:a ; sh:hasValue 5 ; sh:minCount 1 ]'


def test_a_pattern_and_its_flags_are_each_their_own_value():
    text = '[ sh:path ex:a ;\n  sh:pattern "^[a-z]+$" ;\n  sh:flags "i" ]'
    block = _scan_group(text, 0, len(text), 0)
    assert block.parameter('sh:pattern')[2] == '"^[a-z]+$"'
    assert block.parameter('sh:flags')[2] == '"i"'
    assert set_parameter(text, block, 'sh:pattern', '"^b"') == \
        '[ sh:path ex:a ;\n  sh:pattern "^b" ;\n  sh:flags "i" ]'


# --- through the editor -----------------------------------------------------------------

def _patterns(root):
    graph = Graph().parse(root / 'shacl.ttl', format='turtle')
    return set(graph.objects(None, SH.pattern))


def _set_constraint(root, **params):
    from semforge.editor import edits

    answer = edits.set_constraint(None, SimpleNamespace(
        uri=(root / 'shacl.ttl').as_uri(), shape=FILTER_SHAPE, **params))
    assert answer.get('ok'), answer
    return answer


def _with_pattern(root, pattern='^[0-9]+$'):
    """The value of hasStrength with a pattern, added from the tree."""
    _set_constraint(root, path=STRENGTH, parameter='sh:pattern', value=pattern, add=True,
                    layer='value')
    return (root / 'shacl.ttl').read_text()


def test_replacing_a_pattern_from_the_tree_changes_only_that_value(kms):
    before = _with_pattern(kms)
    done = _set_constraint(kms, path=STRENGTH, parameter='sh:pattern', value='^[a-z]+$',
                           add=True, layer='value')
    assert done['action'] == 'replaced'
    assert (kms / 'shacl.ttl').read_text() == before.replace('"^[0-9]+$"', '"^[a-z]+$"')
    assert _patterns(kms) == {Literal('^[a-z]+$')}


def test_editing_a_pattern_in_place_changes_only_that_value(kms):
    """The edit of a constraint the attribute already carries: the value as
    Turtle, written where the old one stands."""
    before = _with_pattern(kms)
    _set_constraint(kms, path=STRENGTH + ['ngsild:hasValue'], parameter='sh:pattern',
                    value='"^[a-z]+$"')
    assert (kms / 'shacl.ttl').read_text() == before.replace('"^[0-9]+$"', '"^[a-z]+$"')
    assert _patterns(kms) == {Literal('^[a-z]+$')}


def test_a_pattern_is_removed_from_the_tree_and_nothing_else(kms):
    original = Graph().parse(kms / 'shacl.ttl', format='turtle')
    _with_pattern(kms)
    _set_constraint(kms, path=STRENGTH + ['ngsild:hasValue'], parameter='sh:pattern',
                    remove=True)
    assert _patterns(kms) == set()
    assert isomorphic(Graph().parse(kms / 'shacl.ttl', format='turtle'), original)


def test_replacing_a_pattern_in_the_attribute_panel_changes_only_that_value(kms):
    """The panel writes the value's block anew: the graph differs from the one
    before in that one pattern, and nowhere else."""
    from semforge.editor import edits

    def set_pattern(value):
        answer = edits.edit_value_forms_feature(None, SimpleNamespace(
            uri=(kms / 'shacl.ttl').as_uri(), shape=FILTER_SHAPE, path=STRENGTH,
            action=SimpleNamespace(op='set', form=0, node=[0], parameter='sh:pattern',
                                   value=value, connective=None, kind=None,
                                   conditions=None)))
        assert answer.get('ok'), answer

    set_pattern('"^a"')
    expected = Graph().parse(kms / 'shacl.ttl', format='turtle')
    (holder,) = expected.subjects(SH.pattern, Literal('^a'))
    expected.set((holder, SH.pattern, Literal('^b')))
    set_pattern('"^b"')
    assert _patterns(kms) == {Literal('^b')}
    assert isomorphic(Graph().parse(kms / 'shacl.ttl', format='turtle'), expected)
