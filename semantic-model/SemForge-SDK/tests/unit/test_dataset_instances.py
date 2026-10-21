"""Multi-instance attributes: one attribute name, several datasetIds.

NGSI-LD identifies an attribute by (entity, name, datasetId). JSON-LD writes
the instances as an array, but it is a dictionary keyed by datasetId: the
default instance carries none (the platform calls it `@none` internally),
every other one its own IRI. sh:minCount and sh:maxCount count these
instances -- distinct live datasetIds, as shacl2flink does -- and observations
of one datasetId are one instance.

So: generated cardinality cases sit AT the boundary, with as many datasetIds
as that takes; the editor adds an instance and changes a datasetId; and the
data a test can be wrong about in ways the platform would never see -- a
datasetId that is no IRI, an "@none" written out, two unstamped instances of
one datasetId -- is reported where it is written.
"""

import json
import os
import shutil
import subprocess

import pytest

from semforge.cooked.constrain import add_attribute_constraint
from semforge.cooked.examples import (add_instance, build_suite, dataset_id_problem,
                                      set_dataset_id)
from semforge.cooked.knowledge import add_attribute_term
from semforge.errors import PackageError
from semforge.expect.attributecase import attribute_test_options, new_attribute_test
from semforge.package import load
from semforge.package.scaffold import create_package
from semforge.sanity import _dataset_checks
from semforge.validate.orchestrator import validate_graphs

PRESSURE = 'myModelEntities:hasPressure'


@pytest.fixture
def counted(tmp_path):
    """A package whose Machine needs 2 to 3 instances of hasPressure."""
    root = str(tmp_path / 'my-model')
    create_package(root)
    package = load(root)
    machine = next(c for c in package.knowledge.subjects() if str(c).endswith('/Machine'))
    add_attribute_term(package, 'hasPressure', 'Property', str(machine))
    package = load(root)
    shape = next(s for s in package.shapes.subjects() if str(s).endswith('/MachineShape'))
    add_attribute_constraint(package, str(shape), 'hasPressure', required=True,
                             datatype='xsd:double')
    shapes = load(root).sources['shapes']
    text = open(shapes, encoding='utf-8').read()
    at = text.index(f'sh:path {PRESSURE} ;')
    head, tail = text[:at], text[at:]
    tail = tail.replace('sh:minCount 1', 'sh:minCount 2', 1).replace(
        'sh:maxCount 1', 'sh:maxCount 3', 1)
    open(shapes, 'w', encoding='utf-8').write(head + tail)
    return root, str(machine)


def _path(root, machine):
    from semforge.cooked.tree import build_tree

    node = next(a for r in build_tree(load(root)) if r.target_class == machine
                for s in r.children for a in s.children
                if a.kind == 'attribute' and a.label.endswith('hasPressure'))
    return list(node.path_chain)


def _written(made):
    document = json.load(open(made['file'], encoding='utf-8'))
    entity = next(e for e in document if e.get('id') == made['resource'])
    value = entity.get(PRESSURE)
    return value if isinstance(value, list) or value is None else [value]


# --- generated cases sit at the boundary ------------------------------------------------

def test_the_options_say_how_many_instances(counted):
    root, machine = counted
    offered = attribute_test_options(load(root), machine, _path(root, machine))
    detail = {o['purpose'].rsplit('/', 1)[-1]: o['detail'] for o in offered['options']}
    assert detail['MinCountConstraintComponent'].startswith(
        'too few: 1 instance(s) where 2 are required')
    assert detail['MaxCountConstraintComponent'].startswith('more than 3: 4 instances')


def test_a_valid_case_has_as_many_instances_as_required(counted):
    root, machine = counted
    made = new_attribute_test(load(root), machine, _path(root, machine), 'valid',
                              'pressure-valid')
    instances = _written(made)
    assert len(instances) == 2
    assert 'datasetId' not in instances[0], 'the default instance carries none'
    assert instances[1]['datasetId'] == 'urn:my-model:dataset:2'
    assert made['passes'], made['failures']


@pytest.mark.parametrize('component, count', [('MinCountConstraintComponent', 1),
                                              ('MaxCountConstraintComponent', 4)])
