"""sh:in lists against the rest of what the value must be.

sh:in compares RDF terms exactly. An item the value's datatype, node kind,
class, bounds, lengths or pattern forbid can never be given; and a number
written `20.5` in Turtle is an xsd:decimal that never equals the xsd:double a
JSON 20.5 becomes. Both are said; the writer types numbers so its own lists
match real data.
"""

import shutil

import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import XSD

from semforge.cooked.listcheck import item_term, list_conflicts
from semforge.cooked.tree import add_constraint
from semforge.cooked.typepage import build_type_page
from semforge.package import load
from semforge.validate import validate_package

BASE_SHACL = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
FILTER = 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter'
STRENGTH = ['iffBaseEntities:hasStrength']
WC = 'https://industryfusion.github.io/contexts/example/v0/filter_knowledge/'


@pytest.mark.parametrize('token, term', [
    ('20.5', Literal('20.5', datatype=XSD.decimal)),
    ('21', Literal('21', datatype=XSD.integer)),
    ('2e1', Literal('2e1', datatype=XSD.double)),
    ('"20.5"^^xsd:double', Literal('20.5', datatype=XSD.double)),
    ('"warm"', Literal('warm')),
    ('true', Literal('true', datatype=XSD.boolean)),
    ('iffFilterKnowledge:WC1', URIRef(WC + 'WC1')),
])
def test_an_item_is_read_as_the_term_it_is(corpus, token, term):
    assert item_term(corpus, token) == term


@pytest.mark.parametrize('params, items, said', [
    ({'sh:datatype': 'xsd:double'}, ['"warm"'], 'xsd:string, but the value must be xsd:double'),
    ({'sh:datatype': 'xsd:double'}, ['21'], 'xsd:integer, but the value must be xsd:double'),
    ({'sh:datatype': 'xsd:string'}, ['iffFilterKnowledge:WC1'], 'is an IRI'),
    ({'sh:nodeKind': 'sh:IRI'}, ['"x"'], 'must be an IRI'),
    ({'sh:nodeKind': 'sh:Literal'}, ['iffFilterKnowledge:WC1'], 'must be a literal'),
    ({'sh:class': 'iffFilterKnowledge:Wasteclass'}, ['iffFilterKnowledge:WC9'],
     'WC9 is not a Wasteclass'),
    ({'sh:maxInclusive': '100'}, ['"150"^^xsd:double'], '150 is outside ≤ 100'),
    ({'sh:minExclusive': '0'}, ['"0"^^xsd:double'], '0 is outside > 0'),
    ({'sh:maxLength': '3'}, ['"long"'], 'longer than 3'),
    ({'sh:pattern': '"^[A-Z]+$"'}, ['"low"'], 'does not match'),
    ({}, ['20.5'], 'never equals it'),
])
def test_a_contradiction_is_said(corpus, params, items, said):
    notes = list_conflicts(corpus, params, items)
    assert any(said in note for note in notes), notes


def test_a_list_that_agrees_says_nothing(corpus):
    assert list_conflicts(corpus, {'sh:class': 'iffFilterKnowledge:Wasteclass'},
                          ['iffFilterKnowledge:WC1', 'iffFilterKnowledge:WC2']) == []
    assert list_conflicts(corpus, {'sh:datatype': 'xsd:double', 'sh:maxInclusive': '100'},
                          ['"20.5"^^xsd:double']) == []


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def test_a_written_list_matches_the_numbers_real_data_carries(kms):
    """The model's filters say hasStrength 0.6 and 0.9 (JSON numbers, so
    xsd:double). A list written `0.6, 0.9` must accept both -- which an
    untyped `( 0.6 0.9 )`, all xsd:decimal, never does."""
    add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH, 'sh:in', '0.6, 0.9')
    with open(f'{kms}/shacl.ttl') as handle:
        assert '"0.6"^^xsd:double' in handle.read()
    found = [v for v in validate_package(load(kms), strict=False).violations
             if v.component.startswith('In')]
    assert found == []


def test_a_contradicting_write_says_so_and_the_page_too(kms):
    done = add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH, 'sh:in',
                          '0.6, 150, "high"')
    assert '150 is outside ≤ 100' in done['note']
    row = next(r for r in build_type_page(load(kms), FILTER)['attributes']
               if r['label'] == 'hasStrength')
    assert any('150 is outside' in n for n in row['notes'])
    assert 'one of: 0.6 · 150 · high' in row['value'], 'typed items read as written'


def test_lists_in_two_shapes_with_nothing_in_common_admit_nothing(corpus):
    from semforge.cooked.accumulate import accumulate

    def row(shape, items):
        return {'label': 'hasState', 'kind': 'Property', 'path': ['x:hasState'],
                'shapeName': shape, 'shape': shape, 'parameters': [], 'presence': '',
                'value': '', 'verbatim': [], 'violations': [], 'tested': 'untested',
                'inherited': False, 'inList': {'items': items, 'path': [], 'value': ''}}
    [merged] = accumulate([row('A', ['"on"']), row('B', ['"off"'])], corpus)
    assert any('share no value' in note for note in merged['notes'])
