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

"""Typed literals (#961, contracts/typed-literals): SemForge declares its doubles.

JSON-LD 1.1 makes a plain whole number an integer, 80.0 included. Every value
SemForge generates or edits for an attribute whose one value is an xsd:double
is written as {"@value": <float>, "@type": <the full XSD IRI>}; integers, and
an attribute that admits integers too, stay plain.
"""

import json
import os
import shutil

import pytest

DOUBLE = 'http://www.w3.org/2001/XMLSchema#double'
E = 'https://example.org/m/entities/'
EXTRA_SHAPES = '''
mShacl:NumbersShape a sh:NodeShape ;
    sh:targetClass mEntities:Machine ;
    sh:property [ sh:path mEntities:hasCount ;
            sh:minCount 0 ;
            sh:maxCount 1 ;
            sh:nodeKind sh:BlankNode ;
            sh:property [ sh:path ngsild:hasValue ;
                    sh:datatype xsd:integer ;
                    sh:minInclusive 0 ;
                    sh:maxInclusive 10 ] ] ;
    sh:property [ sh:path mEntities:hasLevel ;
            sh:minCount 0 ;
            sh:maxCount 1 ;
            sh:nodeKind sh:BlankNode ;
            sh:property [ sh:path ngsild:hasValue ;
                    sh:or ( [ sh:datatype xsd:double ] [ sh:datatype xsd:integer ] ) ;
                    sh:minInclusive 0 ;
                    sh:maxInclusive 100 ] ] .
'''
EXTRA_KNOWLEDGE = ''.join(
    f'\n<{E}{name}> a <http://www.w3.org/2002/07/owl#DatatypeProperty> ; '
    f'<http://www.w3.org/2000/01/rdf-schema#domain> <{E}Machine> ; '
    f'<http://www.w3.org/2000/01/rdf-schema#range> <https://uri.etsi.org/ngsi-ld/Property> .\n'
    for name in ('hasCount', 'hasLevel'))


def declared(number):
    return {'@value': float(number), '@type': DOUBLE}


@pytest.fixture
def root(tmp_path):
    from semforge.package.scaffold import create_package

    root = tmp_path / 'm'
    create_package(str(root))
    with open(root / 'shacl.ttl', 'a') as handle:
        handle.write(EXTRA_SHAPES)
    with open(root / 'knowledge.ttl', 'a') as handle:
        handle.write(EXTRA_KNOWLEDGE)
    return root


def _row(package, label):
    from semforge.cooked.typepage import build_type_page
    return next(r for r in build_type_page(package, E + 'Machine')['attributes']
                if r['label'] == label)


def _generated(package, label, purpose, name):
    """The value a generated case writes for the attribute, and the case."""
    from semforge.expect.attributecase import new_attribute_test

    row = _row(package, label)
    made = new_attribute_test(package, E + 'Machine', row['path'], purpose, name)
    document = json.load(open(made['file'], encoding='utf-8'))
    entity = next(e for e in document if e.get('id') == made['resource'])
    attribute = entity[row['path'][-1]]
    return (attribute[0] if isinstance(attribute, list) else attribute)['value'], made


def _purpose(package, label, component):
    from semforge.expect.attributecase import attribute_test_options
    return next(o['purpose'] for o in attribute_test_options(
        package, E + 'Machine', _row(package, label)['path'])['options']
        if o['purpose'].endswith(component))


# --- generated cases --------------------------------------------------------------------

def test_a_valid_case_declares_its_double(root):
    """A fresh entity of the type: the middle of 0..120, declared."""
    from semforge.expect.addcase import add_test_case
    from semforge.package import load

    made = add_test_case(load(str(root)), 'test_Fresh', 'valid', 'type', E + 'Machine', 'machine')
    entity = json.load(open(next(root.rglob('test_Fresh/good/machine.jsonld')), encoding='utf-8'))[0]
    assert entity['mEntities:hasTemperature']['value'] == declared(60)
    assert made['passes'], made['failures']


def test_a_range_break_declares_its_double_and_breaks_only_the_range(root):
    from semforge.package import load

    package = load(str(root))
    value, made = _generated(package, 'hasTemperature',
                             _purpose(package, 'hasTemperature', 'MaxInclusiveConstraintComponent'),
                             'too-hot-generated')
    assert value == declared(121)
    assert made['passes'], made['failures']


def test_an_integer_attribute_is_a_plain_integer(root):
    from semforge.package import load

    value, made = _generated(load(str(root)), 'hasCount', 'valid', 'valid-count')
    assert value == 5 and isinstance(value, int)
    assert made['passes'], made['failures']


def test_a_double_or_integer_attribute_is_plain(root):
    from semforge.package import load

    value, made = _generated(load(str(root)), 'hasLevel', 'valid', 'valid-level')
    assert value == 50 and isinstance(value, int), 'whole, so an integer; not declared'
    assert made['passes'], made['failures']


