"""Vocabulary classes: the page, and the writes that manage them.

MachineState and Wasteclass are closed value lists. A value is used in the
data, in SPARQL queries, in the shapes and in the knowledge itself, and the
page says where; the writes add a class or a value, change a label and delete
a value -- refusing while it is used unless told otherwise.
"""

import shutil

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDFS

from semforge.cooked.vocabulary import (add_value, add_vocabulary_class,
                                        build_vocabulary_page, remove_value,
                                        set_value_label, vocabulary_classes)
from semforge.errors import PackageError
from semforge.package import load

BASE = 'https://industryfusion.github.io/contexts/example/v0/base_knowledge/'
FILTER_KNOWLEDGE = 'https://industryfusion.github.io/contexts/example/v0/filter_knowledge/'


@pytest.fixture(scope='module')
def machine_state(corpus):
    return build_vocabulary_page(corpus, 'base:MachineState')


def _row(page, name):
    return next(r for r in page['values'] if r['name'] == name)


# --- the page -------------------------------------------------------------------------

def test_the_vocabularies_are_the_classes_that_are_not_entity_types(corpus):
    classes = vocabulary_classes(corpus)
    assert BASE + 'MachineState' in classes
    assert not any(c.endswith('/Filter') for c in classes)


def test_every_value_with_its_label_and_properties(machine_state):
    assert [r['name'] for r in machine_state['values']] == [
        'state_CLEANING', 'state_CLEARING', 'state_ERROR', 'state_OFF', 'state_ON',
        'state_PREPARING', 'state_PROCESSING']
    on = _row(machine_state, 'state_ON')
    assert on['label'] == 'ON'
    assert on['properties'] == [{
        'property': 'base:isValidFor', 'value': 'iffBaseEntities:Machine',
        'name': 'valid for', 'shortValue': 'Machine', 'link': '',
        'type': 'https://industryfusion.github.io/contexts/example/v0/base_entities/Machine'}]


def test_a_property_is_said_in_words():
    from semforge.cooked.vocabulary import _spoken
    assert _spoken('isValidFor') == 'valid for'
    assert _spoken('hasUnit') == 'unit'
    assert _spoken('color') == 'color'
    assert _spoken('is') == 'is'


def test_a_value_says_where_it_is_used(machine_state):
    on = _row(machine_state, 'state_ON')['uses']
    assert on['data'] == 7 and on['queries'] == 6
    owners = {p['owner'] for p in on['places'] if p['kind'] == 'queries'}
    assert 'iffBaseShacl:StateOnFilterShape' in owners
    assert machine_state['summary']['unused'] == 4
    assert _row(machine_state, 'state_ERROR')['uses']['total'] == 0


def test_the_page_names_the_constraint_drawing_from_it(machine_state):
    assert machine_state['constrainedBy'] == [{
        'shape': 'https://industryfusion.github.io/contexts/example/v0/base_shacl/MachineShape',
        'shapeName': 'iffBaseShacl:MachineShape', 'attribute': 'hasState',
        'how': 'sh:class'}]


def test_a_value_used_only_inside_the_knowledge_is_used(corpus):
    """WC2 appears in no data, but WC3 is a higherHazardLevel of it."""
    page = build_vocabulary_page(corpus, FILTER_KNOWLEDGE + 'Wasteclass')
    wc2 = _row(page, 'WC2')
    assert wc2['uses']['data'] == 0 and wc2['uses']['knowledge'] >= 1
    assert page['summary']['unused'] == 0
    assert {r['name'] for r in page['relations']} >= {
        'iffFilterKnowledge:higherHazardLevel'}


def test_an_entity_type_has_no_vocabulary_page(corpus):
    with pytest.raises(PackageError, match='not a vocabulary class'):
        build_vocabulary_page(corpus, 'iffBaseEntities:Filter')


# --- the writes ------------------------------------------------------------------------

@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


def _graph(root):
    return Graph().parse(f'{root}/knowledge.ttl', format='turtle')


def _text(root):
    with open(f'{root}/knowledge.ttl') as handle:
        return handle.read()


def test_a_value_is_added_in_the_class_namespace_and_file(kms):
    before = _text(kms)
    made = add_value(load(kms), 'base:MachineState', 'state_IDLE', 'IDLE')
    assert made['iri'] == BASE + 'state_IDLE'
    after = _text(kms)
    assert after.startswith(before), 'appended, the rest of the file untouched'
    graph = _graph(kms)
    value = URIRef(BASE + 'state_IDLE')
    assert (value, RDFS.label, None) in graph
    assert URIRef(BASE + 'MachineState') in set(graph.objects(value, None))
    page = build_vocabulary_page(load(kms), 'base:MachineState')
    assert 'state_IDLE' in [r['name'] for r in page['values']]


def test_adding_then_deleting_an_unused_value_restores_the_file(kms):
    before = _text(kms)
    add_value(load(kms), 'base:MachineState', 'state_IDLE')
    remove_value(load(kms), BASE + 'state_IDLE')
    assert _text(kms) == before


@pytest.mark.parametrize('name, said', [('state_ON', 'already declared'),
                                        ('1bad', 'not a usable name'),
                                        ('', 'not a usable name')])
def test_a_value_name_is_checked(kms, name, said):
    with pytest.raises(PackageError, match=said):
        add_value(load(kms), 'base:MachineState', name)


def test_a_label_is_changed_added_and_removed_in_place(kms):
    value = BASE + 'state_ON'
    set_value_label(load(kms), value, 'Running')
    assert [str(o) for o in _graph(kms).objects(URIRef(value), RDFS.label)] == ['Running']
    set_value_label(load(kms), value, '')
    assert not list(_graph(kms).objects(URIRef(value), RDFS.label))
    set_value_label(load(kms), value, 'ON')
    assert [str(o) for o in _graph(kms).objects(URIRef(value), RDFS.label)] == ['ON']
    # The rest of the statement is still there.
    assert (URIRef(value), URIRef(BASE + 'isValidFor'), None) in _graph(kms)


def test_a_used_value_is_not_deleted_without_saying_so(kms):
    with pytest.raises(PackageError, match='used in 13 place'):
        remove_value(load(kms), BASE + 'state_ON')
    assert (URIRef(BASE + 'state_ON'), None, None) in _graph(kms)
    done = remove_value(load(kms), BASE + 'state_ON', force=True)
    assert done['left'] == 13
    assert (URIRef(BASE + 'state_ON'), None, None) not in _graph(kms)


def test_a_new_vocabulary_class_lands_where_its_parent_is(kms):
    made = add_vocabulary_class(load(kms), 'Hazard', parent='base:MachineState',
                                label='Hazard level')
    assert made['iri'] == BASE + 'Hazard'
    graph = _graph(kms)
    assert (URIRef(BASE + 'Hazard'), RDFS.subClassOf, URIRef(BASE + 'MachineState')) in graph
    assert BASE + 'Hazard' in vocabulary_classes(load(kms))
    add_value(load(kms), BASE + 'Hazard', 'LOW')
    assert [r['name'] for r in build_vocabulary_page(load(kms), 'base:Hazard')['values']] \
        == ['LOW']


def test_a_new_class_without_a_parent_takes_the_usual_namespace(kms):
    made = add_vocabulary_class(load(kms), 'Shift')
    assert made['iri'].endswith('/Shift')
    with pytest.raises(PackageError, match='already declared'):
        add_vocabulary_class(load(kms), 'Shift')
