"""An entity's type comes from the knowledge, and nowhere else.

Typing a type by hand is the quietest way to break a model: nothing rejects an
undeclared class, no shape targets it, so every constraint stays silent and the
entity reads as validated. The editor therefore offers what the ontology
declares -- and a type that is genuinely missing is declared FIRST.
"""

import shutil

import pytest

from semforge.cooked.choices import entity_types, model_term
from semforge.cooked.examples import add_entity
from semforge.cooked.knowledge import add_entity_type
from semforge.errors import PackageError
from semforge.package import load


@pytest.fixture
def package(tmp_path, corpus_path):
    copy = tmp_path / 'pkg'
    shutil.copytree(corpus_path, copy)
    return load(str(copy))


def test_the_types_are_the_entity_hierarchy(package):
    found, root = entity_types(package)
    assert root.endswith('base_entities/Entity')
    terms = {entry.term for entry in found}
    assert 'iffBaseEntities:Filter' in terms
    assert 'iffBaseEntities:Plasmacutter' in terms
    # A vocabulary class is not a type an entity may have: `MachineState` is
    # the VALUE of a property, not the thing carrying it.
    assert not any('MachineState' in term for term in terms)


def test_a_type_is_named_the_way_the_model_names_it(package):
    """The .jsonld resolves names through its @context, not the shapes file."""
    found, _ = entity_types(package)
    filter_type = next(e for e in found if e.label == 'Filter')
    assert filter_type.term == 'iffBaseEntities:Filter'
    # And it is what the shipped model already writes.
    assert any(entity.get('type') == filter_type.term
               for entity in _entities(package))


def _entities(package):
    import json
    with open(package.sources['model'], encoding='utf-8') as handle:
        document = json.load(handle)
    return document if isinstance(document, list) else [document]


def test_each_type_says_what_will_judge_it(package):
    found, _ = entity_types(package)
    by_label = {entry.label: entry for entry in found}
    # sh:targetClass traverses rdfs:subClassOf*, so an inherited shape counts.
    assert by_label['Filter'].shape.endswith('FilterShape')
    assert by_label['Consumable'].shape == ''
    assert by_label['Filter'].instances >= 1


def test_the_nearest_shape_is_named_and_it_does_not_flicker(package):
    """A Plasmacutter is judged by CutterShape AND MachineShape.

    Naming whichever a set happened to yield made the row change between two
    reads of the same package.
    """
    answers = {entity_types(load(package.path))[0][0].shape for _ in range(5)}
    seen = [next(e for e in entity_types(package)[0] if e.label == 'Plasmacutter')
            for _ in range(5)]
    assert len({entry.shape for entry in seen}) == 1, seen
    assert seen[0].shape.endswith('CutterShape'), seen[0].shape
    assert len(answers) == 1


def test_the_root_is_marked_as_the_root(package):
    found, _ = entity_types(package)
    roots = [entry for entry in found if entry.is_root]
    assert [entry.label for entry in roots] == ['Entity']
    assert roots[0].parent == ''


def test_a_namespace_with_no_agreed_name_keeps_its_iri(package):
    assert model_term(package, 'https://nowhere.example/Thing') == \
        'https://nowhere.example/Thing'


# --- adding what is missing --------------------------------------------------

def test_a_new_type_lands_beside_its_parent(package):
    made = add_entity_type(package, 'Waterjetcutter', 'iffBaseEntities:Cutter')
    assert made['term'] == 'iffBaseEntities:Waterjetcutter'
    assert made['file'] == package.index('knowledge').file_for(
        'https://industryfusion.github.io/contexts/example/v0/base_entities/Cutter')

    again = load(package.path)
    found, _ = entity_types(again)
    added = next(e for e in found if e.label == 'Waterjetcutter')
    assert added.parent == 'iffBaseEntities:Cutter'
    # It inherits what judges a Cutter, which is the point of putting it there.
    assert added.shape.endswith('CutterShape')


