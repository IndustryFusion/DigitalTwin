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

"""The knowledge, cut to what the constraints can read.

On the OPC UA pump package the knowledge is 217,582 triples and the
constraints read 31,356 of them; validation went from 13 s to 2-4 s with the
same verdicts. The cut must never change a verdict, so every way a constraint
can read is covered here, and every way it can read ANYTHING falls back to the
whole knowledge.
"""

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from semforge.validate.readset import (ALWAYS, Unbounded, cut, knowledge_for, near,
                                       query_predicates, read_set)

PREFIXES = '''@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
'''
EX = 'https://example.org/'


def shapes(body):
    return Graph().parse(data=PREFIXES + body, format='turtle')


def names(predicates):
    return {str(p)[len(EX):] for p in predicates if str(p).startswith(EX)}


def test_types_and_the_class_hierarchy_are_always_read():
    assert ALWAYS <= read_set(shapes('ex:S a sh:NodeShape ; sh:targetClass ex:C .'))


@pytest.mark.parametrize('path, expected', [
    ('ex:a', {'a'}),
    ('( ex:a ex:b )', {'a', 'b'}),
    ('[ sh:inversePath ex:a ]', {'a'}),
    ('[ sh:alternativePath ( ex:a [ sh:zeroOrMorePath ex:b ] ) ]', {'a', 'b'}),
    ('( [ sh:oneOrMorePath ex:a ] [ sh:zeroOrOnePath ex:b ] )', {'a', 'b'}),
])
def test_every_predicate_of_a_path_is_read(path, expected):
    graph = shapes(f'ex:S a sh:NodeShape ; sh:property [ sh:path {path} ; sh:minCount 1 ] .')
    assert names(read_set(graph)) == expected


def test_nested_property_shapes_and_predicate_parameters_are_read():
    graph = shapes('''ex:S a sh:NodeShape ;
        sh:targetSubjectsOf ex:t ;
        sh:property [ sh:path ex:a ; sh:equals ex:e ; sh:lessThan ex:l ;
                      sh:property [ sh:path ex:inner ; sh:disjoint ex:d ] ] .''')
    assert names(read_set(graph)) == {'t', 'a', 'e', 'l', 'inner', 'd'}


@pytest.mark.parametrize('text, expected', [
    ('SELECT $this WHERE { $this ex:a [ ex:b ?v ] }', {'a', 'b'}),
    # The regression: FILTER NOT EXISTS keeps the parser's form in rdflib's
    # algebra, and ex:valid was cut away -- a constraint fired that did not.
    ('SELECT $this WHERE { $this a ?t . FILTER NOT EXISTS { ?v ex:valid ?s . '
     '?t rdfs:subClassOf* ?s } }', {'valid'}),
    ('SELECT $this WHERE { FILTER EXISTS { { $this ex:a ?x } UNION { $this ex:b ?y } '
     'OPTIONAL { $this ex:c ?z } } }', {'a', 'b', 'c'}),
    ('SELECT $this WHERE { FILTER EXISTS { SELECT $this WHERE { $this ex:a ?z } } }', {'a'}),
    ('SELECT $this WHERE { $this ex:a ?x . MINUS { $this ex:b ?y } }', {'a', 'b'}),
    ('SELECT $this WHERE { $this ex:a/ex:b|^ex:c ?x }', {'a', 'b', 'c'}),
    ('CONSTRUCT { $this ex:written ?x } WHERE { $this ex:read ?x }', {'read'}),
    ('SELECT $this WHERE { $this $PATH ?x }', set()),
])
def test_what_a_query_reads(text, expected):
    found = query_predicates('PREFIX ex: <https://example.org/>\n'
                             'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n' + text)
    assert names(found) == expected


