"""Units: NGSI-LD's unitCode, as UN/CEFACT Rec 20 common codes.

A curated set ships with the SDK -- each code with its name, symbol and QUDT
quantity, so "temperature" finds CEL, FAH and KEL. A package adds its own as
qudt:Units in its knowledge. A shape says which units an attribute's instances
may say (`sh:property [ sh:path ngsild:unitCode ; sh:in ( "CEL" ) ]` on the
attribute node), pyshacl holds the data to it, and its constraints are named
after the attribute -- hasTemperature.unitCode -- on both sides.
"""

import json
import os
import shutil
import subprocess

import pytest
from rdflib import Literal, URIRef
from rdflib.namespace import RDF

from semforge.cooked.knowledge import build_knowledge
from semforge.cooked.tree import build_tree
from semforge.cooked.typepage import build_type_page
from semforge.cooked.units import (add_unit, attribute_units, find_unit, search_units,
                                   set_unit_code, set_units, units)
from semforge.errors import PackageError
from semforge.expect.attributecase import attribute_test_options, new_attribute_test
from semforge.ngsild.units import CATALOGUE, QUDT
from semforge.package import load
from semforge.package.scaffold import create_package
from semforge.sanity import known_constraints, sanity
from semforge.validate.orchestrator import validate_package

TEMPERATURE = 'myModelEntities:hasTemperature'
MACHINE_ID = 'urn:myModel:machine:1'


@pytest.fixture
def pkg(tmp_path):
    root = str(tmp_path / 'my-model')
    create_package(root)
    package = load(root)
    machine = next(c for c in package.knowledge.subjects() if str(c).endswith('/Machine'))
    shape = next(s for s in package.shapes.subjects() if str(s).endswith('/MachineShape'))
    return root, str(machine), str(shape)


def _violations(root):
    return sorted((r.attribute, r.component) for r in validate_package(
        load(root), strict=False).violations)


# --- the catalogue -----------------------------------------------------------------------

def test_the_curated_set_has_one_entry_per_code_and_says_what_each_is():
    codes = [row[0] for row in CATALOGUE]
    assert len(codes) == len(set(codes)) >= 100
    assert all(name and quantity for _, name, _, quantity in CATALOGUE)


@pytest.mark.parametrize('query, first', [
    ('temperature', ['CEL', 'FAH', 'KEL']), ('celsius', ['CEL']), ('CEL', ['CEL']),
    ('°C', ['CEL']), ('bar', ['BAR', 'MBR']), ('volume flow', ['G2', 'L2', 'MQH', 'MQS'])])
def test_search_by_code_name_symbol_or_quantity(pkg, query, first):
    found = [u['code'] for u in search_units(load(pkg[0]), query)]
    assert found[:len(first)] == first or sorted(found) == sorted(first), found


# --- the package's own -----------------------------------------------------------------

def test_a_unit_of_the_package_s_own_with_the_catalogue_s_terms(pkg):
    root, _, _ = pkg
    made = add_unit(load(root), 'xkg', 'kilogram per stroke', 'mass per stroke', 'kg/str')
    assert (made['code'], made['quantity']) == ('XKG', 'MassPerStroke')
    package = load(root)
    unit = URIRef(made['iri'])
    graph = package.knowledge
    assert (unit, RDF.type, QUDT.Unit) in graph
    assert (unit, QUDT.uneceCommonCode, Literal('XKG')) in graph
    text = open(made['file']).read()
    assert '@prefix qudt: <http://qudt.org/schema/qudt/> .' in text
    assert 'qudt:hasQuantityKind quantitykind:MassPerStroke' in text
    assert find_unit(package, 'XKG')['builtin'] is False
    assert [u['code'] for u in search_units(package, 'stroke')] == ['XKG']


@pytest.mark.parametrize('code, says', [('CEL', 'already degree Celsius'),
                                        ('TOOLONG', 'not a UN/CEFACT common code')])
def test_a_unit_that_cannot_be_added(pkg, code, says):
    with pytest.raises(PackageError, match=says):
        add_unit(load(pkg[0]), code, 'x', 'Temperature')


# --- the shape -------------------------------------------------------------------------