def test_a_new_type_is_refused_under_something_that_is_not_a_type(package):
    with pytest.raises(PackageError) as raised:
        add_entity_type(package, 'Thing', 'iffBaseKnowledge:MachineState')
    assert 'not an entity type' in str(raised.value)


def test_a_duplicate_type_is_refused(package):
    with pytest.raises(PackageError) as raised:
        add_entity_type(package, 'Filter', 'iffBaseEntities:Machine')
    assert 'already declared' in str(raised.value)


def test_a_name_that_is_not_a_class_name_is_refused(package):
    with pytest.raises(PackageError) as raised:
        add_entity_type(package, 'a filter!', 'iffBaseEntities:Machine')
    assert 'class name' in str(raised.value)


# --- and the rule is the package's, not the editor's -------------------------

def test_an_undeclared_type_cannot_be_written_into_the_model(package):
    """The check lives in the SDK, so no client can route around it."""
    with pytest.raises(PackageError) as raised:
        add_entity(package, 'urn:thing:1', 'iffBaseEntities:Waterjetcutter')
    assert 'not an entity type' in str(raised.value)
    assert 'knowledge first' in str(raised.value)


def test_declaring_it_first_makes_it_usable(package):
    add_entity_type(package, 'Waterjetcutter', 'iffBaseEntities:Cutter')
    again = load(package.path)
    path, count = add_entity(again, 'urn:waterjetcutter:1',
                             'iffBaseEntities:Waterjetcutter')
    assert count > 1
    assert 'iffBaseEntities:Waterjetcutter' in open(path, encoding='utf-8').read()


def test_a_prefixed_entity_root_is_expanded(tmp_path):
    """`semforge init` writes `entityRoot: testEntities:Entity`.

    Taking that literally made URIRef('testEntities:Entity'), which matches
    nothing in the knowledge -- so every scaffolded package reported a
    hierarchy of exactly one class, the root, with no descendants below it.
    Silently, because a hierarchy of one is a legal answer.
    """
    from semforge.package.scaffold import create_package

    target = tmp_path / 'fresh'
    target.mkdir()
    create_package(str(target), name='fresh',
                   namespace='https://example.org/fresh/')

    found, root = entity_types(load(str(target)))
    assert root == 'https://example.org/fresh/entities/Entity'
    labels = {entry.label for entry in found}
    assert 'Machine' in labels, labels
    machine = next(entry for entry in found if entry.label == 'Machine')
    assert machine.shape.endswith('MachineShape')
    assert machine.instances == 1


def test_a_brand_new_subtype_inherits_attributes_and_their_value_choices(tmp_path):
    """The whole chain, for the case that exposed the gap.

    Declare a subtype, and everything its parent has must reach it: the
    attributes it may carry (rdfs:domain is inherited), the shape that judges
    them (sh:targetClass traverses rdfs:subClassOf*), and the values that shape
    allows (the individuals of its sh:class).
    """
    from semforge.cooked.choices import attributes_for
    from semforge.cooked.knowledge import add_entity_type
    from semforge.cooked.shapelink import find_property_shape, value_choices
    from semforge.package.scaffold import create_package

    target = tmp_path / 'fresh'
    target.mkdir()
    create_package(str(target), name='fresh',
                   namespace='https://example.org/fresh/')

    package = load(str(target))
    add_entity_type(package, 'Lathe', 'freshEntities:Machine')
    package = load(str(target))

    attribute = 'freshEntities:hasState'
    assert attribute in {entry.term for entry in
                         attributes_for(package, 'freshEntities:Lathe')[0]}

    found = find_property_shape(package, 'freshEntities:Lathe', attribute)
    assert found and found['inherited']

    choices, _ = value_choices(package, 'freshEntities:Lathe', attribute)
    assert {choice['label'] for choice in choices} == {'state_ON', 'state_OFF'}
