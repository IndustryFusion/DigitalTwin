"""Cooked mode: the tree, and invariants S1 and S2."""

import shutil

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic

from semforge.cooked import EDITABLE, RAW_ONLY, apply_edit, build_tree
from semforge.cooked.tree import flatten, remove_constraint, render
from semforge.errors import PackageError
from semforge.package import load

FILTER_SHAPE = ('https://industryfusion.github.io/contexts/example/v0/'
                'base_shacl/FilterShape')
STRENGTH = 'iffBaseEntities:hasStrength'


@pytest.fixture
def editable(tmp_path, corpus):
    package = tmp_path / 'pkg'
    package.mkdir()
    for role, name in (('knowledge', 'knowledge.ttl'), ('shapes', 'shacl.ttl'),
                       ('model', 'model-instance.jsonld')):
        shutil.copy(corpus.sources[role], package / name)
    return load(str(package))


# --- the tree ---------------------------------------------------------------

def test_the_tree_groups_shapes_under_entity_types(corpus):
    roots = build_tree(corpus)
    labels = {node.label for node in roots}
    assert {'Filter', 'Cutter', 'Machine', 'Workpiece'} <= labels
    assert all(node.kind == 'type' for node in roots)


def test_attributes_nest_and_carry_a_value_slot(corpus):
    nodes = {node.label: node for _, node in flatten(build_tree(corpus))}
    assert 'hasStrength' in nodes
    slots = [c for c in nodes['hasStrength'].children if c.kind == 'slot']
    assert len(slots) == 1 and slots[0].label == 'value'


def test_a_sub_attribute_of_a_relationship_appears_below_it(corpus):
    """hasFilter -> hasTrust is the usual NGSI-LD metadata pattern."""
    nodes = {node.label: node for _, node in flatten(build_tree(corpus))}
    children = {c.label for c in nodes['hasFilter'].children}
    assert 'hasTrust' in children


def test_core_parameters_are_editable_and_structure_is_not(corpus):
    for _, node in flatten(build_tree(corpus)):
        if node.kind == 'constraint' and not node.inherited_from:
            assert node.editable and node.parameter in EDITABLE
        if node.parameter in RAW_ONLY:
            assert not node.editable


def test_an_inherited_constraint_is_shown_but_not_edited_here(corpus):
    """It is declared on a supertype, and SHACL conjoins rather than replaces.

    Offering an in-place edit would imply a substitution that does not happen;
    the tree offers "declare it on this type" instead.
    """
    inherited = [n for _, n in flatten(build_tree(corpus))
                 if n.kind == 'constraint' and n.inherited_from]
    assert inherited
    assert all(not n.editable and n.defined_at for n in inherited)


def test_a_sparql_body_is_shown_but_not_offered_as_a_form(corpus):
    """S2: content the cooked view cannot project is marked, not hidden."""
    labels = [node.label for _, node in flatten(build_tree(corpus))]
    assert 'SPARQL constraint' in labels
    assert 'SPARQL rule' in labels
    for _, node in flatten(build_tree(corpus)):
        if node.label.startswith('SPARQL'):
            assert not node.editable
            assert 'edit in the .ttl' in node.detail


def test_a_connective_is_visible_and_raw_only(corpus):
    """sh:or is structure. Hiding it would make the tree lie about the shape."""
    found = [node for _, node in flatten(build_tree(corpus))
             if node.parameter == 'sh:or']
    assert found
    assert all(node.kind == 'raw' and not node.editable for node in found)


def test_every_editable_node_carries_a_complete_address(corpus):
    for _, node in flatten(build_tree(corpus)):
        if node.editable:
            address = node.address
            assert address['shape'] and address['path'] and address['parameter']


def test_render_produces_something_readable(corpus):
    lines = render(build_tree(corpus))
    assert len(lines) > 50
    assert any('hasStrength' in line for line in lines)


# --- S1: a cooked edit IS a raw edit ----------------------------------------

def test_s1_an_edit_changes_the_file_minimally(editable):
    before = open(editable.sources['shapes']).read()
    path, changed = apply_edit(editable, FILTER_SHAPE, [STRENGTH],
                               'sh:minCount', '0')
    after = open(path).read()

    assert changed == 1, 'changing 1 to 0 should rewrite one byte'
    assert len(after) == len(before)
    assert sum(1 for a, b in zip(before, after) if a != b) == 1


