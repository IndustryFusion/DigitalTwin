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

"""What a shape names by an IRI reaches pyshacl (issue #1105).

The shapes of a validation are handed to pyshacl as a part of the shapes
graph (validate/shapes.subgraph_for). Each construct here is validated as
pyshacl validates it on the WHOLE shapes graph -- the reference -- and its
results are complete: every result maps onto a constraint the enumerator
expected (no SF-ENUM-001).
"""

import os

import pyshacl
import pytest
from click.testing import CliRunner
from rdflib import Graph, URIRef
from rdflib.namespace import SH

from semforge.cli.main import cli
from semforge.editor.incremental import changed_shapes
from semforge.package.scaffold import create_package
from semforge.rdfio.frozen import freeze
from semforge.validate import shapes as shape_views
from semforge.validate.applicable import constraints_of_shape, custom_components, focus_nodes
from semforge.validate.normalise import local
from semforge.validate.orchestrator import validate_graphs
from semforge.validate.readset import anchored
from semforge.validate.results import Status

EX = 'https://example.org/'
HEAD = '''@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
'''
DATA = 'ex:a a ex:T ; ex:p 1 . ex:b a ex:T . ex:c a ex:T ; ex:p 2, 3 .'

# The table of the issue, and what else a shape names by an IRI.
CASES = {
    'a custom constraint component': '''
        ex:CC a sh:ConstraintComponent ; sh:parameter [ sh:path ex:par ] ;
            sh:nodeValidator [ a sh:SPARQLSelectValidator ; sh:message "m" ;
                sh:select "SELECT $this WHERE { $this <https://example.org/p> ?v }" ] .
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; ex:par 1 .''',
    'a component of a subclass of sh:ConstraintComponent, with a parameter value': '''
        ex:Kind rdfs:subClassOf sh:ConstraintComponent .
        ex:CC a ex:Kind ; sh:parameter [ sh:path ex:limit ] ;
            sh:validator [ a sh:SPARQLAskValidator ; sh:message "m" ;
                sh:ask "ASK { FILTER (?value < $limit) }" ] .
        ex:S a sh:NodeShape ; sh:targetClass ex:T ;
            sh:property [ sh:path ex:p ; ex:limit 2 ] .''',
    'sh:sparql naming the constraint by an IRI': '''
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:sparql ex:C .
        ex:C sh:message "m" ; sh:select "SELECT $this WHERE { $this <https://example.org/p> ?v }" .''',
    'sh:property naming the property shape by an IRI': '''
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
        ex:P sh:path ex:p ; sh:minCount 1 ; sh:maxCount 1 .''',
    'sh:target naming a SPARQL target by an IRI': '''
        ex:S a sh:NodeShape ; sh:target ex:G ; sh:class ex:Nope .
        ex:G a sh:SPARQLTarget ; sh:select "SELECT ?this WHERE { ?this <https://example.org/p> ?v }" .''',
    'an instance of a sh:SPARQLTargetType': '''
        ex:TT a sh:SPARQLTargetType ; rdfs:subClassOf sh:Target ;
            sh:parameter [ sh:path ex:val ] ;
            sh:select "SELECT ?this WHERE { ?this <https://example.org/p> $val }" .
        ex:S a sh:NodeShape ; sh:target [ a ex:TT ; ex:val 1 ] ; sh:class ex:Nope .''',
    'sh:or of shapes named by an IRI': '''
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:or ( ex:A ex:B ) .
        ex:A sh:property [ sh:path ex:p ; sh:minCount 2 ] .
        ex:B sh:property [ sh:path ex:p ; sh:hasValue 1 ] .''',
    'sh:not naming a shape': '''
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:not ex:N .
        ex:N sh:property [ sh:path ex:p ; sh:minCount 2 ] .''',
    'sh:in naming its list by an IRI': '''
        ex:S a sh:NodeShape ; sh:targetClass ex:T ;
            sh:property [ sh:path ex:p ; sh:in ex:list ] .
        ex:list rdf:first 2 ; rdf:rest ( 3 ) .''',
    'a SPARQL function a constraint calls': '''
        ex:twice a sh:SPARQLFunction ; sh:parameter [ sh:path ex:x ; sh:datatype xsd:integer ] ;
            sh:returnType xsd:integer ; sh:select "SELECT (?x * 2 AS ?result) WHERE {}" .
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:sparql [ sh:message "m" ;
            sh:select """SELECT $this WHERE { $this <https://example.org/p> ?v
                FILTER (<https://example.org/twice>(?v) = 2) }""" ] .''',
}


