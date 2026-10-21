"""The link from a datum to the shape that judges it, and back."""

import shutil

import pytest

from semforge.cooked.examples import build_examples, flatten
from semforge.cooked.shapelink import (ensure_property_shape,
                                       find_property_shape, value_choices)
from semforge.errors import PackageError
from semforge.package import load
from semforge.validate import validate_package


@pytest.fixture
def package(tmp_path, corpus):
    target = tmp_path / 'pkg'
    target.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], target / name)
    for extra in ('context.jsonld', 'semforge.yaml'):
        shutil.copy(f'{corpus.path}/{extra}', target / extra)
    return load(str(target))


def _line(path, number):
    with open(path, encoding='utf-8') as handle:
        return handle.read().splitlines()[number - 1]


# --- finding ------------------------------------------------------------------

def test_the_declaring_shape_is_found_and_the_line_is_the_property(corpus):
    found = find_property_shape(corpus, 'iffBaseEntities:Filter',
                                'hasStrength')
    assert found['shapeName'] == 'iffBaseShacl:FilterShape'
    assert not found['inherited']
    assert 'sh:property' in _line(found['file'], found['line'])


def test_an_inherited_constraint_is_found_where_it_is_declared(corpus):
    """hasState on a Filter is MachineShape's business.

    Landing nowhere for every inherited attribute would make the jump useless
    on exactly the attributes whose home is hardest to guess.
    """
    found = find_property_shape(corpus, 'iffBaseEntities:Filter', 'hasState')
    assert found['shapeName'] == 'iffBaseShacl:MachineShape'
    assert found['inherited']


def test_a_shape_on_the_type_itself_beats_one_it_inherits(corpus):
    found = find_property_shape(corpus, 'iffBaseEntities:Filter',
                                'hasCartridge')
    assert found['shapeName'] == 'iffBaseShacl:FilterShape'
    assert not found['inherited']


def test_the_slot_is_reported_so_a_relationship_is_distinguishable(corpus):
    assert find_property_shape(corpus, 'iffBaseEntities:Filter',
                               'hasCartridge')['slot'] == 'ngsild:hasObject'
    assert find_property_shape(corpus, 'iffBaseEntities:Filter',
                               'hasStrength')['slot'] == 'ngsild:hasValue'


def test_an_unconstrained_attribute_is_reported_as_absent(corpus):
    assert find_property_shape(corpus, 'iffBaseEntities:Filter',
                               'hasNothingAtAll') is None


def test_a_prefixed_or_long_attribute_name_finds_the_same_shape(corpus):
    plain = find_property_shape(corpus, 'iffBaseEntities:Filter', 'hasStrength')
    for spelling in ('iffBaseEntities:hasStrength',
                     'https://example.com/x/hasStrength'):
        assert find_property_shape(corpus, 'iffBaseEntities:Filter',
                                   spelling)['line'] == plain['line']


# --- creating -----------------------------------------------------------------

def test_an_absent_shape_is_created_empty_and_can_then_be_found(package):
    found, how = ensure_property_shape(package, 'iffBaseEntities:Filter',
                                       'iffBaseEntities:hasNewThing')
    assert how == 'created'
    assert found['shapeName'] == 'iffBaseShacl:FilterShape'
    text = open(package.sources['shapes'], encoding='utf-8').read()
    assert 'hasNewThing' in text

    # Found again from a fresh load, at the line that was reported.
    again = load(package.path)
    assert find_property_shape(again, 'iffBaseEntities:Filter',
                               'hasNewThing')['line'] == found['line']
    assert 'hasNewThing' in _line(found['file'], found['line'])


def test_the_created_shape_is_empty_on_purpose_and_still_parses(package):
    ensure_property_shape(package, 'iffBaseEntities:Filter',
                          'iffBaseEntities:hasNewThing')
    fresh = load(package.path)          # parses, or load raises
    report = validate_package(fresh)
    assert report is not None


def test_an_existing_inherited_shape_is_not_copied_down(package):
    """The jump shows you the rule; it does not fork it.

    Writing a local hasState into FilterShape here would be an override, and an
    override is a decision with its own command.
    """
    before = open(package.sources['shapes'], encoding='utf-8').read()
    found, how = ensure_property_shape(package, 'iffBaseEntities:Filter',
                                       'hasState')
    assert how == 'found'
    assert found['inherited']
    assert open(package.sources['shapes'], encoding='utf-8').read() == before


def test_creating_against_a_type_with_no_shape_refuses(package):
    with pytest.raises(PackageError) as raised:
        ensure_property_shape(package, 'iffBaseEntities:NoSuchType', 'hasX')
    assert 'no shape targets' in str(raised.value)


# --- what a value may be ------------------------------------------------------

def test_a_class_constrained_value_offers_the_individuals(corpus):
    options, note = value_choices(corpus, 'iffBaseEntities:Filter', 'hasState')
    labels = [o['label'] for o in options]
    assert 'state_ON' in labels and 'state_OFF' in labels
    assert note == ''
    # Offered in the form the file wants: a Property whose value is an IRI.
    picked = next(o for o in options if o['label'] == 'state_ON')
    assert picked['value'].startswith('{"@id": "')


def test_a_relationship_offers_entities_not_classes(corpus):
    options, _ = value_choices(corpus, 'iffBaseEntities:Filter',
                               'hasCartridge')
    assert [o['label'] for o in options] == ['urn:cartridge:1',
                                             'urn:cartridge:2']


def test_an_unconstrained_value_offers_nothing_and_says_why(corpus):
    options, note = value_choices(corpus, 'iffBaseEntities:Filter',
                                  'hasStrength')
    assert options == []
    assert 'no sh:class' in note

    options, note = value_choices(corpus, 'iffBaseEntities:Filter', 'hasNope')
    assert options == [] and 'no shape constrains' in note


def test_the_options_can_be_searched_and_capped(corpus):
    found, _ = value_choices(corpus, 'iffBaseEntities:Filter', 'hasState',
                             search='clean')
    assert [o['label'] for o in found] == ['state_CLEANING']

    capped, note = value_choices(corpus, 'iffBaseEntities:Filter', 'hasState',
                                 limit=2)
    assert len(capped) == 2
    assert 'showing 2 of' in note


# --- the tree carries what the jump needs ------------------------------------

def test_every_attribute_row_knows_its_entity_type(corpus):
    """Without this the icon has nothing to look the shape up with."""
    report = validate_package(corpus)
    rows = [n for _, n in flatten(build_examples(corpus, report))
            if n.kind in ('attribute', 'dataset', 'instance')]
    assert rows
    assert all(n.entity_type for n in rows), \
        [n.label for n in rows if not n.entity_type]

    state = next(n for _, n in flatten(build_examples(corpus))
                 if n.label.endswith('hasState') and n.entity == 'urn:filter:1')
    assert state.entity_type == 'iffBaseEntities:Filter'
    assert find_property_shape(corpus, state.entity_type,
                               state.path[0])['inherited']
