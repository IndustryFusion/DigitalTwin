"""New test… for one attribute: valid, or one of its constraints firing.

The case the feature was asked for: a freshly scaffolded package, a new
optional attribute (hasPressure, xsd:double), and no way to start a test for
it from the entity type. Every offered test is written, run, and must prove
what it says -- and the existing kms attributes, inherited and relationship
ones included, must work too.
"""

import json
import shutil

import pytest

from semforge.cooked.constrain import add_attribute_constraint
from semforge.cooked.knowledge import add_attribute_term
from semforge.errors import PackageError
from semforge.expect.attributecase import attribute_test_options, new_attribute_test
from semforge.expect.store import load_expectations
from semforge.package import load
from semforge.package.scaffold import create_package

BASE = 'https://industryfusion.github.io/contexts/example/v0/base_entities/'


@pytest.fixture
def fresh(tmp_path):
    """A scaffolded package with a new optional attribute, as the user had."""
    root = str(tmp_path / 'my-model')
    create_package(root)
    package = load(root)
    machine = next(c for c in package.knowledge.subjects()
                   if str(c).endswith('/Machine'))
    add_attribute_term(package, 'hasPressure', 'Property', str(machine),
                       label='Pressure of the machine')
    package = load(root)
    shape = next(s for s in package.shapes.subjects() if str(s).endswith('/MachineShape'))
    add_attribute_constraint(package, str(shape), 'hasPressure', required=False,
                             datatype='xsd:double')
    return root, str(machine)


def _path(root, machine, name):
    from semforge.cooked.tree import build_tree

    node = next(a for r in build_tree(load(root)) if r.target_class == machine
                for s in r.children for a in s.children
                if a.kind == 'attribute' and a.label.endswith(name))
    return list(node.path_chain)


def test_a_new_optional_attribute_offers_what_can_fire(fresh):
    root, machine = fresh
    offered = attribute_test_options(load(root), machine, _path(root, machine, 'hasPressure'))
    components = {o['purpose'].rsplit('/', 1)[-1] for o in offered['options']}
    assert 'valid' in components
    assert {'DatatypeConstraintComponent', 'MaxCountConstraintComponent'} <= components
    # Optional: "left out" cannot fire, so it is not offered as a test.
    detail = {o['purpose'].rsplit('/', 1)[-1]: o['detail'] for o in offered['options']}
    assert 'left out' not in detail.get('MinCountConstraintComponent', '')
    names = {o['name'] for o in offered['options']}
    assert {'pressure-valid', 'pressure-wrong-datatype'} <= names


def test_every_offered_test_for_it_proves_what_it_says(fresh):
    root, machine = fresh
    path = _path(root, machine, 'hasPressure')
    for option in attribute_test_options(load(root), machine, path)['options']:
        made = new_attribute_test(load(root), machine, path, option['purpose'],
                                  option['name'])
        assert made['passes'], (option['purpose'], made['failures'])
        assert made['expect'] == ('valid' if option['purpose'] == 'valid' else 'invalid')
    cases = {e.path for e in load_expectations(root).examples}
    assert any(c.endswith('good/pressure-valid.jsonld') for c in cases)
    assert any(c.endswith('bad/pressure-wrong-datatype.jsonld') for c in cases)


def test_a_broken_value_is_the_one_the_constraint_forbids(fresh):
    root, machine = fresh
    path = _path(root, machine, 'hasPressure')
    purpose = next(o['purpose'] for o in attribute_test_options(load(root), machine, path)[
        'options'] if o['purpose'].endswith('DatatypeConstraintComponent'))
    made = new_attribute_test(load(root), machine, path, purpose, 'p')
    with open(made['file']) as handle:
        scene = json.load(handle)
    entity = next(d for d in scene if d['id'] == made['resource'])
    pressure = next(v for k, v in entity.items() if k.endswith('hasPressure'))
    assert pressure['value'] == 'not a number'
    entry = next(e for e in load_expectations(root).examples if e.path == made['case'])
    assert entry.asserts == [{'constraint': purpose, 'resource': made['resource']}]


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


@pytest.mark.parametrize('entity_type, attribute', [
    ('Filter', 'iffBaseEntities:hasStrength'),     # a range and an sh:or
    ('Filter', 'iffBaseEntities:hasCartridge'),    # a Relationship
    ('Cutter', 'iffBaseEntities:hasState'),        # inherited from MachineShape
])
def test_the_kms_attributes_get_tests_that_hold(kms, entity_type, attribute):
    for option in attribute_test_options(load(kms), BASE + entity_type, [attribute])['options']:
        made = new_attribute_test(load(kms), BASE + entity_type, [attribute],
                                  option['purpose'], option['name'])
        assert made['passes'] == option['automatic'], (option['purpose'], made['failures'])


def test_an_existing_attribute_is_changed_not_replaced(kms):
    """Cutter's hasState carries a sub-attribute; a fresh value would drop it."""
    made = new_attribute_test(load(kms), BASE + 'Cutter', ['iffBaseEntities:hasState'],
                              'valid', 'state-valid')
    with open(made['file']) as handle:
        scene = json.load(handle)
    entity = next(d for d in scene if d['id'] == made['resource'])
    assert 'iffBaseEntities:hasXXXWorkpiece' in entity['iffBaseEntities:hasState']


@pytest.mark.parametrize('purpose, said', [
    ('iffBaseShacl:FilterShape/hasStrength/DatatypeConstraintComponent', 'not a constraint'),
    ('nonsense', 'not a constraint'),
])
def test_a_test_it_cannot_write_is_refused(kms, purpose, said):
    with pytest.raises(PackageError, match=said):
        new_attribute_test(load(kms), BASE + 'Filter', ['iffBaseEntities:hasStrength'],
                           purpose, 'x')


def test_a_name_already_taken_is_refused(kms):
    args = (BASE + 'Filter', ['iffBaseEntities:hasStrength'], 'valid', 'strength')
    new_attribute_test(load(kms), *args)
    with pytest.raises(PackageError, match='already exists'):
        new_attribute_test(load(kms), *args)
