"""Invariants V1 and V2: every applicable constraint reports a status."""

from semforge.validate import Status, validate_package
from semforge.validate.applicable import (constraints_of_shape, enumerate_pairs,
                                          focus_nodes, subclasses_of)
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SH

EX = Namespace('https://example.org/')


def test_v1_every_constraint_has_a_status(corpus):
    report = validate_package(corpus)
    assert len(report.evaluated) > 0
    for result in report.results:
        assert isinstance(result.status, Status)


def test_v1_conformance_is_stated_not_inferred_from_silence(corpus):
    """86 conformant + 3 violated, not '3 violations and silence'."""
    report = validate_package(corpus)
    assert len(report.conformant) > 0
    assert len(report.evaluated) == len(report.conformant) + len(report.violations)


def test_the_enumerator_invariant_holds_on_the_corpus(corpus):
    """Every reported result maps onto an enumerated pair.

    A result that does not is an enumerator bug: an enumerator that quietly
    under-counts turns V1 into decoration, so the drift is detected rather
    than assumed away.
    """
    report = validate_package(corpus)
    assert report.complete, [str(d) for d in report.diagnostics]
    assert [d for d in report.diagnostics if d.code == 'SF-ENUM-001'] == []


def test_drift_is_reported_when_the_enumerator_misses_something(corpus, monkeypatch):
    """The invariant must actually fire, not merely be asserted to hold."""
    from semforge.validate import orchestrator

    monkeypatch.setattr(orchestrator, 'enumerate_pairs',
                        lambda *args, **kwargs: (set(), []))
    report = orchestrator.validate_graphs(
        corpus.model, corpus.shapes, corpus.knowledge)
    assert report.complete is False
    assert [d.code for d in report.diagnostics if d.code == 'SF-ENUM-001']


def test_subclass_closure_reaches_subtypes():
    """sh:targetClass goes through rdfs:subClassOf* -- a Plasmacutter is a Cutter."""
    graph = Graph()
    graph.add((EX.Plasmacutter, RDFS.subClassOf, EX.Cutter))
    graph.add((EX.Lasercutter, RDFS.subClassOf, EX.Cutter))
    assert subclasses_of(graph, EX.Cutter) == {EX.Cutter, EX.Plasmacutter, EX.Lasercutter}


def test_focus_nodes_pick_up_a_subtype_instance():
    shapes = Graph()
    shapes.add((EX.S, SH.targetClass, EX.Cutter))
    knowledge = Graph()
    knowledge.add((EX.Plasmacutter, RDFS.subClassOf, EX.Cutter))
    data = Graph()
    data.add((URIRef('urn:pc:1'), RDF.type, EX.Plasmacutter))

    assert focus_nodes(EX.S, shapes, data, knowledge) == {URIRef('urn:pc:1')}


def test_a_shape_with_no_target_is_not_applicable_not_absent():
    """A shape that matches nothing is reported, not omitted.

    A shape that silently stopped matching anything has no other symptom.
    """
    shapes = Graph()
    shapes.add((EX.S, SH.targetClass, EX.Missing))
    prop = URIRef('urn:prop')
    shapes.add((EX.S, SH.property, prop))
    shapes.add((prop, SH.path, EX.attr))
    shapes.add((prop, SH.minCount, URIRef('urn:1')))

    pairs, inapplicable = enumerate_pairs(shapes, Graph(), Graph())
    assert pairs == set()
    assert [name for name, _ in inapplicable] == [str(EX.S)]


def test_value_shapes_are_attributed_to_the_attribute_that_carries_them(corpus):
    """A constraint on ngsild:hasValue belongs to the attribute above it."""
    shape = URIRef('https://industryfusion.github.io/contexts/example/v0/'
                   'base_shacl/WorkpieceShape')
    declared = constraints_of_shape(shape, corpus.shapes)
    attributes = {attribute for attribute, _ in declared}
    assert 'hasHeight' in attributes
    assert 'hasValue' not in attributes


def test_both_verdict_kinds_appear_in_the_report(corpus):
    report = validate_package(corpus)
    statuses = {r.status for r in report.results}
    assert Status.CONFORMANT in statuses and Status.VIOLATED in statuses


SHARED_CARTRIDGE = '''
{
  "@context": "https://industryfusion.github.io/contexts/staging/example/v0.2/context.jsonld",
  "id": "urn:filter:99",
  "type": "iffBaseEntities:Filter",
  "iffBaseEntities:hasCartridge": {
    "type": "Relationship", "object": "urn:cartridge:1"
  },
  "iffBaseEntities:hasStrength": {"type": "Property", "value": 0.6},
  "iffBaseEntities:hasState": {"type": "Property", "value": {"@id": "base:state_ON"}}
}
'''


def test_inverse_path_constraint_does_not_look_like_drift(corpus):
    """An NGSI-LD inverse path must be named identically on both sides.

    CartridgeShape forbids a cartridge sitting in two filters, and states it
    with the two-hop inverse ( [^ngsild:hasObject] [^hasCartridge] ) -- which
    pyshacl reports as an unnamed blank node. The adapter recovers the
    predicate; the enumerator has to reach the same name, or a violation of
    this rule is reported AND flagged as enumerator drift.

    The corpus cannot expose that: every filter has its own cartridge, which is
    the point of the rule. So this attaches a second filter to urn:cartridge:1
    and makes it fire.
    """
    from rdflib import Graph

    from semforge.validate.orchestrator import validate_graphs

    data = Graph()
    for triple in corpus.model:
        data.add(triple)
    data.parse(data=SHARED_CARTRIDGE, format='json-ld')

    report = validate_graphs(data, corpus.shapes, corpus.knowledge)
    fired = [r for r in report.violations if r.attribute == 'hasCartridge']
    assert fired, 'sharing a cartridge between two filters must violate CartridgeShape'
    assert report.complete, [str(d) for d in report.diagnostics]
    assert [d for d in report.diagnostics if d.code == 'SF-ENUM-001'] == []