def graph(text):
    return Graph().parse(data=HEAD + text, format='turtle')


def whole(shapes, data):
    """(focus node, component) of every result pyshacl gives on the whole
    shapes graph."""
    copy = Graph()
    for triple in data:
        copy.add(triple)
    _, report, _ = pyshacl.validate(copy, shacl_graph=graph_copy(shapes), advanced=True,
                                    inplace=True, do_owl_imports=False)
    return sorted({(str(report.value(r, SH.focusNode)),
                    local(report.value(r, SH.sourceConstraintComponent)))
                   for r in report.objects(None, SH.result)})


def graph_copy(shapes):
    out = Graph()
    for prefix, namespace in shapes.namespaces():
        out.bind(prefix, namespace)
    for triple in shapes:
        out.add(triple)
    return out


def violated(report):
    return sorted({(r.resource, r.component) for r in report.results
                   if r.status is Status.VIOLATED})


@pytest.mark.parametrize('frozen', [False, True], ids=['graph', 'frozen graph'])
@pytest.mark.parametrize('case', CASES)
def test_as_pyshacl_on_the_whole_shapes_graph(case, frozen):
    shapes, data = graph(CASES[case]), graph(DATA)
    expected = whole(shapes, data)
    assert expected, 'the case must violate something'
    report = validate_graphs(data, freeze(shapes) if frozen else shapes)
    assert violated(report) == expected
    assert report.complete
    assert not [d for d in report.diagnostics if d.code == 'SF-ENUM-001']


def test_the_conformant_ones_are_said_to_conform():
    """The custom component is evaluated where it does not fire as well."""
    report = validate_graphs(graph(DATA), graph(CASES['a custom constraint component']))
    conformant = {r.resource for r in report.results
                  if r.status is Status.CONFORMANT and r.component == 'CC'}
    assert conformant == {EX + 'b'}


def test_a_custom_component_is_a_constraint_of_the_shapes_that_use_it():
    shapes = graph(CASES['a custom constraint component'] + '''
        ex:CC2 a sh:ConstraintComponent ; sh:parameter [ sh:path ex:par2 ] , [ sh:path ex:opt ; sh:optional true ] ;
            sh:propertyValidator [ a sh:SPARQLSelectValidator ; sh:select "SELECT $this WHERE { }" ] .
        ex:U a sh:NodeShape ; sh:targetClass ex:T ; ex:par2 1 ;
            sh:property [ sh:path ex:p ; ex:par2 1 ; ex:opt 1 ] ;
            sh:property [ sh:path ex:q ; ex:opt 1 ] .''')
    names = {c[0] for c in custom_components(shapes)}
    assert names == {'CC', 'CC2'}
    assert ('', 'CC') in constraints_of_shape(URIRef(EX + 'S'), shapes)
    found = constraints_of_shape(URIRef(EX + 'U'), shapes)
    # a property validator only on a property shape, and only with every
    # mandatory parameter
    assert ('p', 'CC2') in found
    assert ('', 'CC2') not in found
    assert ('q', 'CC2') not in found


def test_shacls_own_components_are_not_custom():
    shapes = graph('sh:MinCountConstraintComponent a sh:ConstraintComponent ; '
                   'sh:parameter [ sh:path sh:minCount ] ; sh:propertyValidator [ ] .')
    assert custom_components(shapes) == []


def test_a_named_property_shape_shared_by_two_shapes_belongs_to_the_one_that_targets_the_entity():
    shapes = graph('''
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
        ex:R a sh:NodeShape ; sh:targetClass ex:U ; sh:property ex:P .
        ex:P sh:path ex:p ; sh:minCount 1 .''')
    data = graph('ex:a a ex:T . ex:u a ex:U .')
    report = validate_graphs(data, shapes)
    assert sorted((r.resource, r.shape) for r in report.results
                  if r.status is Status.VIOLATED) == [(EX + 'a', EX + 'S'), (EX + 'u', EX + 'R')]
    assert report.complete


