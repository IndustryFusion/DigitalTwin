"""Shape identity: the shape's IRI, with a random part; inside it, path and type.

A constraint is addressed the way SHACL addresses it -- its shape, its path,
its constraint type (`MachineShape-3f9a1c2e/hasTemperature/MinCount…`). The
shape's IRI is the identity, so every shape the editor names carries a random
part: a bare MachineShape reads like a description and gets renamed, merged or
reused as if it were one. A rename changes the name and keeps the random part.

Inside a shape, the path tells constraints apart -- all of it: an attribute's
own sh:minCount and its value's (sh:path ngsild:hasValue) are two references,
hasTemperature/MinCount… and hasTemperature.hasValue/MinCount….
"""

import re
import uuid

import pytest

from semforge.cooked.rename import rename_plan, rename_shape
from semforge.cooked.shapes import add_shape, base_name, identity_suffix, with_identity
from semforge.errors import PackageError
from semforge.package import load
from semforge.package.scaffold import create_package
from semforge.sanity import known_constraints
from semforge.validate.orchestrator import validate_package

TEMPERATURE = 'myModelEntities:hasTemperature'


@pytest.fixture
def pkg(tmp_path):
    root = str(tmp_path / 'my-model')
    create_package(root)
    return root


def _shape(root, name='MachineShape'):
    return str(next(s for s in load(root).shapes.subjects()
                    if str(s).rsplit('/', 1)[-1] == name))


# --- the random part -------------------------------------------------------------------

def test_the_helpers():
    assert identity_suffix('MachineShape-3f9a1c2e') == '-3f9a1c2e'
    assert identity_suffix('MachineShape') == ''
    assert base_name('MachineShape-3f9a1c2e') == 'MachineShape'
    assert with_identity('MachineShape-3f9a1c2e') == 'MachineShape-3f9a1c2e'
    assert with_identity('PumpShape', '-00000000') == 'PumpShape-00000000'
    assert re.fullmatch(r'PumpShape-[0-9a-f]{8}', with_identity('PumpShape'))


def test_every_new_shape_gets_its_own_random_part(pkg):
    first = add_shape(load(pkg), 'PumpShape', 'class', 'Machine')
    second = add_shape(load(pkg), 'ValveShape', 'class', 'Machine')
    names = [m['iri'].rsplit('/', 1)[-1] for m in (first, second)]
    assert all(re.fullmatch(r'(Pump|Valve)Shape-[0-9a-f]{8}', n) for n in names)
    assert identity_suffix(names[0]) != identity_suffix(names[1])


def test_a_name_another_shape_is_read_as_is_refused(pkg):
    add_shape(load(pkg), 'PumpShape', 'class', 'Machine')
    with pytest.raises(PackageError, match='a shape read as PumpShape'):
        add_shape(load(pkg), 'PumpShape', 'class', 'Machine')


def test_a_rename_keeps_the_random_part(pkg):
    made = add_shape(load(pkg), 'PumpShape', 'class', 'Machine')
    suffix = identity_suffix(made['iri'])
    rename_shape(load(pkg), made['iri'], 'PumpingShape')
    assert _shape(pkg, f'PumpingShape{suffix}')


def test_a_shape_without_one_gets_one_and_the_plan_agrees(pkg):
    shape = _shape(pkg)
    derived = f'-{uuid.uuid5(uuid.NAMESPACE_URL, shape).hex[:8]}'
    plan = rename_plan(load(pkg), shape, 'MachineShape')
    assert plan['newName'] == f'MachineShape{derived}', 'renaming to its own name names it'
    assert rename_plan(load(pkg), shape, 'MachineShape')['newName'] == plan['newName']
    rename_shape(load(pkg), shape, 'MachineShape')
    assert _shape(pkg, f'MachineShape{derived}')
    assert not validate_package(load(pkg), strict=False).violations


def test_a_rename_onto_a_name_already_read_is_refused(pkg):
    add_shape(load(pkg), 'PumpShape', 'class', 'Machine')
    with pytest.raises(PackageError, match='PumpShape is already a shape'):
        rename_plan(load(pkg), _shape(pkg), 'PumpShape')


# --- the path, all of it ---------------------------------------------------------------

def test_an_attribute_s_count_and_its_value_s_are_two_references(pkg):
    names = {k.split('/', 1)[1] for k in known_constraints(load(pkg))
             if 'hasTemperature' in k and 'Count' in k}
    assert names == {'hasTemperature/MinCountConstraintComponent',
                     'hasTemperature/MaxCountConstraintComponent',
                     'hasTemperature.hasValue/MinCountConstraintComponent',
                     'hasTemperature.hasValue/MaxCountConstraintComponent'}


def test_a_value_only_constraint_keeps_the_attribute_s_name(pkg):
    names = {k.split('/', 1)[1] for k in known_constraints(load(pkg)) if 'hasTemperature' in k}
    assert 'hasTemperature/DatatypeConstraintComponent' in names
    assert not any(n.startswith('hasTemperature.hasValue/Datatype') for n in names)


def test_a_result_is_named_as_its_constraint_is(pkg):
    """A missing value fires the value's sh:minCount -- named hasTemperature.hasValue,
    exactly as the shape declares it, never as the attribute's own."""
    import json

    model = load(pkg).sources['model']
    document = json.load(open(model))
    entity = next(e for e in document if e.get('id') == 'urn:myModel:machine:1')
    entity[TEMPERATURE] = {'type': 'Property', 'observedAt': entity[TEMPERATURE]['observedAt']}
    json.dump(document, open(model, 'w'), indent=2)
    violated = {(r.attribute, r.component) for r in validate_package(load(pkg), strict=False).violations}
    assert ('hasTemperature.hasValue', 'MinCountConstraintComponent') in violated
    assert ('hasTemperature', 'MinCountConstraintComponent') not in violated
    known = {k.split('/', 1)[1] for k in known_constraints(load(pkg))}
    assert 'hasTemperature.hasValue/MinCountConstraintComponent' in known


def test_a_relationship_s_value_is_its_object(corpus):
    names = {k.split('/', 1)[1] for k in known_constraints(corpus) if 'hasFilter' in k}
    assert 'hasFilter.hasObject/MinCountConstraintComponent' in names
