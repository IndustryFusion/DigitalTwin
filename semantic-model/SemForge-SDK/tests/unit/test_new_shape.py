"""New shape…: a node shape with one target, from the editor.

No command wrote a shape, so a new entity type had no way to get one --
and its type page's + Attribute had nowhere to write. `add_shape` writes
`ns:Name a sh:NodeShape ; sh:target… X .` for an entity type, one entity,
whatever has an attribute, or whatever a relationship points at.
"""

import re
import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import SH

from semforge.cooked.constrain import add_attribute_constraint, own_shape
from semforge.cooked.knowledge import add_attribute_term
from semforge.cooked.shapes import add_shape, build_shapes
from semforge.cooked.typepage import build_type_page
from semforge.errors import PackageError
from semforge.package import load
from semforge.package.scaffold import create_package
from semforge.validate import validate_package


@pytest.fixture
def fresh(tmp_path):
    """A scaffolded package with a new entity type that has no shape."""
    root = str(tmp_path / 'my-model')
    create_package(root)
    package = load(root)
    entity = next(str(c) for c in package.knowledge.subjects() if str(c).endswith('/Entity'))
    space = entity[:-len('Entity')]
    with open(f'{root}/knowledge.ttl', 'a') as handle:
        handle.write(f'\n<{space}Pump> a <http://www.w3.org/2002/07/owl#Class> ;\n'
                     f'    <http://www.w3.org/2000/01/rdf-schema#subClassOf> <{entity}> .\n')
    return root, space


def _graph(root):
    return Graph().parse(f'{root}/shacl.ttl', format='turtle')


@pytest.mark.parametrize('kind, target, predicate', [
    ('class', 'Pump', SH.targetClass),
    ('node', 'urn:my-model:machine:1', SH.targetNode),
    ('subjectsOf', 'hasTemperature', SH.targetSubjectsOf),
    ('objectsOf', 'ngsild:hasObject', SH.targetObjectsOf),
])
def test_each_target_kind_is_written(fresh, kind, target, predicate):
    root, _ = fresh
    with open(f'{root}/shacl.ttl') as handle:
        before = handle.read()
    made = add_shape(load(root), 'NewShape', kind, target)
    with open(f'{root}/shacl.ttl') as handle:
        after = handle.read()
    assert after.startswith(before), 'appended; the rest of the file untouched'
    assert (URIRef(made['iri']), predicate, None) in _graph(root)
    # Named, with a random part: the name is a label, the IRI the identity.
    assert re.fullmatch(r'NewShape-[0-9a-f]{8}', made['iri'].rsplit('/', 1)[-1])
    # In the namespace the package's other shapes use.
    assert made['iri'].startswith(
        next(str(s) for s in _graph(root).subjects(SH.targetClass, None)).rsplit('/', 1)[0])
    assert made['iri'].rsplit('/', 1)[-1] in [
        r['label'].split(':')[-1] for r in build_shapes(load(root))]
    assert not validate_package(load(root), strict=False).violations


@pytest.mark.parametrize('name, kind, target, said', [
    ('MachineShape', 'class', 'Machine', 'already exists'),
    ('PumpShape', 'class', 'Nope', 'not an entity type'),
    ('PumpShape', 'subjectsOf', 'hasNothing', 'not an attribute'),
    ('OneShape', 'node', 'not an iri', 'not an IRI'),
    ('1Shape', 'class', 'Pump', 'not a usable name'),
    ('PumpShape', 'or', 'Pump', 'not a target'),
])
def test_what_it_cannot_write_is_refused(fresh, name, kind, target, said):
    root, _ = fresh
    with pytest.raises(PackageError, match=said):
        add_shape(load(root), name, kind, target)


# --- the node selector, edited on the shape page --------------------------------------

@pytest.fixture
def targets_copy(tmp_path):
    import shutil

    from conftest import TARGETS

    root = tmp_path / 'targets'
    shutil.copytree(TARGETS, root, ignore=shutil.ignore_patterns('.semforge'))
    return str(root)


EX = 'https://example.org/targets/'


def test_a_target_added_then_removed_leaves_the_file_as_it_was(targets_copy):
    from semforge.cooked.shapes import add_target, remove_target, targets

    with open(f'{targets_copy}/shacl.ttl') as handle:
        before = handle.read()
    add_target(load(targets_copy), EX + 'PumpShape', 'node', 'urn:valve:9')
    add_target(load(targets_copy), EX + 'PumpShape', 'subjectsOf', EX + 'hasValve')
    kinds = [t['kind'] for t in targets(load(targets_copy), EX + 'PumpShape')]
    assert sorted(kinds) == ['class', 'node', 'subjectsOf']
    remove_target(load(targets_copy), EX + 'PumpShape', 'subjectsOf', EX + 'hasValve')
    remove_target(load(targets_copy), EX + 'PumpShape', 'node', 'urn:valve:9')
    with open(f'{targets_copy}/shacl.ttl') as handle:
        assert handle.read() == before


def test_taking_the_last_target_off_says_what_is_left(targets_copy):
    from semforge.cooked.shapes import remove_target

    done = remove_target(load(targets_copy), EX + 'HasValveShape', 'subjectsOf',
                         EX + 'hasValve')
    assert 'has no target now' in done['note']
    assert (URIRef(EX + 'HasValveShape'), None, None) in _graph(targets_copy), \
        'the shape and its constraints stay'


@pytest.mark.parametrize('call, said', [
    (lambda p, f: f.remove_target(p, EX + 'HighPressureShape', 'sparql', ''), 'a query'),
    (lambda p, f: f.add_target(p, EX + 'PumpShape', 'class', EX + 'Pump'), 'already selects'),
    (lambda p, f: f.remove_target(p, EX + 'PumpShape', 'node', 'urn:nope'), 'does not select'),
])
def test_target_edits_it_cannot_make_are_refused(targets_copy, call, said):
    from semforge.cooked import shapes

    with pytest.raises(PackageError, match=said):
        call(load(targets_copy), shapes)


def test_a_new_type_gets_its_shape_and_then_its_attributes(fresh):
    """The type page's "Create its shape", then + Attribute."""
    root, space = fresh
    pump = space + 'Pump'
    assert not build_type_page(load(root), pump)['ownShape']
    made = add_shape(load(root), 'PumpShape', 'class', pump)
    assert own_shape(load(root), pump) == made['iri']
    assert build_type_page(load(root), pump)['ownShape'] == made['iri']
    add_attribute_term(load(root), 'hasFlow', 'Property', pump)
    add_attribute_constraint(load(root), made['iri'], 'hasFlow', required=True,
                             datatype='xsd:double')
    rows = build_type_page(load(root), pump)['attributes']
    assert [r['label'] for r in rows] == ['hasFlow']