def test_units_are_written_on_the_attribute_node_and_read_back(pkg):
    root, machine, shape = pkg
    set_units(load(root), shape, [TEMPERATURE], ['CEL', 'KEL'], required=True)
    assert attribute_units(load(root), shape, [TEMPERATURE]) == {
        'codes': ['CEL', 'KEL'], 'required': True}
    text = open(load(root).sources['shapes']).read()
    assert 'sh:property [ sh:path ngsild:unitCode ; sh:in ( "CEL" "KEL" ) ; sh:minCount 1 ]' \
        in text
    row = next(a for a in build_type_page(load(root), machine)['attributes']
               if a['label'] == 'hasTemperature')
    assert row['units'] == ['CEL', 'KEL'] and row['unitRequired']
    assert row['value'].endswith('· in °C, K · unit required')
    assert not [a for a in build_type_page(load(root), machine)['attributes']
                if 'unitCode' in a['label']], 'the unit is no sub-attribute'


def test_changing_and_removing_them(pkg):
    root, _, shape = pkg
    shapes = load(root).sources['shapes']
    before = open(shapes).read()
    set_units(load(root), shape, [TEMPERATURE], ['CEL'])
    set_units(load(root), shape, [TEMPERATURE], ['FAH'])
    assert attribute_units(load(root), shape, [TEMPERATURE]) == {
        'codes': ['FAH'], 'required': False}
    assert open(shapes).read().count('ngsild:unitCode') == 1
    set_units(load(root), shape, [TEMPERATURE], [])
    assert open(shapes).read() == before


def test_an_unknown_unit_is_refused_in_the_shape(pkg):
    root, _, shape = pkg
    with pytest.raises(PackageError, match='New unit'):
        set_units(load(root), shape, [TEMPERATURE], ['ZZZ'])


# --- the data, and what validation says ------------------------------------------------

def test_the_data_is_held_to_the_shape_s_units(pkg):
    root, _, shape = pkg
    set_units(load(root), shape, [TEMPERATURE], ['CEL'], required=True)
    assert _violations(root) == [('hasTemperature.unitCode', 'MinCountConstraintComponent')]
    set_unit_code(load(root), MACHINE_ID, [TEMPERATURE], '', 'FAH')
    assert _violations(root) == [('hasTemperature.unitCode', 'InConstraintComponent')]
    set_unit_code(load(root), MACHINE_ID, [TEMPERATURE], '', 'CEL')
    assert _violations(root) == []


def test_the_unit_constraints_are_named_alike_on_both_sides(pkg):
    root, _, shape = pkg
    set_units(load(root), shape, [TEMPERATURE], ['CEL'], required=True)
    named = {k for k in known_constraints(load(root)) if 'unitCode' in k}
    assert named == {'myModelShacl:MachineShape/hasTemperature.unitCode/InConstraintComponent',
                     'myModelShacl:MachineShape/hasTemperature.unitCode/MinCountConstraintComponent'}


def test_a_unit_is_set_on_every_observation_of_the_instance(pkg):
    root, _, _ = pkg
    model = load(root).sources['model']
    document = json.load(open(model))
    entity = next(e for e in document if e.get('id') == MACHINE_ID)
    first = entity[TEMPERATURE]
    entity[TEMPERATURE] = [first, dict(first, observedAt='2026-01-02T00:00:00.000Z')]
    json.dump(document, open(model, 'w'), indent=2)
    done = set_unit_code(load(root), MACHINE_ID, [TEMPERATURE], '', 'CEL')
    assert done['changed'] == 2
    entity = next(e for e in json.load(open(model)) if e.get('id') == MACHINE_ID)
    assert [i['unitCode'] for i in entity[TEMPERATURE]] == ['CEL', 'CEL']
    set_unit_code(load(root), MACHINE_ID, [TEMPERATURE], '', '')
    entity = next(e for e in json.load(open(model)) if e.get('id') == MACHINE_ID)
    assert not any('unitCode' in i for i in entity[TEMPERATURE])


