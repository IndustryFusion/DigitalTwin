"""Merge into…: fold one shape into another with the same targets.

SHACL conjoins shapes on the same nodes, so a merge must change nothing a
validator decides. That is what these check, on the case that asked for it
and on the kms: the same violations (shape names aside) and every test case
with the same outcome, before and after.
"""

import shutil

import pytest
from rdflib import Graph, URIRef

from semforge.cooked.merge import candidates, merge_shape, plan
from semforge.errors import PackageError
from semforge.expect.runner import run_tests
from semforge.expect.store import compose, load_expectations
from semforge.package import load
from semforge.sanity import known_constraints
from semforge.validate import validate_package
from semforge.validate.orchestrator import validate_graphs

BASE = 'https://industryfusion.github.io/contexts/example/v0/base_shacl/'
FILTER = 'https://industryfusion.github.io/contexts/example/v0/filter_shacl/'


def _verdicts(root):
    """Every violation in the model and in every case, without shape names,
    and every case's outcome."""
    package = load(root)
    found = {('model', str(v.resource), v.attribute, v.component)
             for v in validate_package(package, strict=False).violations}
    examples = load_expectations(package.path).examples
    reports = []
    for example in examples:
        report = validate_graphs(compose(package, example), package.shapes,
                                 package.knowledge, strict=False)
        reports.append((example, report))
        found |= {(example.path, str(v.resource), v.attribute, v.component)
                  for v in report.violations}
    outcomes = {o.example: o.passed for o in run_tests(reports, known_constraints(package))}
    return found, outcomes


@pytest.fixture
def kms(tmp_path, corpus_path):
    target = tmp_path / 'kms'
    shutil.copytree(corpus_path, target, symlinks=False,
                    ignore=shutil.ignore_patterns('.semforge'))
    return str(target)


@pytest.fixture
def two_machine_shapes(tmp_path):
    """The package that asked: two shapes on hasPressure of Machine."""
    from semforge.cooked.constrain import add_attribute_constraint
    from semforge.cooked.knowledge import add_attribute_term
    from semforge.cooked.shapes import add_shape
    from semforge.cooked.tree import add_constraint
    from semforge.package.scaffold import create_package

    root = str(tmp_path / 'my-model')
    create_package(root)
    package = load(root)
    machine = next(str(c) for c in package.knowledge.subjects() if str(c).endswith('/Machine'))
    first = next(str(s) for s in package.shapes.subjects() if str(s).endswith('/MachineShape'))
    add_attribute_term(package, 'hasPressure', 'Property', machine)
    add_attribute_constraint(load(root), first, 'hasPressure', required=False,
                             datatype='xsd:double')
    path = ['myModelEntities:hasPressure']
    add_constraint(load(root), first, path, 'sh:minInclusive', '0')
    second = add_shape(load(root), 'MachineShape2', 'class', machine)['iri']
    add_attribute_constraint(load(root), second, 'hasPressure', required=True)
    add_constraint(load(root), second, path, 'sh:maxExclusive', '100')
    return root, machine, first, second


def test_the_two_machine_shapes_merge_without_changing_a_verdict(two_machine_shapes):
    from semforge.cooked.typepage import build_type_page

    root, machine, first, second = two_machine_shapes
    assert candidates(load(root), second) == [
        {'iri': first, 'name': 'myModelShacl:MachineShape'}]
    before = _verdicts(root)
    done = merge_shape(load(root), second, first)
    assert _verdicts(root) == before
    graph = Graph().parse(f'{root}/shacl.ttl', format='turtle')
    assert (URIRef(second), None, None) not in graph
    row = next(r for r in build_type_page(load(root), machine)['attributes']
               if r['label'] == 'hasPressure')
    assert 'contributions' not in row, 'one shape now'
    assert row['presence'] == 'required · one' and '< 100' in row['value']
    assert any('replaces the weaker sh:minCount 0' in s for s in done['said'])


def test_a_stricter_count_replaces_the_weaker_one_in_place(two_machine_shapes):
    root, _, first, second = two_machine_shapes
    merge_shape(load(root), second, first)
    with open(f'{root}/shacl.ttl') as handle:
        text = handle.read()
    block = text[text.index('sh:path myModelEntities:hasPressure'):]
    block = block[:block.index('sh:property')]
    assert 'sh:minCount 1' in block and 'sh:minCount 0' not in block


@pytest.mark.parametrize('source, into', [
    (BASE + 'StateOnFilterShape', BASE + 'FilterShape'),       # a SPARQL constraint moves
    (FILTER + 'CartridgeShape', BASE + 'CartridgeShape'),      # same attribute, two shapes
    (BASE + 'TimestampCartridgeFromRulesShape', BASE + 'CartridgeShape'),   # a rule moves
])
def test_kms_merges_change_no_verdict_and_no_outcome(kms, source, into):
    before = _verdicts(kms)
    merge_shape(load(kms), source, into)
    assert _verdicts(kms) == before
    assert (URIRef(source), None, None) not in load(kms).shapes


def test_asserts_naming_the_merged_shape_are_renamed(kms):
    """test_CartridgeShape asserts on a shape; after merging it away, the
    assert names the shape it went into and still holds."""
    from semforge.validate.normalise import curie

    package = load(kms)
    asserted = {str(item['constraint']).split('/')[0]
                for e in load_expectations(kms).examples for item in e.asserts}
    pairs = [(BASE + 'CartridgeShape', FILTER + 'CartridgeShape'),
             (FILTER + 'CartridgeShape', BASE + 'CartridgeShape')]
    source, into = next((s, i) for s, i in pairs if curie(package.shapes, URIRef(s)) in asserted)
    name = curie(package.shapes, URIRef(source))
    done = merge_shape(package, source, into)
    assert done['asserts'] >= 1
    names = {str(item['constraint']).split('/')[0]
             for e in load_expectations(kms).examples for item in e.asserts}
    assert name not in names
    _, outcomes = _verdicts(kms)
    assert all(outcomes.values()), outcomes


def test_shapes_selecting_different_nodes_are_not_merged(kms):
    with pytest.raises(PackageError, match='select different nodes'):
        plan(load(kms), BASE + 'FilterShape', BASE + 'MachineShape')
    offered = [c['iri'] for c in candidates(load(kms), BASE + 'FilterShape')]
    assert BASE + 'MachineShape' not in offered


def test_a_shape_with_its_own_settings_is_not_merged(two_machine_shapes):
    root, _, first, second = two_machine_shapes
    with open(f'{root}/shacl.ttl') as handle:
        text = handle.read()
    name = f'myModelShacl:{second.rsplit("/", 1)[-1]}'     # with its random part
    assert f'{name} a sh:NodeShape ;' in text
    text = text.replace(f'{name} a sh:NodeShape ;',
                        f'{name} a sh:NodeShape ;\n    sh:severity sh:Warning ;')
    with open(f'{root}/shacl.ttl', 'w') as handle:
        handle.write(text)
    with pytest.raises(PackageError, match='sh:severity'):
        plan(load(root), second, first)


def test_a_shape_reached_through_sh_node_is_not_merged(two_machine_shapes):
    root, machine, first, second = two_machine_shapes
    with open(f'{root}/shacl.ttl', 'a') as handle:
        handle.write(f'\n<https://example.org/x/User> a <http://www.w3.org/ns/shacl#NodeShape> ;\n'
                     f'    <http://www.w3.org/ns/shacl#targetClass> <{machine}> ;\n'
                     f'    <http://www.w3.org/ns/shacl#node> <{second}> .\n')
    with pytest.raises(PackageError, match='sh:node'):
        plan(load(root), second, first)
