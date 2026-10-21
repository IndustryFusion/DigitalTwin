"""Inherited constraints in the cooked view, and what an "override" really is."""

import json
import shutil

import pytest
from rdflib import Graph

from semforge.cooked.tree import (build_tree, flatten, override_constraint,
                                  override_effect)
from semforge.package import load
from semforge.validate.orchestrator import validate_graphs

SHACL = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
ENTITIES = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'


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


def _type_node(package, label):
    return next(n for _, n in flatten(build_tree(package))
                if n.kind == 'type' and n.label == label)


# --- the fact the design rests on -------------------------------------------

def test_a_shape_on_a_supertype_already_validates_the_subtype(corpus):
    """sh:targetClass goes through the subclass closure.

    MachineShape's hasState is evaluated against urn:filter:1 today. The
    constraint was never missing from Filter -- only from the tree.
    """
    from semforge.validate import validate_package

    report = validate_package(corpus)
    found = [r for r in report.results
             if r.resource == 'urn:filter:1' and r.attribute == 'hasState']
    assert found
    assert all(r.shape == SHACL + 'MachineShape' for r in found)


def test_shacl_conjoins_so_a_subtype_cannot_relax_an_inherited_constraint(package):
    """The reason "override" is the wrong word, proven rather than asserted.

    Adding `hasState minCount 0` to FilterShape leaves MachineShape's
    `minCount 1` firing exactly as before: the two are evaluated together, not
    one instead of the other.
    """
    model = [{'@context': ('https://industryfusion.github.io/contexts/staging/'
                           'example/v0.2/context.jsonld'),
              'id': 'urn:filter:99', 'type': 'iffBaseEntities:Filter',
              'iffBaseEntities:hasStrength': {'type': 'Property', 'value': 0.6},
              'iffBaseEntities:hasCartridge': {'type': 'Relationship',
                                               'object': 'urn:cartridge:1'}}]
    with open(package.sources['model'], 'w') as handle:
        json.dump(model, handle)
    reloaded = load(package.path)

    def fired(shapes):
        report = validate_graphs(reloaded.model, shapes, reloaded.knowledge,
                                 strict=False)
        return [r for r in report.violations
                if r.resource == 'urn:filter:99' and r.attribute == 'hasState']

    before = fired(reloaded.shapes)
    assert before, 'a Filter with no hasState should violate MachineShape'

    weaker = Graph()
    for triple in reloaded.shapes:
        weaker.add(triple)
    weaker.parse(data=f'''
@prefix sh: <http://www.w3.org/ns/shacl#> .
<{SHACL}FilterShape> sh:property [ sh:path <{ENTITIES}hasState> ;
    sh:minCount 0 ; sh:maxCount 1 ; sh:nodeKind sh:BlankNode ] .
''', format='turtle')

    after = fired(weaker)
    assert [r.component for r in after] == [r.component for r in before]
    assert all(r.shape == SHACL + 'MachineShape' for r in after)


# --- the tree ----------------------------------------------------------------

def test_a_subtype_shows_what_it_inherits(corpus):
    node = _type_node(corpus, 'Filter')
    inherited = [c for c in node.children if c.inherited_from]
    assert inherited, 'Filter should show the shapes it inherits'
    assert {c.label for c in inherited} >= {'iffBaseShacl:MachineShape'}
    assert node.detail.endswith('inherited')


def test_the_inherited_attribute_is_visible_on_the_subtype(corpus):
    node = _type_node(corpus, 'Filter')
    labels = {a.label for shape in node.children for a in shape.children}
    assert 'hasState' in labels, 'hasState applies to Filter and must be shown'


def test_inherited_nodes_say_where_they_come_from(corpus):
    node = _type_node(corpus, 'Filter')
    inherited = [c for c in node.children if c.inherited_from][0]
    assert inherited.inherited_class.endswith('Machine')
    assert inherited.defined_at.endswith('shacl.ttl:160') or \
        ':' in inherited.defined_at
    assert 'inherited from Machine' in inherited.detail


def test_inherited_constraints_are_not_editable_in_place(corpus):
    """Editing there would imply a replacement SHACL does not perform."""
    for _, node in flatten(build_tree(corpus)):
        if node.inherited_from:
            assert node.editable is False


def test_a_type_still_shows_its_own_shapes_as_editable(corpus):
    node = _type_node(corpus, 'Filter')
    own = [c for c in node.children if not c.inherited_from]
    assert own
    editable = [n for shape in own for _, n in flatten([shape]) if n.editable]
    assert editable


def test_a_root_type_inherits_nothing(corpus):
    node = _type_node(corpus, 'Machine')
    assert [c for c in node.children if c.inherited_from] == []


# --- the effect analysis -----------------------------------------------------

