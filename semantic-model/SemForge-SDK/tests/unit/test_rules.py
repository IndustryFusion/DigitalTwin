"""Rule evaluation: fixpoint, NGSI-LD update semantics, and the bound."""

import pytest
from rdflib import Graph, Namespace, URIRef

from semforge.errors import CapabilityError
from semforge.rules import run_rules
from semforge.validate.orchestrator import validate_graphs

EX = Namespace('https://example.org/')
WASTECLASS = URIRef('https://industryfusion.github.io/contexts/example/v0/'
                    'filter_entities/hasWasteclass')
CARTRIDGE = URIRef('urn:cartridge:1')


def test_corpus_rules_reach_a_fixpoint(corpus):
    run = run_rules(corpus.model, corpus.shapes, corpus.knowledge)
    assert run.converged
    assert run.iterations <= 3, 'the kms rules should settle almost immediately'


def test_the_wasteclass_rule_escalates_the_cartridge(corpus):
    """ChangeWasteClassRulesShape derives a waste class from the material cut."""
    run = run_rules(corpus.model, corpus.shapes, corpus.knowledge)
    instances = list(run.graph.objects(CARTRIDGE, WASTECLASS))
    assert len(instances) == 1, 'the rule should leave exactly one waste class'


def test_rule_output_replaces_rather_than_adds(corpus):
    """F4, and the one irreducible entry in expected-divergences.txt.

    A rule constructing a second hasWasteclass adds a triple in RDF; as an
    NGSI-LD update it REPLACES the value that was there. Without update
    semantics the attribute ends up with two values and maxCount 1 fires
    against the rule's own shape -- a violation that is an artefact of RDF, not
    a defect in the model.
    """
    run = run_rules(corpus.model, corpus.shapes, corpus.knowledge)
    assert run.replaced >= 1

    with_rules = validate_graphs(corpus.model, corpus.shapes, corpus.knowledge)
    assert not [r for r in with_rules.violations if r.attribute == 'hasWasteclass']

    without_rules = validate_graphs(corpus.model, corpus.shapes, corpus.knowledge,
                                    rules=False)
    spurious = [r for r in without_rules.violations if r.attribute == 'hasWasteclass']
    assert spurious, ('pyshacl applies rules as pure addition, so the spurious '
                      'cardinality violation must still be reproducible')


NON_TERMINATING = '''
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://example.org/> .
ex:Runaway a sh:NodeShape ;
    sh:targetClass ex:C ;
    sh:rule [ a sh:SPARQLRule ;
        sh:construct """
PREFIX ex: <https://example.org/>
CONSTRUCT { ?tail ex:next [ ex:depth "1" ] }
WHERE {
    $this a ex:C .
    { BIND($this as ?tail) } UNION { $this ex:next+ ?tail }
    FILTER NOT EXISTS { ?tail ex:next ?any }
}
""" ] .
'''


def _runaway_package():
    data = Graph()
    data.add((URIRef('urn:thing:1'), URIRef(
        'http://www.w3.org/1999/02/22-rdf-syntax-ns#type'), EX.C))
    shapes = Graph()
    shapes.parse(data=NON_TERMINATING, format='turtle')
    return data, shapes


def test_an_unbounded_rule_hits_the_bound_and_is_reported():
    """A rule whose guard does not bound it is a modelling defect.

    It must surface at authoring time as a named error -- never as a hang, and
    never as a silent stop that looks like convergence.
    """
    data, shapes = _runaway_package()
    run = run_rules(data, shapes, max_iterations=3)
    assert run.converged is False
    assert run.iterations == 3
    assert [d.code for d in run.diagnostics] == ['SF-RULE-001']
    assert 'guard' in run.diagnostics[0].message


def test_a_non_terminating_rule_fails_validation_loudly():
    data, shapes = _runaway_package()
    with pytest.raises(CapabilityError) as exc:
        validate_graphs(data, shapes)
    assert 'terminate' in str(exc.value)


def test_the_input_graph_is_never_mutated(corpus):
    before = len(corpus.model)
    run_rules(corpus.model, corpus.shapes, corpus.knowledge)
    assert len(corpus.model) == before


def test_observed_instances_are_not_replaced(corpus):
    """A value carrying observedAt is an observation, not a rule rewrite.

    Collapsing those is the current view's job, and doing it here would erase
    history the history view is supposed to keep.
    """
    run = run_rules(corpus.model, corpus.shapes, corpus.knowledge)
    strength = URIRef('https://industryfusion.github.io/contexts/example/v0/'
                      'base_entities/hasStrength')
    assert len(list(run.graph.objects(URIRef('urn:filter:1'), strength))) == 4
