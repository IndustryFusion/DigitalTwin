"""Adding constraints an attribute does not carry yet.

"Edit a constraint" could only change what was already there, so a range,
an exclusive bound, a length or a pattern could never be added from the
editor. `add_constraint` adds any of them -- on the value, or a count on the
attribute -- creating the value layer when the attribute has none, writing
one parameter per line, and saying when bounds now admit nothing.
"""

import shutil

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import SH, XSD

from semforge.cooked.tree import add_constraint
from semforge.cooked.typepage import build_type_page, value_text
from semforge.errors import PackageError
from semforge.package import load

BASE_SHACL = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
FILTER = 'https://industryfusion.github.io/contexts/example/v0/base_entities/Filter'
STRENGTH = ['iffBaseEntities:hasStrength']


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _strength(root):
    return next(r for r in build_type_page(load(root), FILTER)['attributes']
                if r['label'] == 'hasStrength')


def test_an_exclusive_bound_is_added_on_its_own_line(kms):
    done = add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH,
                          'sh:maxExclusive', '90')
    assert done['action'] == 'added' and not done['note']
    with open(f'{kms}/shacl.ttl') as handle:
        text = handle.read()
    line = next(found for found in text.splitlines() if 'sh:maxExclusive' in found)
    assert line.strip() == 'sh:maxExclusive 90 ] ] ,' or line.strip().startswith(
        'sh:maxExclusive 90'), line
    assert '< 90' in _strength(kms)['value']


def test_an_existing_parameter_is_replaced_not_doubled(kms):
    def bounds():
        graph = Graph().parse(f'{kms}/shacl.ttl', format='turtle')
        return sorted(str(o) for o in graph.objects(None, SH.maxInclusive))

    before = bounds()
    done = add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH,
                          'sh:maxInclusive', '80')
    assert done['action'] == 'replaced'
    after = bounds()
    # hasStrength's 100.0 became 80; hasWidth keeps its own 100.0.
    expected = list(before)
    expected.remove('100.0')
    assert after == sorted(expected + ['80'])
    assert '0 – 80' in _strength(kms)['value']


def test_bounds_that_admit_nothing_are_said(kms):
    done = add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH,
                          'sh:minExclusive', '100')
    assert 'admit no value' in done['note']


def test_a_count_may_go_on_the_attribute_but_a_datatype_may_not(kms):
    add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH, 'sh:maxCount', '2',
                   layer='attribute')
    with pytest.raises(PackageError, match='goes on the value'):
        add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH, 'sh:datatype',
                       'xsd:double', layer='attribute')


@pytest.mark.parametrize('parameter, value, said', [
    ('sh:minLength', '-1', 'whole number'),
    ('sh:minInclusive', 'ten', 'a number'),
    ('sh:datatype', 'nope:thing', 'not declared'),
    ('sh:or', '( )', 'not a constraint the editor writes'),
])
def test_values_shacl_would_reject_are_refused(kms, parameter, value, said):
    with pytest.raises(PackageError, match=said):
        add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH, parameter, value)


def test_a_missing_value_layer_is_created(tmp_path):
    """PointedAtShape's hasPosition says only minCount: no value layer."""
    from conftest import TARGETS

    root = tmp_path / 'targets'
    shutil.copytree(TARGETS, root, ignore=shutil.ignore_patterns('.semforge'))
    shape = 'https://example.org/targets/PointedAtShape'
    add_constraint(load(str(root)), shape, ['ex:hasPosition'], 'sh:datatype', 'xsd:string')
    graph = Graph().parse(str(root / 'shacl.ttl'), format='turtle')
    attribute = next(graph.objects(URIRef(shape), SH.property))
    value = next(graph.objects(attribute, SH.property))
    assert (value, SH.path, URIRef('https://uri.etsi.org/ngsi-ld/hasValue')) in graph
    assert (value, SH.datatype, XSD.string) in graph


def test_a_pattern_is_written_as_a_string(kms):
    add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH, 'sh:pattern', '^[0-9]+$')
    graph = Graph().parse(f'{kms}/shacl.ttl', format='turtle')
    assert Literal('^[0-9]+$') in set(graph.objects(None, SH.pattern))


