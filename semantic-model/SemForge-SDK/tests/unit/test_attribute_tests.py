#
# Copyright (c) 2026 IndustryFusion Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""New test… for one attribute: one that should conform, or one that should fail.

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


def test_a_new_attribute_offers_two_tests_and_they_say_what_they_do(fresh):
    root, machine = fresh
    path = _path(root, machine, 'hasPressure')
    options = attribute_test_options(load(root), machine, path)['options']
    assert [(o['purpose'], o['name']) for o in options] == [
        ('valid', 'pressure-valid'), ('invalid', 'pressure-invalid')]
    for option in options:
        made = new_attribute_test(load(root), machine, path, option['purpose'], option['name'])
        # One that should fail has no reason yet (test_fail_cases.py).
        assert made['passes'] == (option['purpose'] == 'valid'), made['failures']
        assert made['expect'] == option['purpose']
    cases = {e.path: e for e in load_expectations(root).examples}
    assert any(c.endswith('good/pressure-valid.jsonld') for c in cases)
    bad = next(e for c, e in cases.items() if c.endswith('bad/pressure-invalid.jsonld'))
    assert not bad.asserts and 'It fails until its data is edited' in bad.description


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
def test_the_kms_attributes_get_tests(kms, entity_type, attribute):
    for option in attribute_test_options(load(kms), BASE + entity_type, [attribute])['options']:
        made = new_attribute_test(load(kms), BASE + entity_type, [attribute],
                                  option['purpose'], option['name'])
        assert made['passes'] == (option['purpose'] == 'valid'), made['failures']


def test_an_existing_attribute_is_changed_not_replaced(kms):
    """Cutter's hasState carries a sub-attribute; a fresh value would drop it."""
    made = new_attribute_test(load(kms), BASE + 'Cutter', ['iffBaseEntities:hasState'],
                              'valid', 'state-valid')
    with open(made['file']) as handle:
        scene = json.load(handle)
    entity = next(d for d in scene if d['id'] == made['resource'])
    assert 'iffBaseEntities:hasXXXWorkpiece' in entity['iffBaseEntities:hasState']


@pytest.mark.parametrize('purpose, said', [
    ('iffBaseShacl:FilterShape/hasStrength/DatatypeConstraintComponent', 'valid or invalid'),
    ('nonsense', 'valid or invalid'),
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