@pytest.mark.parametrize('text', [
    'SELECT $this WHERE { $this ?p ?o }',
    'SELECT $this WHERE { FILTER NOT EXISTS { $this ex:a [ ?p ?v ] } }',
    'SELECT $this WHERE { { $this ?p ?o } UNION { $this ex:a ?o } }',
    'SELECT $this WHERE { FILTER EXISTS { SELECT $this WHERE { $this ?p ?z } } }',
    'SELECT $this WHERE { $this !ex:a ?o }',
    'SELECT $this WHERE { VALUES ?p { ex:a } $this ?p ?o }',
    'SELECT $this WHERE { this is not sparql',
])
def test_a_query_that_can_read_anything_is_unbounded(text):
    with pytest.raises(Unbounded):
        query_predicates('PREFIX ex: <https://example.org/>\n' + text)


def test_an_unbounded_query_means_the_whole_knowledge():
    graph = shapes('''ex:S a sh:NodeShape ; sh:targetClass ex:C ;
        sh:sparql [ sh:select "SELECT $this WHERE { $this ?p ?o }" ] .''')
    knowledge = Graph()
    knowledge.add((URIRef(EX + 'x'), URIRef(EX + 'anything'), Literal(1)))
    assert read_set(graph) is None
    assert knowledge_for(graph, knowledge) is knowledge


def test_a_query_uses_the_prefixes_its_shape_declares():
    graph = shapes('''ex:S a sh:NodeShape ; sh:targetClass ex:C ;
        sh:sparql [ sh:prefixes ex:decl ;
                    sh:select "SELECT $this WHERE { $this q:a ?o }" ] .
        ex:decl sh:declare [ sh:prefix "q" ;
            sh:namespace "https://example.org/q/"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] .''')
    assert URIRef('https://example.org/q/a') in read_set(graph)


def test_javascript_constraints_cannot_be_seen_into():
    graph = shapes('ex:S a sh:NodeShape ; sh:js [ sh:jsFunctionName "check" ] .')
    assert read_set(graph) is None


def test_the_cut_keeps_what_is_read_and_drops_the_rest():
    knowledge = Graph()
    keep = [(URIRef(EX + 'x'), RDF.type, URIRef(EX + 'C')),
            (URIRef(EX + 'C'), RDFS.subClassOf, URIRef(EX + 'B')),
            (URIRef(EX + 'x'), URIRef(EX + 'a'), Literal(1))]
    drop = [(URIRef(EX + 'x'), URIRef(EX + 'browseName'), Literal('x'))]
    for triple in keep + drop:
        knowledge.add(triple)
    small = cut(knowledge, ALWAYS | {URIRef(EX + 'a')})
    assert set(small) == set(keep)


def test_the_kms_verdicts_are_the_same_with_and_without_the_cut(corpus):
    from semforge.expect.store import compose, load_expectations
    from semforge.validate.orchestrator import validate_graphs

    def keys(report):
        return sorted((r.resource, r.attribute, r.component, r.shape, r.status.value)
                      for r in report.results)

    graphs = [corpus.model] + [compose(corpus, e)
                               for e in load_expectations(corpus.path).examples]
    for graph in graphs:
        full = validate_graphs(graph, corpus.shapes, corpus.knowledge, strict=False,
                               cut=False, near=False)
        reduced = validate_graphs(graph, corpus.shapes, corpus.knowledge, strict=False)
        assert keys(full) == keys(reduced)


# near(): of the knowledge, what the data can reach. Each case below is one
# where a verdict depends on the knowledge; with near() it must not change.

NEAR_PREFIXES = PREFIXES + '''@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
'''


def turtle(body):
    return Graph().parse(data=NEAR_PREFIXES + body, format='turtle')


def violations(shapes_graph, data, knowledge):
    import pyshacl
    from rdflib.namespace import SH

    merged = Graph()
    for triple in data:
        merged.add(triple)
    for triple in knowledge:
        merged.add(triple)
    _, report, _ = pyshacl.validate(merged, shacl_graph=shapes_graph, do_owl_imports=False)
    return sorted((str(report.value(r, SH.focusNode)), str(report.value(r, SH.sourceConstraintComponent)))
                  for r in report.objects(None, SH.result))


# Noise the data cannot reach: it must be dropped, and must not matter.
NOISE = '''ex:far ex:a ex:farther . ex:farther ex:b "x" . ex:far a ex:Other .
             ex:far ex:browseName "far" .'''