def test_a_count_breaks_at_the_boundary_and_fires(counted, component, count):
    root, machine = counted
    package = load(root)
    purpose = next(o['purpose'] for o in attribute_test_options(
        package, machine, _path(root, machine))['options'] if o['purpose'].endswith(component))
    made = new_attribute_test(package, machine, _path(root, machine), purpose, 'pressure-count')
    instances = _written(made)
    assert len(instances) == count
    assert len({i.get('datasetId', '@none') for i in instances}) == count
    assert made['passes'], made['failures']


def test_another_constraint_breaks_one_instance_and_keeps_the_count(counted):
    root, machine = counted
    package = load(root)
    purpose = next(o['purpose'] for o in attribute_test_options(
        package, machine, _path(root, machine))['options']
        if o['purpose'].endswith('DatatypeConstraintComponent'))
    made = new_attribute_test(package, machine, _path(root, machine), purpose, 'pressure-text')
    instances = _written(made)
    assert len(instances) == 2
    assert isinstance(instances[0]['value'], str) and isinstance(instances[1]['value'], float)
    assert made['passes'], made['failures']


# --- the editor: another instance, another datasetId --------------------------------------

@pytest.fixture
def case(counted):
    from semforge.package.prefixes import add_namespace

    root, machine = counted
    made = new_attribute_test(load(root), machine, _path(root, machine), 'valid', 'two')
    # A datasetId reads attribute[prefix:name]: urn:sensor:* needs its prefix.
    add_namespace(root, 'sensor', 'urn:sensor:')
    return root, made


def _violations(root):
    from semforge.expect.store import compose, load_expectations

    package = load(root)
    example = next(e for e in load_expectations(root).examples if e.path.endswith('two.jsonld'))
    report = validate_graphs(compose(package, example), package.shapes, package.knowledge,
                             strict=False)
    return {r.component for r in report.results
            if r.attribute.endswith('hasPressure')}


def test_add_instance_copies_the_current_one_under_a_new_datasetid(case):
    root, made = case
    added = add_instance(load(root), made['resource'], [PRESSURE], 'urn:sensor:left',
                         file=made['file'])
    assert added['instances'] == 3
    instances = _written(made)
    assert instances[-1] == dict(instances[0], datasetId='urn:sensor:left')


def test_one_instance_too_many_is_what_maxcount_sees(case):
    root, made = case
    for name in ('urn:sensor:left', 'urn:sensor:right'):
        add_instance(load(root), made['resource'], [PRESSURE], name, file=made['file'])
    assert 'MaxCountConstraintComponent' in _violations(root)


@pytest.mark.parametrize('bad, says', [('left', 'not an IRI'), ('@none', 'default instance'),
                                       ('urn:my-model:dataset:2', 'already has an instance')])
def test_add_instance_refuses(case, bad, says):
    root, made = case
    before = open(made['file']).read()
    with pytest.raises(PackageError, match=says):
        add_instance(load(root), made['resource'], [PRESSURE], bad, file=made['file'])
    assert open(made['file']).read() == before


def test_a_single_instance_becomes_an_array(case):
    root, made = case
    set_dataset_id(load(root), made['resource'], [PRESSURE], 'urn:my-model:dataset:2',
                   'urn:sensor:a', file=made['file'])
    document = json.load(open(made['file']))
    entity = next(e for e in document if e.get('id') == made['resource'])
    entity[PRESSURE] = entity[PRESSURE][0]
    json.dump(document, open(made['file'], 'w'), indent=2)
    add_instance(load(root), made['resource'], [PRESSURE], 'urn:sensor:b', file=made['file'])
    assert [i.get('datasetId') for i in _written(made)] == [None, 'urn:sensor:b']


def test_change_datasetid_moves_every_observation_of_it(case):
    root, made = case
    document = json.load(open(made['file']))
    entity = next(e for e in document if e.get('id') == made['resource'])
    second = dict(entity[PRESSURE][1], observedAt='2026-01-01T00:00:00.000Z')
    entity[PRESSURE].append(dict(second, observedAt='2026-01-02T00:00:00.000Z'))
    entity[PRESSURE][1] = second
    json.dump(document, open(made['file'], 'w'), indent=2)
    changed = set_dataset_id(load(root), made['resource'], [PRESSURE],
                             'urn:my-model:dataset:2', 'urn:sensor:right', file=made['file'])
    assert changed['changed'] == 2
    assert [i.get('datasetId') for i in _written(made)] == [
        None, 'urn:sensor:right', 'urn:sensor:right']