def test_an_unknown_unit_in_the_data_is_refused_and_reported(pkg):
    root, _, _ = pkg
    with pytest.raises(PackageError, match='New unit'):
        set_unit_code(load(root), MACHINE_ID, [TEMPERATURE], '', 'ZZZ')
    model = load(root).sources['model']
    document = json.load(open(model))
    next(e for e in document if e.get('id') == MACHINE_ID)[TEMPERATURE]['unitCode'] = 'ZZZ'
    json.dump(document, open(model, 'w'), indent=2)
    [finding] = [f for f in sanity(load(root)) if f.code == 'unit-unknown']
    assert '"unitCode": "ZZZ"' in open(model).read().splitlines()[finding.line - 1]
    assert finding.fix['unit'] == 'ZZZ' and finding.fix['attributePath'] == [TEMPERATURE]


def test_the_quick_fixes_of_an_unknown_unit():
    from lsprotocol import types

    from semforge.editor.server import _fixes_for

    diagnostic = types.Diagnostic(
        range=types.Range(types.Position(0, 0), types.Position(0, 1)), message='',
        data={'code': 'unit-unknown', 'entity': MACHINE_ID, 'attributePath': [TEMPERATURE],
              'file': 'f', 'datasetId': '', 'unit': 'ZZZ'})
    actions = _fixes_for(diagnostic, 'file:///pkg/shacl.ttl')
    assert [(a.title, a.command.command) for a in actions] == [
        ('Choose the unit…', 'semforge.setUnitCode'),
        ('Add ZZZ as a unit of this package…', 'semforge.newUnit')]
    assert actions[0].command.arguments[0]['current'] == 'ZZZ'


# --- New test… -------------------------------------------------------------------------

def test_new_test_writes_a_unit_and_breaks_it(pkg):
    root, machine, shape = pkg
    set_units(load(root), shape, [TEMPERATURE], ['CEL'], required=True)
    node = next(a for r in build_tree(load(root)) if r.target_class == machine
                for s in r.children for a in s.children
                if a.kind == 'attribute' and a.label.endswith('hasTemperature'))
    options = attribute_test_options(load(root), machine, list(node.path_chain))['options']
    unit = {o['label']: o for o in options if 'unit' in o['label']}
    assert set(unit) == {'fires: unit In', 'fires: unit MinCount'}
    for option in [o for o in options if o['purpose'] == 'valid'] + list(unit.values()):
        made = new_attribute_test(load(root), machine, list(node.path_chain),
                                  option['purpose'], option['name'])
        assert made['passes'], (option['name'], made['failures'])
        entity = next(e for e in json.load(open(made['file'])) if e.get('id') == made['resource'])
        said = entity[TEMPERATURE].get('unitCode')
        assert said == {'temperature-valid': 'CEL', 'temperature-wrong-unit': 'FAH',
                        'temperature-no-unit': None}[option['name']], option['name']


# --- the Vocabulary view ----------------------------------------------------------------

def test_the_vocabulary_view_lists_units_by_quantity(pkg):
    root, _, _ = pkg
    add_unit(load(root), 'XKG', 'kilogram per stroke', 'Mass', 'kg/str')
    group = next(r for r in build_knowledge(load(root)) if r.label == 'Vocabulary classes')
    node = next(c for c in group.children if c.kind == 'units')
    assert node.label == 'qudt:Unit' and '1 of the package\'s own' in node.detail
    quantity = next(q for q in node.children if q.label == 'temperature')
    assert [(u.label, u.detail) for u in quantity.children] == [
        ('CEL', 'degree Celsius · °C · UN/CEFACT'), ('FAH', 'degree Fahrenheit · °F · UN/CEFACT'),
        ('KEL', 'kelvin · K · UN/CEFACT')]
    own = next(u for q in node.children for u in q.children if u.label == 'XKG')
    assert own.detail.endswith('own') and own.defined_at


def test_every_unit_is_listed_once(pkg):
    known = units(load(pkg[0]))
    assert len({u['code'] for u in known}) == len(known)


# --- the extension ---------------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
UNITS = {'ok': True, 'quantities': ['Temperature'], 'allowed': ['CEL'], 'required': False,
         'units': [{'code': c, 'name': n, 'symbol': s, 'quantity': q, 'quantityLabel': q.lower(),
                    'builtin': True, 'iri': '', 'term': ''} for c, n, s, q in CATALOGUE[:3]]}


