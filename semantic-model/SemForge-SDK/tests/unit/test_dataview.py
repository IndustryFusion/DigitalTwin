"""View declaration, and the check that it is honest (assertion 6).

Declaring `current` on a shape that aggregates is the silent failure: the
aggregate runs over collapsed instances and returns a plausible wrong number,
never an error. So it fails the build naming the shape.
"""

import pytest
from rdflib import Graph

from semforge.errors import CapabilityError
from semforge.ngsild import DataView
from semforge.validate import shapes as sv
from semforge.validate.orchestrator import validate_graphs

PREAMBLE = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/> .
@prefix semforge: <https://industryfusion.github.io/semforge/v0/> .
"""

AGGREGATING_BODY = """
    SELECT $this (COUNT(?v) AS ?n) WHERE { $this ex:attr [ ex:hasValue ?v ] } GROUP BY $this
"""


def _constraint_shape(extra=''):
    return ("""
ex:S a sh:NodeShape ; sh:targetClass ex:C ; EXTRA
    sh:sparql [ a sh:SPARQLConstraints ; sh:select '''BODY''' ] .
""".replace('EXTRA', extra).replace('BODY', AGGREGATING_BODY))


TWO_SHAPES = """
ex:S1 a sh:NodeShape ; sh:targetClass ex:C1 ;
    sh:sparql [ a sh:SPARQLConstraints ; sh:select '''BODY''' ] .
ex:S2 a sh:NodeShape ; sh:targetClass ex:C2 ;
    sh:sparql [ a sh:SPARQLConstraints ; sh:select '''BODY''' ] .
""".replace('BODY', AGGREGATING_BODY)

RULE_SHAPE = """
ex:S a sh:NodeShape ; sh:targetClass ex:C ;
    sh:rule [ a sh:SPARQLRule ; sh:construct '''BODY''' ] .
""".replace('BODY', AGGREGATING_BODY)


def _shapes(body):
    graph = Graph()
    graph.parse(data=PREAMBLE + body, format='turtle')
    return graph


def test_default_view_is_current():
    graph = _shapes('ex:S a sh:NodeShape ; sh:targetClass ex:C .')
    shape = sv.node_shapes(graph)[0]
    assert sv.view_of(graph, shape) is DataView.CURRENT


def test_declared_history_is_read():
    graph = _shapes(
        'ex:S a sh:NodeShape ; sh:targetClass ex:C ; semforge:dataView "history" .')
    shape = sv.node_shapes(graph)[0]
    assert sv.view_of(graph, shape) is DataView.HISTORY


def test_aggregate_detection():
    assert sv.aggregates(AGGREGATING_BODY)
    assert sv.aggregates('SELECT ?x WHERE {?x ?y ?z} GROUP BY ?x')
    assert sv.aggregates('SELECT (SUM(?v) AS ?t) WHERE {?x ex:v ?v}')
    assert not sv.aggregates('SELECT $this WHERE { $this ex:state ?s . FILTER(?s != ex:ON) }')


def test_6_aggregate_under_current_view_is_an_error():
    graph = _shapes(_constraint_shape())
    found = sv.check_declarations(graph)
    assert len(found) == 1
    assert found[0].code == 'SF-VIEW-001'
    assert 'history' in found[0].message


def test_6_declaring_history_clears_the_error():
    graph = _shapes(_constraint_shape('semforge:dataView "history" ;'))
    assert sv.check_declarations(graph) == []


def test_unknown_view_name_is_an_error_not_a_silent_default():
    graph = _shapes(
        'ex:S a sh:NodeShape ; sh:targetClass ex:C ; semforge:dataView "latest" .')
    found = sv.check_declarations(graph)
    assert len(found) == 1 and found[0].code == 'SF-VIEW-002'


def test_strict_validation_fails_loud_and_names_every_shape():
    graph = _shapes(TWO_SHAPES)
    with pytest.raises(CapabilityError) as exc:
        validate_graphs(Graph(), graph)
    message = str(exc.value)
    # C1: every problem at once, not the first one.
    assert 'S1' in message and 'S2' in message


def test_rule_bodies_are_checked_too():
    graph = _shapes(RULE_SHAPE)
    assert [d.code for d in sv.check_declarations(graph)] == ['SF-VIEW-001']


def test_corpus_declares_nothing_and_needs_nothing(corpus):
    """The production KMS has no GROUP BY: every shape is entity state."""
    partition = sv.partition(corpus.shapes)
    assert set(partition) == {DataView.CURRENT}
    assert sv.check_declarations(corpus.shapes) == []