def test_the_default_instance_can_get_one_and_another_become_it(case):
    root, made = case
    package = load(root)
    set_dataset_id(package, made['resource'], [PRESSURE], '@none', 'urn:sensor:main',
                   file=made['file'])
    set_dataset_id(load(root), made['resource'], [PRESSURE], 'urn:my-model:dataset:2', '',
                   file=made['file'])
    assert [i.get('datasetId') for i in _written(made)] == ['urn:sensor:main', None]
    with pytest.raises(PackageError, match='already has a default instance'):
        set_dataset_id(load(root), made['resource'], [PRESSURE], 'urn:sensor:main', '@none',
                       file=made['file'])


def test_dataset_id_problem():
    assert dataset_id_problem('urn:sensor:left') is None
    assert dataset_id_problem('https://example.org/ds/1') is None
    assert 'not an IRI' in dataset_id_problem('left sensor')
    assert 'default instance' in dataset_id_problem('@none')


# --- the data a count can be wrong about -----------------------------------------------

def _edit(made, change):
    document = json.load(open(made['file']))
    entity = next(e for e in document if e.get('id') == made['resource'])
    change(entity[PRESSURE])
    json.dump(document, open(made['file'], 'w'), indent=2)


def _found(root, code):
    return [f for f in _dataset_checks(load(root)) if f.code == code]


def test_a_generated_case_has_nothing_to_report(case):
    root, _ = case
    assert _dataset_checks(load(root)) == []


def test_a_datasetid_that_is_no_iri(case):
    root, made = case
    _edit(made, lambda instances: instances[1].update(datasetId='left'))
    [finding] = _found(root, 'dataset-not-iri')
    assert finding.severity == 'error' and finding.file == made['file']
    assert '"datasetId": "left"' in open(made['file']).read().splitlines()[finding.line - 1]
    assert finding.fix == {'entity': made['resource'], 'attributePath': [PRESSURE],
                           'file': made['file'], 'index': 1, 'old': 'left'}


def test_an_explicit_none_and_its_fix(case):
    root, made = case
    _edit(made, lambda instances: instances[0].update(datasetId='@none'))
    [finding] = _found(root, 'dataset-none')
    fix = finding.fix
    set_dataset_id(load(root), fix['entity'], fix['attributePath'], fix['old'], '@none',
                   file=fix['file'])
    assert 'datasetId' not in _written({'file': made['file'], 'resource': made['resource']})[0]
    assert not _found(root, 'dataset-none')


def test_two_unstamped_instances_of_one_datasetid_and_their_fix(case):
    root, made = case
    _edit(made, lambda instances: instances.append(dict(instances[1])))
    [finding] = _found(root, 'dataset-duplicate')
    assert finding.fix['index'] == 2 and finding.fix['old'] == 'urn:my-model:dataset:2'
    assert 'keeps only the last' in finding.message
    fix = finding.fix
    set_dataset_id(load(root), fix['entity'], fix['attributePath'], fix['old'],
                   'urn:sensor:third', file=fix['file'], index=fix['index'])
    assert [i.get('datasetId') for i in _written(made)] == [
        None, 'urn:my-model:dataset:2', 'urn:sensor:third']
    assert not _found(root, 'dataset-duplicate')


def test_later_observations_are_no_duplicate(case):
    root, made = case
    _edit(made, lambda instances: instances.append(
        dict(instances[1], observedAt='2026-01-02T00:00:00.000Z')))
    assert not _found(root, 'dataset-duplicate')


def test_unstamped_copies_are_one_too(case):
    root, made = case

    def unstamped(instances):
        for instance in instances:
            instance.pop('observedAt', None)
        instances.append(dict(instances[0]))
    _edit(made, unstamped)
    [finding] = _found(root, 'dataset-duplicate')
    assert 'the default instance without observedAt' in finding.message