def test_the_subgraph_holds_only_what_the_shapes_reach():
    shapes = graph(CASES['sh:property naming the property shape by an IRI'] + '''
        ex:Other a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:OP .
        ex:OP sh:path ex:q ; sh:minCount 1 .
        ex:T rdfs:label "a class, named by sh:targetClass" .''')
    part = shape_views.subgraph_for(shapes, [URIRef(EX + 'S')])
    subjects = set(part.subjects())
    assert {URIRef(EX + 'S'), URIRef(EX + 'P')} <= subjects
    assert not subjects & {URIRef(EX + 'Other'), URIRef(EX + 'OP'), URIRef(EX + 'T')}
    # the data terms are not followed: ex:p is no subject of the part
    assert URIRef(EX + 'p') not in subjects


def test_the_subgraph_is_kept_per_shape_set():
    shapes = freeze(graph(CASES['a custom constraint component']))
    kept = shape_views.subgraph_for(shapes, [URIRef(EX + 'S')])
    assert shape_views.subgraph_for(shapes, [URIRef(EX + 'S')]) is kept
    assert shape_views.globals_of(shapes) is shape_views.globals_of(shapes)
    assert custom_components(shapes) is custom_components(shapes)


def test_a_cycle_through_names_ends():
    shapes = graph('''
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:node ex:N .
        ex:N sh:or ( ex:S ex:M ) . ex:M sh:node ex:N ; sh:minCount 0 .''')
    part = shape_views.subgraph_for(shapes, [URIRef(EX + 'S')])
    assert {URIRef(EX + n) for n in 'SNM'} <= set(part.subjects())


def test_a_target_type_finds_its_focus_nodes():
    shapes = graph(CASES['an instance of a sh:SPARQLTargetType'])
    assert focus_nodes(URIRef(EX + 'S'), shapes, graph(DATA)) == {URIRef(EX + 'a')}


def test_a_validator_unanchors_the_knowledge():
    """A validator's query can read any triple of the knowledge, as a SPARQL
    constraint can: the knowledge is not narrowed to what the data reaches."""
    assert not anchored(graph(CASES['a custom constraint component']))


@pytest.mark.parametrize('changed', ['component', 'function', 'target type'])
def test_changing_a_global_revalidates_everything(changed):
    before = {
        'component': CASES['a custom constraint component'],
        'function': CASES['a SPARQL function a constraint calls'],
        'target type': CASES['an instance of a sh:SPARQLTargetType'],
    }[changed]
    after = before.replace('"m"', '"n"') if changed == 'component' else \
        before.replace('* 2', '* 3') if changed == 'function' else before.replace('$val', '?other')
    assert before != after
    assert changed_shapes(graph(before), graph(after)) is None


def test_changing_a_named_shape_only_revalidates_who_names_it():
    before = graph(CASES['sh:property naming the property shape by an IRI'] +
                   'ex:Z a sh:NodeShape ; sh:targetClass ex:T ; sh:minCount 0 .')
    after = graph(CASES['sh:property naming the property shape by an IRI'].replace('sh:maxCount 1', 'sh:maxCount 2') +
                  'ex:Z a sh:NodeShape ; sh:targetClass ex:T ; sh:minCount 0 .')
    assert changed_shapes(before, after) == {EX + 'P', EX + 'S'}


# --- a package's tests -------------------------------------------------------

HOT = '''
freshShacl:HotComponent a sh:ConstraintComponent ;
    sh:parameter [ sh:path freshShacl:hotAbove ] ;
    sh:nodeValidator [ a sh:SPARQLSelectValidator ;
        sh:message "hotter than {$hotAbove}" ;
        sh:select """SELECT $this WHERE {
            $this <https://example.org/fresh/entities/hasTemperature>/<https://uri.etsi.org/ngsi-ld/hasValue> ?t .
            FILTER (?t > $hotAbove) }""" ] .
freshShacl:MachineShape freshShacl:hotAbove 100.0 .
'''