@pytest.mark.parametrize('shapes_body, data_body, knowledge_body', [
    # A knowledge entity a shape targets by class is validated as before.
    ('ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:a ; sh:minCount 1 ] .',
     'ex:d a ex:C ; ex:a "1" .',
     'ex:k a ex:Sub . ex:Sub rdfs:subClassOf ex:C .'),
    # ... and one it targets by name.
    ('ex:S a sh:NodeShape ; sh:targetNode ex:k ; sh:property [ sh:path ex:a ; sh:minCount 1 ] .',
     'ex:d ex:x "1" .',
     'ex:k ex:b "2" .'),
    # ... and by implicit class target.
    ('ex:C a sh:NodeShape, rdfs:Class ; sh:property [ sh:path ex:a ; sh:minCount 1 ] .',
     'ex:d a ex:C ; ex:a "1" .',
     'ex:k a ex:C .'),
    # An inverse path reads knowledge pointing INTO the data.
    ('ex:S a sh:NodeShape ; sh:targetClass ex:C ; '
     'sh:property [ sh:path [ sh:inversePath ex:partOf ] ; sh:maxCount 1 ] .',
     'ex:d a ex:C .',
     'ex:k1 ex:partOf ex:d . ex:k2 ex:partOf ex:d .'),
    # sh:class on a value typed in the knowledge, through the class hierarchy.
    ('ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:link ; sh:class ex:T ] .',
     'ex:d a ex:C ; ex:link ex:k , ex:j .',
     'ex:k a ex:Sub . ex:Sub rdfs:subClassOf ex:T . ex:j a ex:Other .'),
    # sh:node into a knowledge entity, two hops deep.
    ('ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:link ; sh:node ex:N ] . '
     'ex:N a sh:NodeShape ; sh:property [ sh:path ( ex:b ex:c ) ; sh:hasValue "ok" ] .',
     'ex:d a ex:C ; ex:link ex:k , ex:j .',
     'ex:k ex:b ex:m . ex:m ex:c "ok" . ex:j ex:b ex:n . ex:n ex:c "no" .'),
    # A transitive path walks as far as the knowledge goes.
    ('ex:S a sh:NodeShape ; sh:targetClass ex:C ; '
     'sh:property [ sh:path [ sh:oneOrMorePath ex:b ] ; sh:maxCount 2 ] .',
     'ex:d a ex:C ; ex:b ex:k .',
     'ex:k ex:b ex:m . ex:m ex:b ex:n .'),
])
def test_near_never_changes_a_verdict(shapes_body, data_body, knowledge_body):
    shapes_graph = turtle(shapes_body)
    data = turtle(data_body)
    knowledge = turtle(knowledge_body + NOISE)
    reduced = near(shapes_graph, knowledge, data)
    assert reduced is not None
    assert (URIRef(EX + 'far'), URIRef(EX + 'browseName'), Literal('far')) not in reduced
    expected = violations(shapes_graph, data, knowledge)
    assert expected, 'each case must depend on the knowledge to mean anything'
    assert violations(shapes_graph, data, reduced) == expected


@pytest.mark.parametrize('shapes_body', [
    'ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:a ; sh:property [ sh:path ex:a ; sh:maxCount 1 ] .',
    'ex:S a sh:NodeShape ; sh:targetObjectsOf ex:a ; sh:property [ sh:path ex:a ; sh:maxCount 1 ] .',
    'ex:S a sh:NodeShape ; sh:targetClass ex:C ; '
    'sh:sparql [ sh:select "SELECT $this WHERE { $this <https://example.org/a> ?o }" ] .',
])
def test_near_does_not_guess_what_it_cannot_anchor(shapes_body):
    assert near(turtle(shapes_body), turtle(NOISE), turtle('ex:d ex:a "1" .')) is None


def test_the_kms_falls_back_to_the_whole_cut(corpus):
    # Its SPARQL constraints can read any triple.
    assert near(corpus.shapes, corpus.knowledge, corpus.model) is None