def test_the_quick_fixes(case):
    from lsprotocol import types

    from semforge.editor.server import _fixes_for

    def fixes(code, **data):
        diagnostic = types.Diagnostic(
            range=types.Range(types.Position(0, 0), types.Position(0, 1)), message='',
            data=dict(data, code=code, entity='urn:x', attributePath=[PRESSURE], file='f'))
        return [(a.title, a.command.command, a.command.arguments[0]) for a in
                _fixes_for(diagnostic, 'file:///pkg/shacl.ttl')]

    [(title, command, argument)] = fixes('dataset-none', old='@none')
    assert command == 'semforge.setDatasetId' and argument['new'] == '@none'
    [(title, _, argument)] = fixes('dataset-not-iri', old='left')
    assert title == 'Change the datasetId…' and 'new' not in argument
    [(title, _, argument)] = fixes('dataset-duplicate', old='@none', index=2)
    assert argument['index'] == 2 and argument['old'] == '@none'
    register, change = fixes('dataset-unregistered', old='urn:x:1', namespace='urn:x:')
    assert register[:2] == ('Register a prefix for urn:x:…', 'semforge.addNamespace')
    assert register[2]['namespace'] == 'urn:x:'
    assert change[1] == 'semforge.setDatasetId' and change[2]['old'] == 'urn:x:1'


# --- the tree --------------------------------------------------------------------------

def test_the_tree_names_the_default_instance_and_knows_the_others(case):
    root, made = case
    rows = []

    def walk(nodes):
        for node in nodes:
            rows.append(node)
            walk(node.children)
    walk(build_suite(load(root)))
    attribute = next(n for n in rows if n.kind == 'attribute' and n.label == 'hasPressure'
                     and n.entity == made['resource'])
    assert '2 instances' in attribute.detail
    default, other = attribute.children
    assert (default.label, other.label) == ('hasPressure', 'hasPressure[myModelDataset:2]')
    assert default.detail == '1.0 · Property · default'
    assert other.detail.startswith('1.0 · Property')
    assert set(default.datasets) == {'@none', 'urn:my-model:dataset:2'}


def test_generated_datasetids_register_their_namespace(case):
    from semforge.package.prefixes import declared_prefixes

    root, _ = case
    assert declared_prefixes(root)['myModelDataset'] == 'urn:my-model:dataset:'


def test_a_datasetid_in_no_registered_namespace_is_refused(case):
    root, made = case
    with pytest.raises(PackageError, match='no namespace this package registers'):
        add_instance(load(root), made['resource'], [PRESSURE], 'urn:elsewhere:x',
                     file=made['file'])


def test_one_already_in_the_data_is_reported_with_a_register_fix(case):
    from semforge.sanity import sanity

    root, made = case
    _edit(made, lambda instances: instances[1].update(datasetId='urn:elsewhere:x'))
    [finding] = [f for f in sanity(load(root)) if f.code == 'dataset-unregistered']
    assert finding.fix['namespace'] == 'urn:elsewhere:'
    assert 'hasPressure[prefix:name]' in finding.message


# --- the extension ---------------------------------------------------------------------

DRIVE = os.path.join(os.path.dirname(__file__), '..', 'harness', 'drive.js')
SRC = os.path.join(os.path.dirname(__file__), '..', '..', 'vscode', 'src')
ROW = {'kind': 'dataset', 'label': '7.0', 'entity': 'urn:m:1', 'attributePath': [PRESSURE],
       'datasetId': '@none', 'datasets': ['@none', 'urn:m:1:hasPressure:2'], 'file': 'case.jsonld',
       'editable': True, 'children': []}


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


def test_add_instance_suggests_a_datasetid_the_attribute_has_not(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.addInstance',
        'node': {'raw': ROW, 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['sensor:hasPressure-2'], 'inputs': ['urn-left'],
        'replies': {'semforge/addInstance': {'ok': True, 'instances': 3},
                    'semforge/vocabularyNamespaces': {'namespaces': [
                        {'prefix': 'sensor', 'namespace': 'urn:sensor:', 'terms': 0,
                         'default': False}]}}})
    labels = [i['label'] for i in seen['quickPicks'][0]['items']]
    assert 'Default instance' not in labels, 'a new instance is never the default one'
    assert '$(edit) Type a full IRI…' not in labels, 'only a registered namespace'
    assert seen['inputs'][0]['value'] == 'hasPressure-2'
    assert _asked(seen, 'semforge/addInstance') == [{
        'uri': 'file:///pkg/shacl.ttl', 'entity': 'urn:m:1', 'attributePath': [PRESSURE],
        'datasetId': 'urn:sensor:urn-left', 'file': 'case.jsonld'}]