@pytest.fixture
def fresh(tmp_path):
    root = str(tmp_path / 'fresh')
    create_package(root, name='fresh', layout='flat')
    with open(os.path.join(root, 'shacl.ttl'), 'a', encoding='utf-8') as handle:
        handle.write(HOT)
    return root


def assert_hot(root, resource='urn:fresh:machine:1'):
    path = os.path.join(root, 'examples', 'test_MachineShape', 'bad', 'expectations.yaml')
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text + f'''      - constraint: freshShacl:MachineShape/HotComponent
        resource: {resource}
''')


def test_verify_tests_checks_a_custom_component(fresh):
    """The case that is too hot asserts the custom component: it fires."""
    assert_hot(fresh)
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code == 0, result.output


def test_verify_tests_fails_where_the_custom_component_does_not_fire(fresh):
    """Above 200 the component does not fire on 180: the assert of it fails
    the case, naming it."""
    with open(os.path.join(fresh, 'shacl.ttl'), encoding='utf-8') as handle:
        text = handle.read()
    with open(os.path.join(fresh, 'shacl.ttl'), 'w', encoding='utf-8') as handle:
        handle.write(text.replace('freshShacl:hotAbove 100.0', 'freshShacl:hotAbove 200.0'))
    assert_hot(fresh)
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code != 0
    assert 'asserted freshShacl:MachineShape/HotComponent to fire on urn:fresh:machine:1, but it did not' \
        in result.output, result.output


def test_a_named_property_shape_inside_a_named_property_shape():
    """An attribute node, as NGSI-LD writes one, constrained by a property
    shape named inside a named property shape: attributed to the node shape."""
    shapes = graph('''
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
        ex:P sh:path ex:attr ; sh:minCount 1 ; sh:property ex:Q .
        ex:Q sh:path ex:val ; sh:minCount 1 .''')
    data = graph('ex:a a ex:T ; ex:attr [ ex:val 1 ] . ex:b a ex:T ; ex:attr [ ] . ex:c a ex:T .')
    report = validate_graphs(data, shapes)
    assert report.complete
    fired = {(r.resource, r.shape) for r in report.results if r.status is Status.VIOLATED}
    assert fired == {(EX + 'b', EX + 'S'), (EX + 'c', EX + 'S')}


def test_check_knows_the_custom_component(fresh):
    """semforge check takes an assert of the component as one of a declared
    constraint, and the parameter's sh:path for no attribute."""
    assert_hot(fresh)
    result = CliRunner().invoke(cli, ['check', fresh])
    assert 'HotComponent' not in result.output, result.output
    assert 'hotAbove' not in result.output, result.output
    with open(os.path.join(fresh, 'examples', 'test_MachineShape', 'bad', 'expectations.yaml'),
              'a', encoding='utf-8') as handle:
        handle.write('      - constraint: freshShacl:MachineShape/NoSuchComponent\n'
                     '        resource: urn:fresh:machine:1\n')
    result = CliRunner().invoke(cli, ['check', fresh])
    assert 'asserts freshShacl:MachineShape/NoSuchComponent, a constraint no shape declares' in result.output
    assert 'freshShacl:MachineShape/HotComponent' in result.output


# --- shared parts, shapes reached by name, components ----------------------------

SHARED = '''
    ex:N1 a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
    ex:N2 a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:P .
    ex:P sh:path ex:p ; sh:minCount 1 ; sh:maxCount 1 .'''


@pytest.mark.parametrize('frozen', [False, True], ids=['graph', 'frozen graph'])
def test_a_part_shared_by_two_shapes_on_the_same_entity_is_violated_for_both(frozen):
    shapes = graph(SHARED)
    report = validate_graphs(graph('ex:a a ex:T . ex:b a ex:T ; ex:p 1, 2 . ex:c a ex:T ; ex:p 1 .'),
                             freeze(shapes) if frozen else shapes)
    assert report.complete
    fired = sorted((r.resource, r.component, r.shape) for r in report.results
                   if r.status is Status.VIOLATED)
    assert fired == sorted((EX + entity, component, EX + shape) for shape in ('N1', 'N2')
                           for entity, component in (('a', 'MinCountConstraintComponent'),
                                                     ('b', 'MaxCountConstraintComponent')))
    conformant = {(r.resource, r.component, r.shape) for r in report.results
                  if r.status is Status.CONFORMANT}
    assert not {(entity, component, shape) for entity, component, shape in fired} & conformant
    assert (EX + 'c', 'MinCountConstraintComponent', EX + 'N2') in conformant


