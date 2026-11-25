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

"""The prefixes of a query whose sh:prefixes names an IRI (issue #1098).

SHACL 5.2.1: the declarations of the nodes `sh:prefixes` names and of what they
import, in the shapes graph. `zz` is bound by no Turtle prefix here: only
sh:declare can define it.
"""

import os

import pyshacl
import pytest
from click.testing import CliRunner
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, SH

from semforge.cli.main import cli
from semforge.cooked import sparqlbench
from semforge.cooked.shapepage import _query
from semforge.package.loader import load
from semforge.package.offline import network_uses
from semforge.package.scaffold import create_package
from semforge.rdfio.frozen import freeze
from semforge.rules import run_rules
from semforge.validate import prefixes
from semforge.validate import shapes as shape_views
from semforge.validate.applicable import focus_nodes
from semforge.validate.orchestrator import validate_graphs
from semforge.validate.readset import read_set
from semforge.validate.results import Status

EX = 'https://example.org/'
HEAD = '''@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
'''


def declare(prefix='zz', namespace=EX):
    return f'sh:declare [ sh:prefix "{prefix}" ; sh:namespace "{namespace}"^^xsd:anyURI ]'


ZZ = declare()
# What sh:prefixes names, and what the shapes graph says of it.
HOLDERS = {
    'IRI': ('ex:ns', f'ex:ns {ZZ} .'),
    'ontology': ('ex:ont', f'ex:ont a owl:Ontology ; {ZZ} .'),
    'declaration that is an IRI': (
        'ex:ont', f'ex:ont sh:declare ex:zz . ex:zz sh:prefix "zz" ; sh:namespace "{EX}"^^xsd:anyURI .'),
    'several': ('ex:other, ex:ns', f'ex:other {declare("oo", "urn:o:")} . ex:ns {ZZ} .'),
    'several ontologies': ('ex:other, ex:ns', f'ex:other a owl:Ontology ; {declare("oo", "urn:o:")} .'
                                              f'ex:ns a owl:Ontology ; {ZZ} .'),
    'import': ('ex:ont', f'ex:ont a owl:Ontology ; owl:imports ex:base . ex:base a owl:Ontology ; {ZZ} .'),
    'import beside own': (
        'ex:ont', f'ex:ont a owl:Ontology ; {declare("oo", "urn:o:")} ; owl:imports ex:base .'
                  f'ex:base a owl:Ontology ; {ZZ} .'),
    'import without ontologies': ('ex:ns', f'ex:ns owl:imports ex:base . ex:base {ZZ} .'),
    'import of an import, in a circle': (
        'ex:ont', f'ex:ont owl:imports ex:mid . ex:mid owl:imports ex:base, <urn:not:here> .'
                  f'ex:base owl:imports ex:ont ; {ZZ} .'),
    'blank node': (f'[ {ZZ} ]', ''),
    'blank node that imports': ('[ owl:imports ex:ns ]', f'ex:ns {ZZ} .'),
}


def graph(text):
    return Graph().parse(data=HEAD + text, format='turtle')


DATA = graph('ex:a a ex:T ; ex:p 1 . ex:b a ex:T .')


def constraint(names):
    return f'''ex:S a sh:NodeShape ; sh:targetClass ex:T ;
        sh:sparql [ sh:prefixes {names} ; sh:message "m" ;
            sh:select "SELECT $this WHERE {{ $this zz:p ?v }}" ] .'''


def rule(names):
    return f'''ex:S a sh:NodeShape ; sh:targetClass ex:T ;
        sh:rule [ a sh:SPARQLRule ; sh:prefixes {names} ;
            sh:construct "CONSTRUCT {{ $this zz:made 1 }} WHERE {{ $this zz:p ?v }}" ] .'''


def target(names):
    return f'''ex:S a sh:NodeShape ; sh:nodeKind sh:BlankNode ;
        sh:target [ a sh:SPARQLTarget ; sh:prefixes {names} ;
            sh:select "SELECT ?this WHERE {{ ?this zz:p ?v }}" ] .'''


def violating(shapes, data=DATA):
    return {r.resource for r in validate_graphs(data, shapes).results
            if r.status is Status.VIOLATED}


@pytest.mark.parametrize('holder', HOLDERS)
def test_a_constraint(holder):
    names, text = HOLDERS[holder]
    assert violating(graph(constraint(names) + text)) == {EX + 'a'}