@pytest.mark.parametrize('parameters, said', [
    ({'sh:minExclusive': '0'}, '> 0'),
    ({'sh:minExclusive': '0', 'sh:maxInclusive': '10'}, '> 0 and ≤ 10'),
    ({'sh:minInclusive': '0', 'sh:maxInclusive': '10'}, '0 – 10'),
    ({'sh:datatype': 'xsd:string', 'sh:maxLength': '20'}, 'text · at most 20 characters'),
    ({'sh:minLength': '2', 'sh:maxLength': '8'}, '2 – 8 characters'),
    ({'sh:pattern': '"^[A-Z]+$"'}, 'matching ^[A-Z]+$'),
])
def test_the_value_says_the_new_constraints_in_words(parameters, said):
    assert said in value_text('Property', parameters, [])


# --- sh:in: the value is one of a list -------------------------------------------------

WC = 'https://industryfusion.github.io/contexts/example/v0/filter_knowledge/'
CARTRIDGE = 'https://industryfusion.github.io/contexts/example/v0/base_entities/FilterCartridge'
WASTE = ['iffFilterEntities:hasWasteclass']


def _waste(root):
    rows = build_type_page(load(root), CARTRIDGE)['attributes']
    return next(r for r in rows if r['label'] == 'hasWasteclass')


def _in_values(root):
    graph = Graph().parse(f'{root}/shacl.ttl', format='turtle')
    return [[str(i) for i in graph.items(head)] for head in graph.objects(None, SH['in'])]


def test_a_vocabulary_list_is_written_and_read_back(kms):
    """hasWasteclass draws from Wasteclass; restrict it to two of its values,
    written with the knowledge's own prefix."""
    shape = 'https://industryfusion.github.io/contexts/example/v0/filter_shacl/CartridgeShape'
    done = add_constraint(load(kms), shape, WASTE, 'sh:in',
                          ['iffFilterKnowledge:WC1', 'iffFilterKnowledge:WC2'])
    assert done['action'] == 'added'
    assert [WC + 'WC1', WC + 'WC2'] in _in_values(kms)
    row = _waste(kms)
    assert row['inList']['items'] == ['iffFilterKnowledge:WC1', 'iffFilterKnowledge:WC2']
    assert 'one of: WC1 · WC2' in row['value']
    assert 'Constraints' in row['valueLocked']


def test_editing_a_list_replaces_it(kms):
    shape = 'https://industryfusion.github.io/contexts/example/v0/filter_shacl/CartridgeShape'
    add_constraint(load(kms), shape, WASTE, 'sh:in', ['iffFilterKnowledge:WC1'])
    before = len(_in_values(kms))
    done = add_constraint(load(kms), shape, WASTE, 'sh:in',
                          ['iffFilterKnowledge:WC1', 'iffFilterKnowledge:WC3'])
    assert done['action'] == 'replaced' and len(_in_values(kms)) == before
    assert [WC + 'WC1', WC + 'WC3'] in _in_values(kms)


def test_a_typed_list_keeps_numbers_numbers_and_quotes_text(kms):
    add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH, 'sh:in', '10, 20.5, "high"')
    lists = _in_values(kms)
    assert ['10', '20.5', 'high'] in lists


@pytest.mark.parametrize('value, said', [
    ([], 'admits no value'),
    ('   ', 'admits no value'),
    (['nope:x'], 'not declared'),
])
def test_a_list_shacl_cannot_use_is_refused(kms, value, said):
    with pytest.raises(PackageError, match=said):
        add_constraint(load(kms), BASE_SHACL + 'FilterShape', STRENGTH, 'sh:in', value)


def test_a_list_is_removed_like_any_constraint(kms):
    from semforge.cooked.tree import remove_constraint

    shape = 'https://industryfusion.github.io/contexts/example/v0/filter_shacl/CartridgeShape'
    add_constraint(load(kms), shape, WASTE, 'sh:in', ['iffFilterKnowledge:WC1'])
    row = _waste(kms)
    remove_constraint(load(kms), shape, row['inList']['path'], 'sh:in')
    assert _waste(kms)['inList'] is None