def test_the_focus_nodes_of_the_holders_are_found_once_per_validation(monkeypatch):
    from semforge.validate.adapters import pyshacl_adapter

    calls = []
    real = pyshacl_adapter.focus_nodes

    def counting(shape, *args, **kwargs):
        calls.append(shape)
        return real(shape, *args, **kwargs)

    monkeypatch.setattr(pyshacl_adapter, 'focus_nodes', counting)
    data = graph(' '.join(f'ex:e{n} a ex:T .' for n in range(50)))
    report = validate_graphs(data, freeze(graph(SHARED)))
    assert len([r for r in report.results if r.status is Status.VIOLATED]) == 100
    assert sorted(calls) == [URIRef(EX + 'N1'), URIRef(EX + 'N2')]


VIEWS = '''@prefix semforge: <https://industryfusion.github.io/semforge/v0/> .
    ex:N1 a sh:NodeShape ; sh:targetClass ex:T ; sh:or ( ex:M ex:M2 ) .
    ex:M a sh:NodeShape ; sh:targetClass ex:T ; semforge:dataView "history" ;
        sh:property [ sh:path ex:p ; sh:maxCount 1 ] .
    ex:M2 sh:property [ sh:path ex:q ; sh:minCount 1 ] .'''


def test_a_shape_reached_by_name_is_not_evaluated_on_its_own_in_another_view():
    report = validate_graphs(graph('ex:b a ex:T ; ex:p 1, 2 .'), graph(VIEWS))
    assert report.complete
    fired = sorted((r.shape, r.component, r.view) for r in report.results
                   if r.status is Status.VIOLATED)
    # the sh:or on the current view, and M once, on its own view
    assert fired == [(EX + 'M', 'MaxCountConstraintComponent', 'history'),
                     (EX + 'N1', 'OrConstraintComponent', 'current')]


def test_only_evaluates_only_what_was_asked_for():
    shapes = graph('''
        ex:N1 a sh:NodeShape ; sh:targetClass ex:T ; sh:not ex:M .
        ex:M a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:maxCount 1 ] .''')
    report = validate_graphs(graph('ex:b a ex:T ; ex:p 1, 2 . ex:c a ex:T .'), shapes, only={EX + 'N1'})
    assert report.complete
    assert {r.shape for r in report.results} == {EX + 'N1'}


def test_a_class_reached_by_name_is_not_a_target_there():
    shapes = graph('''@prefix owl: <http://www.w3.org/2002/07/owl#> .
        ex:N1 a sh:NodeShape ; sh:targetClass ex:U ; sh:node ex:T .
        ex:T a sh:NodeShape, owl:Class ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .''')
    part = shape_views.subgraph_for(shapes, [URIRef(EX + 'N1')])
    assert (URIRef(EX + 'T'), SH.property, None) in part
    assert (URIRef(EX + 'T'), None, URIRef('http://www.w3.org/2002/07/owl#Class')) not in part
    assert (URIRef(EX + 'N1'), SH.targetClass, URIRef(EX + 'U')) in part


def test_a_component_two_classes_down_is_no_component_for_pyshacl_nor_here():
    shapes = graph('''
        ex:Kind rdfs:subClassOf sh:ConstraintComponent . ex:Sub rdfs:subClassOf ex:Kind .
        ex:CC a ex:Sub ; sh:parameter [ sh:path ex:par ] ;
            sh:nodeValidator [ a sh:SPARQLSelectValidator ;
                sh:select "SELECT $this WHERE { $this <https://example.org/p> ?v }" ] .
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; ex:par 1 .''')
    data = graph(DATA)
    assert whole(shapes, data) == []
    assert custom_components(shapes) == []
    report = validate_graphs(data, shapes)
    assert not [r for r in report.results if r.component == 'CC']