def _drive(tmp_path, scenario):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    for name in ('shacl.ttl', 'knowledge.ttl', 'model-instance.jsonld'):
        (tmp_path / name).write_text('')
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(scenario))
    out = subprocess.run([node, DRIVE, str(tmp_path), os.path.join(SRC, 'extension.js'),
                          str(path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _asked(seen, method):
    return [r['params'] for r in seen['requests'] if r['method'] == method]


def test_unit_on_an_instance_offers_the_allowed_first_and_writes_it(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.setUnitCode',
        'node': {'raw': {'kind': 'dataset', 'entity': MACHINE_ID, 'entityType': 'e:Machine',
                         'attributePath': [TEMPERATURE], 'datasetId': '@none',
                         'file': 'case.jsonld', 'label': 'hasTemperature'},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['FAH'],
        'replies': {'semforge/units': UNITS, 'semforge/setUnitCode': {'ok': True}}})
    labels = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert labels[:4] == ['No unit', 'Allowed by the shape', 'CEL', 'Every unit']
    assert 'Search by code, name or quantity' in seen['quickPicks'][0]['placeHolder']
    assert _asked(seen, 'semforge/setUnitCode') == [{
        'uri': 'file:///pkg/shacl.ttl', 'entity': MACHINE_ID, 'attributePath': [TEMPERATURE],
        'datasetId': '', 'code': 'FAH', 'file': 'case.jsonld'}]


def test_new_unit_asks_code_name_symbol_quantity(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.newUnit', 'node': {'packageUri': 'file:///pkg/shacl.ttl'},
        'inputs': ['xkg', 'kilogram per stroke', 'kg/str'], 'picks': ['Temperature'],
        'replies': {'semforge/units': UNITS,
                    'semforge/addUnit': {'ok': True, 'code': 'XKG', 'name': 'kilogram per stroke'}}})
    assert _asked(seen, 'semforge/addUnit') == [{
        'uri': 'file:///pkg/shacl.ttl', 'code': 'XKG', 'name': 'kilogram per stroke',
        'symbol': 'kg/str', 'quantity': 'Temperature', 'namespace': None}]


def test_add_attribute_asks_the_unit_when_the_shape_names_some(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addAttribute',
        'node': {'raw': {'kind': 'entity', 'entity': MACHINE_ID, 'entityType': 'e:Machine',
                         'file': 'case.jsonld', 'label': MACHINE_ID, 'children': []},
                 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['e:hasTemperature', 'Default instance', 'CEL'], 'inputs': ['21.5'],
        'replies': {'semforge/attributes': {'attributes': [
            {'term': 'e:hasTemperature', 'kind': 'Property', 'constrained': True,
             'domains': ['e:Machine'], 'comment': ''}]},
            'semforge/valueChoices': {'choices': []}, 'semforge/units': UNITS,
            'semforge/addAttribute': {'ok': True, 'kind': 'Property'}}})
    assert _asked(seen, 'semforge/addAttribute')[0]['unitCode'] == 'CEL'


def test_unit_on_a_type_page_row_writes_the_shape(tmp_path, pkg):
    root, machine, _ = pkg
    page = dict(build_type_page(load(root), machine), ok=True)
    row = next(i for i, a in enumerate(page['attributes']) if a['label'] == 'hasTemperature')
    seen = _drive(tmp_path, {
        'command': 'semforge.openTypePage',
        'node': {'raw': {'kind': 'type', 'targetClass': machine, 'label': 'Machine',
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'menu', 'row': row}],
        'picks': ['$(symbol-ruler) Unit…', ['CEL', 'FAH'], 'Required'],
        'replies': {'semforge/typePage': page, 'semforge/units': dict(UNITS, allowed=[]),
                    'semforge/setUnits': {'ok': True}}})
    menu = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert '$(symbol-ruler) Unit…' in menu
    [sent] = _asked(seen, 'semforge/setUnits')
    assert (sent['codes'], sent['required'], sent['path']) == (['CEL', 'FAH'], True, [TEMPERATURE])