def test_change_datasetid_from_a_row_can_make_it_the_default(tmp_path):
    # No default instance yet, so becoming it is offered.
    row = dict(ROW, datasetId='urn:m:1:hasPressure:2',
               datasets=['urn:m:1:hasPressure:2', 'urn:sensor:b'])
    seen = _drive(tmp_path, {
        'command': 'semforge.setDatasetId',
        'node': {'raw': row, 'packageUri': 'file:///pkg/shacl.ttl'},
        'picks': ['Default instance'],
        'replies': {'semforge/setDatasetId': {'ok': True, 'changed': 1}}})
    assert _asked(seen, 'semforge/setDatasetId') == [{
        'uri': 'file:///pkg/shacl.ttl', 'new': '@none', 'entity': 'urn:m:1',
        'attributePath': [PRESSURE], 'file': 'case.jsonld', 'old': 'urn:m:1:hasPressure:2'}]


def test_a_quick_fix_with_its_answer_asks_nothing(tmp_path):
    seen = _drive(tmp_path, {
        'command': 'semforge.setDatasetId',
        'args': [],
        'node': {'packageUri': 'file:///pkg/shacl.ttl', 'entity': 'urn:m:1',
                 'attributePath': [PRESSURE], 'file': 'case.jsonld', 'old': '@none',
                 'new': '@none'},
        'replies': {'semforge/setDatasetId': {'ok': True, 'changed': 1}}})
    assert not seen['inputs']
    assert _asked(seen, 'semforge/setDatasetId')[0]['new'] == '@none'


# --- the case page: names, the right instance, removing just it ------------------------

@pytest.fixture
def observed(case):
    """The default instance observed twice, then myModelDataset:2 -- three
    JSON members, two instances: a row matched by position lands wrong."""
    from semforge.cooked.casepage import build_case_page

    root, made = case

    def observe(instances):
        instances[0]['observedAt'] = '2026-01-01T00:00:00.000Z'
        instances.insert(1, dict(instances[0], observedAt='2026-01-02T00:00:00.000Z'))
    _edit(made, observe)
    page = build_case_page(load(root), made['case'])
    card = next(c for f in page['files'] for c in f['cards'] if c['id'] == made['resource'])
    return page, card


def test_case_rows_read_attribute_prefix_name(observed):
    _, card = observed
    rows = [r for r in card['attributes'] if r['name'] == 'hasPressure']
    assert [r['display'] for r in rows] == ['hasPressure', 'hasPressure',
                                            'hasPressure[myModelDataset:2]']
    assert {r['instances'] for r in rows} == {2}


def test_case_rows_are_joined_to_their_own_datasetid(observed):
    _, card = observed
    row = next(r for r in card['attributes'] if r.get('dataset') == 'urn:my-model:dataset:2')
    assert row['node']['kind'] == 'dataset'
    assert row['node']['datasetId'] == 'urn:my-model:dataset:2'


def test_remove_on_a_case_row_takes_just_that_instance(tmp_path, observed):
    page, card = observed
    c = next(i for f in page['files'] for i, x in enumerate(f['cards']) if x is card)
    r = next(i for i, x in enumerate(card['attributes'])
             if x.get('dataset') == 'urn:my-model:dataset:2')
    seen = _drive(tmp_path, {
        'command': 'semforge.openCasePage',
        'node': {'raw': {'kind': 'example', 'label': 'two.jsonld', 'file': page['file'],
                         'children': []}, 'packageUri': 'file:///pkg/shacl.ttl'},
        'webviewMessages': [{'command': 'rowMenu', 'at': f'0.{c}.{r}'}],
        'picks': ['$(trash) Remove hasPressure[myModelDataset:2]'],
        'replies': {'semforge/casePage': dict(page, ok=True)}})
    items = {i['label']: i.get('description') for i in seen['quickPicks'][0]['items']}
    assert items['$(trash) Remove hasPressure[myModelDataset:2]'] == 'this instance only'
    assert items['$(trash) Remove hasPressure…'] == 'all 2 instances, from this entity'
    ran = [e['args'][0]['raw'] for e in seen['executed']
           if e['command'] == 'semforge.removeCaseValue']
    assert ran and ran[0]['kind'] == 'dataset' and ran[0]['datasetId'] == 'urn:my-model:dataset:2'