@pytest.mark.parametrize('parameter,old,new,expected', [
    ('sh:minCount', '1', '2', 'stricter'),
    ('sh:minCount', '1', '0', 'weaker'),
    ('sh:maxCount', '1', '5', 'weaker'),
    ('sh:maxCount', '5', '1', 'stricter'),
    ('sh:maxInclusive', '100.0', '50.0', 'stricter'),
    ('sh:maxInclusive', '100.0', '200.0', 'weaker'),
    ('sh:minInclusive', '0.0', '10.0', 'stricter'),
    ('sh:minCount', '1', '1', 'same'),
    ('sh:datatype', 'xsd:double', 'xsd:string', 'unknown'),
    ('sh:class', 'a:B', 'a:C', 'unknown'),
])
def test_override_effect(parameter, old, new, expected):
    assert override_effect(parameter, old, new) == expected


def test_the_lattice_is_keyed_by_parameter_not_component(corpus):
    """The diff keys it by constraint component; a cooked node carries the
    SHACL parameter. Without bridging them every numeric case reads 'unknown'."""
    from semforge.cooked.tree import WEAKER_BY_PARAMETER

    assert 'sh:minCount' in WEAKER_BY_PARAMETER
    assert 'MinCountConstraintComponent' not in WEAKER_BY_PARAMETER


# --- pulling a constraint down ----------------------------------------------

def test_declaring_an_inherited_constraint_adds_it_to_the_subtype(package):
    path, how = override_constraint(
        package, SHACL + 'FilterShape', ['iffBaseEntities:hasState'],
        'sh:minCount', '1')
    assert how == 'added-attribute'

    reloaded = load(package.path)
    node = _type_node(reloaded, 'Filter')
    own = [c for c in node.children if not c.inherited_from]
    attributes = {a.label for shape in own for a in shape.children}
    assert 'hasState' in attributes, 'it should now be declared on Filter itself'
    Graph().parse(path, format='turtle')


def test_the_addition_does_not_disturb_the_rest_of_the_file(package):
    before = open(package.sources['shapes']).read()
    override_constraint(package, SHACL + 'FilterShape',
                        ['iffBaseEntities:hasState'], 'sh:minCount', '1')
    after = open(package.sources['shapes']).read()

    marker = 'iffBaseShacl:MachineShape'
    assert before.split(marker)[1] == after.split(marker)[1]
    for line in before.splitlines():
        if line.strip().startswith('#'):
            assert line in after


def test_adding_to_an_attribute_the_shape_already_has(package):
    _, how = override_constraint(
        package, SHACL + 'FilterShape', ['iffBaseEntities:hasStrength'],
        'sh:minCount', '1')
    assert how == 'added-to-existing'
    Graph().parse(package.sources['shapes'], format='turtle')


# --- every node knows where it is --------------------------------------------

def test_every_node_carries_its_own_file_and_line(corpus):
    """Selecting a node moves the .ttl to it, so a shape-level line is not enough."""
    located = [n for _, n in flatten(build_tree(corpus))
               if n.kind in ('shape', 'attribute', 'slot', 'constraint')]
    assert located
    for node in located:
        assert node.defined_at, f'{node.kind} {node.label} has no location'
        file_part, _, line = node.defined_at.rpartition(':')
        assert file_part.endswith('shacl.ttl') and line.isdigit()


def test_sibling_constraints_get_distinct_lines(corpus):
    """A tree that points every constraint at the top of its block makes the
    reader hunt for the line themselves."""
    node = _type_node(corpus, 'Filter')
    shape = next(c for c in node.children if not c.inherited_from)
    attribute = next(a for a in shape.children if a.label == 'hasStrength')
    lines = {c.parameter: int(c.defined_at.rpartition(':')[2])
             for c in attribute.children if c.kind == 'constraint'}
    assert len(set(lines.values())) > 1, f'all on one line: {lines}'


def test_an_inherited_node_keeps_its_own_line_not_the_shapes(corpus):
    """Stamping the shape's locator over the subtree sent every jump to the
    same line, which is exactly what makes go-to-definition useless."""
    node = _type_node(corpus, 'Filter')
    inherited = next(c for c in node.children
                     if c.inherited_from and c.children
                     and c.children[0].kind == 'attribute')
    attribute = inherited.children[0]
    assert attribute.defined_at != inherited.defined_at
    assert int(attribute.defined_at.rpartition(':')[2]) > \
        int(inherited.defined_at.rpartition(':')[2])


def test_the_location_points_at_the_real_text(corpus):
    """Read the line back and check it says what the node claims."""
    with open(corpus.sources['shapes']) as handle:
        lines = handle.read().splitlines()

    checked = 0
    for _, node in flatten(build_tree(corpus)):
        if node.kind != 'constraint' or not node.defined_at:
            continue
        line = lines[int(node.defined_at.rpartition(':')[2]) - 1]
        assert node.parameter in line, \
            f'{node.parameter} not on its own line: {line!r}'
        checked += 1
    assert checked > 20