def test_a_choice_between_a_value_and_a_list_is_still_a_double(tmp_path):
    """OPC UA: sh:or ( [hasValue double] [hasValueList …] ) is a choice of form."""
    from semforge.expect.attributecase import new_attribute_test
    from semforge.package import load
    from semforge.cooked.typepage import build_type_page

    pumps = os.path.join(os.path.dirname(__file__), '..', 'corpus', 'opcua-pumps')
    root = tmp_path / 'opcua-pumps'
    shutil.copytree(pumps, root, ignore=shutil.ignore_patterns('.semforge'))
    package = load(str(root))
    cls = 'http://opcfoundation.org/UA/Pumps/DriveMeasurementsType'
    row = next(r for r in build_type_page(package, cls)['attributes'] if r['label'] == 'hasVoltage')
    made = new_attribute_test(package, cls, row['path'], 'valid', 'valid voltage')
    document = json.load(open(made['file'], encoding='utf-8'))
    entity = next(e for e in document if e.get('id') == made['resource'])
    key = next(k for k in entity if k.endswith('hasVoltage'))
    attribute = entity[key]
    value = (attribute[0] if isinstance(attribute, list) else attribute)['value']
    assert isinstance(value, dict) and value['@type'] == DOUBLE, value
    assert made['passes'], made['failures']


# --- the scaffold and the editor --------------------------------------------------------

def test_a_new_package_declares_its_doubles(root):
    for path in ('model-instance.jsonld', 'examples/test_MachineShape/good/running.jsonld',
                 'examples/test_MachineShape/bad/too-hot.jsonld'):
        found = [f for f in root.rglob(os.path.basename(path))]
        assert found, path
        for entity in json.load(open(found[0], encoding='utf-8')):
            value = entity['mEntities:hasTemperature']['value']
            assert isinstance(value, dict) and value['@type'] == DOUBLE, (path, value)


def _example(root):
    return next(root.rglob('running.jsonld'))


def _temperature(root):
    entity = json.load(open(_example(root), encoding='utf-8'))[0]
    attribute = entity['mEntities:hasTemperature']
    return attribute[-1]['value'] if isinstance(attribute, list) else attribute['value']


@pytest.mark.parametrize('typed, expected', [
    ('80', declared(80)),
    ('80.5', declared(80.5)),
    (json.dumps(declared(80)), declared(80)),
])
def test_a_value_set_on_a_page_is_declared(root, typed, expected):
    from semforge.cooked.examples import set_value
    from semforge.package import load

    package = load(str(root))
    entity_id = json.load(open(_example(root), encoding='utf-8'))[0]['id']
    set_value(package, entity_id, ['mEntities:hasTemperature', 'value'], typed,
              file=str(_example(root)))
    assert _temperature(root) == expected


def test_a_value_object_the_modeller_typed_is_kept(root):
    from semforge.cooked.examples import set_value
    from semforge.package import load

    package = load(str(root))
    entity_id = json.load(open(_example(root), encoding='utf-8'))[0]['id']
    own = {'@value': '80', '@type': DOUBLE}
    set_value(package, entity_id, ['mEntities:hasTemperature', 'value'], json.dumps(own),
              file=str(_example(root)))
    assert _temperature(root) == own


def test_an_observation_is_declared(root):
    from semforge.cooked.examples import add_observation
    from semforge.package import load

    package = load(str(root))
    entity_id = json.load(open(_example(root), encoding='utf-8'))[0]['id']
    add_observation(package, entity_id, ['mEntities:hasTemperature'], value='90',
                    observed_at='2026-01-02T00:00:00.000Z', file=str(_example(root)))
    assert _temperature(root) == declared(90)


def test_other_attributes_are_left_alone(root):
    from semforge.cooked.examples import set_value
    from semforge.package import load

    package = load(str(root))
    entity_id = json.load(open(_example(root), encoding='utf-8'))[0]['id']
    set_value(package, entity_id, ['mEntities:hasState', 'value'],
              '{"@id": "mKnowledge:state_OFF"}', file=str(_example(root)))
    entity = json.load(open(_example(root), encoding='utf-8'))[0]
    assert entity['mEntities:hasState']['value'] == {'@id': 'mKnowledge:state_OFF'}


# --- passed on -----------------------------------------------------------------------------

def test_an_export_keeps_the_declared_value(root, tmp_path):
    from semforge.package import load
    from semforge.target.export import export

    written = export(load(str(root)), str(tmp_path / 'out'))
    text = open(written['model'], encoding='utf-8').read()
    assert DOUBLE in text or 'xsd:double' in text, 'the declared type survives the export'