@pytest.mark.parametrize('holder', HOLDERS)
def test_a_constraint_of_a_property_and_of_a_referenced_shape(holder):
    names, text = HOLDERS[holder]
    shapes = graph(f'''ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:node ex:Inner .
        ex:Inner a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:sparql [ sh:prefixes {names} ;
            sh:message "m" ; sh:select "SELECT $this ?value WHERE {{ $this zz:p ?value }}" ] ] .''' + text)
    assert violating(shapes) == {EX + 'a'}


@pytest.mark.parametrize('holder', HOLDERS)
def test_a_rule(holder):
    names, text = HOLDERS[holder]
    shapes = graph(rule(names) + text)
    run = run_rules(DATA, shapes)
    assert set(run.graph.subjects(URIRef(EX + 'made'))) == {URIRef(EX + 'a')}
    assert violating(shapes) == set()              # and validation runs, too


@pytest.mark.parametrize('holder', HOLDERS)
def test_a_target(holder):
    names, text = HOLDERS[holder]
    shapes = graph(target(names) + text)
    assert focus_nodes(URIRef(EX + 'S'), shapes, DATA) == {URIRef(EX + 'a')}
    assert violating(shapes) == {EX + 'a'}


@pytest.mark.parametrize('holder', HOLDERS)
def test_a_validator(holder):
    """In the graph pyshacl gets of a whole shapes graph, as the rules do."""
    names, text = HOLDERS[holder]
    shapes = graph(f'''ex:Component a sh:ConstraintComponent ; sh:parameter [ sh:path ex:limit ] ;
        sh:nodeValidator [ a sh:SPARQLSelectValidator ; sh:prefixes {names} ; sh:message "m" ;
            sh:select "SELECT $this WHERE {{ $this zz:p ?v }}" ] .
        ex:S a sh:NodeShape ; sh:targetClass ex:T ; ex:limit 1 .''' + text)
    copy = Graph()
    for triple in shapes:
        copy.add(triple)
    prefixes.complete(copy, shapes)
    conforms, report, _ = pyshacl.validate(Graph() + DATA, shacl_graph=copy, advanced=True)
    assert not conforms
    assert set(report.objects(None, SH.focusNode)) == {URIRef(EX + 'a')}


@pytest.mark.parametrize('holder', HOLDERS)
def test_what_reads_the_prefixes_itself(holder):
    names, text = HOLDERS[holder]
    shapes = graph(constraint(names) + text)
    assert URIRef(EX + 'p') in read_set(shapes)
    query = next(shapes.objects(URIRef(EX + 'S'), SH.sparql))

    class Package:
        pass
    package = Package()
    package.shapes = shapes
    line = f'PREFIX zz: <{EX}>'
    assert line in sparqlbench._prefix_lines(package, query)
    assert line in _query(package, query, SH.select)
    assert sparqlbench._prefix_lines(package, None) == []


# --- only what sh:prefixes names ------------------------------------------------

@pytest.mark.parametrize('kind', ['', 'a owl:Ontology ;'])
def test_another_ontology_does_not_take_a_prefix_over(kind):
    """pyshacl gives a query whose node is no ontology every ontology's
    prefixes, and which of two wins is chance."""
    shapes = graph(rule('ex:ns') + f'''
        ex:ns {kind} {ZZ} .''' + ''.join(
            f'ex:other{i} a owl:Ontology ; {declare("zz", f"urn:wrong{i}:")} .' for i in range(20)))
    run = run_rules(DATA, shapes)
    assert set(run.graph.subjects(URIRef(EX + 'made'))) == {URIRef(EX + 'a')}


@pytest.mark.parametrize('text', [rule('ex:empty'), constraint('ex:empty'), target('ex:empty')])
def test_a_prefix_of_an_ontology_that_is_not_named_is_not_declared(text):
    shapes = graph(text + f'ex:empty a owl:Ontology . ex:ont a owl:Ontology ; {ZZ} .')
    with pytest.raises(Exception, match='Unknown namespace prefix'):
        validate_graphs(DATA, shapes)


def test_two_queries_of_one_shape_keep_their_own_prefixes():
    shapes = graph(constraint('ex:one') + f'''
        ex:S sh:sparql [ sh:prefixes ex:two ; sh:message "n" ;
            sh:select "SELECT $this WHERE {{ $this zz:p ?v }}" ] .
        ex:one {ZZ} . ex:two a owl:Ontology ; {declare("zz", "urn:other:")} .''')
    data = graph('ex:a a ex:T ; ex:p 1 . ex:b a ex:T ; <urn:other:p> 1 .')
    messages = {(r.resource, r.message) for r in validate_graphs(data, shapes).results
                if r.status is Status.VIOLATED}
    assert messages == {(EX + 'a', 'm'), (EX + 'b', 'n')}