def test_s1_the_edit_is_the_one_intended(editable):
    apply_edit(editable, FILTER_SHAPE, [STRENGTH], 'sh:minCount', '0')
    reloaded = load(editable.path)
    tree = {node.label: node for _, node in flatten(build_tree(reloaded))}
    counts = {c.parameter: c.value for c in tree['hasStrength'].children
              if c.kind == 'constraint'}
    assert counts['sh:minCount'] == '0'
    assert counts['sh:maxCount'] == '1'


def test_s1_every_comment_survives_an_edit(editable):
    before = open(editable.sources['shapes']).read()
    apply_edit(editable, FILTER_SHAPE, [STRENGTH], 'sh:minCount', '0')
    after = open(editable.sources['shapes']).read()
    for line in before.splitlines():
        if line.strip().startswith('#'):
            assert line in after, 'a comment was lost'


def test_s1_the_rest_of_the_graph_is_untouched(editable, corpus):
    """Only the edited triple differs; everything else is isomorphic."""
    apply_edit(editable, FILTER_SHAPE, [STRENGTH], 'sh:minCount', '0')
    edited = Graph()
    edited.parse(editable.sources['shapes'], format='turtle')
    assert not isomorphic(edited, corpus.shapes)
    assert abs(len(edited) - len(corpus.shapes)) <= 1


def test_s1_an_edit_that_would_break_the_file_is_refused(editable):
    """The result is parsed before it is written."""
    with pytest.raises(Exception):
        apply_edit(editable, FILTER_SHAPE, [STRENGTH], 'sh:minCount', '] oops [')
    Graph().parse(editable.sources['shapes'], format='turtle')   # still valid


def test_s1_structure_cannot_be_edited_through_the_cooked_api(editable):
    with pytest.raises(PackageError) as exc:
        apply_edit(editable, FILTER_SHAPE, [STRENGTH], 'sh:or', 'anything')
    assert 'not editable in the cooked view' in str(exc.value)


def test_editing_a_value_slot_constraint(editable):
    apply_edit(editable, FILTER_SHAPE, [STRENGTH, 'ngsild:hasValue'],
               'sh:maxInclusive', '50.0')
    reloaded = load(editable.path)
    nodes = {node.label: node for _, node in flatten(build_tree(reloaded))}
    slot = [c for c in nodes['hasStrength'].children if c.kind == 'slot'][0]
    values = {c.parameter: c.value for c in slot.children}
    assert values['sh:maxInclusive'] == '50.0'


def test_removing_a_constraint(editable):
    _, removed = remove_constraint(editable, FILTER_SHAPE, [STRENGTH],
                                   'sh:minCount')
    assert removed > 0
    reloaded = load(editable.path)
    nodes = {node.label: node for _, node in flatten(build_tree(reloaded))}
    parameters = {c.parameter for c in nodes['hasStrength'].children}
    assert 'sh:minCount' not in parameters
    assert 'sh:maxCount' in parameters


def test_an_unknown_attribute_is_named_in_the_error(editable):
    with pytest.raises(PackageError) as exc:
        apply_edit(editable, FILTER_SHAPE, ['iffBaseEntities:nope'],
                   'sh:minCount', '0')
    assert 'nope' in str(exc.value)


def test_the_edit_changes_the_verdict(editable):
    """Cooked and raw are one state, so an edit moves validation.

    urn:filter:1 resolves to hasStrength 0.6 under the current view. Tightening
    the upper bound to 0.5 must make it fail -- which is the end-to-end proof
    that a tree edit reaches the engine.
    """
    from semforge.validate import validate_package

    before = validate_package(load(editable.path))
    assert not [r for r in before.violations if r.attribute == 'hasStrength']

    apply_edit(editable, FILTER_SHAPE, [STRENGTH, 'ngsild:hasValue'],
               'sh:maxInclusive', '0.5')

    after = validate_package(load(editable.path))
    fired = [r for r in after.violations if r.attribute == 'hasStrength']
    assert fired, 'tightening the bound below the value should raise a violation'
    assert any('MaxInclusive' in r.component for r in fired)