# --- the graph handed on ---------------------------------------------------------

def test_the_package_s_own_graph_is_not_written_to_and_the_kept_one_is_per_version():
    text = constraint('ex:ns') + f'ex:ns {ZZ} .'
    before = graph(text)
    size = len(before)
    shapes = freeze(before)
    subject = URIRef(EX + 'S')
    kept = shape_views.subgraph_for(shapes, [subject])
    run_rules(DATA, shapes)
    assert len(shapes) == size
    assert (URIRef(EX + 'ns'), RDF.type, OWL.Ontology) not in shapes
    assert shape_views.subgraph_for(shapes, [subject]) is kept
    # Only the imported declaration changes: another graph, another subgraph.
    changed = freeze(graph(text.replace(f'"{EX}"', '"urn:other:"')))
    namespaces = set(shape_views.subgraph_for(changed, [subject]).objects(None, SH.namespace))
    assert {str(n) for n in namespaces} == {'urn:other:'}


# --- a package ---------------------------------------------------------------------

@pytest.fixture
def fresh(tmp_path):
    root = str(tmp_path / 'fresh')
    create_package(root, name='fresh', layout='flat')
    return root


FOR_PACKAGE = {
    'constraint': '''freshShacl:PShape sh:targetClass freshEntities:Machine ;
        sh:sparql [ sh:prefixes freshShacl:ont ; sh:message "m" ;
            sh:select "SELECT $this WHERE {{ {body} }}" ] .''',
    'rule': '''freshShacl:PShape sh:targetClass freshEntities:Machine ;
        sh:rule [ a sh:SPARQLRule ; sh:prefixes freshShacl:ont ;
            sh:construct "CONSTRUCT {{ $this zz:made 1 }} WHERE {{ {body} }}" ] .''',
    'target': '''freshShacl:PShape sh:nodeKind sh:IRI ; sh:target [ a sh:SPARQLTarget ;
            sh:prefixes freshShacl:ont ;
            sh:select "SELECT ?this WHERE {{ {body} }}" ] .''',
    'validator': '''freshShacl:PShape a sh:ConstraintComponent ;
        sh:parameter [ sh:path freshShacl:par ] ;
        sh:nodeValidator [ a sh:SPARQLSelectValidator ; sh:prefixes freshShacl:ont ;
            sh:select "SELECT $this WHERE {{ {body} }}" ] .''',
}


def add(root, kind, body, namespace='urn:zz:'):
    with open(os.path.join(root, 'shacl.ttl'), 'a', encoding='utf-8') as handle:
        handle.write(f'''
freshShacl:ont <http://www.w3.org/2002/07/owl#imports> freshShacl:base .
freshShacl:base sh:declare [ sh:prefix "zz" ;
    sh:namespace "{namespace}"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] .
freshShacl:PShape a sh:NodeShape .
''' + FOR_PACKAGE[kind].format(body=body))


@pytest.mark.parametrize('kind', ['constraint', 'rule', 'target'])
def test_the_tests_of_a_package_run(fresh, kind):
    add(fresh, kind, '?this zz:none ?v')
    result = CliRunner().invoke(cli, ['verify', '--tests', fresh])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize('kind', FOR_PACKAGE)
def test_service_is_refused_with_a_declared_prefix(fresh, kind):
    add(fresh, kind, 'SERVICE zz:sparql { ?this zz:none ?v }')
    result = CliRunner().invoke(cli, ['verify', '--tests', '--allow-network', fresh])
    assert result.exit_code == 2
    assert 'uses SPARQL SERVICE zz:sparql' in result.output
    assert 'freshShacl:PShape' in result.output


def test_an_imported_namespace_that_breaks_out_of_its_iri_is_refused(fresh):
    """A namespace is put into the query as it is written."""
    add(fresh, 'rule', '?this zz:none ?v',
        'urn:zz:> CONSTRUCT { $this <urn:x> 1 } WHERE { SERVICE <urn:s> { ?s ?p ?o } } #')
    assert [s for s, _, _ in network_uses(load(fresh))] == ['freshShacl:PShape (rule)']
